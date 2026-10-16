"""Write the synthetic demo replay case ``data/replay/demo-agung-20261014/``.

SYNTHETIC DEMO DATA. Nothing in this case was recorded. The volcanoes, airports, flight
information regions, callsigns and their usual routes are real (``data/volcanoes.json``,
``data/airports.json``, ``data/routes_apac.json``); every product, observation, weather report
and aircraft position is invented here so that one short replay shows each source TEPHRA reads
and the situations it handles. The manifest says so (``synthetic: true``, notes that open with
"Synthetic demo data"), the Wall and the Desk label the replay "synthetic demo data", and the
backtest never scores it.

The story, 14 Oct 2026 (UTC):

* Agung (Bali) erupts at 0542Z. The observatory's VONAs put the ash higher than every official
  product (11,500 m from its 0700Z notice) and moving south; the SIGMET moves it west and
  Darwin's VAA south-west, so the sources disagree on height and direction. Ash reaches Bali's
  airport (WADD), whose METARs and amended TAF report VA. Darwin's next VAA (0748Z, after the
  demo window) raises the top from FL350 to FL380.
* Sakurajima (Kyushu) erupts at 0510Z; Tokyo VAAC's final advisory at 0630Z says the ash has
  dissipated. JMA reports a new eruption at 0652Z and RJJJ issues a SIGMET, while Tokyo's "no
  ash" advisory is still in force: a CONFLICT.
* Semeru (East Java) and Dukono (Halmahera) carry routine low-level SIGMETs and VAAs.

The demo window, 0705Z to 0715Z, comes after the last product in it: the picture holds while
the aircraft move, so each minute of the loop shows the same things. Flights are real airline
callsigns on their usual legs (VRS standing data), each on the great circle between the real
airports at a level the semicircular rule allows, climbing, cruising and descending at plain
speeds for its class (turboprop, narrowbody, widebody) with the wind aloft in its ground speed.
Their positions and times are invented. The flights the demo turns on ("heroes") are placed
with the app's own exposure check against the official area, so at the window start some are
inside, some minutes from it and some half an hour out, at the levels that make the code
offer each action.

Feeds in the case: AWC international SIGMETs, MAGMA VONA list pages, JMA's eruption reports
(Atom feed and VFVO52 documents), Tokyo VAAC list and text pages, Darwin VAA bulletins (the ten
tgftp slots and JMA's Darwin backup list), AWC METARs and TAFs, Open-Meteo pressure-level winds
and adsb.lol point answers. Satellite frames and raw Himawari data are not invented: TEPHRA
credits each frame to JMA or NICT, and a drawn picture would pass for their imagery.

Each feed is stored under the exact URL its poller requests. The context feeds' URLs (station
lists, wind points, ADS-B query points) depend on what the replay shows, so they are found as
``scripts/record_replay.py`` finds them: replay ticks through a logging source list what the
pollers ask for, each URL is filled across the window, and probing repeats until nothing is
missing. Everything is seeded; a rerun writes the same bytes.

Usage (no network)::

    uv run python scripts/make_demo_case.py
    uv run python scripts/record_replay.py probe --case demo-agung-20261014 \
        --from 2026-10-14T07:05Z --at 2026-10-14T07:05Z --at 2026-10-14T07:15Z
"""

# ruff: noqa: RUF001  (JMA's Japanese text uses full-width colons and brackets)

from __future__ import annotations

import argparse
import asyncio
import hashlib
import importlib.util
import json
import math
import random
import shutil
import sys
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from functools import cache
from pathlib import Path
from types import ModuleType
from typing import Any, Final
from urllib.parse import parse_qsl, urlsplit

from shapely import unary_union

from tephra.config import PROJECT_ROOT, REGIONS, Settings
from tephra.feeds.adsb import parse_adsb
from tephra.feeds.airports import load_airports
from tephra.feeds.base import FetchResult
from tephra.feeds.jma_volcano import JMA_EQVOL_URL
from tephra.feeds.routes import ROUTES_FILE, load_routes
from tephra.feeds.sigmet import SIGMET_URL, parse_sigmets
from tephra.feeds.vaac import (
    DARWIN_BACKUP_LIST_URL,
    DARWIN_BULLETIN_URLS,
    TOKYO_LIST_URL,
    parse_vaa,
)
from tephra.feeds.volcanoes import load_volcanoes
from tephra.feeds.vona import VONA_LIST_URL
from tephra.feeds.winds import PRESSURE_LEVELS_HPA
from tephra.geo.cone import geometry_to_shape, official_layers, shape_to_geometry
from tephra.geo.exposure import find_crossings
from tephra.geo.fuel import category_for_type
from tephra.geo.units import distance_nm, initial_bearing_deg
from tephra.models import AdsbQueryPoint, AircraftCategory, FeedId, ReplayCase, ReplayRecord
from tephra.policy import load_policy
from tephra.util import timeutil

CASE_ID: Final = "demo-agung-20261014"
LABEL: Final = (
    "SYNTHETIC DEMO: Agung ash closes Bali while Sakurajima erupts, 14 Oct 2026 (invented data)"
)
REGION: Final = "java_bali"
VOLCANO_IDS: Final = ["264020", "282080"]
"""Agung first (the Wall opens on it), then Sakurajima: the two the plume reader reads."""
SEED: Final = 20261014
START: Final = datetime(2026, 10, 14, 6, 30, tzinfo=UTC)
END: Final = datetime(2026, 10, 14, 8, 15, tzinfo=UTC)
DEMO_FROM: Final = datetime(2026, 10, 14, 7, 5, tzinfo=UTC)
DEMO_TO: Final = datetime(2026, 10, 14, 7, 15, tzinfo=UTC)
ADSB_STEP: Final = timedelta(seconds=30)
CONTEXT_FEEDS: Final = (FeedId.TAF, FeedId.METAR, FeedId.WINDS, FeedId.ADSB)
MAX_ROUNDS: Final = 6
JSON_TYPE: Final = "application/json; charset=utf-8"
HTML_TYPE: Final = "text/html"
TEXT_TYPE: Final = "text/plain"
XML_TYPE: Final = "application/xml"
MARK: Final = (
    "SYNTHETIC DEMO DATA made by TEPHRA's scripts/make_demo_case.py for a product demo. "
    "Not issued by any agency and not a copy of any real page."
)
NOTES: Final = (
    "Synthetic demo data, invented for TEPHRA's product demo by scripts/make_demo_case.py "
    "(seeded, no network); nothing in this case was recorded or happened. Real: the volcanoes, "
    "airports, FIRs, airline callsigns and their usual routes (data/volcanoes.json, "
    "data/airports.json, data/routes_apac.json, VRS standing data CC0); each flight flies the "
    "great circle of its callsign's leg at a semicircular-rule level. Invented: every SIGMET, "
    "VONA, JMA eruption report, Tokyo and Darwin VAA, METAR, TAF, wind profile and aircraft "
    "position and time, each stored under the URL the live poller requests so the same parsers "
    "read it. The HTML and XML pages say so in a comment; the JSON answers cannot. Story (UTC, "
    "14 Oct 2026): Agung erupts at 0542Z; the observatory puts the ash higher than every official "
    "product (0700Z notice) and moving south while the SIGMET says west and Darwin south-west; "
    "WADD's METARs and amended TAF report VA; Darwin's next VAA at 0748Z raises the top to "
    "FL380. Sakurajima's Tokyo VAA closes the event at 0630Z, JMA reports a new eruption at "
    "0652Z and RJJJ a SIGMET while that VAA is in force. Semeru and Dukono carry routine SIGMETs "
    "and VAAs. Not in this case: satellite frames and raw Himawari data (TEPHRA credits frames "
    "to JMA or NICT; an invented picture would pass for theirs). Never scored by the backtest. "
    "Demo window 0705Z-0715Z (TEPHRA_REPLAY_START, TEPHRA_REPLAY_END), after the last product "
    "in it, so every minute of the loop shows the same picture."
)

DATA_DIR: Final = PROJECT_ROOT / "data"


def at(day: int, hhmm: str) -> datetime:
    return datetime(2026, 10, day, int(hhmm[:2]), int(hhmm[2:]), tzinfo=UTC)


# --- formatting helpers ---------------------------------------------------------------


def iso(when: datetime) -> str:
    return timeutil.to_iso(when)


def epoch(when: datetime) -> int:
    return int(when.timestamp())


def ddhhmm(when: datetime) -> str:
    return when.strftime("%d%H%M")


def dm(lat: float, lon: float) -> str:
    """``(-8.343, 115.508)`` -> ``S0821 E11530``: whole minutes, as SIGMETs and VAAs write."""

    def part(value: float, positive: str, negative: str, width: int) -> str:
        minutes = round(abs(value) * 60)
        return f"{positive if value >= 0 else negative}{minutes // 60:0{width}d}{minutes % 60:02d}"

    return f"{part(lat, 'N', 'S', 2)} {part(lon, 'E', 'W', 3)}"


def snap(value: float) -> float:
    """A coordinate on the whole-minute grid the bulletins write."""
    return math.copysign(round(abs(value) * 60) / 60, value)


Ring = list[tuple[float, float]]


def ring(*points: tuple[float, float]) -> Ring:
    """Closed ``(lat, lon)`` ring on the minute grid."""
    snapped = [(snap(lat), snap(lon)) for lat, lon in points]
    return [*snapped, snapped[0]]


def ring_text(points: Ring) -> str:
    return " - ".join(dm(lat, lon) for lat, lon in points)


def wrap(text: str, width: int = 68, indent: str = "") -> list[str]:
    lines: list[str] = []
    current = ""
    for word in text.split():
        if current and len(current) + 1 + len(word) > width:
            lines.append(current)
            current = indent + word
        else:
            current = f"{current} {word}" if current else word
    lines.append(current)
    return lines


def json_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode()


# --- volcanoes ----------------------------------------------------------------------------


@dataclass(frozen=True)
class Vent:
    id: str
    name: str
    lat: float
    lon: float


AGUNG: Final = Vent("264020", "AGUNG", -8.343, 115.508)
SAKURAJIMA: Final = Vent("282080", "SAKURAJIMA", 31.5772, 130.6589)
SEMERU: Final = Vent("263300", "SEMERU", -8.108, 112.922)
DUKONO: Final = Vent("268010", "DUKONO", 1.6992, 127.8783)
LEWOTOLOK: Final = Vent("264230", "LEWOTOLOK", -8.274, 123.508)
IBU: Final = Vent("268030", "IBU", 1.488, 127.63)


def snapshot_times(arrivals: Iterable[datetime]) -> list[datetime]:
    """When a list feed changes: the window start, then each arrival after it. A list page at
    time t holds every product that arrived by t."""
    return sorted({START, *(when for when in arrivals if when > START)})


# --- SIGMETs (AWC international SIGMET JSON) ---------------------------------------------


