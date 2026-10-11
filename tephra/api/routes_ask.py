"""HTTP routes of Ask TEPHRA and the AI budget meter.

* ``POST /desk/ask`` a typed question, answered by the Ask agent.
* ``POST /desk/ask/voice`` a recorded question: transcribed, then answered.
* ``POST /desk/ask/speak`` a stored answer, spoken by Gemini text-to-speech.
* ``GET /budget`` calls used and allowed per model tier today (public).

When a model step fails the response is 503 ``{"error": "ai_unavailable", "message": "AI
UNAVAILABLE: ..."}`` and nothing is substituted.
"""

from typing import Annotated, Any, Final

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import Response
from pydantic import Field

from tephra.agents import ask, voice
from tephra.agents.ask import AiUnavailable, AskAnswer, AskFailure
from tephra.agents.budget import BudgetView, budget_view
from tephra.agents.voice import MAX_AUDIO_BYTES, SpeechCache, Transcript
from tephra.api import ApiError
from tephra.api.auth import require_csrf
from tephra.api.server import DeskSession, RuntimeDep, _actor, _json
from tephra.config import Settings
from tephra.models import ErrorBody, SseEvent, TephraModel, TraceEvent
from tephra.pipeline import Runtime
from tephra.store.base import Collection

__all__ = ["BudgetView", "budget_view", "router"]

router = APIRouter()

_FLIGHT_ID_PATTERN: Final = r"^[A-Za-z0-9:_.-]{1,64}$"


class AskRequest(TephraModel):
    question: str = Field(min_length=1, max_length=ask.MAX_QUESTION_CHARS)
    flight_id: str | None = Field(default=None, pattern=_FLIGHT_ID_PATTERN)


class SpeakRequest(TephraModel):
    answer_id: str = Field(pattern=r"^ask_[0-9a-f]{12}$")


class VoiceResponse(TephraModel):
    transcript: Transcript
    answer: AskAnswer


class AiUnavailableBody(ErrorBody):
    message: str = Field(description="'AI UNAVAILABLE: <reason>'")


def _unavailable(reason: str, *, problems: list[str] | None = None) -> Response:
    text = (
        reason
        if reason.startswith(ask.UNAVAILABLE_PREFIX)
        else f"{ask.UNAVAILABLE_PREFIX}: {reason}"
    )
    body = AiUnavailableBody(
        error="ai_unavailable", detail=text, message=text, problems=problems or []
    )
    return _json(body, 503)


def _trace_sink(runtime: Runtime) -> Any:
    def sink(event: TraceEvent) -> None:
        runtime.trace(
            event.stage,
            event.actor,
            event.message,
            level=event.level,
            volcano_id=event.volcano_id,
            flight_id=event.flight_id,
            detail=event.detail,
        )

    return sink


async def _answer(
    runtime: Runtime, session: Any, question: str, flight_id: str | None
) -> AskAnswer | AskFailure:
    result = await ask.answer_question(
        runtime, runtime.llm, question, flight_id=flight_id, trace=_trace_sink(runtime)
    )
    await ask.store_ask(runtime.store, result, actor=_actor(session))
    await _publish_budget(runtime)
    return result


async def _publish_budget(runtime: Runtime) -> None:
    runtime.bus.publish(SseEvent.BUDGET, await budget_view(runtime.settings, runtime.llm))


@router.post("/desk/ask", response_model=AskAnswer, dependencies=[Depends(require_csrf)])
async def desk_ask(body: AskRequest, session: DeskSession, runtime: RuntimeDep) -> Response:
    question = body.question.strip()
    if not question:
        raise ApiError(422, "validation_failed", "The question is empty")
    result = await _answer(runtime, session, question, body.flight_id)
    if isinstance(result, AskFailure):
        return _unavailable(result.reason)
    return _json(result)


@router.post("/desk/ask/voice", response_model=VoiceResponse, dependencies=[Depends(require_csrf)])
async def desk_ask_voice(
    session: DeskSession,
    runtime: RuntimeDep,
    audio: Annotated[UploadFile, File()],
    flight_id: Annotated[str | None, Form(pattern=_FLIGHT_ID_PATTERN)] = None,
) -> Response:
    data = await audio.read(MAX_AUDIO_BYTES + 1)
    if len(data) > MAX_AUDIO_BYTES:
        raise ApiError(413, "too_large", f"Audio is limited to {MAX_AUDIO_BYTES} bytes")
    try:
        transcript = await voice.transcribe(runtime.llm, data, audio.content_type or "")
    except AiUnavailable as exc:
        return _unavailable(str(exc))
    finally:
        await _publish_budget(runtime)
    result = await _answer(runtime, session, transcript.text, flight_id)
    if isinstance(result, AskFailure):
        return _unavailable(result.reason, problems=[f"transcript: {transcript.text}"])
    return _json(VoiceResponse(transcript=transcript, answer=result))


@router.post("/desk/ask/speak", dependencies=[Depends(require_csrf)])
async def desk_ask_speak(
    body: SpeakRequest, session: DeskSession, runtime: RuntimeDep, request: Request
) -> Response:
    cache = _speech_cache(request)
    wav = cache.get(body.answer_id)
    if wav is None:
        doc = await runtime.store.get(Collection.ASK_LOG, body.answer_id)
        if doc is None or doc.get("status") not in ("answered", "refused"):
            raise ApiError(404, "not_found", "No such answer")
        answer = AskAnswer.model_validate(doc)
        try:
            wav = await voice.speak(
                answer.answer,
                answer.language,
                llm=runtime.llm,
                model=runtime.settings.model_tts,
                client_factory=lambda: _tts_client(request, runtime.settings),
                timeout_s=runtime.settings.llm_timeout_s,
            )
        except AiUnavailable as exc:
            return _unavailable(str(exc))
        finally:
            await _publish_budget(runtime)
        cache.put(body.answer_id, wav)
    return Response(content=wav, media_type="audio/wav", headers={"cache-control": "no-store"})


@router.get("/budget", response_model=BudgetView)
async def get_budget(runtime: RuntimeDep) -> Response:
    return _json(await budget_view(runtime.settings, runtime.llm))


def _speech_cache(request: Request) -> SpeechCache:
    state = request.app.state
    if getattr(state, "speech_cache", None) is None:
        state.speech_cache = SpeechCache()
    cache: SpeechCache = state.speech_cache
    return cache


def _tts_client(request: Request, settings: Settings) -> Any:
    state = request.app.state
    if getattr(state, "tts_client", None) is None:
        state.tts_client = voice.make_tts_client(settings)
    return state.tts_client
