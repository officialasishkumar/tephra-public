"""The deterministic discrepancy finder, tested on the two Semeru cases re-verified in
research/13 (texts copied from the AWC SIGMET archive and the MAGMA VONA pages quoted
there) plus small crafted cases for the rules those days do not exercise."""

import re
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from tephra.config import Settings
from tephra.feeds.base import FetchResult
from tephra.feeds.sigmet import SIGMET_URL, parse_sigmets
from tephra.feeds.vaac import DARWIN_BULLETIN_URLS, parse_vaa
from tephra.feeds.volcanoes import VolcanoCatalogue, load_volcanoes
from tephra.models import (
    AviationColor,
    Discrepancy,
    DiscrepancyKind,
    EvidenceState,
    FeedHealth,
    FeedId,
    FeedStatus,
    GeoPolygon,
    Provenance,
    RunMode,
    Sigmet,
    VaacAdvisory,
    VaacCentre,
    VaacStep,
    VaLayer,
    Volcano,
    Vona,
    WindLevel,
    WindProfile,
    make_source_id,
    polygon_from_latlon,
)
from tephra.reconcile import (
    build_situation,
    evidence_state,
    find_active,
    find_discrepancies,
    select_records,
)
from tephra.util.hashing import sha256_bytes, sha256_text
from tephra.util.timeutil import compact

FEEDS_TEXT = Path(__file__).resolve().parent / "fixtures" / "feeds_text"

SEMERU = Volcano(
    id="263300",
    name="Semeru",
    aliases=["SEMERU"],
    magma_code="SMR",
    country="Indonesia",
    lat=-8.108,
    lon=112.92,
    summit_elev_m=3676,
    observatory="Semeru Volcano Observatory (PVMBG)",
    vaac=VaacCentre.DARWIN,
)
BROMO = Volcano(
    id="263310",
    name="Tengger Caldera",
    aliases=["BROMO", "TENGGER CALDERA"],
    magma_code="BRO",
    country="Indonesia",
    lat=-7.942,
    lon=112.95,
    summit_elev_m=2329,
    observatory="Bromo Volcano Observatory (PVMBG)",
    vaac=VaacCentre.DARWIN,
)
KERINCI = Volcano(
    id="261170",
    name="Kerinci",
    aliases=["KERINCI"],
    country="Indonesia",
    lat=-1.697,
    lon=101.264,
    summit_elev_m=3800,
    observatory="PVMBG (CVGHM), Indonesia",
    vaac=VaacCentre.DARWIN,
)
LEWOTOLOK = Volcano(
    id="264230",
    name="Ili Lewotolok",
    aliases=["LEWOTOLOK", "ILI LEWOTOLOK"],
    magma_code="LEW",
    country="Indonesia",
    lat=-8.274,
    lon=123.508,
    summit_elev_m=1423,
    observatory="Ili Lewotolok Volcano Observatory (PVMBG)",
    vaac=VaacCentre.DARWIN,
)
SAKURAJIMA = Volcano(
    id="282080",
    name="Sakurajima",
    aliases=["SAKURAJIMA", "SAKURAJIMA (AIRA CALDERA)"],
    country="Japan",
    lat=31.593,
    lon=130.657,
    summit_elev_m=1117,
    observatory="Kagoshima Local Meteorological Office (JMA)",
    vaac=VaacCentre.TOKYO,
)
MARAPI = Volcano(
    id="261140",
    name="Marapi",
    aliases=["MARAPI"],
    country="Indonesia",
    lat=-0.381,
    lon=100.473,
    summit_elev_m=2885,
    observatory="Marapi Volcano Observatory (PVMBG)",
    vaac=VaacCentre.DARWIN,
)
SETTINGS = Settings(_env_file=None)


def utc(year: int, month: int, day: int, hour: int, minute: int) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=UTC)


def degmin(token: str) -> float:
    """``S0806`` -> -8.1, ``E11255`` -> 112.9167 (SIGMET/VAA degrees and minutes)."""
    hemisphere, digits = token[0], token[1:]
    degrees, minutes = int(digits[:-2]), int(digits[-2:])
    value = degrees + minutes / 60
    return -value if hemisphere in "SW" else value


def ring(text: str, *, decimals: int | None = None) -> GeoPolygon:
    points = []
    for vertex in text.split(" - "):
        lat_token, lon_token = vertex.split()
        lat, lon = degmin(lat_token), degmin(lon_token)
        if decimals is not None:
            lat, lon = round(lat, decimals), round(lon, decimals)
        points.append((lat, lon))
    return polygon_from_latlon(points)


def provenance(source_id: str, feed: FeedId, issued_at: datetime) -> Provenance:
    return Provenance(
        source_id=source_id,
        feed=feed,
        url="https://example.test/" + source_id,
        fetched_at=issued_at + timedelta(minutes=3),
        issued_at=issued_at,
        sha256=sha256_text(source_id),
    )


def make_sigmet(
    *,
    series: str,
    valid_from: datetime,
    valid_to: datetime,
    observed_at: datetime,
    polygon: GeoPolygon | None,
    toward_deg: float | None,
    speed_kt: float | None,
    raw: str,
    top_ft: int = 15000,
    fir: str = "WAAF",
    volcano_name: str = "SEMERU",
) -> Sigmet:
    source_id = make_source_id("SIGMET", fir, series, compact(valid_from))
    return Sigmet(
        provenance=provenance(source_id, FeedId.SIGMET, valid_from),
        fir_id=fir,
        series_id=series,
        volcano_name=volcano_name,
        observed=True,
        observed_at=observed_at,
        base_ft=0,
        top_ft=top_ft,
        polygon=polygon,
        movement_toward_deg=toward_deg,
        movement_speed_kt=speed_kt,
        valid_from=valid_from,
        valid_to=valid_to,
        raw_text=raw,
    )


def make_vona(
    *,
    issued_at: datetime,
    notice: str,
    ash: bool,
    top_m: int | None = None,
    toward_deg: float | None = None,
    direction_text: str | None = None,
) -> Vona:
    source_id = make_source_id("VONA", "SEMERU", compact(issued_at))
    height = "Ash-cloud is not observed." if top_m is None else f"around {top_m} M"
    return Vona(
        provenance=provenance(source_id, FeedId.VONA, issued_at),
        notice_number=notice,
        volcano_name="Semeru",
        volcano_code="SMR",
        issued_at=issued_at,
        color_code=AviationColor.ORANGE,
        ash_observed=ash,
        cloud_top_m=top_m,
        cloud_top_ft=round(top_m * 3.28084) if top_m is not None else None,
        movement_toward_deg=toward_deg,
        movement_text=direction_text,
        source_text="Semeru Volcano Observatory",
        raw_text=f"VONA {notice} Semeru (263300) {height}",
    )


def make_vaa(
    *,
    number: str,
    issued_at: datetime,
    observation: VaacStep | None,
    forecasts: list[VaacStep] | None = None,
    next_advisory_at: datetime | None = None,
    final: bool = False,
    raw: str = "VA ADVISORY",
    volcano: Volcano = SEMERU,
    vaac: VaacCentre = VaacCentre.DARWIN,
) -> VaacAdvisory:
    source_id = make_source_id("VAA", vaac.value, volcano.id, number)
    feed = FeedId.VAAC_DARWIN if vaac is VaacCentre.DARWIN else FeedId.VAAC_TOKYO
    return VaacAdvisory(
        provenance=provenance(source_id, feed, issued_at),
        vaac=vaac,
        advisory_nr=number,
        issued_at=issued_at,
        volcano_name=volcano.aliases[0],
        volcano_number=volcano.id,
        observation=observation,
        forecasts=forecasts or [],
        next_advisory_at=next_advisory_at,
        final=final,
        raw_text=raw,
    )


def kinds(found: list[Discrepancy]) -> dict[tuple[DiscrepancyKind, str], Discrepancy]:
    return {(d.kind, d.aspect): d for d in found}


# --- the real cases (research/13) -------------------------------------------------------