@dataclass(frozen=True)
class SigmetSpec:
    fir: str
    fir_name: str
    office: str
    heading: str
    series: str
    issued: datetime
    valid_to: datetime
    volcano: Vent
    name_text: str
    obs_at: datetime
    area: Ring
    base_ft: int
    top_ft: int
    move_dir: str
    move_kt: int
    change: str
    ends_at: datetime | None = None
    """When AWC shortens ``validTimeTo`` (a cancellation it does not relay as a record)."""

    def raw(self) -> str:
        base = "SFC" if self.base_ft == 0 else f"FL{self.base_ft // 100:03d}"
        band = f"{base}/FL{self.top_ft // 100:03d}"
        body = (
            f"{self.fir} {self.fir_name} FIR VA ERUPTION MT {self.name_text} PSN "
            f"{dm(self.volcano.lat, self.volcano.lon)} VA CLD OBS AT {self.obs_at:%H%M}Z WI "
            f"{ring_text(self.area)} {band} MOV {self.move_dir} {self.move_kt:02d}KT {self.change}="
        )
        head = [
            f"{self.heading} {self.office} {ddhhmm(self.issued)}",
            f"{self.fir} SIGMET {self.series} VALID {ddhhmm(self.issued)}/{ddhhmm(self.valid_to)} "
            f"{self.office}-",
        ]
        return "\n".join([*head, *wrap(body)])

    def record(self, as_of: datetime) -> dict[str, Any]:
        valid_to = self.valid_to
        if self.ends_at is not None and as_of >= self.ends_at:
            valid_to = self.ends_at
        return {
            "icaoId": self.office,
            "firId": self.fir,
            "firName": f"{self.fir} {self.fir_name}",
            "receiptTime": iso(self.issued + timedelta(minutes=1)),
            "validTimeFrom": epoch(self.issued),
            "validTimeTo": epoch(valid_to),
            "seriesId": self.series,
            "hazard": "VA",
            "qualifier": f"ERUPTION MT {self.name_text}",
            "base": self.base_ft,
            "top": self.top_ft,
            "geom": "AREA",
            "coords": [{"lon": round(lon, 3), "lat": round(lat, 3)} for lat, lon in self.area],
            "dir": self.move_dir,
            "spd": str(self.move_kt),
            "chng": self.change,
            "rawSigmet": self.raw(),
        }


AGUNG_SIGMET_AREA: Final = ring((-8.30, 115.53), (-8.25, 114.83), (-8.75, 115.00), (-8.83, 115.42))
SEMERU_AREA: Final = ring((-8.08, 112.90), (-7.85, 113.20), (-7.95, 113.35), (-8.15, 113.00))
DUKONO_AREA: Final = ring((1.67, 127.78), (2.53, 128.05), (2.48, 128.62), (1.57, 127.90))
SAKURA_Y01_AREA: Final = ring((31.60, 130.65), (31.67, 131.00), (31.47, 131.08), (31.53, 130.63))
SAKURA_Y02_AREA: Final = ring((31.62, 130.70), (31.05, 130.70), (30.95, 130.35), (31.50, 130.50))

SIGMETS: Final = [
    SigmetSpec(
        "WAAF", "UJUNG PANDANG", "WAAA", "WVID21", "04", at(14, "0350"), at(14, "0950"),
        DUKONO, "DUKONO", at(14, "0330"), DUKONO_AREA, 0, 7000, "NE", 10, "NC",
    ),
    SigmetSpec(
        "WAAF", "UJUNG PANDANG", "WAAA", "WVID21", "05", at(14, "0430"), at(14, "1030"),
        SEMERU, "SEMERU", at(14, "0400"), SEMERU_AREA, 0, 14000, "NE", 10, "NC",
    ),
    SigmetSpec(
        "RJJJ", "FUKUOKA", "RJTD", "WVJP31", "Y01", at(14, "0522"), at(14, "1122"),
        SAKURAJIMA, "SAKURAJIMA (AIRA CALDERA)", at(14, "0510"), SAKURA_Y01_AREA, 0, 8000,
        "E", 10, "NC", ends_at=at(14, "0635"),
    ),
    SigmetSpec(
        "WAAF", "UJUNG PANDANG", "WAAA", "WVID21", "06", at(14, "0610"), at(14, "1210"),
        AGUNG, "AGUNG", at(14, "0600"), AGUNG_SIGMET_AREA, 0, 25000, "W", 15, "INTSF",
    ),
    SigmetSpec(
        "RJJJ", "FUKUOKA", "RJTD", "WVJP31", "Y02", at(14, "0702"), at(14, "1302"),
        SAKURAJIMA, "SAKURAJIMA (AIRA CALDERA)", at(14, "0652"), SAKURA_Y02_AREA, 0, 11000,
        "S", 15, "NC",
    ),
]  # fmt: skip


def sigmet_records(store: Store) -> list[ReplayRecord]:
    url = f"{SIGMET_URL}?format=json&hazard=va"
    times = snapshot_times(spec.issued + timedelta(minutes=1) for spec in SIGMETS)
    times += [spec.ends_at for spec in SIGMETS if spec.ends_at and spec.ends_at > START]
    records = []
    for when in sorted(set(times)):
        listed = [
            spec.record(when)
            for spec in SIGMETS
            if spec.issued + timedelta(minutes=1) <= when <= spec.valid_to
        ]
        records.append(store.put(FeedId.SIGMET, url, when, json_bytes(listed), JSON_TYPE))
    return records


# --- MAGMA VONA list pages ------------------------------------------------------------------


@dataclass(frozen=True)
class VonaSpec:
    magma_id: int
    volcano: str
    issued: datetime
    color: str
    text: str


VONAS: Final = [
    VonaSpec(
        99003, "Lewotolok", at(12, "2210"), "Orange",
        "Eruption with volcanic ash cloud at 2202 UTC (0702 local). Best estimate of ash-cloud "
        "top is around 7392 FT (2310 M) above sea level or 2816 FT (880 M) above summit. May be "
        "higher than what can be observed clearly. Source of height data: ground observer. Ash "
        "cloud moving to west.",
    ),
    VonaSpec(
        99004, "Dukono", at(13, "0315"), "Orange",
        "Eruption with volcanic ash cloud at 0300 UTC (1200 local). Best estimate of ash-cloud "
        "top is around 6080 FT (1900 M) above sea level or 2006 FT (627 M) above summit. May be "
        "higher than what can be observed clearly. Source of height data: ground observer. Ash "
        "cloud moving to north-east.",
    ),
    VonaSpec(
        99005, "Semeru", at(13, "2340"), "Orange",
        "Eruption with volcanic ash cloud at 2331 UTC (0631 local). Best estimate of ash-cloud "
        "top is around 12800 FT (4000 M) above sea level or 1098 FT (343 M) above summit. May be "
        "higher than what can be observed clearly. Source of height data: ground observer. Ash "
        "cloud moving to north-east.",
    ),
    VonaSpec(
        99006, "Semeru", at(14, "0338"), "Orange",
        "Eruption at 0331 UTC (1031 local). Ash-cloud is not observed. Ash-cloud is not "
        "observed..",
    ),
    VonaSpec(
        99007, "Agung", at(14, "0552"), "Red",
        "Eruption with volcanic ash cloud at 0542 UTC (1342 local). Best estimate of ash-cloud "
        "top is around 30080 FT (9400 M) above sea level or 20490 FT (6403 M) above summit. May "
        "be higher than what can be observed clearly. Source of height data: ground observer. "
        "Ash cloud moving to south. Volcanic ash is observed to be thick.",
    ),
    VonaSpec(
        99008, "Agung", at(14, "0700"), "Red",
        "Eruption with volcanic ash cloud at 0652 UTC (1452 local). Best estimate of ash-cloud "
        "top is around 36800 FT (11500 M) above sea level or 27210 FT (8503 M) above summit. May "
        "be higher than what can be observed clearly. Source of height data: ground observer. "
        "Ash cloud moving to south. Volcanic ash is observed to be thick. Ash fall is reported "
        "in Karangasem.",
    ),
]  # fmt: skip


def vona_card(spec: VonaSpec) -> str:
    return "\n".join(
        [
            '<div class="timeline-item">',
            f'<div class="timeline-time"><small>{spec.issued:%Y-%m-%d %H:%M:%S} UTC</small> '
            f'<a class="btn" href="#">{spec.color}</a></div>',
            '<div class="timeline-body">',
            f'<p class="timeline-title"><a href="#">{spec.volcano} - '
            f"{spec.issued:%Y%m%d/%H%M}Z</a></p>",
            f'<p class="timeline-text">{spec.text}</p>',
            f'<a class="card-link" href="{VONA_LIST_URL}/{spec.magma_id}">View</a>',
            "</div>",
            "</div>",
        ]
    )


def vona_page(listed: Sequence[VonaSpec]) -> bytes:
    cards = [vona_card(spec) for spec in sorted(listed, key=lambda s: s.issued, reverse=True)]
    return "\n".join(
        [
            f"<!-- {MARK} -->",
            "<!DOCTYPE html>",
            '<html lang="en"><head><meta charset="utf-8">'
            "<title>VONA list, page 1 (synthetic demo data)</title></head>",
            "<body>",
            *cards,
            "</body></html>",
            "",
        ]
    ).encode()


def vona_records(store: Store) -> list[ReplayRecord]:
    times = snapshot_times(spec.issued + timedelta(minutes=1) for spec in VONAS)
    return [
        store.put(
            FeedId.VONA,
            VONA_LIST_URL,
            when,
            vona_page([spec for spec in VONAS if spec.issued + timedelta(minutes=1) <= when]),
            HTML_TYPE,
        )
        for when in times
    ]


# --- VAAs (Darwin bulletins and Tokyo text pages) -------------------------------------------


@dataclass(frozen=True)
class Layer:
    base_ft: int
    top_ft: int
    area: Ring
    move: str = ""

    def text(self) -> str:
        base = "SFC" if self.base_ft == 0 else f"FL{self.base_ft // 100:03d}"
        tail = f" {self.move}" if self.move else ""
        return f"{base}/FL{self.top_ft // 100:03d} {ring_text(self.area[:-1])}{tail}"


@dataclass(frozen=True)
class VaaSpec:
    centre: str
    heading: str
    issued: datetime
    volcano: Vent
    volcano_text: str
    area_name: str
    elev_text: str
    number: str
    info_source: str
    colour: str
    details: str
    obs_at: datetime
    obs: Sequence[Layer] | str
    forecasts: Sequence[tuple[int, Sequence[Layer] | str]]
    remarks: str
    next_text: str

    def lines(self) -> list[str]:
        obs = (
            self.obs if isinstance(self.obs, str) else " ".join(layer.text() for layer in self.obs)
        )
        fields = [
            ("DTG", f"{self.issued:%Y%m%d/%H%M}Z"),
            ("VAAC", self.centre),
            ("VOLCANO", f"{self.volcano_text} {self.volcano.id}"),
            ("PSN", dm(self.volcano.lat, self.volcano.lon)),
            ("AREA", self.area_name),
            ("SUMMIT ELEV" if self.centre == "TOKYO" else "SOURCE ELEV", self.elev_text),
            ("ADVISORY NR", self.number),
            ("INFO SOURCE", self.info_source),
            ("AVIATION COLOUR CODE", self.colour),
            ("ERUPTION DETAILS", self.details),
            ("OBS VA DTG", f"{self.obs_at:%d/%H%M}Z"),
            ("OBS VA CLD", obs),
        ]
        for hours, step in self.forecasts:
            when = self.obs_at + timedelta(hours=hours)
            body = step if isinstance(step, str) else " ".join(layer.text() for layer in step)
            fields.append((f"FCST VA CLD +{hours} HR", f"{when:%d/%H%M}Z {body}"))
        fields += [("RMK", self.remarks), ("NXT ADVISORY", f"{self.next_text}=")]
        lines = [f"{self.heading} {ddhhmm(self.issued)}", "VA ADVISORY"]
        for key, value in fields:
            lines += wrap(f"{key}: {value}", 66, " " * 8)
        return lines


