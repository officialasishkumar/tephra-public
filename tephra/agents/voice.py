"""Voice for Ask TEPHRA: Gemini hears the dispatcher and Gemini speaks the answer.

``transcribe`` is one lite structured call with the recording attached. ``speak`` is one call
to the Gemini text-to-speech model, which answers 24 kHz 16-bit mono PCM; it is wrapped in a
WAV header here. Both count against the lite tier's daily budget. When a call fails there is
no substitute (no browser speech, no canned audio): the caller gets ``AiUnavailable`` and the
text answer stands on its own.

The ``llm`` argument of both functions is the same ``LlmBackend`` the rest of the agents use,
so a scripted backend tests them without a key. Library code takes the model id as an
argument; the route wiring reads it from the settings.
"""

import asyncio
import io
import re
import wave
from collections import OrderedDict
from collections.abc import Callable
from typing import Any, Final

from pydantic import Field

from tephra.agents.ask import MAX_ANSWER_CHARS, MAX_QUESTION_CHARS, AiUnavailable, Language
from tephra.agents.llm import LlmBackend, LlmPart, daily_quota_spent
from tephra.config import Settings
from tephra.models import LlmBackendName, TephraModel

__all__ = [
    "ALLOWED_AUDIO_TYPES",
    "MAX_AUDIO_BYTES",
    "SpeechCache",
    "Transcript",
    "make_tts_client",
    "speak",
    "transcribe",
]

MAX_AUDIO_BYTES: Final = 1024 * 1024
"""One megabyte: about 30 seconds of compressed speech (the Desk records no longer)."""
ALLOWED_AUDIO_TYPES: Final = frozenset(
    {
        "audio/webm",
        "audio/ogg",
        "audio/mp4",
        "audio/mpeg",
        "audio/aac",
        "audio/wav",
        "audio/x-wav",
        "audio/flac",
    }
)
TTS_SAMPLE_RATE_HZ: Final = 24_000
TTS_VOICE: Final = "Kore"
"""One of Gemini's prebuilt voices; the model speaks English, Bahasa Indonesia and Japanese."""
_LANGUAGE_CODES: Final[dict[str, str]] = {"en": "en-US", "id": "id-ID", "ja": "ja-JP"}
_PCM_MIME: Final = re.compile(r"^audio/(?:l16|pcm)\b", re.IGNORECASE)
_RATE: Final = re.compile(r"rate=(\d+)")
_VOICE_LABEL: Final = "DISPATCHER VOICE"
_SYSTEM: Final = """You transcribe a dispatcher's spoken question for TEPHRA, a volcanic-ash
decision desk of a fictional airline. The attachment is an audio recording of
the dispatcher. Write down exactly the words spoken, in the language spoken (English,
Bahasa Indonesia or Japanese). Do not answer the question, translate it, correct it or add
words. Keep flight numbers, ICAO codes and numbers as digits and capitals as spoken. If there is
no intelligible speech, return an empty text. Reply with one JSON object: text, language
(en, id or ja)."""


class _Heard(TephraModel):
    """What the model returns (its structured output)."""

    text: str = Field(description="The words spoken, nothing else; empty if none")
    language: Language


class Transcript(_Heard):
    llm_backend: LlmBackendName
    model_id: str


async def transcribe(llm: LlmBackend, audio: bytes, mime_type: str) -> Transcript:
    """One lite call: the dispatcher's recording to text. Raises ``AiUnavailable``."""
    media_type = mime_type.split(";")[0].strip().lower()
    if media_type not in ALLOWED_AUDIO_TYPES:
        raise AiUnavailable(f"UNSUPPORTED AUDIO TYPE {media_type or 'NONE'}")
    if not audio or len(audio) > MAX_AUDIO_BYTES:
        raise AiUnavailable(f"AUDIO MUST BE 1 TO {MAX_AUDIO_BYTES} BYTES")
    if llm.name == "stub":
        raise AiUnavailable("NO MODEL: VOICE NEEDS GEMINI (TEPHRA_LLM=stub)")
    part = LlmPart.of_audio(audio, label=_VOICE_LABEL, mime_type=media_type)
    heard, call = await llm.structured(
        tier="lite", system=_SYSTEM, parts=[part], schema=_Heard, stub=_unheard
    )
    if heard is None:
        raise AiUnavailable(call.error or "NO TRANSCRIPT")
    text = " ".join(heard.text.split())
    if not text:
        raise AiUnavailable("NO SPEECH RECOGNISED")
    if len(text) > MAX_QUESTION_CHARS:
        raise AiUnavailable(f"TRANSCRIPT IS LONGER THAN {MAX_QUESTION_CHARS} CHARACTERS")
    return Transcript(
        text=text, language=heard.language, llm_backend=llm.name, model_id=call.model_id
    )