SIGMET_11_POLYGON = "S0804 E11251 - S0801 E11256 - S0813 E11322 - S0835 E11320 - S0838 E11300"
SIGMET_11 = make_sigmet(
    series="11",
    valid_from=utc(2026, 9, 23, 17, 25),
    valid_to=utc(2026, 9, 23, 23, 25),
    observed_at=utc(2026, 9, 23, 17, 0),
    polygon=ring(SIGMET_11_POLYGON),
    toward_deg=135,
    speed_kt=10,
    raw=(
        "WVID21 WAAA 231725 WAAF SIGMET 11 VALID 231725/232325 WAAA- WAAF UJUNG PANDANG FIR "
        "VA ERUPTION MT SEMERU PSN S0806 E11255 VA CLD OBS AT 1700Z WI "
        f"{SIGMET_11_POLYGON} - S0804 E11251 SFC/FL150 MOV SE 10KT NC="
    ),
)
SIGMET_12_SEP_POLYGON = "S0806 E11250 - S0801 E11254 - S0812 E11322 - S0824 E11323 - S0828 E11309"
SIGMET_12_SEP = make_sigmet(
    series="12",
    valid_from=utc(2026, 9, 25, 11, 20),
    valid_to=utc(2026, 9, 25, 17, 20),
    observed_at=utc(2026, 9, 25, 11, 0),
    polygon=ring(SIGMET_12_SEP_POLYGON),
    toward_deg=135,
    speed_kt=10,
    raw=(
        "WAAF SIGMET 12 VALID 251120/251720 WAAA- WAAF UJUNG PANDANG FIR VA ERUPTION MT "
        "SEMERU PSN S0806 E11255 VA CLD OBS AT 1100Z WI "
        f"{SIGMET_12_SEP_POLYGON} - S0806 E11250 SFC/FL150 MOV SE 10KT NC="
    ),
)
# "Best estimate of ash-cloud top is around 13363 FT (4176 M)": MAGMA's feet are metres x 3.2.
VONA_1806 = make_vona(
    issued_at=utc(2026, 9, 23, 22, 21),
    notice="2026SMR1806",
    ash=True,
    top_m=4176,
    toward_deg=45,
    direction_text="Ash cloud moving to northeast",
)


def test_semeru_23_sep_simultaneous_pair() -> None:
    """VONA 2221Z against the SIGMET in force at its own time (WAAF 11), no VAA anywhere."""
    at = utc(2026, 9, 23, 23, 0)
    found = find_discrepancies(
        SEMERU, sigmets=[SIGMET_11], vonas=[VONA_1806], vaas=[], at=at, settings=SETTINGS
    )
    by_kind = kinds(found)
    sigmet_id, vona_id = SIGMET_11.provenance.source_id, VONA_1806.provenance.source_id

    envelope = by_kind[DiscrepancyKind.ENVELOPE, "top"]
    assert envelope.magnitude == 13701 - 15000  # 4176 m x 3.28084, inside SFC/FL150
    assert envelope.source_ids == sorted([sigmet_id, vona_id])
    assert "13,701 ft" in envelope.summary
    assert "SFC/FL150" in envelope.summary

    direction = by_kind[DiscrepancyKind.DIRECTION_MISMATCH, "direction"]
    assert direction.magnitude == 90  # NE against SE
    # 15 km NE of the vent lies outside a polygon reaching about 10 km north (research/13).
    assert (DiscrepancyKind.DIRECTION_MISMATCH, "polygon") in by_kind

    silences = [d for d in found if d.kind is DiscrepancyKind.SILENCE]
    assert {tuple(d.source_ids) for d in silences} == {(vona_id,), (sigmet_id,)}
    assert by_kind[DiscrepancyKind.LAG, "time"].magnitude == 321  # OBS 1700Z vs VONA 2221Z

    assert DiscrepancyKind.CONFLICT not in {d.kind for d in found}
    assert DiscrepancyKind.HEIGHT_MISMATCH not in {d.kind for d in found}


def test_semeru_25_sep_cited_pair_is_lag_envelope_and_silence() -> None:
    """The pair as first cited: VONA 23 Sep 2221Z against SIGMET 12 of 25 Sep.

    No SIGMET in the input was valid at the VONA's time, so the VONA is compared with the
    SIGMET in force now. The products are 36 h 39 min apart (LAG); the height sits inside
    the band (ENVELOPE); no VAA (SILENCE). Drift directions are not compared: research/13
    calls this pair "not a fair test" (row 2) and finds the direction mismatch against the
    SIGMETs valid at the VONA's own time (row 3, the 23 Sep test above). The polygon probe
    is not run either: it needs a SIGMET valid when the VONA was issued.
    """
    at = utc(2026, 9, 25, 12, 0)
    found = find_discrepancies(
        SEMERU, sigmets=[SIGMET_12_SEP], vonas=[VONA_1806], vaas=[], at=at, settings=SETTINGS
    )
    by_kind = kinds(found)
    lag = by_kind[DiscrepancyKind.LAG, "time"]
    assert lag.magnitude == 36 * 60 + 39
    assert "36 h 39 min" in lag.summary
    assert (DiscrepancyKind.ENVELOPE, "top") in by_kind
    assert DiscrepancyKind.DIRECTION_MISMATCH not in {d.kind for d in found}
    assert any(d.kind is DiscrepancyKind.SILENCE for d in found)
    assert all(d.kind is not DiscrepancyKind.CONFLICT for d in found)


def test_a_fresh_vona_is_compared_with_the_sigmet_that_followed_it() -> None:
    """Within VONA_FRESH_H the newest SIGMET is still a fair comparison: the 23 Sep 2221Z
    VONA (NE) against WAAF 16, which replaced WAAF 11 at 2325Z with MOV SE."""
    polygon_text = "S0807 E11252 - S0802 E11256 - S0810 E11323 - S0825 E11329 - S0834 E11305"
    waaf_16 = make_sigmet(
        series="16",
        valid_from=utc(2026, 9, 23, 23, 25),
        valid_to=utc(2026, 9, 24, 5, 25),
        observed_at=utc(2026, 9, 23, 22, 50),
        polygon=ring(polygon_text),
        toward_deg=135,
        speed_kt=10,
        raw=f"WAAF SIGMET 16 VALID 232325/240525 ... SEMERU ... WI {polygon_text} SFC/FL150 MOV SE",
    )
    found = find_discrepancies(
        SEMERU,
        sigmets=[waaf_16],
        vonas=[VONA_1806],
        vaas=[],
        at=utc(2026, 9, 24, 0, 0),
        settings=SETTINGS,
    )
    assert kinds(found)[DiscrepancyKind.DIRECTION_MISMATCH, "direction"].magnitude == 90


def test_semeru_7_oct_non_observation_is_lag_not_conflict() -> None:
    """SIGMET 12 "VA CLD OBS AT 1010Z ... MOV NE 05KT" against VONA 1122Z "Ash-cloud is not
    observed".

    The rule: a non-observation is an evidence state, never a CONFLICT; CONFLICT needs an
    explicit negative (a VAA saying no ash is expected). What remains between the two
    products is that their observation times differ by 72 minutes, more than the 20-minute
    LAG threshold, so the pair is a LAG whose summary says the VONA could not observe. The
    SIGMET also has no VAA behind it in this input, which is a SILENCE. The VONA was issued
    after dusk, so its evidence state is NIGHT_BLIND (research/13: 38 min after civil dusk).
    """
    polygon_text = "S0818 E11306 - S0813 E11240 - S0749 E11237 - S0739 E11301 - S0756 E11318"
    sigmet = make_sigmet(
        series="12",
        valid_from=utc(2026, 10, 7, 10, 30),
        valid_to=utc(2026, 10, 7, 16, 30),
        observed_at=utc(2026, 10, 7, 10, 10),
        polygon=ring(polygon_text),
        toward_deg=45,
        speed_kt=5,
        raw=(
            "WAAF SIGMET 12 VALID 071030/071630 WAAA- WAAF UJUNG PANDANG FIR VA ERUPTION MT "
            f"SEMERU PSN S0806 E11255 VA CLD OBS AT 1010Z WI {polygon_text} - S0818 E11306 "
            "SFC/FL150 MOV NE 05KT NC="
        ),
    )
    vona = make_vona(issued_at=utc(2026, 10, 7, 11, 22), notice="2026SMR1902", ash=False)
    at = utc(2026, 10, 7, 11, 30)

    found = find_discrepancies(
        SEMERU, sigmets=[sigmet], vonas=[vona], vaas=[], at=at, settings=SETTINGS
    )

    assert {d.kind for d in found} == {DiscrepancyKind.LAG, DiscrepancyKind.SILENCE}
    lag = next(d for d in found if d.kind is DiscrepancyKind.LAG)
    assert lag.magnitude == 72
    assert set(lag.source_ids) == {sigmet.provenance.source_id, vona.provenance.source_id}
    assert "not a conflict" in lag.summary
    silence = next(d for d in found if d.kind is DiscrepancyKind.SILENCE)
    assert silence.source_ids == [sigmet.provenance.source_id]
    assert evidence_state(vona, SEMERU, at) is EvidenceState.NIGHT_BLIND
    assert evidence_state(sigmet, SEMERU, at) is EvidenceState.OBSERVED_SAT
    daylight = make_vona(issued_at=utc(2026, 10, 7, 3, 55), notice="2026SMR1900", ash=False)
    assert evidence_state(daylight, SEMERU, utc(2026, 10, 7, 4, 0)) is EvidenceState.NOT_OBSERVED


