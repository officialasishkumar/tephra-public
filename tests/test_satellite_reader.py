"""The Satellite Reader: frame choice, answer checks, box placement, one repair, no fallback.

The model is a scripted stand-in and the frames are small synthetic crops; nothing here
touches the network or Gemini.
"""

from collections.abc import Callable, Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from pydantic import BaseModel

from tephra.agents.llm import LlmCall, LlmPart, StubBackend, prompt_hash
from tephra.agents.satellite_reader import (
    NOTE,
    PROMPT_PATH,
    BoxRead,
    SatelliteExtraction,
    SatelliteReading,
    is_current,
    plume_part,
    read_satellite,
    select_frames,
    validate_extraction,
)
from tephra.config import PROJECT_ROOT
from tephra.feeds.volcanoes import load_volcanoes
from tephra.models import (
    BBox,
    FeedId,
    FrameProduct,
    GeoPolygon,
    LlmBackendName,
    OfficialLayer,
    Provenance,
    SatelliteFrame,
    TraceEvent,
    TraceStage,
)
from tephra.util import timeutil
from tephra.util.timeutil import FixedClock, use_clock

AT = datetime(2026, 10, 11, 12, 0, tzinfo=UTC)
SCAN = datetime(2026, 10, 11, 11, 0, tzinfo=UTC)
VOLCANO = load_volcanoes(PROJECT_ROOT / "data").get("282080")
assert VOLCANO is not None  # Sakurajima, vent 31.5772 N 130.6589 E
BBOX = BBox(west=130.0, south=31.0, east=131.0, north=32.0)
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16


@pytest.fixture(autouse=True)
def clock() -> Any:
    with use_clock(FixedClock(AT)):
        yield


def frame(
    product: FrameProduct,
    observed_at: datetime = SCAN,
    *,
    bbox: BBox | None = None,
    volcano_id: str = "282080",
) -> tuple[SatelliteFrame, bytes]:
    source_id = f"FRAME:{product.value}:{volcano_id}:{timeutil.compact(observed_at)}"
    provenance = Provenance(
        source_id=source_id,
        feed=FeedId.FRAMES,
        url=f"https://example.test/{product.value}.jpg",
        fetched_at=AT,
        issued_at=observed_at,
        sha256="ab" * 32,
    )
    made = SatelliteFrame(
        provenance=provenance,
        product=product,
        observed_at=observed_at,
        volcano_id=volcano_id,
        image_key=f"frames/{volcano_id}_{product.value}.png",
        width_px=200,
        height_px=200,
        bbox=bbox,
        caption="test crop",
    )
    return made, PNG


def pair(bbox: BBox | None = None) -> list[tuple[SatelliteFrame, bytes]]:
    return [frame(FrameProduct.DUST_RGB, bbox=bbox), frame(FrameProduct.B13_IR, bbox=bbox)]


def seen(**changes: Any) -> SatelliteExtraction:
    base: dict[str, Any] = {
        "ash_visible": "yes",
        "so2_visible": "uncertain",
        "obscured_by_cloud": "no",
        "boxes": [BoxRead(label="ash", box_2d=[400, 500, 600, 700])],
        "limits": "Thin cirrus lies over the eastern edge of the crop.",
    }
    return SatelliteExtraction(**{**base, **changes})


def layer(west: float, east: float) -> OfficialLayer:
    ring = [(west, 31.7), (east, 31.7), (east, 31.3), (west, 31.3), (west, 31.7)]
    return OfficialLayer(
        source_id=f"SIGMET:RJJJ:1:{west}",
        kind="SIGMET",
        layer="SIGMET",
        label="SIGMET RJJJ 1",
        volcano_id="282080",
        polygon=GeoPolygon(coordinates=[ring]),
        base_ft=0,
        top_ft=15_000,
        valid_from=AT - timedelta(hours=1),
        valid_to=AT + timedelta(hours=5),
    )