def fc(hours: int, top_ft: int, *points: tuple[float, float]) -> tuple[int, list[Layer]]:
    """A forecast step with one SFC-based layer."""
    return hours, [Layer(0, top_ft, ring(*points))]


def agung_layers(top_ft: int, low: Ring, high: Ring, high_move: str) -> list[Layer]:
    return [Layer(0, 25000, low, "MOV W 15KT"), Layer(25000, top_ft, high, high_move)]


AGUNG_12: Final = VaaSpec(
    "DARWIN",
    "FVAU03 ADRM",
    at(14, "0635"),
    AGUNG,
    "AGUNG",
    "INDONESIA",
    "2997M AMSL",
    "2026/12",
    "HIMAWARI-9, CVGHM",
    "RED",
    "ERUPTION AT 14/0542Z. VA TO FL350 OBS ON SATELLITE IMAGERY",
    at(14, "0610"),
    agung_layers(
        35000,
        ring((-8.28, 115.55), (-8.22, 114.75), (-8.70, 114.85), (-8.85, 115.40)),
        ring((-8.27, 115.52), (-8.15, 114.70), (-8.60, 114.35), (-9.10, 114.90), (-8.45, 115.58)),
        "MOV SW 25KT",
    ),
    [
        fc(
            6,
            35000,
            (-8.20, 115.60),
            (-8.00, 114.30),
            (-8.70, 113.90),
            (-9.35, 114.70),
            (-8.60, 115.70),
        ),
        fc(
            12,
            35000,
            (-8.15, 115.60),
            (-7.90, 114.10),
            (-8.70, 113.60),
            (-9.50, 114.50),
            (-8.70, 115.75),
        ),
        fc(
            18,
            30000,
            (-8.15, 115.60),
            (-7.85, 113.90),
            (-8.75, 113.40),
            (-9.55, 114.40),
            (-8.75, 115.75),
        ),
    ],
    "VA EXTD W AND SW ON SATELLITE IMAGERY. HEIGHT BASED ON SATELLITE IMAGERY, GROUND REPORTS "
    "AND MODEL GUIDANCE. AIRPORT WADD AFFECTED.",
    "WILL BE ISSUED BY 20261014/0835Z",
)

AGUNG_13: Final = VaaSpec(
    "DARWIN",
    "FVAU04 ADRM",
    at(14, "0748"),
    AGUNG,
    "AGUNG",
    "INDONESIA",
    "2997M AMSL",
    "2026/13",
    "HIMAWARI-9, CVGHM, PIREP",
    "RED",
    "ERUPTION AT 14/0652Z. VA TO FL380 OBS ON SATELLITE IMAGERY",
    at(14, "0730"),
    agung_layers(
        38000,
        ring((-8.27, 115.56), (-8.18, 114.62), (-8.72, 114.72), (-8.88, 115.42)),
        ring((-8.25, 115.55), (-8.08, 114.55), (-8.62, 114.10), (-9.25, 114.80), (-8.50, 115.62)),
        "MOV SW 30KT",
    ),
    [
        fc(
            6,
            38000,
            (-8.18, 115.62),
            (-7.95, 114.15),
            (-8.75, 113.70),
            (-9.45, 114.60),
            (-8.62, 115.75),
        ),
        fc(
            12,
            35000,
            (-8.15, 115.62),
            (-7.88, 113.95),
            (-8.75, 113.45),
            (-9.55, 114.45),
            (-8.72, 115.78),
        ),
        fc(
            18,
            30000,
            (-8.15, 115.62),
            (-7.85, 113.80),
            (-8.80, 113.30),
            (-9.60, 114.35),
            (-8.78, 115.78),
        ),
    ],
    "NEW ERUPTION AT 0652Z. VA EXTD W AND SW ON SATELLITE IMAGERY. PILOT REPORT OF VA AT "
    "FL370. AIRPORT WADD AFFECTED.",
    "WILL BE ISSUED BY 20261014/1300Z",
)

SEMERU_1201: Final = VaaSpec(
    "DARWIN",
    "FVAU02 ADRM",
    at(14, "0445"),
    SEMERU,
    "SEMERU",
    "INDONESIA",
    "3657M AMSL",
    "2026/1201",
    "HIMAWARI-9, CVGHM",
    "ORANGE",
    "VA TO FL140 OBS AT 14/0400Z EXTD NE",
    at(14, "0400"),
    [Layer(0, 14000, SEMERU_AREA, "MOV NE 10KT")],
    [
        fc(6, 14000, (-8.08, 112.90), (-7.80, 113.25), (-7.92, 113.45), (-8.15, 113.00)),
        fc(12, 14000, (-8.08, 112.90), (-7.78, 113.25), (-7.92, 113.50), (-8.15, 113.00)),
        (18, "NO VA EXP"),
    ],
    "VA OBS ON SATELLITE EXTD NE. HEIGHT AND MOVEMENT BASED ON SATELLITE IMAGERY, GROUND REPORTS "
    "AND MODEL GUIDANCE.",
    "WILL BE ISSUED BY 20261014/1045Z",
)

DUKONO_871: Final = VaaSpec(
    "DARWIN",
    "FVAU01 ADRM",
    at(14, "0355"),
    DUKONO,
    "DUKONO",
    "INDONESIA",
    "1229M AMSL",
    "2026/871",
    "HIMAWARI-9, CVGHM",
    "ORANGE",
    "VA TO FL070 OBS AT 14/0330Z EXTD NE",
    at(14, "0330"),
    [Layer(0, 7000, DUKONO_AREA, "MOV NE 10KT")],
    [
        fc(6, 7000, (1.65, 127.80), (2.57, 127.87), (2.53, 128.30), (2.20, 128.67), (1.60, 127.95)),
        fc(
            12, 7000, (1.62, 127.80), (2.53, 127.53), (2.63, 127.92), (2.52, 128.30), (1.62, 128.00)
        ),
        fc(
            18, 7000, (1.62, 127.80), (2.53, 127.53), (2.63, 127.92), (2.52, 128.30), (1.62, 128.00)
        ),
    ],
    "CONTINUOUS VA OBS ON SATELLITE EXTD NE. HEIGHT AND MOVEMENT BASED ON SATELLITE IMAGERY, "
    "GROUND REPORTS AND MODEL GUIDANCE.",
    "NO LATER THAN 20261014/0955Z",
)

DARWIN_CURRENT: Final = [AGUNG_12, AGUNG_13, SEMERU_1201, DUKONO_871]
OLD_DARWIN: Final = [
    VaaSpec(
        "DARWIN", f"FVAU{slot:02d} ADRM", issued, vent, vent.name, "INDONESIA", elev, number,
        "HIMAWARI-9, CVGHM", "ORANGE", "VA TO FL070 OBS", issued - timedelta(minutes=20),
        "VA NOT IDENTIFIABLE FM SATELLITE DATA",
        [(6, "NO VA EXP"), (12, "NO VA EXP"), (18, "NO VA EXP")],
        "VA NOT IDENTIFIABLE ON SATELLITE IMAGERY IN CLEAR CONDITIONS.",
        "NO FURTHER ADVISORIES",
    )
    for slot, issued, vent, elev, number in [
        (3, at(12, "2030"), LEWOTOLOK, "1431M AMSL", "2026/311"),
        (4, at(12, "2340"), IBU, "1325M AMSL", "2026/1140"),
        (5, at(13, "0115"), SEMERU, "3657M AMSL", "2026/1196"),
        (6, at(13, "0240"), DUKONO, "1229M AMSL", "2026/866"),
        (7, at(12, "1810"), LEWOTOLOK, "1431M AMSL", "2026/310"),
        (8, at(12, "1505"), IBU, "1325M AMSL", "2026/1139"),
        (9, at(12, "1140"), SEMERU, "3657M AMSL", "2026/1193"),
        (10, at(12, "0925"), DUKONO, "1229M AMSL", "2026/864"),
        (1, at(12, "0610"), SEMERU, "3657M AMSL", "2026/1192"),
        (2, at(12, "0330"), DUKONO, "1229M AMSL", "2026/863"),
    ]
]  # fmt: skip
"""What each tgftp slot held before the window: advisories more than a day old, which the
poller reads and leaves out (it keeps a day of advisories)."""


def darwin_text(spec: VaaSpec) -> bytes:
    """A tgftp slot file: a sequence line, the bulletin, and a line saying what it is (the
    parser starts at the WMO heading and stops at ``NXT ADVISORY``, so neither reaches it)."""
    serial = int(hashlib.sha256(spec.number.encode()).hexdigest()[:3], 16) % 1000
    return "\n".join([f"{serial:03d}", *spec.lines(), "", MARK, ""]).encode()


def darwin_records(store: Store) -> list[ReplayRecord]:
    records: list[ReplayRecord] = []
    for slot, url in enumerate(DARWIN_BULLETIN_URLS, start=1):
        heading = f"FVAU{slot:02d} ADRM"
        held = [spec for spec in [*OLD_DARWIN, *DARWIN_CURRENT] if spec.heading == heading]
        before = max(
            (s for s in held if s.issued + timedelta(minutes=2) <= START), key=lambda s: s.issued
        )
        records.append(store.put(FeedId.VAAC_DARWIN, url, START, darwin_text(before), TEXT_TYPE))
        for spec in held:
            if spec.issued + timedelta(minutes=2) > START:
                when = spec.issued + timedelta(minutes=2)
                records.append(
                    store.put(FeedId.VAAC_DARWIN, url, when, darwin_text(spec), TEXT_TYPE)
                )
    backup = "\n".join(
        [
            f"<!-- {MARK} -->",
            "<!DOCTYPE HTML>",
            '<html lang="en"><head><meta charset="UTF-8">'
            "<title>Darwin VAAC backup list (synthetic demo data)</title></head><body>",
            '<table><tr class="mtx"><th>Date Time</th><th>Volcano</th><th>Area</th>'
            "<th>Advisory Number</th><th>Text</th></tr></table>",
            "</body></html>",
            "",
        ]
    ).encode()
    records.append(store.put(FeedId.VAAC_DARWIN, DARWIN_BACKUP_LIST_URL, START, backup, HTML_TYPE))
    return records