# --- one source twice: SIGMET echoing a VAA polygon -------------------------------------

DARWIN_1157_POLYGON = "S0803 E11253 - S0754 E11316 - S0807 E11324 - S0820 E11318 - S0811 E11253"


def darwin_1157() -> VaacAdvisory:
    observation = VaacStep(
        offset_h=0,
        valid_at=utc(2026, 10, 9, 18, 0),
        layers=[
            VaLayer(
                base_ft=0,
                top_ft=15000,
                polygon=ring(DARWIN_1157_POLYGON),
                movement_toward_deg=90,
                movement_speed_kt=10,
            )
        ],
        text=f"OBS VA CLD: SFC/FL150 {DARWIN_1157_POLYGON} MOV E 10KT",
    )
    return make_vaa(
        number="2026/1157",
        issued_at=utc(2026, 10, 9, 18, 20),
        observation=observation,
        next_advisory_at=utc(2026, 10, 10, 0, 20),
    )


def echoing_sigmet() -> Sigmet:
    # The AWC JSON carries 3-decimal coordinates and closes the ring the VAA leaves open.
    return make_sigmet(
        series="12",
        valid_from=utc(2026, 10, 9, 18, 20),
        valid_to=utc(2026, 10, 10, 0, 20),
        observed_at=utc(2026, 10, 9, 18, 0),
        polygon=ring(DARWIN_1157_POLYGON, decimals=3),
        toward_deg=90,
        speed_kt=10,
        raw="WAAF SIGMET 12 VALID 091820/100020 ... VA ERUPTION MT SEMERU ... MOV E 10KT NC=",
    )


def test_sigmet_echoing_a_vaa_is_one_source() -> None:
    at = utc(2026, 10, 9, 19, 40)
    not_seen = make_vona(issued_at=utc(2026, 10, 9, 18, 0), notice="2026SMR1910", ash=False)
    found = find_discrepancies(
        SEMERU,
        sigmets=[echoing_sigmet()],
        vonas=[not_seen],
        vaas=[darwin_1157()],
        at=at,
        settings=SETTINGS,
    )
    assert found == []


def test_discrepancy_against_an_echo_names_both_products() -> None:
    sigmet, vaa = echoing_sigmet(), darwin_1157()
    vona = make_vona(
        issued_at=utc(2026, 10, 9, 18, 30),
        notice="2026SMR1911",
        ash=True,
        top_m=4376,
        toward_deg=0,
        direction_text="Ash cloud moving to north",
    )
    found = find_discrepancies(
        SEMERU,
        sigmets=[sigmet],
        vonas=[vona],
        vaas=[vaa],
        at=utc(2026, 10, 9, 19, 0),
        settings=SETTINGS,
    )
    direction = kinds(found)[DiscrepancyKind.DIRECTION_MISMATCH, "direction"]
    assert set(direction.source_ids) == {
        sigmet.provenance.source_id,
        vaa.provenance.source_id,
        vona.provenance.source_id,
    }
    assert "SIGMET WAAF 12 = VAA DARWIN 2026/1157" in direction.summary
    assert not any(
        set(d.source_ids) == {sigmet.provenance.source_id, vaa.provenance.source_id} for d in found
    )


# --- CONFLICT needs an explicit negative ------------------------------------------------


def test_conflict_when_vaa_says_no_ash_and_a_vona_then_reports_ash() -> None:
    dissipated = make_vaa(
        number="2026/1200",
        issued_at=utc(2026, 10, 12, 12, 0),
        observation=VaacStep(offset_h=0, valid_at=utc(2026, 10, 12, 11, 50), text="VA DISSIPATED"),
        forecasts=[
            VaacStep(
                offset_h=6,
                valid_at=utc(2026, 10, 12, 17, 50),
                no_ash_expected=True,
                text="NO VA EXP",
            )
        ],
        final=True,
    )
    vona = make_vona(
        issued_at=utc(2026, 10, 12, 12, 20), notice="2026SMR1950", ash=True, top_m=4376
    )
    at = utc(2026, 10, 12, 12, 30)
    found = find_discrepancies(
        SEMERU, sigmets=[], vonas=[vona], vaas=[dissipated], at=at, settings=SETTINGS
    )
    conflict = kinds(found)[DiscrepancyKind.CONFLICT, "ash_observed"]
    assert conflict.magnitude == 30  # VONA 30 min after the VAA observation step
    assert evidence_state(dissipated, SEMERU, at) is EvidenceState.NO_VA_EXPECTED


def test_not_identifiable_final_vaa_is_never_a_conflict() -> None:
    """Sakurajima 2026/249 style: "VA NOT IDENTIFIABLE FM SATELLITE DATA ... NO FURTHER
    ADVISORIES" is a VAAC that could not see the ash, not an all-clear."""
    blind = make_vaa(
        number="2026/1201",
        issued_at=utc(2026, 10, 12, 12, 0),
        observation=VaacStep(
            offset_h=0,
            valid_at=utc(2026, 10, 12, 11, 50),
            not_identifiable=True,
            text="VA NOT IDENTIFIABLE FM SATELLITE DATA",
        ),
        final=True,
    )
    vona = make_vona(
        issued_at=utc(2026, 10, 12, 12, 20), notice="2026SMR1951", ash=True, top_m=4376
    )
    at = utc(2026, 10, 12, 12, 30)
    found = find_discrepancies(
        SEMERU, sigmets=[], vonas=[vona], vaas=[blind], at=at, settings=SETTINGS
    )
    assert all(d.kind is not DiscrepancyKind.CONFLICT for d in found)
    assert evidence_state(blind, SEMERU, at) is EvidenceState.NOT_IDENTIFIABLE


# --- tolerances, silence, ids -----------------------------------------------------------


def test_height_tolerance_separates_envelope_from_mismatch() -> None:
    """26 Sep 2255Z: 4976 m (16,325 ft) against SFC/FL150 is 1,325 ft above the top."""
    vona = make_vona(issued_at=utc(2026, 9, 23, 22, 21), notice="2026SMR1830", ash=True, top_m=4976)
    at = utc(2026, 9, 23, 23, 0)
    default = kinds(
        find_discrepancies(
            SEMERU, sigmets=[SIGMET_11], vonas=[vona], vaas=[], at=at, settings=SETTINGS
        )
    )
    assert default[DiscrepancyKind.ENVELOPE, "top"].magnitude == 1325
    strict = Settings(_env_file=None, height_tolerance_ft=1000)
    tight = kinds(
        find_discrepancies(
            SEMERU, sigmets=[SIGMET_11], vonas=[vona], vaas=[], at=at, settings=strict
        )
    )
    assert tight[DiscrepancyKind.HEIGHT_MISMATCH, "top"].magnitude == 1325


def test_direction_and_lag_tolerances_come_from_settings() -> None:
    at = utc(2026, 9, 23, 23, 0)
    loose = Settings(_env_file=None, direction_tolerance_deg=100, lag_threshold_min=400)
    found = kinds(
        find_discrepancies(
            SEMERU, sigmets=[SIGMET_11], vonas=[VONA_1806], vaas=[], at=at, settings=loose
        )
    )
    assert (DiscrepancyKind.DIRECTION_MISMATCH, "direction") not in found
    assert (DiscrepancyKind.LAG, "time") not in found


