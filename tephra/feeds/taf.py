"""TAFs and METARs from aviationweather.gov JSON, and the alternate screen built on them.

AWC renders visibility in statute miles (``2.49`` for a reported 4000 m) or as ``"6+"``,
and leaves it as ``""`` in groups that do not change it. Values are converted back to
metres here; groups that omit a value are left as None and are not screened for it.
"""

import logging
from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta
from typing import Any, Final

from tephra.config import (
    ALTERNATE_ETA_WINDOW_MIN,
    ALTERNATE_MIN_CEILING_FT,
    ALTERNATE_MIN_VISIBILITY_M,
)
from tephra.feeds.base import FetchResult, Source
from tephra.models import AlternateCheck, FeedId, Metar, Taf, TafPeriod, make_source_id
from tephra.util import timeutil

__all__ = [
    "METAR_URL",
    "TAF_URL",
    "assess_alternate",
    "fetch_metars",
    "fetch_tafs",
    "parse_metars",
    "parse_tafs",
    "station_params",
]

TAF_URL: Final = "https://aviationweather.gov/api/data/taf"
METAR_URL: Final = "https://aviationweather.gov/api/data/metar"

log = logging.getLogger(__name__)

_CHUNK = 20
_METRES_PER_SM = 1609.344
_VIS_UNLIMITED_M = 9999
"""AWC's ``"6+"`` is how it renders a reported 9999 (10 km or more) or CAVOK."""
_CEILING_COVERS = frozenset({"BKN", "OVC", "OVX", "VV"})
_NO_WEATHER = frozenset({"NSW"})
_PREVAILING_CHANGES = frozenset({None, "FM", "BECMG"})
"""Groups that set the prevailing conditions; TEMPO and PROB groups only overlay them."""


def station_params(icaos: Sequence[str]) -> dict[str, str]:
    return {"ids": ",".join(_stations(icaos)), "format": "json"}


def _stations(icaos: Sequence[str]) -> list[str]:
    return sorted({icao.strip().upper() for icao in icaos if icao.strip()})


# --- parsing ----------------------------------------------------------------------------


def parse_tafs(result: FetchResult) -> list[Taf]:
    """The latest TAF per station in the response."""
    latest: dict[str, Taf] = {}
    for record in _records(result, "TAF"):
        try:
            taf = _parse_taf(record, result)
        except (KeyError, TypeError, ValueError) as exc:
            log.warning("skipping unreadable TAF %s: %s", record.get("icaoId", "?"), exc)
            continue
        current = latest.get(taf.icao)
        if current is None or taf.issued_at > current.issued_at:
            latest[taf.icao] = taf
    return sorted(latest.values(), key=lambda taf: taf.icao)


def parse_metars(result: FetchResult) -> list[Metar]:
    """The latest METAR per station in the response."""
    latest: dict[str, Metar] = {}
    for record in _records(result, "METAR"):
        try:
            metar = _parse_metar(record, result)
        except (KeyError, TypeError, ValueError) as exc:
            log.warning("skipping unreadable METAR %s: %s", record.get("icaoId", "?"), exc)
            continue
        current = latest.get(metar.icao)
        if current is None or metar.observed_at > current.observed_at:
            latest[metar.icao] = metar
    return sorted(latest.values(), key=lambda metar: metar.icao)


def _records(result: FetchResult, kind: str) -> list[Mapping[str, Any]]:
    if not result.content.strip():
        return []  # AWC answers an empty body when no station has a report
    try:
        payload = result.json()
    except ValueError as exc:
        raise ValueError(f"{kind} response is not JSON: {exc}") from exc
    if not isinstance(payload, list):
        raise ValueError(f"{kind} response is not a JSON array")
    return [record for record in payload if isinstance(record, Mapping)]