SAKURA_TOKYO: Final = [
    VaaSpec(
        "TOKYO", "FVFE01 RJTD", at(14, "0525"), SAKURAJIMA, "SAKURAJIMA (AIRA CALDERA)", "JAPAN",
        "1117M", "2026/791", "HIMAWARI-9 JMA", "NIL", "ERUPTED AT 20261014/0510Z FL080 REPORTED",
        at(14, "0510"), [Layer(0, 8000, SAKURA_Y01_AREA, "MOV E 10KT")],
        [(6, "NO VA EXP"), (12, "NO VA EXP"), (18, "NO VA EXP")], "NIL",
        "WILL BE ISSUED BY 20261014/1125Z",
    ),
    VaaSpec(
        "TOKYO", "FVFE01 RJTD", at(14, "0630"), SAKURAJIMA, "SAKURAJIMA (AIRA CALDERA)", "JAPAN",
        "1117M", "2026/792", "HIMAWARI-9 JMA", "NIL", "ERUPTED AT 20261014/0510Z FL080 REPORTED",
        at(14, "0620"), "VA DISSIPATED",
        [(6, "NO VA EXP"), (12, "NO VA EXP"), (18, "NO VA EXP")], "VA CLD HAS DISSIPATED.",
        "NO FURTHER ADVISORIES",
    ),
]  # fmt: skip
OLD_TOKYO: Final = [
    ("SUWANOSEJIMA", "JAPAN", at(12, "2315"), "2026/402", "28209000"),
    ("KANLAON", "PHILIPPINES", at(12, "1957"), "2026/261", "27202000"),
    ("SAKURAJIMA", "JAPAN", at(12, "0841"), "2026/790", "28208000"),
]
"""Older list rows (more than a day before the window), which the poller skips."""


def tokyo_url(issued: datetime, number_code: str, advisory_nr: str) -> str:
    seq = int(advisory_nr.split("/")[1])
    return (
        "https://ds.data.jma.go.jp/svd/vaac/data/TextData/"
        f"{issued:%Y}/{issued:%Y%m%d}_{number_code}_{seq:04d}_Text.html"
    )


def tokyo_page(spec: VaaSpec) -> bytes:
    text = "<BR>".join(spec.lines())
    return "\n".join(
        [
            f"<!-- {MARK} -->",
            "<!DOCTYPE HTML>",
            '<html lang="en">',
            "<head>",
            "\t<title>Tokyo VAAC | Volcanic Ash Advisory Text (synthetic demo data)</title>",
            '\t<meta charset="UTF-8">',
            "</head>",
            "<body>",
            '\t<div class="mtx">',
            f"\t\t<!-- VAA Text Start -->{text}<BR><!-- VAA Text End -->",
            "\t</div>",
            "</body>",
            "</html>",
            "",
        ]
    ).encode()


def tokyo_row(issued: datetime, volcano: str, area: str, number: str, href: str) -> str:
    return (
        f'<tr class="mtx"><td style="DISPLAY: none">{issued:%Y/%m/%d %H:%M:%S}</td>'
        f"<td>{issued:%H:%M} UTC, {issued:%d %b}. {issued:%Y}</td><td>{volcano}</td>"
        f'<td>{area}</td><td>{number}</td><td><a href="{href}">Text</a></td></tr>'
    )


def tokyo_records(store: Store) -> list[ReplayRecord]:
    records: list[ReplayRecord] = []
    rows = [
        (
            spec.issued,
            "SAKURAJIMA",
            "JAPAN",
            spec.number,
            tokyo_url(spec.issued, "28208000", spec.number),
        )
        for spec in SAKURA_TOKYO
    ]
    rows += [
        (issued, name, area, number, tokyo_url(issued, code, number))
        for name, area, issued, number, code in OLD_TOKYO
    ]
    times = snapshot_times(spec.issued + timedelta(minutes=2) for spec in SAKURA_TOKYO)
    for when in times:
        listed = sorted(
            (row for row in rows if row[0] + timedelta(minutes=2) <= when),
            key=lambda row: row[0],
            reverse=True,
        )
        page = "\n".join(
            [
                f"<!-- {MARK} -->",
                "<!DOCTYPE HTML>",
                '<html lang="en"><head><meta charset="UTF-8">'
                "<title>Tokyo VAAC | VAA list (synthetic demo data)</title></head><body>",
                "<table>",
                '<tr class="mtx"><th>Date Time</th><th>Volcano</th><th>Area</th>'
                "<th>Advisory Number</th><th>Text</th></tr>",
                *(tokyo_row(*row[:4], row[4].rsplit("data/", 1)[1]) for row in listed),
                "</table></body></html>",
                "",
            ]
        ).encode()
        records.append(store.put(FeedId.VAAC_TOKYO, TOKYO_LIST_URL, when, page, HTML_TYPE))
    for spec in SAKURA_TOKYO:
        url = tokyo_url(spec.issued, "28208000", spec.number)
        when = max(START, spec.issued + timedelta(minutes=2))
        records.append(store.put(FeedId.VAAC_TOKYO, url, when, tokyo_page(spec), HTML_TYPE))
    return records


# --- JMA eruption reports (Atom feed and VFVO52 documents) ------------------------------------


@dataclass(frozen=True)
class JmaEruption:
    reported: datetime
    erupted: datetime
    above_crater_m: int
    above_sea_ft: int
    direction: str
    amount: str

    @property
    def url(self) -> str:
        return (
            "https://www.data.jma.go.jp/developer/xml/data/"
            f"{self.reported:%Y%m%d%H%M%S}_0_VFVO52_400000.xml"
        )


JST: Final = timedelta(hours=9)
JMA_ERUPTIONS: Final = [
    JmaEruption(at(14, "0516"), at(14, "0510"), 1600, 8000, "東", "中量"),
    JmaEruption(at(14, "0658"), at(14, "0652"), 2300, 11000, "南", "多量"),
]


def jst(when: datetime) -> str:
    return (when + JST).strftime("%Y-%m-%dT%H:%M:%S+09:00")


def jma_report(event: JmaEruption) -> bytes:
    """A VFVO52 document in the layout of JMA's (``tests/fixtures/jma``), indented."""
    local = event.erupted + JST
    utc = event.erupted.strftime("%d%H%M")
    headline = f"火　　山：桜島\n日　　時：{local:%Y年%m月%d日%H時%M分}({utc}UTC)\n現　　象：噴火"
    kind = "<Kind><Name>噴火</Name><Code>52</Code></Kind>"
    area = '<Areas codeType="火山名"><Area><Name>桜島</Name><Code>506</Code>'
    title = "噴火に関する火山観測報"
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f"<!-- {MARK} -->",
        '<Report xmlns="http://xml.kishou.go.jp/jmaxml1/"'
        ' xmlns:jmx="http://xml.kishou.go.jp/jmaxml1/">',
        "  <Control>",
        f"    <Title>{title}</Title>",
        f"    <DateTime>{iso(event.reported).replace('.000', '')}</DateTime>",
        "    <Status>通常</Status>",
        "    <EditorialOffice>福岡管区気象台</EditorialOffice>",
        "    <PublishingOffice>福岡管区気象台　鹿児島地方気象台</PublishingOffice>",
        "  </Control>",
        '  <Head xmlns="http://xml.kishou.go.jp/jmaxml1/informationBasis1/">',
        f"    <Title>火山名　桜島　{title}</Title>",
        f"    <ReportDateTime>{jst(event.reported)}</ReportDateTime>",
        f"    <TargetDateTime>{jst(event.erupted)}</TargetDateTime>",
        f"    <EventID>{event.reported + JST:%Y%m%d%H%M%S}_506</EventID>",
        "    <InfoType>発表</InfoType>",
        "    <Serial>1</Serial>",
        f"    <InfoKind>{title}</InfoKind>",
        "    <InfoKindVersion>1.0_0</InfoKindVersion>",
        "    <Headline>",
        f"      <Text>{headline}</Text>",
        f'      <Information type="{title}"><Item>{kind}{area}</Area></Areas></Item></Information>',
        "    </Headline>",
        "  </Head>",
        '  <Body xmlns="http://xml.kishou.go.jp/jmaxml1/body/volcanology1/"'
        ' xmlns:jmx_eb="http://xml.kishou.go.jp/jmaxml1/elementBasis1/">',
        f'    <VolcanoInfo type="{title}">',
        "      <Item>",
        "        <EventTime>",
        f'          <EventDateTime significant="yyyy-mm-ddThh:mm">{jst(event.erupted)}'
        "</EventDateTime>",
        '          <EventDateTimeUTC significant="yyyy-mm-ddThh:mm">'
        f"{iso(event.erupted).replace('.000', '')}</EventDateTimeUTC>",
        "        </EventTime>",
        f"        {kind}",
        f"        {area}<CraterName>南岳山頂火口</CraterName></Area></Areas>",
        "      </Item>",
        "    </VolcanoInfo>",
        "    <VolcanoObservation>",
        "      <ColorPlume>",
        '        <jmx_eb:PlumeHeightAboveCrater type="火口上噴煙高度" unit="m"'
        f' description="火口上{event.above_crater_m}m">{event.above_crater_m}'
        "</jmx_eb:PlumeHeightAboveCrater>",
        '        <jmx_eb:PlumeHeightAboveSeaLevel type="海抜噴煙高度" unit="FT"'
        f' description="海抜{event.above_sea_ft}FT">{event.above_sea_ft}'
        "</jmx_eb:PlumeHeightAboveSeaLevel>",
        '        <jmx_eb:PlumeDirection type="噴煙の流向" unit="漢字"'
        f' description="{event.direction}">{event.direction}</jmx_eb:PlumeDirection>',
        "      </ColorPlume>",
        f"      <OtherObservation>火口：南岳山頂火口\n噴煙量：{event.amount}</OtherObservation>",
        "    </VolcanoObservation>",
        "  </Body>",
        "</Report>",
        "",
    ]
    return "\n".join(lines).encode()


def jma_feed(listed: Sequence[JmaEruption], when: datetime) -> bytes:
    entries = [
        f"""  <entry>
    <title>噴火に関する火山観測報</title>
    <id>{event.url}</id>
    <updated>{iso(event.reported).replace(".000", "")}</updated>
    <author>
      <name>鹿児島地方気象台</name>
    </author>
    <link type="application/xml" href="{event.url}"/>
    <content type="text">【火山名　桜島　噴火に関する火山観測報】桜島で噴火。</content>
  </entry>"""
        for event in sorted(listed, key=lambda e: e.reported, reverse=True)
    ]
    return f"""<?xml version="1.0" encoding="utf-8"?>
<!-- {MARK} -->
<feed xmlns="http://www.w3.org/2005/Atom" lang="ja">
  <title>高頻度（地震火山）</title>
  <subtitle>JMAXML publishing feed (synthetic demo data)</subtitle>
  <updated>{jst(when)}</updated>
  <id>{JMA_EQVOL_URL}#short_{epoch(when)}</id>
  <link rel="self" href="{JMA_EQVOL_URL}"/>
{chr(10).join(entries)}
</feed>
""".encode()