def test_overdue_vaa_is_silence() -> None:
    vaa = darwin_1157()
    found = find_discrepancies(
        SEMERU,
        sigmets=[echoing_sigmet()],
        vonas=[],
        vaas=[vaa],
        at=utc(2026, 10, 10, 0, 45),
        settings=SETTINGS,
    )
    overdue = kinds(found)[DiscrepancyKind.SILENCE, "presence"]
    assert overdue.source_ids == [vaa.provenance.source_id]
    assert overdue.magnitude == 25
    assert "overdue" in overdue.summary


def test_ids_are_stable_and_short() -> None:
    at = utc(2026, 9, 23, 23, 0)

    def run() -> list[str]:
        found = find_discrepancies(
            SEMERU, sigmets=[SIGMET_11], vonas=[VONA_1806], vaas=[], at=at, settings=SETTINGS
        )
        return [d.id for d in found]

    first = run()
    assert first == run()
    assert len(set(first)) == len(first)
    assert all(re.fullmatch(r"D-[0-9a-f]{8}", identifier) for identifier in first)


def test_results_are_ordered_by_severity() -> None:
    found = find_discrepancies(
        SEMERU,
        sigmets=[SIGMET_11],
        vonas=[VONA_1806],
        vaas=[],
        at=utc(2026, 9, 23, 23, 0),
        settings=SETTINGS,
    )
    ranks = {"WARNING": 0, "CAUTION": 1, "INFO": 2}
    severities = [ranks[d.severity.value] for d in found]
    assert severities == sorted(severities)


# --- activity, record selection, situation ----------------------------------------------


def test_named_sigmet_activates_only_its_volcano() -> None:
    catalogue = VolcanoCatalogue([SEMERU, BROMO])
    at = utc(2026, 9, 23, 23, 0)
    active = find_active(
        catalogue, sigmets=[SIGMET_11], vonas=[VONA_1806], vaas=[], at=at, settings=SETTINGS
    )
    assert list(active) == [SEMERU.id]
    assert any("SIGMET WAAF 11" in reason for reason in active[SEMERU.id])
    assert any("VONA 2026SMR1806" in reason for reason in active[SEMERU.id])

    sigmets, vonas, vaas = select_records(
        catalogue,
        BROMO,
        sigmets=[SIGMET_11],
        vonas=[VONA_1806],
        vaas=[],
        at=at,
        settings=SETTINGS,
    )
    assert (sigmets, vonas, vaas) == ([], [], [])


def test_unnamed_sigmet_goes_to_the_nearest_vent_within_the_radius() -> None:
    catalogue = VolcanoCatalogue([SEMERU, BROMO])
    unnamed = SIGMET_11.model_copy(
        update={
            "volcano_name": None,
            "raw_text": "WAAF SIGMET 11 VALID 231725/232325 VA CLD OBS AT 1700Z SFC/FL150=",
            "polygon": ring("S0754 E11255 - S0754 E11259 - S0758 E11259 - S0758 E11255"),
        }
    )
    at = utc(2026, 9, 23, 23, 0)
    active = find_active(catalogue, sigmets=[unnamed], vonas=[], vaas=[], at=at, settings=SETTINGS)
    assert list(active) == [BROMO.id]
    assert "km from the vent" in active[BROMO.id][0]


def test_select_records_keeps_window_and_newest_vaa() -> None:
    catalogue = VolcanoCatalogue([SEMERU, BROMO])
    at = utc(2026, 10, 9, 19, 40)
    older = darwin_1157().model_copy(
        update={
            "advisory_nr": "2026/1156",
            "issued_at": utc(2026, 10, 9, 12, 20),
            "provenance": provenance(
                make_source_id("VAA", "DARWIN", SEMERU.id, "2026/1156"),
                FeedId.VAAC_DARWIN,
                utc(2026, 10, 9, 12, 20),
            ),
        }
    )
    stale_vona = make_vona(issued_at=utc(2026, 10, 8, 12, 0), notice="2026SMR1890", ash=True)
    fresh_vona = make_vona(issued_at=utc(2026, 10, 9, 18, 0), notice="2026SMR1910", ash=False)
    expired = SIGMET_11
    sigmets, vonas, vaas = select_records(
        catalogue,
        SEMERU,
        sigmets=[echoing_sigmet(), expired],
        vonas=[stale_vona, fresh_vona],
        vaas=[older, darwin_1157()],
        at=at,
        settings=SETTINGS,
    )
    assert [s.series_id for s in sigmets] == ["12"]
    assert vonas == [fresh_vona]
    assert [v.advisory_nr for v in vaas] == ["2026/1157"]


def test_build_situation_sets_floor_discrepancies_and_winds() -> None:
    at = utc(2026, 9, 23, 23, 0)
    winds = [
        WindProfile(
            provenance=provenance(
                f"WINDS:-8.11:112.92:{compact(at + timedelta(hours=offset))}", FeedId.WINDS, at
            ),
            lat=-8.11,
            lon=112.92,
            valid_at=at + timedelta(hours=offset),
            levels=[WindLevel(pressure_hpa=600, flight_level=140, speed_kt=18, from_deg=313)],
        )
        for offset in (-3, 0, 1, 30)
    ]
    situation = build_situation(
        SEMERU,
        active_reasons=["test"],
        sigmets=[SIGMET_11],
        vonas=[VONA_1806],
        vaas=[],
        winds=winds,
        frames=[],
        btd=None,
        at=at,
        mode=RunMode.REPLAY,
        settings=SETTINGS,
    )
    assert situation.official_valid_now()
    assert situation.official_top_ft() == 15000
    assert [p.valid_at for p in situation.winds] == [at, at + timedelta(hours=1)]
    assert situation.discrepancies == find_discrepancies(
        SEMERU, sigmets=[SIGMET_11], vonas=[VONA_1806], vaas=[], at=at, settings=SETTINGS
    )


@pytest.mark.parametrize(
    ("hours_after", "expected"),
    [(0.5, EvidenceState.OBSERVED_SAT), (7.5, EvidenceState.STALE)],
)
def test_vaa_evidence_goes_stale_after_validity(
    hours_after: float, expected: EvidenceState
) -> None:
    vaa = darwin_1157()
    at = vaa.issued_at + timedelta(hours=hours_after)
    assert evidence_state(vaa, SEMERU, at) is expected


# --- census findings (research/14, 9 Sep to 9 Oct 2026) ---------------------------------


def test_a_sigmet_on_the_far_side_of_the_globe_is_not_near_a_vent() -> None:
    """SEFG A5, 20 Sep: Ecuador's Sangay sits 180 degrees of longitude from Kerinci. One
    vertex unwrapped across the antimeridian, the ring spanned the globe, and the SIGMET read
    as "polygon 30 km from the vent" of Kerinci (14 Sangay SIGMETs did this in 30 days)."""
    polygon_text = "S0149 W07844 - S0200 W07820 - S0201 W07819 - S0210 W07816 - S0217 W07840"
    sangay = make_sigmet(
        series="A5",
        fir="SEFG",
        volcano_name="SANGAY",
        valid_from=utc(2026, 9, 20, 21, 33),
        valid_to=utc(2026, 9, 21, 3, 33),
        observed_at=utc(2026, 9, 20, 20, 30),
        polygon=ring(f"{polygon_text} - S0207 W07852"),
        toward_deg=225,
        speed_kt=5,
        top_ft=26000,
        raw=(
            "WVEQ31 SEQU 202133 SEFG SIGMET A5 VALID 202133/210333 SEGU- SEFG GUAYAQUIL FIR "
            f"VA ERUPTION MT SANGAY PSN S0200 W07820 VA CLD OBS AT 2030Z WI {polygon_text} - "
            "S0207 W07852 - S0149 W07844 SFC/FL260 MOV SW 5KT="
        ),
    )
    catalogue = VolcanoCatalogue([SEMERU, KERINCI])
    at = utc(2026, 9, 20, 22, 0)

    assert (
        find_active(catalogue, sigmets=[sangay], vonas=[], vaas=[], at=at, settings=SETTINGS) == {}
    )
    chosen = select_records(
        catalogue, KERINCI, sigmets=[sangay], vonas=[], vaas=[], at=at, settings=SETTINGS
    )
    assert chosen == ([], [], [])