class ScriptedLlm:
    """Answers with the scripted extractions in order, as a non-stub backend would."""

    def __init__(
        self, answers: Sequence[SatelliteExtraction | None], name: LlmBackendName = "gemini"
    ):
        self.name: LlmBackendName = name
        self._answers = list(answers)
        self.calls = 0
        self.parts: list[Sequence[LlmPart]] = []
        self.system = ""

    def model_id(self, tier: str) -> str:
        return "gemini-test-lite"

    async def pace(self, tier: str, tokens: int = 0) -> None:
        return None

    async def reserve(self, tier: str) -> str | None:
        return None

    async def exhaust(self, tier: str) -> None:
        raise AssertionError("the Satellite Reader never closes a tier itself")

    async def structured[T: BaseModel](
        self,
        *,
        tier: str,
        system: str,
        parts: Sequence[LlmPart],
        schema: type[T],
        stub: Callable[[], T],
        temperature: float | None = None,
    ) -> tuple[T | None, LlmCall]:
        assert tier == "lite"
        answer = self._answers[self.calls]
        self.calls += 1
        self.parts.append(parts)
        self.system = system
        call = LlmCall(
            backend=self.name,
            model_id="gemini-test-lite",
            prompt_hash=prompt_hash(system, parts),
            raw_text="{}" if answer is None else answer.model_dump_json(),
            error=None if answer is not None else "api_error 503 UNAVAILABLE",
        )
        return (None if answer is None else schema.model_validate(answer.model_dump())), call


# --- frame choice -----------------------------------------------------------------------


def test_the_newest_dust_and_infrared_frames_of_this_volcano_are_chosen() -> None:
    older = SCAN - timedelta(minutes=10)
    frames = [
        frame(FrameProduct.DUST_RGB, older),
        frame(FrameProduct.DUST_RGB, SCAN),
        frame(FrameProduct.B13_IR, older),
        frame(FrameProduct.TRUE_COLOR, SCAN),
        frame(FrameProduct.DUST_RGB, SCAN + timedelta(minutes=10), volcano_id="282090"),
    ]
    chosen = select_frames(VOLCANO, frames)
    assert set(chosen) == {FrameProduct.DUST_RGB, FrameProduct.B13_IR}
    assert chosen[FrameProduct.DUST_RGB][0].observed_at == SCAN
    assert chosen[FrameProduct.B13_IR][0].observed_at == older


async def test_a_reading_is_current_until_a_newer_frame_arrives() -> None:
    frames = pair()
    reading = await read_satellite(VOLCANO, frames, [], ScriptedLlm([seen()]))
    assert is_current(reading, VOLCANO, frames)
    assert not is_current(None, VOLCANO, frames)
    newer = [*frames, frame(FrameProduct.DUST_RGB, SCAN + timedelta(minutes=10))]
    assert not is_current(reading, VOLCANO, newer)
    assert is_current(reading, VOLCANO, [*frames, frame(FrameProduct.TRUE_COLOR)])


# --- the reading ------------------------------------------------------------------------


async def test_boxes_become_polygons_with_bearing_distance_and_official_overlap() -> None:
    llm = ScriptedLlm([seen()])
    official = [layer(130.4, 130.8)]
    reading = await read_satellite(VOLCANO, pair(BBOX), official, llm)
    assert reading.status == "read"
    assert reading.reason is None
    assert reading.id.startswith("SAT-")
    assert reading.georeferenced
    assert reading.observed_at == SCAN
    assert reading.frame_ids == [
        "FRAME:DUST_RGB:282080:20261011T1100Z",
        "FRAME:B13_IR:282080:20261011T1100Z",
    ]
    assert (reading.ash_visible, reading.so2_visible, reading.obscured_by_cloud) == (
        "yes",
        "uncertain",
        "no",
    )
    assert reading.limits == "Thin cirrus lies over the eastern edge of the crop."
    assert reading.note == NOTE
    assert (reading.llm_backend, reading.model_id, reading.label) == (
        "gemini",
        "gemini-test-lite",
        None,
    )

    (box,) = reading.boxes
    assert box.box_2d == (400, 500, 600, 700)
    assert box.polygon is not None
    corners = [(130.5, 31.6), (130.7, 31.6), (130.7, 31.4), (130.5, 31.4), (130.5, 31.6)]
    (ring,) = box.polygon.coordinates
    assert len(ring) == len(corners)
    for got, want in zip(ring, corners, strict=True):
        assert got == pytest.approx(want)
    assert box.bearing_from_vent_deg is not None
    assert 205 < box.bearing_from_vent_deg < 220
    assert box.distance_km is not None
    assert 9 < box.distance_km < 11.5
    assert box.beyond_official is False


async def test_a_box_that_pokes_out_of_the_official_area_is_marked_and_no_area_is_not() -> None:
    narrow = await read_satellite(
        VOLCANO, pair(BBOX), [layer(130.55, 130.65)], ScriptedLlm([seen()])
    )
    assert narrow.boxes[0].beyond_official is True
    none_given = await read_satellite(VOLCANO, pair(BBOX), [], ScriptedLlm([seen()]))
    assert none_given.boxes[0].beyond_official is None


