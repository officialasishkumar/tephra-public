"""The Satellite Reader: Gemini looks at the newest Himawari crops of one volcano.

One lite call sees the Dust RGB and Band 13 crops that ``feeds/satellite.py`` already
fetched, and answers in categories (ash visible yes/no/uncertain, cloud cover, boxes in the
Dust RGB image). Code checks the answer, then turns boxes into lat/lon polygons and a
bearing and distance from the vent when the frame is georeferenced. The reading is
supporting evidence only: ``plume_part`` offers it to the Plume Reader as text with its own
source id, it never narrows anything, and the model never sets a height, a number or a time.

JMA ``se3`` crops carry a ``bbox`` (an equirectangular grid), so their boxes become lat/lon
polygons; a frame without one (Mercator or geostationary crops) keeps pixel boxes.
A model failure, or an answer that fails the checks after one repair, is
``AI UNAVAILABLE``: nothing is substituted.
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Annotated, Final, Literal

import shapely
from pydantic import Field
from shapely.geometry import Polygon, shape
from shapely.geometry.base import BaseGeometry

from tephra.agents.llm import LlmBackend, LlmPart, prompt_hash
from tephra.agents.plume_reader import AI_UNAVAILABLE
from tephra.config import NO_MODEL_LABEL
from tephra.geo.units import haversine_km, initial_bearing_deg
from tephra.models import (
    BBox,
    FrameProduct,
    GeoPolygon,
    LlmBackendName,
    OfficialLayer,
    SatelliteFrame,
    TephraModel,
    TraceActor,
    TraceEvent,
    TraceSink,
    TraceStage,
    UtcDatetime,
    Volcano,
)
from tephra.util import timeutil
from tephra.util.hashing import stable_id

__all__ = [
    "PROMPT_PATH",
    "SatelliteBox",
    "SatelliteExtraction",
    "SatelliteReading",
    "is_current",
    "plume_part",
    "read_satellite",
    "select_frames",
    "validate_extraction",
]

PROMPT_PATH: Final[Path] = Path(__file__).resolve().parent / "prompts" / "satellite_reader.md"
MAX_BOXES: Final = 4
MAX_LIMITS_CHARS: Final = 400
BOX_SCALE: Final = 1000
REPAIR_ECHO_CHARS: Final = 3000
READ_PRODUCTS: Final = (FrameProduct.DUST_RGB, FrameProduct.B13_IR)
"""The products the model sees, the Dust RGB first: boxes are drawn on it."""
NOTE: Final = (
    "Supporting evidence only. A picture that shows no ash, or that cannot be read, never "
    "narrows the hazard, lowers an action or sets a height."
)
_DIGIT: Final = re.compile(r"\d")

Answer = Literal["yes", "no", "uncertain"]
Coordinate = Annotated[int, Field(ge=0, le=BOX_SCALE)]
Frames = Sequence[tuple[SatelliteFrame, bytes]]


# --- what the model returns -------------------------------------------------------------


class BoxRead(TephraModel):
    label: Literal["ash", "so2"]
    box_2d: Annotated[list[Coordinate], Field(min_length=4, max_length=4)]


class SatelliteExtraction(TephraModel):
    ash_visible: Answer
    so2_visible: Answer
    obscured_by_cloud: Answer
    boxes: Annotated[list[BoxRead], Field(max_length=MAX_BOXES)]
    limits: str


# --- what TEPHRA stores -----------------------------------------------------------------


class SatelliteBox(TephraModel):
    """An ash box in the Dust RGB image, placed on the map when the frame is georeferenced."""

    label: Literal["ash"] = "ash"
    box_2d: tuple[int, int, int, int] = Field(description="[ymin, xmin, ymax, xmax], 0-1000")
    polygon: GeoPolygon | None = None
    bearing_from_vent_deg: float | None = Field(
        default=None, description="Bearing from the vent to the box centre; needs a georeference"
    )
    distance_km: float | None = None
    beyond_official: bool | None = Field(
        default=None,
        description="True when part of the box lies outside every official area given; "
        "None without a georeference or without official areas",
    )


class SatelliteReading(TephraModel):
    id: str = Field(description="SAT-<hash>; the source id the Plume Reader may cite")
    volcano_id: str
    created_at: UtcDatetime
    replay: bool = False
    status: Literal["read", "no_frames", "ai_unavailable"]
    reason: str | None = None
    observed_at: UtcDatetime | None = Field(
        default=None, description="Scan time of the newest frame read"
    )
    frame_ids: list[str] = Field(default_factory=list, description="Source ids of the frames read")
    ash_visible: Answer | None = None
    so2_visible: Answer | None = None
    obscured_by_cloud: Answer | None = None
    boxes: list[SatelliteBox] = Field(default_factory=list)
    georeferenced: bool = False
    limits: str | None = Field(default=None, description="Written by the model; no digits")
    note: str = NOTE
    llm_backend: LlmBackendName | None = None
    model_id: str | None = None
    prompt_hash: str | None = None
    label: str | None = Field(default=None, description="NO MODEL for the stub backend")


# --- the call ---------------------------------------------------------------------------


def select_frames(
    volcano: Volcano, frames: Frames
) -> dict[FrameProduct, tuple[SatelliteFrame, bytes]]:
    """The newest frame of each product the reader uses, for this volcano."""
    newest: dict[FrameProduct, tuple[SatelliteFrame, bytes]] = {}
    for frame, png in frames:
        if frame.product not in READ_PRODUCTS or frame.volcano_id != volcano.id:
            continue
        held = newest.get(frame.product)
        if held is None or frame.observed_at > held[0].observed_at:
            newest[frame.product] = (frame, png)
    return newest


def is_current(reading: SatelliteReading | None, volcano: Volcano, frames: Frames) -> bool:
    """True when ``reading`` was made from these newest frames: the gate that keeps a call
    from being spent twice on the same scan."""
    chosen = select_frames(volcano, frames)
    return reading is not None and reading.frame_ids == _frame_ids(chosen)


async def read_satellite(
    volcano: Volcano,
    frames: Frames,
    official_layers: Sequence[OfficialLayer],
    llm: LlmBackend,
    *,
    replay: bool = False,
    trace: TraceSink | None = None,
) -> SatelliteReading:
    """One reading of the newest frames. The call is the caller's to gate: run it only when
    the Plume Reader is about to be asked about this volcano and ``is_current`` is False."""
    chosen = select_frames(volcano, frames)
    frame_ids = _frame_ids(chosen)
    reading = _Maker(volcano, chosen, frame_ids, llm, replay)
    emit = _Emitter(trace, volcano)
    actor: TraceActor = "stub" if llm.name == "stub" else "gemini"
    if FrameProduct.DUST_RGB not in chosen:
        emit("code", "Satellite Reader: no Dust RGB frame for this volcano, nothing read")
        return reading.made("no_frames", reason="no Dust RGB frame for this volcano")

    system = _system_prompt()
    parts = _parts(volcano, chosen)
    p_hash = prompt_hash(system, parts)
    emit(actor, f"Satellite Reader: asking {llm.model_id('lite')} ({len(chosen)} images)")
    extraction, call = await llm.structured(
        tier="lite", system=system, parts=parts, schema=SatelliteExtraction, stub=_stub
    )
    problems = _problems(extraction, call.error)
    if problems and call.raw_text:
        emit("code", "Satellite Reader output rejected; one repair call", level="warn")
        repair = [*parts, LlmPart.of_text(_repair_text(problems, call.raw_text))]
        extraction, call = await llm.structured(
            tier="lite", system=system, parts=repair, schema=SatelliteExtraction, stub=_stub
        )
        problems = _problems(extraction, call.error)
    if extraction is None or problems:
        reason = f"{AI_UNAVAILABLE}: {'; '.join(problems)}"
        emit("code", f"Satellite Reader: {reason}", level="error")
        return reading.made("ai_unavailable", reason=reason, prompt=p_hash)

    result = reading.made(
        "read",
        extraction=extraction,
        boxes=_place_boxes(extraction, volcano, chosen[FrameProduct.DUST_RGB][0], official_layers),
        prompt=p_hash,
    )
    emit(
        actor,
        f"Satellite Reader: ash visible {result.ash_visible}, cloud {result.obscured_by_cloud}",
    )
    return result


def validate_extraction(extraction: SatelliteExtraction) -> list[str]:
    """Every reason to reject the answer; an empty list means accepted."""
    problems: list[str] = []
    ash_boxes = [box for box in extraction.boxes if box.label == "ash"]
    if any(box.label == "so2" for box in extraction.boxes) or extraction.so2_visible != "uncertain":
        problems.append("so2: the Dust RGB product cannot show sulphur dioxide; answer uncertain")
    if extraction.ash_visible == "yes" and not ash_boxes:
        problems.append("ash_visible is yes but no ash box was given")
    if extraction.ash_visible != "yes" and extraction.boxes:
        problems.append("boxes must be empty unless ash_visible is yes")
    if extraction.obscured_by_cloud != "no" and extraction.ash_visible == "no":
        problems.append("ash_visible is no while cloud may cover the area; not seeing is uncertain")
    for index, box in enumerate(extraction.boxes):
        ymin, xmin, ymax, xmax = box.box_2d
        if ymin >= ymax or xmin >= xmax:
            problems.append(f"boxes[{index}] has no area: [ymin, xmin, ymax, xmax] must grow")
    if _DIGIT.search(extraction.limits):
        problems.append("limits contains digits; the images give no figures")
    if len(extraction.limits) > MAX_LIMITS_CHARS:
        problems.append(f"limits is longer than {MAX_LIMITS_CHARS} characters")
    return problems


def plume_part(reading: SatelliteReading) -> LlmPart | None:
    """The reading as text for the Plume Reader's input, cited as ``[SAT-...]``; None unless
    the picture was read. Every figure in it was computed by code."""
    if reading.status != "read":
        return None
    lines = [
        f"[{reading.id}] SATELLITE CHECK (supporting evidence only; read from "
        f"{', '.join(reading.frame_ids)}): ash visible {reading.ash_visible}; "
        f"cloud over the area {reading.obscured_by_cloud}; sulphur dioxide {reading.so2_visible}.",
    ]
    for box in reading.boxes:
        if box.bearing_from_vent_deg is None:
            lines.append(f"Ash box {list(box.box_2d)} in the Dust RGB image (not georeferenced).")
            continue
        bearing, distance = box.bearing_from_vent_deg, box.distance_km
        where = f"{bearing:.0f} degrees true and {distance:.0f} km from the vent"
        beyond = " Part of it lies outside the official areas." if box.beyond_official else ""
        lines.append(f"Ash box centred {where}.{beyond}")
    if reading.limits:
        lines.append(f"Reader's limits: {reading.limits}")
    lines.append(reading.note)
    return LlmPart.of_text("\n".join(lines))


# --- building the reading ---------------------------------------------------------------


@dataclass(frozen=True)
class _Maker:
    volcano: Volcano
    chosen: dict[FrameProduct, tuple[SatelliteFrame, bytes]]
    frame_ids: list[str]
    llm: LlmBackend
    replay: bool

    def made(
        self,
        status: Literal["read", "no_frames", "ai_unavailable"],
        *,
        reason: str | None = None,
        extraction: SatelliteExtraction | None = None,
        boxes: list[SatelliteBox] | None = None,
        prompt: str | None = None,
    ) -> SatelliteReading:
        dust = self.chosen.get(FrameProduct.DUST_RGB)
        return SatelliteReading(
            id=stable_id("SAT", self.volcano.id, *self.frame_ids),
            volcano_id=self.volcano.id,
            created_at=timeutil.now(),
            replay=self.replay,
            status=status,
            reason=reason,
            observed_at=max(frame.observed_at for frame, _ in self.chosen.values())
            if self.chosen
            else None,
            frame_ids=self.frame_ids,
            ash_visible=extraction.ash_visible if extraction else None,
            so2_visible=extraction.so2_visible if extraction else None,
            obscured_by_cloud=extraction.obscured_by_cloud if extraction else None,
            boxes=boxes or [],
            georeferenced=dust is not None and dust[0].bbox is not None,
            limits=extraction.limits.strip() if extraction else None,
            llm_backend=self.llm.name,
            model_id=self.llm.model_id("lite"),
            prompt_hash=prompt,
            label=NO_MODEL_LABEL if self.llm.name == "stub" else None,
        )


def _place_boxes(
    extraction: SatelliteExtraction,
    volcano: Volcano,
    dust: SatelliteFrame,
    official_layers: Sequence[OfficialLayer],
) -> list[SatelliteBox]:
    official = (
        shapely.unary_union(
            [shape(layer.polygon.model_dump(mode="json")) for layer in official_layers]
        )
        if official_layers
        else None
    )
    placed: list[SatelliteBox] = []
    for box in extraction.boxes:
        ymin, xmin, ymax, xmax = box.box_2d
        if dust.bbox is None:
            placed.append(SatelliteBox(box_2d=(ymin, xmin, ymax, xmax)))
        else:
            placed.append(_on_map((ymin, xmin, ymax, xmax), dust.bbox, volcano, official))
    return placed


def _on_map(
    box: tuple[int, int, int, int], bbox: BBox, volcano: Volcano, official: BaseGeometry | None
) -> SatelliteBox:
    """Pixel box to polygon by linear interpolation inside the frame's bbox: the crops span a
    few degrees, where that differs from the true projection by less than a pixel or two."""
    ymin, xmin, ymax, xmax = box

    def lonlat(x: int, y: int) -> tuple[float, float]:
        return (
            bbox.west + (bbox.east - bbox.west) * x / BOX_SCALE,
            bbox.north - (bbox.north - bbox.south) * y / BOX_SCALE,
        )

    ring = [lonlat(xmin, ymin), lonlat(xmax, ymin), lonlat(xmax, ymax), lonlat(xmin, ymax)]
    ring.append(ring[0])
    centre_lon, centre_lat = lonlat((xmin + xmax) // 2, (ymin + ymax) // 2)
    return SatelliteBox(
        box_2d=box,
        polygon=GeoPolygon(coordinates=[ring]),
        bearing_from_vent_deg=round(
            initial_bearing_deg(volcano.lat, volcano.lon, centre_lat, centre_lon), 1
        ),
        distance_km=round(haversine_km(volcano.lat, volcano.lon, centre_lat, centre_lon), 1),
        beyond_official=None if official is None else not official.contains(Polygon(ring)),
    )


def _stub() -> SatelliteExtraction:
    """Offline test answer (``TEPHRA_LLM=stub``): nothing was looked at."""
    return SatelliteExtraction(
        ash_visible="uncertain",
        so2_visible="uncertain",
        obscured_by_cloud="uncertain",
        boxes=[],
        limits="The stub backend reads no image.",
    )


def _problems(extraction: SatelliteExtraction | None, error: str | None) -> list[str]:
    if extraction is None:
        return [f"no usable model output ({error or 'unknown error'})"]
    return validate_extraction(extraction)


def _frame_ids(chosen: dict[FrameProduct, tuple[SatelliteFrame, bytes]]) -> list[str]:
    return [
        chosen[product][0].provenance.source_id for product in READ_PRODUCTS if product in chosen
    ]


def _parts(
    volcano: Volcano, chosen: dict[FrameProduct, tuple[SatelliteFrame, bytes]]
) -> list[LlmPart]:
    intro = f"VOLCANO: {volcano.name} (GVP {volcano.id}).\nThe first image is the Dust RGB crop"
    intro += (
        ", the second the Band 13 infrared crop of the same scan."
        if FrameProduct.B13_IR in chosen
        else "; no infrared image is available."
    )
    parts = [LlmPart.of_text(f"{intro}\nBoxes refer to the Dust RGB image only.")]
    for product in READ_PRODUCTS:
        if product in chosen:
            frame, png = chosen[product]
            parts.append(LlmPart.of_image(png, label=frame.provenance.source_id))
    return parts


def _repair_text(problems: Sequence[str], previous: str) -> str:
    listed = "\n".join(f"- {problem}" for problem in problems)
    return (
        "REPAIR\n"
        "Code rejected your previous answer for these reasons:\n"
        f"{listed}\n"
        "Your previous answer was:\n"
        f"{previous[:REPAIR_ECHO_CHARS]}\n"
        "Return a corrected JSON object that fixes every reason."
    )


class _Emitter:
    def __init__(self, sink: TraceSink | None, volcano: Volcano) -> None:
        self._sink = sink
        self._volcano_id = volcano.id

    def __call__(
        self,
        actor: TraceActor,
        message: str,
        *,
        level: Literal["info", "warn", "error"] = "info",
    ) -> None:
        if self._sink is not None:
            self._sink(
                TraceEvent.new(
                    TraceStage.SATELLITE, actor, message, level=level, volcano_id=self._volcano_id
                )
            )


@cache
def _system_prompt() -> str:
    return PROMPT_PATH.read_text(encoding="utf-8")