MARAPI_80_RAW = (
    "VA ADVISORY DTG: 20260926/2158Z VAAC: DARWIN VOLCANO: MARAPI 261140 ADVISORY NR: 2026/80 "
    "EST VA DTG: 26/2140Z EST VA CLD: VA NOT IDENTIFIABLE FM SATELLITE DATA WIND SFC/FL120 "
    "180/10KT FCST VA CLD +6 HR: 27/0340Z NO VA EXP ... RMK: VA NOT IDENTIFIABLE ON RECENT "
    "SATELLITE IMAGERY DUE TO OBSCURATION BY MET CLOUD. ADVISORY WILL BE UPDATED IF NEW "
    "INFORMATION IS RECEIVED. NXT ADVISORY: NO FURTHER ADVISORIES="
)
TAAL_29_RAW = (
    "VA ADVISORY DTG: 20261008/1810Z VAAC: DARWIN VOLCANO: TAAL 273070 ADVISORY NR: 2026/29 "
    "OBS VA DTG: 08/1810Z OBS VA CLD: FCST VA CLD +6 HR: 09/0010Z NOT PROVIDED ... RMK: PLEASE "
    "SEE FVFE01 RJTD 081750 ISSUED BY VAAC TOKYO WHICH DESCRIBES CONDITIONS OVER OR NEAR THE "
    "VAAC DARWIN AREA OF RESPONSIBILITY. NXT ADVISORY: NO FURTHER ADVISORIES="
)


def closing_vaa(kind: str, issued_at: datetime) -> VaacAdvisory:
    """Darwin's two closing shapes that say nothing about whether ash is there."""
    obs_at = issued_at - timedelta(minutes=18)
    if kind == "met_cloud":  # Marapi 2026/80: the template adds NO VA EXP forecasts
        observation = VaacStep(
            offset_h=0,
            valid_at=obs_at,
            estimated=True,
            not_identifiable=True,
            text="VA NOT IDENTIFIABLE FM SATELLITE DATA WIND SFC/FL120 180/10KT",
        )
        step = {"no_ash_expected": True, "text": "NO VA EXP"}
        raw = MARAPI_80_RAW
    else:  # Taal 2026/29: a hand-over notice with a blank cloud field
        observation = VaacStep(offset_h=0, valid_at=obs_at, text="")
        step = {"not_available": True, "text": "NOT PROVIDED"}
        raw = TAAL_29_RAW
    forecasts = [
        VaacStep(offset_h=hours, valid_at=obs_at + timedelta(hours=hours), **step)
        for hours in (6, 12, 18)
    ]
    return make_vaa(
        number="2026/1290",
        issued_at=issued_at,
        observation=observation,
        forecasts=forecasts,
        final=True,
        raw=raw,
    )


@pytest.mark.parametrize(
    ("kind", "state"),
    [
        ("met_cloud", EvidenceState.NOT_IDENTIFIABLE),
        ("hand_over", EvidenceState.FORECAST_NOT_AVAILABLE),
    ],
)
def test_a_closing_vaa_that_saw_no_ash_is_never_a_conflict(kind: str, state: EvidenceState) -> None:
    """Census: every Darwin closing advisory reads "VA NOT IDENTIFIABLE" and fills its
    forecasts with NO VA EXP, met cloud or not; hand-over notices carry no cloud at all.
    Neither is an all-clear, so an ash VONA 20 minutes later is not a CONFLICT (it was one
    on 13 Sep for Manam 2026/29 against SIGMET AYPM V2)."""
    vaa = closing_vaa(kind, utc(2026, 10, 12, 12, 0))
    vona = make_vona(
        issued_at=utc(2026, 10, 12, 12, 20), notice="2026SMR1960", ash=True, top_m=4376
    )
    at = utc(2026, 10, 12, 12, 30)
    found = find_discrepancies(
        SEMERU, sigmets=[], vonas=[vona], vaas=[vaa], at=at, settings=SETTINGS
    )
    assert all(d.kind is not DiscrepancyKind.CONFLICT for d in found)
    assert evidence_state(vaa, SEMERU, at) is state


def test_an_ash_vona_under_a_vaa_in_force_is_lag_not_silence() -> None:
    """Census: Darwin re-issues Semeru every 6 h and reflects a new VONA a median 228 min
    later. With a VAA in force the VAAC is not silent; the gap is a LAG (it was a SILENCE
    warning in 137 of Semeru's 721 active hours)."""
    vona = make_vona(
        issued_at=utc(2026, 10, 9, 21, 0),
        notice="2026SMR1912",
        ash=True,
        top_m=4176,
        toward_deg=90,
        direction_text="Ash cloud moving to east",
    )
    found = find_discrepancies(
        SEMERU,
        sigmets=[echoing_sigmet()],
        vonas=[vona],
        vaas=[darwin_1157()],
        at=utc(2026, 10, 9, 22, 30),
        settings=SETTINGS,
    )
    by_kind = kinds(found)
    assert DiscrepancyKind.SILENCE not in {d.kind for d in found}
    assert by_kind[DiscrepancyKind.LAG, "time"].magnitude == 180  # OBS 1800Z vs VONA 2100Z


def test_an_ash_vona_after_the_vaac_closed_the_event_is_silence() -> None:
    """The onset case the census counts (Karangetang 30 Sep, Sinabung 1 Oct): ash reported
    and no VAA in force or issued since."""
    vaa = closing_vaa("met_cloud", utc(2026, 10, 12, 6, 0))
    vona = make_vona(
        issued_at=utc(2026, 10, 12, 12, 20), notice="2026SMR1961", ash=True, top_m=4376
    )
    found = find_discrepancies(
        SEMERU, sigmets=[], vonas=[vona], vaas=[vaa], at=utc(2026, 10, 12, 13, 0), settings=SETTINGS
    )
    silence = kinds(found)[DiscrepancyKind.SILENCE, "presence"]
    assert silence.source_ids == [vona.provenance.source_id]
    assert silence.magnitude == 40


def sakurajima_249() -> VaacAdvisory:
    return make_vaa(
        number="2026/249",
        issued_at=utc(2026, 9, 25, 12, 52),
        observation=VaacStep(
            offset_h=0,
            valid_at=utc(2026, 9, 25, 12, 30),
            not_identifiable=True,
            text="VA NOT IDENTIFIABLE FM SATELLITE DATA WIND FL080 240/11KT",
        ),
        forecasts=[
            VaacStep(
                offset_h=hours,
                valid_at=utc(2026, 9, 25, 12, 30) + timedelta(hours=hours),
                not_available=True,
                text="NOT AVBL",
            )
            for hours in (6, 12, 18)
        ],
        final=True,
        volcano=SAKURAJIMA,
        vaac=VaacCentre.TOKYO,
        raw="FVFE01 RJTD 251252 VA ADVISORY ... ADVISORY NR: 2026/249 ... NO FURTHER ADVISORIES=",
    )


def test_a_sigmet_left_open_after_the_vaac_closed_the_event_is_not_silence() -> None:
    """research/13 and /14 section 4.5: Tokyo closes Sakurajima 2026/249 ("VA NOT
    IDENTIFIABLE ... NO FURTHER ADVISORIES") and RJJJ B01 stays valid for six hours, as in
    67 of 71 Sakurajima cases. The VAAC spoke; B01 outliving it is not a silent VAAC."""
    b01 = make_sigmet(
        series="B01",
        fir="RJJJ",
        volcano_name="SAKURAJIMA (AIRA CALDERA)",
        valid_from=utc(2026, 9, 25, 12, 57),
        valid_to=utc(2026, 9, 25, 18, 57),
        observed_at=utc(2026, 9, 25, 12, 36),
        polygon=None,
        toward_deg=90,
        speed_kt=None,
        top_ft=8000,
        raw=(
            "WVJP31 RJTD 251257 RJJJ SIGMET B01 VALID 251257/251857 RJTD- RJJJ FUKUOKA FIR VA "
            "ERUPTION MT SAKURAJIMA (AIRA CALDERA) PSN N3136 E13039 VA CLD OBS AT 1236Z FL080 "
            "MOV E="
        ),
    )
    found = find_discrepancies(
        SAKURAJIMA,
        sigmets=[b01],
        vonas=[],
        vaas=[sakurajima_249()],
        at=utc(2026, 9, 25, 15, 0),
        settings=SETTINGS,
    )
    assert all(d.kind is not DiscrepancyKind.SILENCE for d in found)


