"""The deterministic discrepancy finder, tested on the two Semeru cases re-verified in
research/13 (texts copied from the AWC SIGMET archive and the MAGMA VONA pages quoted
there) plus small crafted cases for the rules those days do not exercise."""

import re
from datetime import UTC, datetime, timedelta

import pytest

from tephra.config import Settings
from tephra.feeds.volcanoes import VolcanoCatalogue
from tephra.models import (
    AviationColor,
    Discrepancy,
    DiscrepancyKind,
    EvidenceState,
    FeedId,
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
from tephra.util.hashing import sha256_text
from tephra.util.timeutil import compact

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
    polygon: GeoPolygon,
    toward_deg: float,
    speed_kt: float,
    raw: str,
    top_ft: int = 15000,
) -> Sigmet:
    source_id = make_source_id("SIGMET", "WAAF", series, compact(valid_from))
    return Sigmet(
        provenance=provenance(source_id, FeedId.SIGMET, valid_from),
        fir_id="WAAF",
        fir_name="WAAF UJUNG PANDANG",
        series_id=series,
        volcano_name="SEMERU",
        volcano_lat=degmin("S0806"),
        volcano_lon=degmin("E11255"),
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
) -> VaacAdvisory:
    source_id = make_source_id("VAA", "DARWIN", SEMERU.id, number)
    return VaacAdvisory(
        provenance=provenance(source_id, FeedId.VAAC_DARWIN, issued_at),
        vaac=VaacCentre.DARWIN,
        advisory_nr=number,
        issued_at=issued_at,
        volcano_name="SEMERU",
        volcano_number=SEMERU.id,
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


def test_semeru_25_sep_cited_pair_is_lag_envelope_direction_and_silence() -> None:
    """The pair as first cited: VONA 23 Sep 2221Z against SIGMET 12 of 25 Sep.

    No SIGMET in the input was valid at the VONA's time, so the VONA is compared with the
    SIGMET in force now. The products are 36 h 39 min apart (LAG); the height sits inside
    the band (ENVELOPE); NE against SE is a DIRECTION_MISMATCH; no VAA (SILENCE). The polygon
    probe is not run: it needs a SIGMET valid when the VONA was issued.
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
    assert by_kind[DiscrepancyKind.DIRECTION_MISMATCH, "direction"].magnitude == 90
    assert (DiscrepancyKind.DIRECTION_MISMATCH, "polygon") not in by_kind
    assert any(d.kind is DiscrepancyKind.SILENCE for d in found)
    assert all(d.kind is not DiscrepancyKind.CONFLICT for d in found)


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