def jma_records(store: Store) -> list[ReplayRecord]:
    times = snapshot_times(e.reported + timedelta(minutes=1) for e in JMA_ERUPTIONS)
    records = [
        store.put(
            FeedId.JMA_VOLCANO,
            JMA_EQVOL_URL,
            when,
            jma_feed([e for e in JMA_ERUPTIONS if e.reported + timedelta(minutes=1) <= when], when),
            XML_TYPE,
        )
        for when in times
    ]
    records += [
        store.put(
            FeedId.JMA_VOLCANO, event.url, max(START, event.reported), jma_report(event), XML_TYPE
        )
        for event in JMA_ERUPTIONS
    ]
    return records


# --- METARs and TAFs (AWC JSON) ------------------------------------------------------------------

Group = dict[str, Any]
"""One TAF group: change, prob, start, end, wind (deg, kt), vis_m, wx, clouds."""


@cache
def airport_catalogue() -> Any:
    return load_airports(DATA_DIR, min_runway_m=0)


def _vis_sm(vis_m: int) -> str | float:
    return "6+" if vis_m >= 9999 else round(vis_m / 1609.344, 2)


def _clouds_json(clouds: str) -> list[dict[str, Any]]:
    layers = []
    for token in clouds.split():
        if token in ("NSC", "CAVOK"):
            continue
        cover, base = token[:3], token[3:6]
        layers.append({"cover": cover, "base": int(base) * 100})
    return layers


def _flight_category(vis_m: int, clouds: str) -> str:
    ceilings = [layer["base"] for layer in _clouds_json(clouds) if layer["cover"] in ("BKN", "OVC")]
    ceiling = min(ceilings, default=99999)
    if vis_m < 1600 or ceiling < 500:
        return "LIFR"
    if vis_m < 4800 or ceiling < 1000:
        return "IFR"
    if vis_m <= 8000 or ceiling <= 3000:
        return "MVFR"
    return "VFR"


@dataclass(frozen=True)
class Weather:
    wind: tuple[int, int]
    vis_m: int
    wx: str
    clouds: str
    temp: int
    dew: int
    qnh: int


def _station_rng(icao: str) -> random.Random:
    return random.Random(f"{SEED}:{icao}")


def station_weather(icao: str, when: datetime) -> Weather:
    """The weather a station reports at ``when``: Bali's airport under the ash, the rest a
    tropical or autumn afternoon with a few showers."""
    airport = airport_catalogue().get(icao)
    lat = airport.lat if airport is not None else -7.0
    rng = _station_rng(icao)
    if icao == "WADD":
        steps = {
            "0600": Weather((100, 8), 9999, "", "FEW018 SCT100", 31, 24, 1009),
            "0630": Weather((60, 6), 6000, "VA", "FEW018 BKN100", 30, 24, 1009),
            "0700": Weather((50, 7), 4000, "VA", "FEW018 BKN090", 29, 24, 1009),
            "0730": Weather((40, 8), 3000, "VA", "SCT018 BKN080", 29, 24, 1010),
            "0800": Weather((40, 8), 2500, "VA", "SCT018 BKN080", 28, 24, 1010),
        }
        key = max(k for k in steps if at(14, k) <= max(when, at(14, "0600")))
        return steps[key]
    if lat > 20:
        wind = (rng.choice([300, 310, 320, 330, 340]), rng.randint(6, 14))
        return Weather(
            wind, 9999, "", rng.choice(["FEW030", "FEW025 SCT060", "SCT030"]), 22, 13, 1016
        )
    wind = (rng.choice([90, 100, 110, 120, 130]), rng.randint(5, 12))
    wx = ""
    clouds = rng.choice(["FEW020", "FEW018 SCT100", "SCT020", "FEW020CB SCT100"])
    vis = 9999
    if icao in ("WIII", "WIHH") and when >= at(14, "0700"):
        wx, clouds, vis = "VCTS", "FEW018CB BKN100", 8000
    elif icao == "WARR":
        wx, vis = "-RA", 8000
    return Weather(
        wind, vis, wx, clouds, rng.randint(29, 33), rng.randint(22, 25), rng.randint(1008, 1011)
    )


def metar_record(icao: str, observed: datetime) -> dict[str, Any]:
    weather = station_weather(icao, observed)
    airport = airport_catalogue().get(icao)
    vis = "9999" if weather.vis_m >= 9999 else f"{weather.vis_m:04d}"
    tokens = [
        icao,
        f"{ddhhmm(observed)}Z",
        f"{weather.wind[0]:03d}{weather.wind[1]:02d}KT",
        vis,
        *([weather.wx] if weather.wx else []),
        weather.clouds,
        f"{weather.temp:02d}/{weather.dew:02d}",
        f"Q{weather.qnh}",
        *([] if weather.wx == "VA" else ["NOSIG"]),
    ]
    return {
        "icaoId": icao,
        "receiptTime": iso(observed + timedelta(minutes=3)),
        "obsTime": epoch(observed),
        "reportTime": iso(observed),
        "temp": weather.temp,
        "dewp": weather.dew,
        "wdir": weather.wind[0],
        "wspd": weather.wind[1],
        "visib": _vis_sm(weather.vis_m),
        "altim": weather.qnh,
        "metarType": "METAR",
        "rawOb": "METAR " + " ".join(tokens),
        "lat": airport.lat if airport else None,
        "lon": airport.lon if airport else None,
        "name": airport.name if airport else icao,
        "wxString": weather.wx or None,
        "clouds": _clouds_json(weather.clouds),
        "fltCat": _flight_category(weather.vis_m, weather.clouds),
    }


def taf_groups(icao: str, as_of: datetime) -> tuple[datetime, bool, list[Group]]:
    """``(issued, amended, groups)`` of the TAF in force at ``as_of``."""
    weather = station_weather(icao, at(14, "0600"))
    base: Group = {
        "change": None,
        "prob": None,
        "start": at(14, "0600"),
        "end": at(15, "1200"),
        "wind": weather.wind,
        "vis_m": 9999,
        "wx": "",
        "clouds": weather.clouds.replace("CB", ""),
    }
    issued, amended = at(14, "0500"), False
    groups = [base]
    lat = (airport_catalogue().get(icao) or airport_catalogue().get("WIII")).lat
    if lat < 20:
        groups.append(
            {
                **base,
                "change": "TEMPO",
                "start": at(14, "0900"),
                "end": at(14, "1300"),
                "wind": None,
                "vis_m": 4000,
                "wx": "TSRA",
                "clouds": "FEW018CB BKN090",
            }
        )
    if icao == "WADD" and as_of >= at(14, "0640"):
        issued, amended = at(14, "0640"), True
        groups = [
            {**base, "start": at(14, "0700"), "wind": (50, 8), "vis_m": 4000, "wx": "VA",
             "clouds": "FEW018 BKN090"},
            {**base, "change": "BECMG", "start": at(14, "1200"), "end": at(14, "1400"),
             "wind": None, "vis_m": 6000, "wx": "VA", "clouds": ""},
            {**base, "change": "TEMPO", "start": at(14, "1400"), "end": at(14, "1800"),
             "wind": None, "vis_m": 3000, "wx": "VA", "clouds": ""},
        ]  # fmt: skip
    if icao == "WADL" and as_of >= at(14, "0650"):
        issued, amended = at(14, "0650"), True
        groups = [
            {**base, "start": at(14, "0700")},
            {**base, "change": "TEMPO", "prob": 30, "start": at(14, "1000"), "end": at(14, "1800"),
             "wind": None, "vis_m": 5000, "wx": "VA", "clouds": ""},
        ]  # fmt: skip
    return issued, amended, groups


def _group_text(group: Group) -> str:
    def stamp(when: datetime) -> str:
        return f"{when:%d%H}"

    tokens: list[str] = []
    if group["prob"]:
        tokens.append(f"PROB{group['prob']}")
    if group["change"]:
        tokens.append(group["change"])
    if group["change"] or group["prob"]:
        tokens.append(f"{stamp(group['start'])}/{stamp(group['end'])}")
    if group["wind"]:
        tokens.append(f"{group['wind'][0]:03d}{group['wind'][1]:02d}KT")
    tokens.append("9999" if group["vis_m"] >= 9999 else f"{group['vis_m']:04d}")
    if group["wx"]:
        tokens.append(group["wx"])
    if group["clouds"]:
        tokens.append(group["clouds"])
    return " ".join(tokens)


def taf_record(icao: str, as_of: datetime) -> dict[str, Any]:
    issued, amended, groups = taf_groups(icao, as_of)
    valid_from, valid_to = groups[0]["start"], at(15, "1200")
    head = ["TAF", *(["AMD"] if amended else []), icao, f"{ddhhmm(issued)}Z",
            f"{valid_from:%d%H}/{valid_to:%d%H}"]  # fmt: skip
    raw = " ".join(head) + " " + " ".join(_group_text(group) for group in groups)
    airport = airport_catalogue().get(icao)
    fcsts = []
    for index, group in enumerate(groups):
        start = group["start"]
        end = group["end"] if group["change"] not in (None, "BECMG") else valid_to
        if group["change"] is None and index + 1 < len(groups):
            later = [g["start"] for g in groups[index + 1 :] if g["change"] == "BECMG"]
            end = min(later, default=end)
        fcsts.append(
            {
                "timeFrom": epoch(start),
                "timeTo": epoch(end),
                "timeBec": epoch(group["end"]) if group["change"] == "BECMG" else None,
                "fcstChange": group["change"],
                "probability": group["prob"],
                "wdir": group["wind"][0] if group["wind"] else None,
                "wspd": group["wind"][1] if group["wind"] else None,
                "visib": _vis_sm(group["vis_m"]),
                "wxString": group["wx"] or None,
                "clouds": _clouds_json(group["clouds"]),
            }
        )
    return {
        "icaoId": icao,
        "issueTime": iso(issued),
        "validTimeFrom": epoch(valid_from),
        "validTimeTo": epoch(valid_to),
        "rawTAF": raw,
        "lat": airport.lat if airport else None,
        "lon": airport.lon if airport else None,
        "name": airport.name if airport else icao,
        "fcsts": fcsts,
    }


def station_ids(url: str) -> list[str]:
    query = dict(parse_qsl(urlsplit(url).query))
    return [icao for icao in query.get("ids", "").split(",") if icao]


def metar_fill(store: Store, url: str) -> list[ReplayRecord]:
    records = []
    when = START
    while when <= END:
        observed = timeutil.floor_minutes(when, 30)
        body = json_bytes([metar_record(icao, observed) for icao in station_ids(url)])
        records.append(store.put(FeedId.METAR, url, when, body, JSON_TYPE))
        when = timeutil.floor_minutes(when, 30) + timedelta(minutes=30)
    return records


def taf_fill(store: Store, url: str) -> list[ReplayRecord]:
    changes = [START, at(14, "0641"), at(14, "0651")]
    return [
        store.put(
            FeedId.TAF,
            url,
            when,
            json_bytes([taf_record(i, when) for i in station_ids(url)]),
            JSON_TYPE,
        )
        for when in changes
    ]


# --- winds (Open-Meteo pressure levels) --------------------------------------------------------