LEWOTOLOK_15_POLYGON = "S0819 E12328 - S0810 E12321 - S0801 E12324 - S0801 E12335 - S0819 E12332"


def lewotolok_15() -> Sigmet:
    """The live run of 10 Oct 2026: WAAF 15 was in force while the Darwin poller saw no VAA."""
    return make_sigmet(
        series="15",
        volcano_name="LEWOTOLOK",
        valid_from=utc(2026, 10, 9, 23, 10),
        valid_to=utc(2026, 10, 10, 5, 10),
        observed_at=utc(2026, 10, 9, 22, 50),
        polygon=ring(LEWOTOLOK_15_POLYGON),
        toward_deg=0,
        speed_kt=5,
        top_ft=7000,
        raw=(
            "WVID21 WAAA 092310 WAAF SIGMET 15 VALID 092310/100510 WAAA- WAAF UJUNG PANDANG FIR "
            f"VA ERUPTION MT LEWOTOLOK PSN S0816 E12330 VA CLD OBS AT 2250Z WI "
            f"{LEWOTOLOK_15_POLYGON} - S0819 E12328 SFC/FL070 MOV N 05KT NC="
        ),
    )


def darwin_health(status: FeedStatus, last_success_at: datetime | None) -> dict[FeedId, FeedHealth]:
    return {
        FeedId.VAAC_DARWIN: FeedHealth(
            feed=FeedId.VAAC_DARWIN,
            status=status,
            cadence_s=SETTINGS.cadence_s(FeedId.VAAC_DARWIN),
            last_attempt_at=last_success_at,
            last_success_at=last_success_at,
        )
    }


LEWOTOLOK_AT = utc(2026, 10, 10, 4, 51)


@pytest.mark.parametrize(
    ("status", "last_success_at"),
    [
        (FeedStatus.ERROR, utc(2026, 10, 10, 2, 0)),
        (FeedStatus.STALE, utc(2026, 10, 10, 4, 10)),
        (FeedStatus.NEVER, None),
        (FeedStatus.OK, utc(2026, 10, 10, 4, 0)),  # OK once, but not for 51 minutes
    ],
)
def test_no_silence_while_the_vaa_feed_is_degraded(
    status: FeedStatus, last_success_at: datetime | None
) -> None:
    """A polling gap is not a silent VAAC: with the Darwin feed failing or stale, say nothing."""
    found = find_discrepancies(
        LEWOTOLOK,
        sigmets=[lewotolok_15()],
        vonas=[],
        vaas=[],
        at=LEWOTOLOK_AT,
        settings=SETTINGS,
        feed_health=darwin_health(status, last_success_at),
    )
    assert all(d.kind is not DiscrepancyKind.SILENCE for d in found)


def test_silence_needs_a_healthy_feed_that_saw_no_vaa() -> None:
    health = darwin_health(FeedStatus.OK, LEWOTOLOK_AT - timedelta(minutes=2))
    found = find_discrepancies(
        LEWOTOLOK,
        sigmets=[lewotolok_15()],
        vonas=[],
        vaas=[],
        at=LEWOTOLOK_AT,
        settings=SETTINGS,
        feed_health=health,
    )
    silence = kinds(found)[DiscrepancyKind.SILENCE, "presence"]
    assert silence.magnitude == 5 * 60 + 41
    situation = build_situation(
        LEWOTOLOK,
        active_reasons=["test"],
        sigmets=[lewotolok_15()],
        vonas=[],
        vaas=[],
        winds=[],
        frames=[],
        btd=None,
        at=LEWOTOLOK_AT,
        mode=RunMode.LIVE,
        settings=SETTINGS,
        feed_health=darwin_health(FeedStatus.ERROR, LEWOTOLOK_AT - timedelta(hours=1)),
    )
    assert situation.discrepancies == []


def marapi(number: str, *, final: bool) -> VaacAdvisory:
    """Darwin issued Marapi 2026/82 and 2026/83 with one DTG; 83 closed what 82 opened."""
    obs_at = utc(2026, 9, 29, 17, 10)
    return make_vaa(
        number=number,
        issued_at=utc(2026, 9, 29, 17, 30),
        observation=VaacStep(
            offset_h=0, valid_at=obs_at, estimated=True, not_identifiable=True, text="VA NOT ID"
        ),
        forecasts=[
            VaacStep(
                offset_h=hours,
                valid_at=obs_at + timedelta(hours=hours),
                no_ash_expected=True,
                text="NO VA EXP",
            )
            for hours in (6, 12, 18)
        ],
        next_advisory_at=None if final else utc(2026, 9, 29, 23, 30),
        final=final,
        volcano=MARAPI,
    )


@pytest.mark.parametrize("order", ["82_first", "83_first"])
def test_of_two_vaas_with_one_dtg_the_higher_number_is_newest(order: str) -> None:
    """Census, 30 Sep: with 2026/82 read as the newest, Marapi showed "next advisory overdue"
    for 11 hours after 2026/83 had ended the advisories."""
    vaas = [marapi("2026/82", final=False), marapi("2026/83", final=True)]
    if order == "83_first":
        vaas.reverse()
    at = utc(2026, 9, 30, 1, 0)
    found = find_discrepancies(MARAPI, sigmets=[], vonas=[], vaas=vaas, at=at, settings=SETTINGS)
    assert all(d.kind is not DiscrepancyKind.SILENCE for d in found)
    catalogue = VolcanoCatalogue([SEMERU, MARAPI])
    _, _, chosen = select_records(
        catalogue, MARAPI, sigmets=[], vonas=[], vaas=vaas, at=at, settings=SETTINGS
    )
    assert [vaa.advisory_nr for vaa in chosen] == ["2026/83"]
    # 2026/83 ended the advisories at 1730Z (in force to 1830Z); 2026/82 no longer counts.
    evening = utc(2026, 9, 29, 21, 0)
    assert (
        find_active(catalogue, sigmets=[], vonas=[], vaas=vaas, at=evening, settings=SETTINGS) == {}
    )


def test_a_sigmet_and_the_one_replacing_it_are_not_a_disagreement() -> None:
    """Census, 8 Oct 0020Z: WAAF 01 (= Darwin 2026/1150, MOV W) started two minutes before
    WAAF 26 (MOV NE) ended. AWC relays no CNL, so the two overlap at every hand-over (143
    times in 30 days); the pair read as a 135-degree DIRECTION_MISMATCH exactly when the new
    SIGMET changed the inputs and opened the quota gate."""
    old_text = "S0806 E11249 - S0736 E11311 - S0741 E11331 - S0802 E11333 - S0816 E11301"
    new_text = (
        "S0824 E11249 - S0817 E11234 - S0803 E11235 - S0748 E11304 - S0755 E11318 - S0811 E11318"
    )
    waaf_26 = make_sigmet(
        series="26",
        valid_from=utc(2026, 10, 7, 22, 30),
        valid_to=utc(2026, 10, 8, 0, 22),
        observed_at=utc(2026, 10, 7, 22, 10),
        polygon=ring(old_text),
        toward_deg=45,
        speed_kt=5,
        raw=f"WAAF SIGMET 26 VALID 072230/080430 ... SEMERU ... WI {old_text} SFC/FL150 MOV NE",
    )
    waaf_01 = make_sigmet(
        series="01",
        valid_from=utc(2026, 10, 8, 0, 20),
        valid_to=utc(2026, 10, 8, 6, 20),
        observed_at=utc(2026, 10, 8, 0, 0),
        polygon=ring(new_text, decimals=3),
        toward_deg=270,
        speed_kt=5,
        raw=f"WAAF SIGMET 01 VALID 080020/080620 ... SEMERU ... WI {new_text} SFC/FL150 MOV W 05KT",
    )
    darwin_1150 = make_vaa(
        number="2026/1150",
        issued_at=utc(2026, 10, 8, 0, 20),
        observation=VaacStep(
            offset_h=0,
            valid_at=utc(2026, 10, 8, 0, 0),
            layers=[
                VaLayer(
                    base_ft=0,
                    top_ft=15000,
                    polygon=ring(new_text),
                    movement_toward_deg=270,
                    movement_speed_kt=5,
                )
            ],
            text=f"OBS VA CLD: SFC/FL150 {new_text} MOV W 05KT",
        ),
        next_advisory_at=utc(2026, 10, 8, 6, 20),
    )
    found = find_discrepancies(
        SEMERU,
        sigmets=[waaf_26, waaf_01],
        vonas=[],
        vaas=[darwin_1150],
        at=utc(2026, 10, 8, 0, 21),
        settings=SETTINGS,
    )
    assert found == []