def _unheard() -> _Heard:
    """Required by the ``structured`` protocol; the stub backend is refused before the call."""
    return _Heard(text="", language="en")


def make_tts_client(settings: Settings) -> Any:
    """A Gemini client for speech: AI Studio key only, never Vertex AI or ADC."""
    from google import genai
    from google.genai import types

    api_key = settings.gemini_api_key
    if api_key is None:
        raise AiUnavailable("GEMINI_API_KEY IS NOT SET")
    return genai.Client(
        api_key=api_key.get_secret_value(),
        vertexai=False,
        http_options=types.HttpOptions(timeout=int(settings.llm_timeout_s * 1000)),
    )


async def speak(
    text: str,
    language: Language,
    *,
    llm: LlmBackend,
    model: str,
    client_factory: Callable[[], Any],
    timeout_s: float,
) -> bytes:
    """Speak ``text`` with the Gemini TTS ``model``; as a WAV file. Raises ``AiUnavailable``."""
    from google.genai import types

    if not text.strip() or len(text) > MAX_ANSWER_CHARS:
        raise AiUnavailable(f"TEXT TO SPEAK MUST BE 1 TO {MAX_ANSWER_CHARS} CHARACTERS")
    if llm.name == "stub":
        raise AiUnavailable("NO MODEL: SPEECH NEEDS GEMINI (TEPHRA_LLM=stub)")
    if not llm.reserve("lite"):
        raise AiUnavailable("budget_exhausted")
    client = client_factory()
    config = types.GenerateContentConfig(
        response_modalities=["AUDIO"],
        speech_config=types.SpeechConfig(
            language_code=_LANGUAGE_CODES[language],
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=TTS_VOICE)
            ),
        ),
    )
    try:
        response = await asyncio.wait_for(
            client.aio.models.generate_content(model=model, contents=text, config=config),
            timeout=timeout_s,
        )
    except Exception as exc:  # any SDK, transport or timeout failure: no voice reply
        if daily_quota_spent(exc):
            llm.exhaust("lite")
        raise AiUnavailable(_describe(exc)) from exc
    data, mime = _audio_of(response)
    return pcm_to_wav(data, rate_hz=_rate_of(mime))


def pcm_to_wav(pcm: bytes, *, rate_hz: int = TTS_SAMPLE_RATE_HZ) -> bytes:
    """16-bit little-endian mono PCM in a WAV container."""
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(rate_hz)
        wav.writeframes(pcm)
    return buffer.getvalue()


def _audio_of(response: Any) -> tuple[bytes, str]:
    candidates = getattr(response, "candidates", None) or []
    content = getattr(candidates[0], "content", None) if candidates else None
    for part in getattr(content, "parts", None) or []:
        inline = getattr(part, "inline_data", None)
        if inline is not None and inline.data:
            mime = inline.mime_type or ""
            if not _PCM_MIME.match(mime):
                raise AiUnavailable(f"UNEXPECTED AUDIO TYPE {mime or 'NONE'}")
            return bytes(inline.data), mime
    raise AiUnavailable("empty_response NO AUDIO")


def _rate_of(mime: str) -> int:
    found = _RATE.search(mime)
    return int(found.group(1)) if found else TTS_SAMPLE_RATE_HZ


def _describe(exc: BaseException) -> str:
    if isinstance(exc, TimeoutError):
        return "timeout"
    code = getattr(exc, "code", None)
    if code is not None:
        return f"api_error {code} {getattr(exc, 'status', '') or ''}".strip()
    return f"{type(exc).__name__}: {exc}"[:300]


class SpeechCache:
    """The last few spoken answers, so a second tap on the speaker spends no quota."""

    def __init__(self, size: int = 8) -> None:
        self._size = size
        self._items: OrderedDict[str, bytes] = OrderedDict()

    def get(self, answer_id: str) -> bytes | None:
        wav = self._items.get(answer_id)
        if wav is not None:
            self._items.move_to_end(answer_id)
        return wav

    def put(self, answer_id: str, wav: bytes) -> None:
        self._items[answer_id] = wav
        self._items.move_to_end(answer_id)
        while len(self._items) > self._size:
            self._items.popitem(last=False)