WIND_PROFILES: Final[dict[str, dict[int, tuple[int, int]]]] = {
    # hPa -> (from_deg, kt): easterly trades below, north-easterlies aloft over Bali and Java
    "south": {850: (110, 12), 700: (100, 15), 600: (90, 16), 500: (80, 18), 400: (60, 22),
              300: (45, 27), 250: (40, 30), 200: (30, 28), 150: (20, 24)},
    # a north-easterly surge low over Kyushu, the westerly jet aloft
    "kyushu": {850: (20, 18), 700: (10, 16), 600: (330, 22), 500: (285, 38), 400: (280, 52),
               300: (275, 66), 250: (270, 74), 200: (270, 70), 150: (265, 58)},
    # south-westerlies over Halmahera
    "north": {850: (220, 8), 700: (215, 10), 600: (210, 11), 500: (210, 12), 400: (200, 14),
              300: (190, 16), 250: (180, 18), 200: (170, 20), 150: (160, 18)},
}  # fmt: skip


def winds_body(lat: float, lon: float, when: datetime) -> bytes:
    profile = WIND_PROFILES[regime(lat)]
    first = timeutil.floor_minutes(when, 60) - timedelta(hours=1)
    hours = [first + timedelta(hours=index) for index in range(25)]
    hourly: dict[str, list[Any]] = {"time": [h.strftime("%Y-%m-%dT%H:%M") for h in hours]}
    rng = random.Random(f"{SEED}:winds:{lat:.2f}:{lon:.2f}")
    phases = {hpa: rng.uniform(0, 2 * math.pi) for hpa in PRESSURE_LEVELS_HPA}
    for hpa in PRESSURE_LEVELS_HPA:
        direction, speed = profile[hpa]
        index_hours = [(h - at(14, "0000")).total_seconds() / 3600 for h in hours]
        hourly[f"wind_speed_{hpa}hPa"] = [
            round(speed + 3 * math.sin(phases[hpa] + t / 5), 1) for t in index_hours
        ]
        hourly[f"wind_direction_{hpa}hPa"] = [
            round((direction + 8 * math.sin(phases[hpa] + t / 7)) % 360) for t in index_hours
        ]
    units = {"time": "iso8601"}
    for hpa in PRESSURE_LEVELS_HPA:
        units[f"wind_speed_{hpa}hPa"] = "kn"
        units[f"wind_direction_{hpa}hPa"] = "°"
    payload = {
        "latitude": lat,
        "longitude": lon,
        "generationtime_ms": 0.0,
        "utc_offset_seconds": 0,
        "timezone": "GMT",
        "timezone_abbreviation": "GMT",
        "elevation": 0.0,
        "hourly_units": units,
        "hourly": hourly,
    }
    return json_bytes(payload)


def winds_fill(store: Store, url: str) -> list[ReplayRecord]:
    query = dict(parse_qsl(urlsplit(url).query))
    lat, lon = float(query["latitude"]), float(query["longitude"])
    times = [START, *(h for h in (at(14, "0700"), at(14, "0800")) if START < h <= END)]
    return [
        store.put(FeedId.WINDS, url, when, winds_body(lat, lon, when), JSON_TYPE) for when in times
    ]


# --- aircraft ---------------------------------------------------------------------------------

FLEETS: Final[dict[str, Sequence[str]]] = {
    # the types each airline flies on these routes (public fleet lists, rounded to the main ones)
    "GIA": ("B738", "B738", "B738", "A333"), "CTV": ("A320", "A320", "AT76"),
    "BTK": ("A320", "B739"), "LNI": ("B739", "B738"), "AWQ": ("A320",),
    "AXM": ("A320", "A20N"), "SJV": ("A320",),
    "SJY": ("B738",), "WON": ("AT72", "AT76"), "TNU": ("A320",), "PAS": ("A320",),
    "IDX": ("A320",), "SIA": ("A359", "B78X", "B38M"), "TGW": ("A20N", "A21N", "B788"),
    "MAS": ("B738", "A333"), "MXD": ("B738",), "QFA": ("A332", "B738"), "JST": ("A320", "A321"),
    "VOZ": ("B738",), "AIQ": ("A320",), "JAL": ("B738", "B763", "A359"), "ANA": ("B788", "B738"),
    "SKY": ("B738",), "APJ": ("A320",), "JJP": ("A320",), "SNJ": ("B738",), "JTA": ("B738",),
    "CPA": ("A333", "A359"), "CAL": ("A333", "B738"), "EVA": ("A321", "B78X"),
    "KAL": ("B77W", "A333"), "TTW": ("A320",), "CEB": ("A320", "A21N"), "PAL": ("A321",),
    "VJC": ("A321",), "HVN": ("A321",), "CES": ("A320",), "CSN": ("A321",), "CSH": ("B738",),
    "THA": ("B788",),
}  # fmt: skip
JAC_TYPES: Final = ("AT76", "AT46")
"""JAL flight numbers 3000-3999 are Japan Air Commuter's turboprop services out of Kagoshima."""

Step = tuple[int, int, int]
"""One climb or descent segment: (up to or down to ft, ft per minute, ground speed kt)."""


@dataclass(frozen=True)
class Performance:
    """A plain schedule for one class of aircraft: climb and descent in segments at still-air
    ground speeds, cruise at a true airspeed that the wind aloft adds to or takes from. Round
    textbook numbers (250 kt below FL100, about 3 nm per 1,000 ft of descent), not type data."""

    tas_kt: float
    climb: tuple[Step, ...]
    descent: tuple[Step, ...]
    top_fl: int
    emitter: str
    """ADS-B emitter category: A2 small, A3 large, A5 heavy."""


JET: Final = Performance(
    452,
    ((10000, 2500, 250), (24000, 2000, 330), (45000, 1300, 420)),
    ((10000, 2300, 380), (3000, 1300, 240), (0, 800, 160)),
    390,
    "A3",
)
HEAVY: Final = Performance(
    488,
    ((10000, 2300, 250), (24000, 1800, 340), (45000, 1200, 430)),
    ((10000, 2200, 390), (3000, 1300, 240), (0, 800, 165)),
    410,
    "A5",
)
PROP: Final = Performance(
    275,
    ((10000, 1500, 180), (30000, 1000, 210)),
    ((10000, 1500, 250), (3000, 1000, 200), (0, 700, 140)),
    250,
    "A2",
)
PRESSURE_FL: Final = {850: 50, 700: 100, 600: 140, 500: 180, 400: 240, 300: 300, 250: 340,
                      200: 390, 150: 450}  # fmt: skip
"""The flight level each pressure level stands at in the standard atmosphere."""
LANDED_FT: Final = 400
"""Below this a flight is on the runway or about to be: it leaves the ADS-B answers."""


def performance(type_icao: str) -> Performance:
    category = category_for_type(type_icao)
    if category is AircraftCategory.TURBOPROP:
        return PROP
    return HEAVY if category is AircraftCategory.WIDEBODY else JET


def fleet(callsign: str) -> Sequence[str]:
    number = callsign[3:]
    if callsign.startswith("JAL") and number.isdigit() and 3000 <= int(number) < 4000:
        return JAC_TYPES
    return FLEETS.get(callsign[:3], ("A320", "B738"))


def eastbound(track_deg: float) -> bool:
    return 0 <= track_deg % 360 < 180