def test_two_clouds_of_one_sigmet_are_not_a_disagreement() -> None:
    """WAAF 05, 26 Sep (Dukono): one SIGMET, two clouds ("... MOV NE 05KT NC AND OBS AT 0700Z
    WI ... SFC/FL150 MOV W 15KT"), which feeds-text keeps as 05 and 05 AREA 2."""
    dukono = SEMERU.model_copy(
        update={
            "id": "268010",
            "name": "Dukono",
            "aliases": ["DUKONO"],
            "lat": 1.693,
            "lon": 127.894,
        }
    )
    first = "N0130 E12757 - N0139 E12734 - N0235 E12716 - N0257 E12803 - N0211 E12903"
    second = "N0135 E12714 - N0133 E12709 - N0141 E12707 - N0143 E12713"
    raw = (
        "WAAF SIGMET 05 VALID 260720/261320 ... DUKONO ... VA CLD OBS AT 0700Z WI "
        f"{first} SFC/FL070 MOV NE 05KT NC AND OBS AT 0700Z WI {second} SFC/FL150 MOV W 15KT WKN="
    )
    common = {
        "valid_from": utc(2026, 9, 26, 7, 20),
        "valid_to": utc(2026, 9, 26, 13, 20),
        "observed_at": utc(2026, 9, 26, 7, 0),
        "volcano_name": "DUKONO",
        "raw": raw,
    }
    area_1 = make_sigmet(
        series="05", polygon=ring(first), toward_deg=45, speed_kt=5, top_ft=7000, **common
    )
    area_2 = make_sigmet(
        series="05 AREA 2", polygon=ring(second), toward_deg=270, speed_kt=15, **common
    )
    found = find_discrepancies(
        dukono,
        sigmets=[area_1, area_2],
        vonas=[],
        vaas=[],
        at=utc(2026, 9, 26, 10, 20),
        settings=SETTINGS,
    )
    assert all(d.kind in {DiscrepancyKind.SILENCE} for d in found)


def test_a_sigmet_reissued_for_an_eruption_the_vaac_closed_is_not_silence() -> None:
    """Census, 23 Sep (Mayon): Tokyo 2026/795 answered and closed the 0212Z eruption at
    0230Z; RPHI re-issued it at 0621Z as SIGMET 5 ("VA CLD OBS AT 0212Z")."""
    mayon = SAKURAJIMA.model_copy(
        update={"id": "273030", "name": "Mayon", "aliases": ["MAYON"], "lat": 13.257}
    )
    closing = make_vaa(
        number="2026/795",
        issued_at=utc(2026, 9, 23, 2, 30),
        observation=VaacStep(
            offset_h=0,
            valid_at=utc(2026, 9, 23, 2, 12),
            not_identifiable=True,
            text="VA NOT IDENTIFIABLE FM SATELLITE DATA",
        ),
        final=True,
        volcano=mayon,
        vaac=VaacCentre.TOKYO,
    )
    rphi_5 = make_sigmet(
        series="5",
        fir="RPHI",
        volcano_name="MAYON",
        valid_from=utc(2026, 9, 23, 6, 21),
        valid_to=utc(2026, 9, 23, 12, 21),
        observed_at=utc(2026, 9, 23, 2, 12),
        polygon=None,
        toward_deg=None,
        speed_kt=None,
        raw="WVPH31 RPLL 230621 RPHI SIGMET 5 VALID 230621/231221 RPLL- RPHI MANILA FIR VA "
        "ERUPTION MT MAYON PSN N1315 E12341 VA CLD OBS AT 0212Z=",
    )
    found = find_discrepancies(
        mayon,
        sigmets=[rphi_5],
        vonas=[],
        vaas=[closing],
        at=utc(2026, 9, 23, 8, 0),
        settings=SETTINGS,
    )
    assert all(d.kind is not DiscrepancyKind.SILENCE for d in found)


def test_a_sigmet_reissued_under_a_new_number_replaces_the_old_one() -> None:
    """Census, 28 Sep 2240Z (Dukono): WAAF issued the same two-cloud SIGMET as 14 and then
    as 16; AWC cut 14 short at 2320Z. Until then their clouds were compared crosswise."""
    dukono = SEMERU.model_copy(
        update={"id": "268010", "name": "Dukono", "aliases": ["DUKONO"], "lon": 127.894}
    )
    first = "N0135 E12752 - N0148 E12747 - N0203 E12751 - N0200 E12812 - N0137 E12815"
    second = "N0141 E12740 - N0139 E12733 - N0146 E12731 - N0148 E12738"

    def copy(series: str, valid_to: datetime) -> list[Sigmet]:
        common = {
            "valid_from": utc(2026, 9, 28, 22, 40),
            "valid_to": valid_to,
            "observed_at": utc(2026, 9, 28, 22, 20),
            "volcano_name": "DUKONO",
            "raw": f"WAAF SIGMET {series} VALID 282240/290440 ... DUKONO ... WI {first} "
            f"SFC/FL070 MOV NE 05KT NC AND OBS AT 2220Z WI {second} SFC/FL120 MOV W 10KT",
        }
        return [
            make_sigmet(
                series=series, polygon=ring(first), toward_deg=45, speed_kt=5, top_ft=7000, **common
            ),
            make_sigmet(
                series=f"{series} AREA 2",
                polygon=ring(second),
                toward_deg=270,
                speed_kt=10,
                top_ft=12000,
                **common,
            ),
        ]

    sigmets = [*copy("14", utc(2026, 9, 28, 23, 20)), *copy("16", utc(2026, 9, 29, 4, 40))]
    found = find_discrepancies(
        dukono, sigmets=sigmets, vonas=[], vaas=[], at=utc(2026, 9, 28, 23, 0), settings=SETTINGS
    )
    assert found == []


# --- whole census snapshots through the real parsers ------------------------------------


def census_records(volcano_name: str, snapshot: str, at: datetime) -> tuple[Volcano, list[Sigmet]]:
    """One volcano's SIGMETs at ``at`` from a saved AWC snapshot, chosen as the pipeline does."""
    content = (FEEDS_TEXT / snapshot).read_bytes()
    result = FetchResult(
        feed=FeedId.SIGMET,
        url=SIGMET_URL,
        status_code=200,
        content=content,
        content_type="application/json",
        fetched_at=at,
        sha256=sha256_bytes(content),
    )
    valid = [sigmet for sigmet in parse_sigmets(result) if sigmet.valid_to >= at]
    catalogue = load_volcanoes(SETTINGS.data_dir)
    volcano = catalogue.resolve(volcano_name)
    assert volcano is not None
    chosen, _, _ = select_records(
        catalogue, volcano, sigmets=valid, vonas=[], vaas=[], at=at, settings=SETTINGS
    )
    return volcano, chosen