async def test_without_a_georeference_boxes_stay_pixel_boxes() -> None:
    reading = await read_satellite(VOLCANO, pair(), [layer(130.4, 130.8)], ScriptedLlm([seen()]))
    assert reading.status == "read"
    assert not reading.georeferenced
    (box,) = reading.boxes
    assert box.box_2d == (400, 500, 600, 700)
    assert (box.polygon, box.bearing_from_vent_deg, box.distance_km, box.beyond_official) == (
        None,
        None,
        None,
        None,
    )


async def test_the_model_sees_text_first_then_dust_then_infrared_labelled_by_source_id() -> None:
    llm = ScriptedLlm([seen(ash_visible="uncertain", boxes=[])])
    reading = await read_satellite(VOLCANO, pair(), [], llm)
    assert llm.calls == 1
    parts = llm.parts[0]
    assert [part.kind for part in parts] == ["text", "image", "image"]
    assert [part.label for part in parts[1:]] == reading.frame_ids
    assert "Sakurajima" in (parts[0].text or "")
    assert reading.boxes == []
    assert "never lowers" in " ".join(llm.system.split())


async def test_without_a_dust_frame_nothing_is_read_and_no_call_is_made() -> None:
    llm = ScriptedLlm([])
    frames = [frame(FrameProduct.B13_IR), frame(FrameProduct.TRUE_COLOR)]
    reading = await read_satellite(VOLCANO, frames, [], llm)
    assert reading.status == "no_frames"
    assert reading.reason == "no Dust RGB frame for this volcano"
    assert llm.calls == 0
    assert reading.ash_visible is None
    assert plume_part(reading) is None


async def test_infrared_is_optional() -> None:
    llm = ScriptedLlm([seen(ash_visible="uncertain", boxes=[])])
    reading = await read_satellite(VOLCANO, [frame(FrameProduct.DUST_RGB)], [], llm)
    assert reading.status == "read"
    assert [part.kind for part in llm.parts[0]] == ["text", "image"]
    assert "no infrared image" in (llm.parts[0][0].text or "")


# --- checks, repair and failure ---------------------------------------------------------


def box(*coords: int, label: str = "ash") -> BoxRead:
    return BoxRead(label=label, box_2d=list(coords))  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("changes", "fragment"),
    [
        ({"so2_visible": "yes"}, "so2"),
        ({"so2_visible": "no"}, "so2"),
        ({"boxes": [box(10, 10, 20, 20, label="so2")]}, "so2"),
        ({"boxes": []}, "no ash box"),
        ({"ash_visible": "uncertain"}, "boxes must be empty"),
        ({"ash_visible": "no"}, "boxes must be empty"),
        ({"ash_visible": "no", "boxes": [], "obscured_by_cloud": "yes"}, "not seeing is uncertain"),
        ({"ash_visible": "no", "boxes": [], "obscured_by_cloud": "uncertain"}, "not seeing"),
        ({"boxes": [box(500, 500, 400, 600)]}, "no area"),
        ({"boxes": [box(100, 300, 200, 300)]}, "no area"),
        ({"limits": "The plume looks about 40 km long."}, "digits"),
        ({"limits": "x" * 401}, "longer than 400"),
    ],
)
def test_answers_that_break_the_rules_are_rejected(changes: dict[str, Any], fragment: str) -> None:
    problems = validate_extraction(seen(**changes))
    assert any(fragment in problem for problem in problems), problems


def test_a_clear_picture_with_no_ash_is_accepted_and_cloud_makes_it_uncertain() -> None:
    clear = seen(ash_visible="no", boxes=[], obscured_by_cloud="no", limits="The crop is clear.")
    assert validate_extraction(clear) == []
    cloudy = seen(ash_visible="uncertain", boxes=[], obscured_by_cloud="yes")
    assert validate_extraction(cloudy) == []


def test_the_schema_bounds_boxes_to_four_numbers_between_zero_and_a_thousand() -> None:
    with pytest.raises(ValueError, match="box_2d"):
        BoxRead(label="ash", box_2d=[1, 2, 3])
    with pytest.raises(ValueError, match="box_2d"):
        BoxRead(label="ash", box_2d=[0, 0, 1001, 10])
    with pytest.raises(ValueError, match="boxes"):
        seen(boxes=[box(1, 1, 2, 2)] * 5)