def level_ok(fl: int, track_deg: float) -> bool:
    """The ICAO semicircular rule (true track standing in for magnetic): eastbound odd
    thousands of feet, westbound even."""
    return fl % 10 == 0 and (fl // 10) % 2 == (1 if eastbound(track_deg) else 0)


def cruise_levels(perf: Performance, dist_nm: float, track_deg: float) -> list[int]:
    """Levels an airline files for a leg this long: a 300 nm hop tops out near FL230, a long
    sector at the type's ceiling."""
    ceiling = min(perf.top_fl, 150 + int(dist_nm / 3.5))
    floor = max(110, ceiling - 60)
    return [fl for fl in range(floor // 10 * 10, ceiling + 1, 10) if level_ok(fl, track_deg)]


def regime(lat: float) -> str:
    return "kyushu" if lat > 20 else "north" if lat > -2 else "south"


def wind_along(lat: float, track_deg: float, fl: int) -> float:
    """The wind's component along the track at ``fl`` (positive: a tailwind), from the same
    profiles the winds feed serves."""
    profile = WIND_PROFILES[regime(lat)]
    hpa = min(profile, key=lambda level: abs(PRESSURE_FL[level] - fl))
    from_deg, speed = profile[hpa]
    return -speed * math.cos(math.radians(from_deg - track_deg))


def great_circle_point(
    lat1: float, lon1: float, lat2: float, lon2: float, fraction: float
) -> tuple[float, float]:
    p1, l1, p2, l2 = map(math.radians, (lat1, lon1, lat2, lon2))
    d = 2 * math.asin(
        math.sqrt(
            math.sin((p2 - p1) / 2) ** 2
            + math.cos(p1) * math.cos(p2) * math.sin((l2 - l1) / 2) ** 2
        )
    )
    if d < 1e-12:
        return lat1, lon1
    a = math.sin((1 - fraction) * d) / math.sin(d)
    b = math.sin(fraction * d) / math.sin(d)
    x = a * math.cos(p1) * math.cos(l1) + b * math.cos(p2) * math.cos(l2)
    y = a * math.cos(p1) * math.sin(l1) + b * math.cos(p2) * math.sin(l2)
    z = a * math.sin(p1) + b * math.sin(p2)
    return math.degrees(math.atan2(z, math.hypot(x, y))), math.degrees(math.atan2(y, x))


@dataclass(frozen=True)
class Leg:
    """One piece of the vertical profile: from ``alt_from`` to ``alt_to`` at a steady rate."""

    start_min: float
    start_nm: float
    minutes: float
    alt_from: float
    alt_to: float
    gs_kt: float

    @property
    def nm(self) -> float:
        return self.minutes * self.gs_kt / 60

    @property
    def rate_fpm(self) -> float:
        return (self.alt_to - self.alt_from) / self.minutes


def _segments(perf: Performance, cruise_ft: int) -> tuple[list[Leg], list[Leg]]:
    """Climb and descent legs (times and distances from zero) for a cruise level."""
    climb: list[Leg] = []
    alt = 0
    for to_ft, fpm, gs in perf.climb:
        top = min(to_ft, cruise_ft)
        if top > alt:
            climb.append(Leg(0, 0, (top - alt) / fpm, alt, top, gs))
            alt = top
    descent: list[Leg] = []
    alt = cruise_ft
    for down_to, fpm, gs in perf.descent:
        if down_to < alt:
            descent.append(Leg(0, 0, (alt - down_to) / fpm, alt, down_to, gs))
            alt = down_to
    return climb, descent


@dataclass
class Flight:
    """One airline flight on the great circle of its callsign's usual leg."""

    callsign: str
    origin: str
    dest: str
    o: tuple[float, float]
    d: tuple[float, float]
    cruise_ft: int
    type_icao: str
    tas_kt: float
    dep: datetime = START
    hex: str = field(init=False)
    dist_nm: float = field(init=False)
    legs: list[Leg] = field(init=False)

    def __post_init__(self) -> None:
        self.hex = hashlib.sha256(f"tephra-demo:{self.callsign}".encode()).hexdigest()[:6]
        self.dist_nm = distance_nm(*self.o, *self.d)
        perf = performance(self.type_icao)
        while True:
            climb, descent = _segments(perf, self.cruise_ft)
            cruise_nm = self.dist_nm - sum(leg.nm for leg in [*climb, *descent])
            if cruise_nm >= max(15.0, 0.1 * self.dist_nm) or self.cruise_ft <= 6000:
                break
            self.cruise_ft -= 2000  # the next level down in the same direction
        middle = great_circle_point(*self.o, *self.d, 0.5)
        track = initial_bearing_deg(*middle, *self.d)
        cruise_gs = self.tas_kt + wind_along(middle[0], track, self.cruise_ft // 100)
        cruise = Leg(0, 0, max(cruise_nm, 0.0) / cruise_gs * 60, self.cruise_ft, self.cruise_ft,
                     cruise_gs)  # fmt: skip
        self.legs = []
        at_min = at_nm = 0.0
        for leg in [*climb, cruise, *descent]:
            if leg.minutes <= 0:
                continue
            self.legs.append(Leg(at_min, at_nm, leg.minutes, leg.alt_from, leg.alt_to, leg.gs_kt))
            at_min += leg.minutes
            at_nm += leg.nm

    @property
    def block_min(self) -> float:
        last = self.legs[-1]
        return last.start_min + last.minutes

    @property
    def route_nm(self) -> float:
        """The profile's own length; it differs from the great circle by rounding only."""
        last = self.legs[-1]
        return last.start_nm + last.nm

    def minutes_to(self, flown_nm: float) -> float:
        for leg in self.legs:
            if flown_nm <= leg.start_nm + leg.nm:
                return leg.start_min + (flown_nm - leg.start_nm) / leg.gs_kt * 60
        return self.block_min

    def state(self, when: datetime) -> dict[str, float] | None:
        """Position, level and speeds at ``when``; None on the ground."""
        elapsed = (when - self.dep).total_seconds() / 60
        leg = next(
            (leg for leg in self.legs if leg.start_min <= elapsed < leg.start_min + leg.minutes),
            None,
        )
        if leg is None:
            return None
        into = elapsed - leg.start_min
        alt = leg.alt_from + into * leg.rate_fpm
        if alt < LANDED_FT:
            return None
        flown = leg.start_nm + into * leg.gs_kt / 60
        lat, lon = great_circle_point(*self.o, *self.d, min(1.0, flown / self.route_nm))
        if leg.rate_fpm < 0:  # cleared down: to FL100 first, then to the approach altitude
            selected: float | None = 10000 if alt > 11000 else 3000
        else:
            selected = self.cruise_ft
        return {"lat": lat, "lon": lon, "alt": alt, "gs": leg.gs_kt,
                "track": initial_bearing_deg(lat, lon, *self.d), "rate": leg.rate_fpm,
                "selected": selected}  # fmt: skip

    def adsb_entry(self, when: datetime, rng: random.Random) -> dict[str, Any] | None:
        seen = round(rng.uniform(0.2, 6.0), 1)
        state = self.state(when - timedelta(seconds=seen))
        if state is None:
            return None
        alt = int(round(state["alt"] / 25) * 25)
        entry: dict[str, Any] = {
            "hex": self.hex,
            "type": "adsb_icao",
            "flight": f"{self.callsign:<8}",
            "t": self.type_icao,
            "alt_baro": alt,
            "alt_geom": alt + 375,
            "gs": round(state["gs"] + rng.uniform(-3, 3), 1),
            "track": round(state["track"], 2),
            "baro_rate": int(round(state["rate"] / 64) * 64),
            "category": performance(self.type_icao).emitter,
            "lat": round(state["lat"], 6),
            "lon": round(state["lon"], 6),
            "seen_pos": seen,
            "seen": round(seen * 0.8, 1),
        }
        if state["selected"] is not None:
            entry["nav_altitude_mcp"] = 16 * round(state["selected"] / 16)
        return entry


@cache
def route_table() -> tuple[dict[str, str], Any]:
    raw = json.loads((DATA_DIR / ROUTES_FILE).read_text(encoding="utf-8"))
    return raw["routes"], load_routes(DATA_DIR)


def leg_positions(origin: str, dest: str) -> tuple[tuple[float, float], tuple[float, float]] | None:
    _, table = route_table()
    o = table.position(origin, airport_catalogue())
    d = table.position(dest, airport_catalogue())
    if o is None or d is None or distance_nm(*o, *d) < 80:
        return None
    return o, d


def make_flight(callsign: str, rng: random.Random, cruise_fl: int | None = None) -> Flight | None:
    """The callsign's usual leg, a type its airline flies there, and a level filed by the
    semicircular rule (``cruise_fl`` for a hero, which must keep the rule)."""
    routes, _ = route_table()
    chain = routes.get(callsign, "").split("-")
    if len(chain) != 2:
        return None
    ends = leg_positions(chain[0], chain[1])
    if ends is None:
        return None
    o, d = ends
    type_icao = rng.choice(list(fleet(callsign)))
    perf = performance(type_icao)
    dist = distance_nm(*o, *d)
    if perf is PROP and dist > 450:
        type_icao, perf = "A320", JET  # nobody flies an ATR this far
    track = initial_bearing_deg(*o, *d)
    if cruise_fl is None:
        cruise_fl = rng.choice(cruise_levels(perf, dist, track))
    elif not level_ok(cruise_fl, track):
        raise SystemExit(f"{callsign} {chain[0]}-{chain[1]} at FL{cruise_fl} breaks the "
                         f"semicircular rule (track {track:.0f})")  # fmt: skip
    return Flight(
        callsign, chain[0], chain[1], o, d, cruise_fl * 100, type_icao,
        perf.tas_kt * rng.uniform(0.98, 1.02),
    )  # fmt: skip


@dataclass(frozen=True)
class Box:
    west: float
    south: float
    east: float
    north: float

    def contains(self, lat: float, lon: float) -> bool:
        return self.west <= lon <= self.east and self.south <= lat <= self.north

    @property
    def centre(self) -> tuple[float, float]:
        return (self.south + self.north) / 2, (self.west + self.east) / 2


TRAFFIC_AREAS: Final = [
    # (box the route must cross, flights): each passes the box centre at a random time
    (Box(104.0, -10.5, 120.0, -4.5), 190),
    (Box(127.5, 29.5, 133.5, 34.5), 120),
    (Box(124.5, -1.5, 130.5, 3.5), 10),
]


def _crosses(flight: Flight, box: Box) -> float | None:
    """Distance flown (nm) at the route's point nearest the box centre, if it enters the box."""
    steps = max(8, int(flight.dist_nm / 20))
    best: tuple[float, float] | None = None
    centre = box.centre
    for index in range(steps + 1):
        lat, lon = great_circle_point(*flight.o, *flight.d, index / steps)
        if not box.contains(lat, lon):
            continue
        gap = distance_nm(lat, lon, *centre)
        if best is None or gap < best[0]:
            best = (gap, flight.route_nm * index / steps)
    return None if best is None else best[1]


# --- the flights the demo turns on ---------------------------------------------------------


@cache
def official_area(volcano_id: str) -> tuple[Any, int, int]:
    """The union of a volcano's official layers at ``DEMO_FROM`` and its band: the area TEPHRA
    draws with no model (OFFICIAL), read from this case's own products by the app's parsers."""
    volcano = load_volcanoes(DATA_DIR).get(volcano_id)
    if volcano is None:
        raise SystemExit(f"volcano {volcano_id} is not in the catalogue")
    issued = [
        spec.record(DEMO_FROM)
        for spec in SIGMETS
        if spec.volcano.id == volcano_id and spec.issued <= DEMO_FROM
    ]
    sigmets = parse_sigmets(_fetched(FeedId.SIGMET, json_bytes(issued)))
    vaas = [
        vaa
        for spec in [*DARWIN_CURRENT, *SAKURA_TOKYO]
        if spec.volcano.id == volcano_id and spec.issued <= DEMO_FROM
        if (vaa := parse_vaa(_fetched(FeedId.VAAC_DARWIN, darwin_text(spec)))) is not None
    ]
    layers = official_layers(volcano, sigmets, vaas, DEMO_FROM)
    shape = unary_union([geometry_to_shape(layer.polygon, ref_lon=volcano.lon) for layer in layers])
    base = min(layer.base_ft for layer in layers)
    top = max(layer.top_ft for layer in layers)
    return shape_to_geometry(shape), base, top


def _fetched(feed: FeedId, content: bytes) -> FetchResult:
    return FetchResult(
        feed=feed,
        url="",
        status_code=200,
        content=content,
        content_type=None,
        fetched_at=DEMO_FROM,
        sha256=hashlib.sha256(content).hexdigest(),
    )


@cache
def exposure_rules() -> tuple[int, int]:
    """(lookahead minutes, vertical margin ft) as the app runs them."""
    lookahead = Settings.model_fields["exposure_lookahead_min"].default
    return lookahead, load_policy(DATA_DIR).exposure.vertical_margin_ft.value


def minutes_to_area(flight: Flight, when: datetime, volcano_id: str) -> int | None:
    """What the app's exposure check says of this flight at ``when``: minutes to entry (0
    inside), or None when its track and level miss the area."""
    state = flight.state(when)
    if state is None:
        return None
    body = adsb_body([flight], state["lat"], state["lon"], 50, when)
    query = AdsbQueryPoint(lat=state["lat"], lon=state["lon"], radius_nm=50)
    aircraft = parse_adsb(_fetched(FeedId.ADSB, body), query).aircraft
    geometry, base, top = official_area(volcano_id)
    lookahead, margin = exposure_rules()
    crossings = find_crossings(
        geometry, base, top, aircraft, when, lookahead_min=lookahead, vertical_margin_ft=margin
    )
    return crossings[0].step if crossings else None


def lead_at(flight: Flight, volcano_id: str, when: datetime) -> int | None:
    """Minutes to entry at ``when``, or minus the minutes it has already been inside."""
    step = minutes_to_area(flight, when, volcano_id)
    if step != 0:
        return step
    inside = 0
    while inside < 30:
        earlier = when - timedelta(minutes=inside + 1)
        if minutes_to_area(flight, earlier, volcano_id) != 0:
            break
        inside += 1
    return -inside


@dataclass(frozen=True)
class Hero:
    """A flight placed so that ``at_min`` minutes into the demo window the app's own exposure
    check finds it ``lead_min`` minutes from ``volcano``'s official area (negative: inside
    that long). Most are placed at the window start; a few later, so that every minute of the
    loop has flights in each situation."""

    origin: str
    dest: str
    prefixes: tuple[str, ...]
    cruise_fl: int
    lead_min: int
    volcano: Vent
    at_min: int = 0


HEROES: Final = [
    # Agung, official area SFC/FL350. With no model the code drafts: inside or 15 min or less
    # and below the clear levels, DIVERT; at FL330 or above, CHANGE_LEVEL to FL370-FL390; 16 to
    # 30 min out for closed Bali (no route to it), HOLD; past 15 min with a destination clear
    # of the ash, REROUTE. A model weighs the same options.
    Hero("WIII", "WADD", ("GIA",), 350, -3, AGUNG),  # descending into Bali, in the ash
    Hero("WATT", "WIII", ("GIA", "CTV", "BTK"), 300, -2, AGUNG),  # Kupang-Jakarta, crossing it
    Hero("YPPH", "WADD", ("QFA", "VOZ", "JST", "AWQ"), 340, 4, AGUNG),  # Perth-Bali, descending
    Hero("WARR", "WADD", ("BTK", "CTV", "AWQ"), 210, 7, AGUNG),  # the Surabaya shuttle
    Hero("YPPH", "VHHH", ("CPA",), 340, 9, AGUNG),  # Perth-Hong Kong overflight
    Hero("WSSS", "WADD", ("SIA",), 370, 12, AGUNG),  # Singapore-Bali, descending
    Hero("VHHH", "YPPH", ("CPA",), 350, 16, AGUNG),  # Hong Kong-Perth overflight
    Hero("WIII", "WADD", ("BTK", "LNI", "CTV"), 310, 19, AGUNG),
    Hero("WIII", "WATT", ("GIA", "CTV", "BTK"), 310, 22, AGUNG),  # Jakarta-Kupang, past Bali
    Hero("WMKK", "WADD", ("AXM", "MAS"), 310, 26, AGUNG),
    Hero("YPPH", "VHHH", ("CPA",), 320, 24, AGUNG),  # a lower Perth-Hong Kong: around it
    Hero("WIII", "WADD", ("CTV", "LNI", "AWQ"), 330, 38, AGUNG),
    # Sakurajima, RJJJ SIGMET Y02 SFC/FL110 over Kagoshima Bay, south of the airport (RJFK).
    # Arrivals from the islands to the south meet it once cleared down, a few minutes out,
    # so they are staggered through the window.
    Hero("RJKA", "RJFK", ("JAL", "SKY"), 170, -2, SAKURAJIMA),  # Amami-Kagoshima, inside
    Hero("ROAH", "RJFK", ("SNJ", "ANA"), 310, 3, SAKURAJIMA),  # Naha-Kagoshima
    Hero("RJKN", "RJFK", ("JAL",), 170, 3, SAKURAJIMA, at_min=4),  # Tokunoshima-Kagoshima
    Hero("RORY", "RJFK", ("JAL",), 190, 2, SAKURAJIMA, at_min=8),  # Yoron-Kagoshima
]


def place_hero(flight: Flight, hero: Hero) -> None:
    """Set the departure time so that :func:`lead_at` is the hero's lead: of the departure
    minutes that give it, the middle one, so ADS-B timing jitter cannot tip it either way."""
    hits = []
    offset = 0.0
    when = DEMO_FROM + timedelta(minutes=hero.at_min)
    while offset < flight.block_min:
        flight.dep = when - timedelta(minutes=offset)
        if lead_at(flight, hero.volcano.id, when) == hero.lead_min:
            hits.append(offset)
        offset += 0.5
    if not hits:
        raise SystemExit(f"{flight.callsign} never shows {hero.lead_min} min from {hero.volcano}")
    run = [hits[0]]  # the first run of consecutive offsets
    for value in hits[1:]:
        if value - run[-1] > 0.5:
            break
        run.append(value)
    flight.dep = when - timedelta(minutes=run[len(run) // 2])


def hero_flights(rng: random.Random) -> list[Flight]:
    routes, _ = route_table()
    flights: list[Flight] = []
    used: set[str] = set()
    for hero in HEROES:
        callsigns = sorted(
            cs
            for cs, chain in routes.items()
            if chain == f"{hero.origin}-{hero.dest}" and cs[:3] in hero.prefixes and cs not in used
        )
        callsigns.sort(key=lambda cs: hero.prefixes.index(cs[:3]))
        if not callsigns:
            raise SystemExit(f"no callsign flies {hero.origin}-{hero.dest} for {hero.prefixes}")
        flight = make_flight(callsigns[0], rng, hero.cruise_fl)
        if flight is None:
            raise SystemExit(f"{callsigns[0]} has no usable route")
        place_hero(flight, hero)
        used.add(flight.callsign)
        flights.append(flight)
    return flights


def traffic() -> list[Flight]:
    rng = random.Random(SEED)
    flights = hero_flights(rng)
    taken = {flight.callsign for flight in flights}
    routes, _ = route_table()
    for box, count in TRAFFIC_AREAS:
        candidates: list[tuple[Flight, float]] = []
        for callsign in sorted(routes):
            if callsign in taken:
                continue
            flight = make_flight(callsign, rng)
            if flight is None:
                continue
            flown = _crosses(flight, box)
            if flown is not None:
                candidates.append((flight, flown))
        rng.shuffle(candidates)
        span = (END - START).total_seconds() / 60 + 40
        for flight, flown in candidates[:count]:
            # the moment it passes nearest the area's centre, anywhere from 20 min before the
            # case to 20 min after it
            centre_at = START - timedelta(minutes=20) + timedelta(minutes=rng.uniform(0, span))
            flight.dep = centre_at - timedelta(minutes=flight.minutes_to(flown))
            taken.add(flight.callsign)
            flights.append(flight)
    return sorted(flights, key=lambda flight: flight.callsign)


def adsb_body(
    flights: Sequence[Flight], lat: float, lon: float, radius_nm: float, when: datetime
) -> bytes:
    rng = random.Random(f"{SEED}:adsb:{lat}:{lon}:{epoch(when)}")
    aircraft = []
    for flight in flights:
        entry = flight.adsb_entry(when, rng)
        if entry is None or distance_nm(lat, lon, entry["lat"], entry["lon"]) > radius_nm:
            continue
        entry["dst"] = round(distance_nm(lat, lon, entry["lat"], entry["lon"]), 3)
        aircraft.append(entry)
    stamp = int(when.timestamp() * 1000)
    payload = {"ac": aircraft, "msg": "No error", "now": stamp, "total": len(aircraft),
               "ctime": stamp, "ptime": 0}  # fmt: skip
    return json_bytes(payload)


def adsb_fill(store: Store, url: str, flights: Sequence[Flight]) -> list[ReplayRecord]:
    parts = urlsplit(url).path.split("/")
    lat, lon, radius = float(parts[-3]), float(parts[-2]), float(parts[-1])
    records = []
    when = START
    while when <= END:
        body = adsb_body(flights, lat, lon, radius, when)
        records.append(store.put(FeedId.ADSB, url, when, body, "application/json"))
        when += ADSB_STEP
    return records


# --- the case on disk ----------------------------------------------------------------------------


class Store:
    """Writes each body once under ``raw/<feed>/`` (named by its hash) and makes its record."""

    def __init__(self, case_dir: Path) -> None:
        self.case_dir = case_dir

    def put(
        self, feed: FeedId, url: str, when: datetime, content: bytes, content_type: str
    ) -> ReplayRecord:
        digest = hashlib.sha256(content).hexdigest()
        kind = content_type.split(";")[0].strip()
        suffix = {"application/json": ".json", "text/html": ".html", "application/xml": ".xml"}
        relative = Path("raw") / feed.value / f"{digest[:20]}{suffix.get(kind, '.txt')}"
        target = self.case_dir / relative
        if not target.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
        return ReplayRecord(
            feed=feed,
            url=url,
            fetched_at=when,
            sha256=digest,
            path=relative.as_posix(),
            status_code=200,
            content_type=content_type,
        )


def product_records(store: Store) -> list[ReplayRecord]:
    return [
        *sigmet_records(store),
        *vona_records(store),
        *darwin_records(store),
        *tokyo_records(store),
        *jma_records(store),
    ]


def write_manifest(case_dir: Path, records: Iterable[ReplayRecord]) -> ReplayCase:
    case = ReplayCase(
        case_id=CASE_ID,
        label=LABEL,
        recorded_from=START,
        recorded_to=END,
        region=REGION,
        volcano_ids=VOLCANO_IDS,
        notes=NOTES,
        synthetic=True,
        records=sorted(records, key=lambda record: (record.fetched_at, record.url)),
    )
    (case_dir / "manifest.json").write_text(case.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return case


def probe_times() -> list[datetime]:
    """Every two minutes over the case and every 30 s in the demo window, where the flights
    near the ash (and so the alternates asked for) change fastest."""
    times = set()
    when = START
    while when <= END:
        times.add(when)
        when += timedelta(minutes=2)
    when = DEMO_FROM - timedelta(minutes=2)
    while when <= DEMO_TO + timedelta(minutes=2):
        times.add(when)
        when += timedelta(seconds=30)
    return sorted(times)


def load_recorder() -> ModuleType:
    name = "tephra_script_record_replay"
    spec = importlib.util.spec_from_file_location(
        name, PROJECT_ROOT / "scripts" / "record_replay.py"
    )
    if spec is None or spec.loader is None:
        raise SystemExit("scripts/record_replay.py not found")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def build(case_dir: Path) -> ReplayCase:
    flights = traffic()  # placed before anything on disk changes: a hero that misses fails here
    shutil.rmtree(case_dir / "raw", ignore_errors=True)
    case_dir.mkdir(parents=True, exist_ok=True)
    store = Store(case_dir)
    records = product_records(store)
    fillers: dict[FeedId, Callable[[Store, str], list[ReplayRecord]]] = {
        FeedId.METAR: metar_fill,
        FeedId.TAF: taf_fill,
        FeedId.WINDS: winds_fill,
        FeedId.ADSB: lambda s, url: adsb_fill(s, url, flights),
    }
    recorder = load_recorder()
    filled: set[str] = set()
    times = probe_times()
    case = write_manifest(case_dir, records)
    for round_number in range(1, MAX_ROUNDS + 1):
        print(f"probe {round_number}: {len(times)} replay ticks")
        missing = asyncio.run(recorder.missing_urls(DATA_DIR, case, times, CONTEXT_FEEDS))
        todo = {url: feed for url, feed in missing.items() if url not in filled}
        if not todo:
            break
        for url, feed in sorted(todo.items(), key=lambda item: (item[1].value, item[0])):
            print(f"  filling {feed.value}: {url}")
            records += fillers[feed](store, url)
            filled.add(url)
        case = write_manifest(case_dir, records)
    else:
        raise SystemExit(f"URLs still missing after {MAX_ROUNDS} probes")
    return case


def main(argv: list[str] | None = None) -> int:
    argparse.ArgumentParser(description=__doc__.split("\n\n")[0]).parse_args(argv)
    case_dir = DATA_DIR / "replay" / CASE_ID  # the replay probes read the case from here
    case = build(case_dir)
    size = sum(path.stat().st_size for path in case_dir.rglob("*") if path.is_file())
    print(f"wrote {case.case_id}: {len(case.records)} records, {size / 1e6:.1f} MB")
    print(f"region {REGIONS[REGION].name}; demo window {iso(DEMO_FROM)} to {iso(DEMO_TO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