def test_one_office_never_disagrees_with_itself_and_each_series_keeps_its_latest() -> None:
    """Census 25 Sep 03:00Z, 13 RJJJ records for Sakurajima. JMA runs lettered series side by
    side: Y03 (0225Z) and X01 (0226Z) split the two clouds of Y02 (0214Z), which replaced
    Y01; X01 replaced X02 and the previous day's X01. Compared pairwise, successive SIGMETs
    gave 32 LAG and ENVELOPE lines in the 23 Sep replay. The latest of each series stands, and
    the office is never compared with itself."""
    at = utc(2026, 9, 25, 3, 0)
    sakurajima, sigmets = census_records("Sakurajima", "isigmet_va_20260925_0300.json", at)
    assert len(sigmets) == 13
    found = find_discrepancies(
        sakurajima, sigmets=sigmets, vonas=[], vaas=[], at=at, settings=SETTINGS
    )
    assert {d.kind for d in found} == {DiscrepancyKind.SILENCE}
    assert {source for d in found for source in d.source_ids} == {
        "SIGMET:RJJJ:X01:20260925T0226Z",
        "SIGMET:RJJJ:Y03:20260925T0225Z",
    }


def test_a_later_series_takes_the_cloud_over() -> None:
    """Census 7 Oct 10:00Z (Sakurajima): RJJJ P01 (MOV SE, OBS 0418Z) stayed valid to 1048Z
    after Q01 (MOV W, OBS 0908Z) took over at 0929Z, and Tokyo 2026/273 drew the new cloud
    MOV W. Kept in force, P01 read as a 135-degree DIRECTION_MISMATCH against 2026/273."""
    p01 = make_sigmet(
        series="P01",
        fir="RJJJ",
        volcano_name="SAKURAJIMA (AIRA CALDERA)",
        valid_from=utc(2026, 10, 7, 4, 48),
        valid_to=utc(2026, 10, 7, 10, 48),
        observed_at=utc(2026, 10, 7, 4, 18),
        polygon=None,
        toward_deg=135,
        speed_kt=None,
        top_ft=9000,
        raw=(
            "WVJP31 RJTD 070448 RJJJ SIGMET P01 VALID 070448/071048 RJTD- RJJJ FUKUOKA FIR VA "
            "ERUPTION MT SAKURAJIMA (AIRA CALDERA) PSN N3136 E13039 VA CLD OBS AT 0418Z FL090 "
            "MOV SE="
        ),
    )
    q01 = make_sigmet(
        series="Q01",
        fir="RJJJ",
        volcano_name="SAKURAJIMA (AIRA CALDERA)",
        valid_from=utc(2026, 10, 7, 9, 29),
        valid_to=utc(2026, 10, 7, 15, 29),
        observed_at=utc(2026, 10, 7, 9, 8),
        polygon=None,
        toward_deg=270,
        speed_kt=None,
        top_ft=9000,
        raw=(
            "WVJP31 RJTD 070929 RJJJ SIGMET Q01 VALID 070929/071529 RJTD- RJJJ FUKUOKA FIR VA "
            "ERUPTION MT SAKURAJIMA (AIRA CALDERA) PSN N3136 E13039 VA CLD OBS AT 0908Z FL090 "
            "MOV W="
        ),
    )
    cloud = "N3137 E13036 - N3137 E13040 - N3133 E13040 - N3133 E13036"
    tokyo_273 = make_vaa(
        number="2026/273",
        issued_at=utc(2026, 10, 7, 9, 58),
        observation=VaacStep(
            offset_h=0,
            valid_at=utc(2026, 10, 7, 9, 30),
            layers=[
                VaLayer(
                    base_ft=0,
                    top_ft=9000,
                    polygon=ring(cloud),
                    movement_toward_deg=270,
                    movement_speed_kt=15,
                )
            ],
            text=f"OBS VA CLD: SFC/FL090 {cloud} MOV W 15KT",
        ),
        next_advisory_at=utc(2026, 10, 7, 12, 0),
        volcano=SAKURAJIMA,
        vaac=VaacCentre.TOKYO,
    )
    found = find_discrepancies(
        SAKURAJIMA,
        sigmets=[p01, q01],
        vonas=[],
        vaas=[tokyo_273],
        at=utc(2026, 10, 7, 10, 0),
        settings=SETTINGS,
    )
    [lag] = found
    assert lag.kind is DiscrepancyKind.LAG
    assert set(lag.source_ids) == {q01.provenance.source_id, tokyo_273.provenance.source_id}
    assert lag.magnitude == 22


def test_the_clouds_of_one_census_sigmet_are_never_compared() -> None:
    """Census 26 Sep 08:00Z, WAAF 05 (Dukono): SFC/FL070 MOV NE and, joined by AND, SFC/FL150
    MOV W. feeds-text keeps them as 05 and 05 AREA 2; compared with each other they would read
    as a 135-degree DIRECTION_MISMATCH and an 8,000 ft ENVELOPE."""
    at = utc(2026, 9, 26, 8, 0)
    dukono, sigmets = census_records("Dukono", "isigmet_va_20260926_0800.json", at)
    assert sorted(sigmet.series_id for sigmet in sigmets) == ["05", "05 AREA 2"]
    found = find_discrepancies(dukono, sigmets=sigmets, vonas=[], vaas=[], at=at, settings=SETTINGS)
    assert {d.kind for d in found} == {DiscrepancyKind.SILENCE}


FVAU05_LEWOTOLOK_322 = (FEEDS_TEXT / "tgftp_fvau05_lewotolok_2026-322.txt").read_text()
LEWOTOLOK_323_CLOSING = """FVAU06 ADRM 100100
VA ADVISORY
DTG: 20261010/0100Z
VAAC: DARWIN
VOLCANO: LEWOTOLOK 264230
PSN: S0816 E12330
AREA: INDONESIA
SOURCE ELEV: 1423M AMSL
ADVISORY NR: 2026/323
INFO SOURCE: HIMAWARI-9
ERUPTION DETAILS: VA TO FL070 OBS AT 09/2250Z
EST VA DTG: 10/0040Z
EST VA CLD: VA NOT IDENTIFIABLE FM SATELLITE DATA WIND SFC/FL070 180/05KT
FCST VA CLD +6 HR: 10/0640Z NO VA EXP
FCST VA CLD +12 HR: 10/1240Z NO VA EXP
FCST VA CLD +18 HR: 10/1840Z NO VA EXP
RMK: VA NO LONGER IDENTIFIABLE ON SATELLITE IMAGERY.
NXT ADVISORY: NO FURTHER ADVISORIES="""
"""A closing advisory in Darwin's template, issued after the real 2026/322 (constructed)."""


def darwin_bulletin(text: str, slot: int) -> VaacAdvisory:
    content = text.encode()
    result = FetchResult(
        feed=FeedId.VAAC_DARWIN,
        url=DARWIN_BULLETIN_URLS[slot - 1],
        status_code=200,
        content=content,
        content_type="text/plain",
        fetched_at=utc(2026, 10, 10, 2, 0),
        sha256=sha256_bytes(content),
    )
    vaa = parse_vaa(result)
    assert vaa is not None
    return vaa


@pytest.mark.parametrize("order", ["322_first", "323_first"])
def test_a_vaa_closed_by_a_later_one_no_longer_keeps_the_volcano_active(order: str) -> None:
    """feeds-text, 10 Oct: tgftp slot 5 held Lewotolok 2026/322 (next advisory by 0510Z) after
    a later advisory had ended the event. Any VAA within its own validity used to count, so
    the superseded 2026/322 kept Lewotolok active while select_records used 2026/323."""
    superseded = darwin_bulletin(FVAU05_LEWOTOLOK_322, slot=5)
    closing = darwin_bulletin(LEWOTOLOK_323_CLOSING, slot=6)
    vaas = [superseded, closing] if order == "322_first" else [closing, superseded]
    catalogue = VolcanoCatalogue([SEMERU, LEWOTOLOK])
    at = utc(2026, 10, 10, 3, 0)
    assert superseded.is_current(at)
    assert closing.final
    assert not closing.is_current(at)

    assert find_active(catalogue, sigmets=[], vonas=[], vaas=vaas, at=at, settings=SETTINGS) == {}
    _, _, chosen = select_records(
        catalogue, LEWOTOLOK, sigmets=[], vonas=[], vaas=vaas, at=at, settings=SETTINGS
    )
    assert [vaa.advisory_nr for vaa in chosen] == ["2026/323"]
    assert (
        find_discrepancies(LEWOTOLOK, sigmets=[], vonas=[], vaas=chosen, at=at, settings=SETTINGS)
        == []
    )