def _parse_taf(record: Mapping[str, Any], result: FetchResult) -> Taf:
    icao = str(record["icaoId"]).strip().upper()
    issued_at = timeutil.parse_iso(record["issueTime"])
    valid_from = timeutil.parse_iso(record["validTimeFrom"])
    valid_to = timeutil.parse_iso(record["validTimeTo"])
    items = [item for item in record.get("fcsts") or [] if isinstance(item, Mapping)]
    periods = _hold_until_change_completes(items, [_parse_period(item) for item in items])
    source_id = make_source_id("TAF", icao, timeutil.compact(issued_at))
    return Taf(
        provenance=result.provenance(
            source_id, issued_at=issued_at, valid_from=valid_from, valid_to=valid_to
        ),
        icao=icao,
        issued_at=issued_at,
        valid_from=valid_from,
        valid_to=valid_to,
        periods=periods,
        raw_text=str(record.get("rawTAF") or "").strip(),
    )


def _parse_period(item: Mapping[str, Any]) -> TafPeriod:
    return TafPeriod(
        valid_from=timeutil.parse_iso(item["timeFrom"]),
        valid_to=timeutil.parse_iso(item["timeTo"]),
        change=_change(item.get("fcstChange"), item.get("probability")),
        visibility_m=_visibility_m(item.get("visib")),
        ceiling_ft=_ceiling_ft(item.get("clouds"), item.get("vertVis")),
        weather=_weather(item.get("wxString")),
        wind_from_deg=_number(item.get("wdir")),
        wind_speed_kt=_number(item.get("wspd")),
    )


def _hold_until_change_completes(
    items: Sequence[Mapping[str, Any]], periods: list[TafPeriod]
) -> list[TafPeriod]:
    """Extend the prevailing group before each BECMG to the end of the change (``timeBec``).

    AWC ends a group where the next BECMG begins, but during ``BECMG 1004/1006`` the old
    conditions may hold until 06Z: an improving BECMG counts only once the change completes.
    """
    held = list(periods)
    for index, item in enumerate(items):
        completes = _optional_time(item.get("timeBec"))
        if held[index].change != "BECMG" or completes is None:
            continue
        for prior in range(index - 1, -1, -1):
            if held[prior].change in _PREVAILING_CHANGES:
                if held[prior].valid_to < completes:
                    held[prior] = held[prior].model_copy(update={"valid_to": completes})
                break
    return held