async def test_one_repair_can_fix_a_rejected_answer() -> None:
    bad = seen(limits="Cloud covers 80 percent of the crop.")
    llm = ScriptedLlm([bad, seen()])
    reading = await read_satellite(VOLCANO, pair(), [], llm)
    assert reading.status == "read"
    assert llm.calls == 2
    repair = llm.parts[1][-1].text or ""
    assert repair.startswith("REPAIR")
    assert "digits" in repair


async def test_an_answer_that_stays_rejected_is_ai_unavailable_with_nothing_substituted() -> None:
    bad = seen(so2_visible="yes")
    llm = ScriptedLlm([bad, bad])
    reading = await read_satellite(VOLCANO, pair(), [], llm)
    assert llm.calls == 2
    assert reading.status == "ai_unavailable"
    assert reading.reason is not None
    assert reading.reason.startswith("AI UNAVAILABLE: so2")
    assert (reading.ash_visible, reading.boxes, reading.limits) == (None, [], None)
    assert plume_part(reading) is None


async def test_a_model_failure_is_ai_unavailable() -> None:
    llm = ScriptedLlm([None, None])
    reading = await read_satellite(VOLCANO, pair(), [], llm)
    assert reading.status == "ai_unavailable"
    assert reading.reason == "AI UNAVAILABLE: no usable model output (api_error 503 UNAVAILABLE)"
    assert reading.frame_ids  # the frames are still named, so the gate does not retry this scan


async def test_the_stub_backend_reads_nothing_and_says_so() -> None:
    reading = await read_satellite(VOLCANO, pair(), [], StubBackend())
    assert reading.status == "read"
    assert (reading.ash_visible, reading.so2_visible, reading.obscured_by_cloud) == (
        "uncertain",
    ) * 3
    assert reading.boxes == []
    assert (reading.llm_backend, reading.label) == ("stub", "NO MODEL")


async def test_the_reader_traces_what_it_does() -> None:
    events: list[TraceEvent] = []
    bad = seen(so2_visible="yes")
    await read_satellite(VOLCANO, pair(), [], ScriptedLlm([bad, seen()]), trace=events.append)
    assert {event.stage for event in events} == {TraceStage.SATELLITE}
    assert [event.level for event in events] == ["info", "warn", "info"]
    assert {event.volcano_id for event in events} == {"282080"}
    assert events[0].actor == "gemini"
    assert events[1].actor == "code"


# --- offering the reading to the Plume Reader -------------------------------------------


async def test_plume_part_is_text_with_the_sat_id_and_code_computed_figures() -> None:
    reading = await read_satellite(
        VOLCANO, pair(BBOX), [layer(130.55, 130.65)], ScriptedLlm([seen()])
    )
    part = plume_part(reading)
    assert part is not None
    assert part.kind == "text"
    text = part.text or ""
    assert text.startswith(f"[{reading.id}] SATELLITE CHECK (supporting evidence only")
    assert ", ".join(reading.frame_ids) in text
    assert "ash visible yes" in text
    assert "degrees true and" in text
    assert "km from the vent" in text
    assert "Part of it lies outside the official areas." in text
    assert "Thin cirrus lies over the eastern edge of the crop." in text
    assert text.endswith(NOTE)


async def test_plume_part_says_pixel_box_when_there_is_no_georeference() -> None:
    reading = await read_satellite(VOLCANO, pair(), [], ScriptedLlm([seen()]))
    part = plume_part(reading)
    assert part is not None
    assert "Ash box [400, 500, 600, 700] in the Dust RGB image (not georeferenced)." in (
        part.text or ""
    )


def test_the_reading_round_trips_through_the_store() -> None:
    reading = SatelliteReading(
        id="SAT-0123456789ab",
        volcano_id="282080",
        created_at=AT,
        status="no_frames",
        reason="no Dust RGB frame for this volcano",
    )
    assert SatelliteReading.model_validate(reading.model_dump(mode="json")) == reading


def test_the_prompt_states_the_rules_the_validator_enforces() -> None:
    prompt = " ".join(PROMPT_PATH.read_text(encoding="utf-8").split())
    for phrase in (
        "Not seeing ash is not evidence of no ash",
        "is always `uncertain`",
        "Never give an `so2` box",
    ):
        assert phrase in prompt