def _optional_time(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    try:
        return timeutil.parse_iso(value)
    except (TypeError, ValueError):
        return None


def _parse_metar(record: Mapping[str, Any], result: FetchResult) -> Metar:
    icao = str(record["icaoId"]).strip().upper()
    observed = record.get("obsTime") or record.get("reportTime")
    if observed is None:
        raise ValueError("METAR has no observation time")
    observed_at = timeutil.parse_iso(observed)
    source_id = make_source_id("METAR", icao, timeutil.compact(observed_at))
    return Metar(
        provenance=result.provenance(source_id, issued_at=observed_at),
        icao=icao,
        observed_at=observed_at,
        visibility_m=_visibility_m(record.get("visib")),
        ceiling_ft=_ceiling_ft(record.get("clouds"), record.get("vertVis")),
        weather=_weather(record.get("wxString")),
        flight_category=str(record.get("fltCat") or "").strip() or None,
        raw_text=str(record.get("rawOb") or "").strip(),
    )


def _change(change: Any, probability: Any) -> str | None:
    kind = str(change or "").strip().upper() or None
    chance = _number(probability)
    if chance is None:
        return kind
    prob = f"PROB{round(chance)}"
    return prob if kind in (None, "PROB") else f"{prob} {kind}"


def _visibility_m(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        if text.endswith("+"):
            return _VIS_UNLIMITED_M
        try:
            miles = float(text)
        except ValueError:
            return None
    else:
        miles = float(value)
    # Reported visibilities are whole hundreds of metres; AWC's 2-decimal miles round-trip
    # to within a few metres of them (1.86 SM -> 2993 m, reported as 3000 m).
    return int(round(miles * _METRES_PER_SM / 100.0) * 100)


def _ceiling_ft(clouds: Any, vertical_visibility: Any) -> int | None:
    bases: list[int] = []
    for layer in clouds if isinstance(clouds, list) else []:
        if not isinstance(layer, Mapping):
            continue
        base = _number(layer.get("base"))
        if str(layer.get("cover") or "").upper() in _CEILING_COVERS and base is not None:
            bases.append(round(base))
    vv = _number(vertical_visibility)
    if vv is not None:
        bases.append(round(vv))
    return min(bases) if bases else None


def _weather(value: Any) -> list[str]:
    tokens = str(value or "").upper().split()
    return [token for token in tokens if token not in _NO_WEATHER]


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None  # "VRB" winds and other non-numeric codes


# --- fetching ---------------------------------------------------------------------------


async def fetch_tafs(source: Source, icaos: Sequence[str]) -> list[Taf]:
    tafs: list[Taf] = []
    for chunk in _chunks(icaos):
        result = await source.fetch(TAF_URL, feed=FeedId.TAF, params=station_params(chunk))
        tafs.extend(parse_tafs(result))
    return tafs


async def fetch_metars(source: Source, icaos: Sequence[str]) -> list[Metar]:
    metars: list[Metar] = []
    for chunk in _chunks(icaos):
        result = await source.fetch(METAR_URL, feed=FeedId.METAR, params=station_params(chunk))
        metars.extend(parse_metars(result))
    return metars


def _chunks(icaos: Sequence[str]) -> list[list[str]]:
    stations = _stations(icaos)
    return [stations[index : index + _CHUNK] for index in range(0, len(stations), _CHUNK)]


# --- alternate screen -------------------------------------------------------------------


def assess_alternate(taf: Taf | None, eta: datetime, *, icao: str | None = None) -> AlternateCheck:
    """Simplified planning-minima screen of one alternate's TAF around ``eta``.

    ``icao`` names the aerodrome when there is no TAF to take it from.
    """
    eta = timeutil.ensure_utc(eta)
    if taf is None:
        return AlternateCheck(icao=icao or "", ok=False, reasons=["NO TAF"], checked_for=eta)
    if not taf.valid_from <= eta <= taf.valid_to:
        return AlternateCheck(
            icao=taf.icao,
            ok=False,
            reasons=["TAF NOT VALID AT ETA"],
            taf_source_id=taf.provenance.source_id,
            checked_for=eta,
        )
    window = timedelta(minutes=ALTERNATE_ETA_WINDOW_MIN)
    start, end = eta - window, eta + window
    blocking: list[str] = []
    notes: list[str] = []
    for period in taf.periods:
        if period.valid_to <= start or period.valid_from >= end:
            continue
        blocking.extend(_blocking_reasons(period))
        if any("TS" in token for token in period.weather):
            notes.append(f"TS {_group_label(period)}")
    reasons = list(dict.fromkeys([*blocking, *notes]))
    return AlternateCheck(
        icao=taf.icao,
        ok=not blocking,
        reasons=reasons,
        taf_source_id=taf.provenance.source_id,
        checked_for=eta,
    )


def _blocking_reasons(period: TafPeriod) -> list[str]:
    label = _group_label(period)
    reasons: list[str] = []
    if any("VA" in token for token in period.weather):
        reasons.append(f"VA {label}")
    if period.visibility_m is not None and period.visibility_m < ALTERNATE_MIN_VISIBILITY_M:
        reasons.append(f"VIS {period.visibility_m} M BELOW {ALTERNATE_MIN_VISIBILITY_M} M {label}")
    if period.ceiling_ft is not None and period.ceiling_ft < ALTERNATE_MIN_CEILING_FT:
        reasons.append(
            f"CEILING {period.ceiling_ft} FT BELOW {ALTERNATE_MIN_CEILING_FT} FT {label}"
        )
    return reasons


def _group_label(period: TafPeriod) -> str:
    return f"IN {period.change} GROUP" if period.change else "IN BASE FORECAST"
