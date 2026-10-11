"""Tests for the archive importers and derivers in ``scripts/record_replay.py``.

The fixtures are cut from real data fetched on 2026-10-10 while the replay cases were
built: NOAAPort bulletins from the IEM archive (6 Sep 2026), adsb.lol heatmap rows
(5 Sep 2026 17:28-17:29Z), IEM ASOS METAR lines (4-6 Sep 2026) and an Open-Meteo
Historical Forecast answer (Semeru, 25 Sep 2026). Nothing here reaches the network.
"""

import argparse
import gzip
import importlib.util
import io
import json
import struct
import sys
import tarfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from tephra.config import PROJECT_ROOT
from tephra.feeds.adsb import parse_adsb
from tephra.feeds.base import FetchResult
from tephra.feeds.sigmet import SIGMET_PARAMS, SIGMET_URL, parse_sigmets
from tephra.feeds.taf import parse_metars
from tephra.feeds.vaac import DARWIN_BULLETIN_URLS, parse_vaa
from tephra.feeds.winds import parse_winds, wind_params
from tephra.geo.units import initial_bearing_deg
from tephra.models import AdsbQueryPoint, FeedId
from tephra.util.hashing import sha256_bytes


def _load_recorder() -> ModuleType:
    name = "tephra_script_record_replay"
    spec = importlib.util.spec_from_file_location(
        name, PROJECT_ROOT / "scripts" / "record_replay.py"
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module  # dataclasses resolve the module's postponed annotations
    spec.loader.exec_module(module)
    return module


rr = _load_recorder()

HOUR_00 = datetime(2026, 9, 6, 0, tzinfo=UTC)
HOUR_04 = datetime(2026, 9, 6, 4, tzinfo=UTC)

# --- real NOAAPort bulletins (IEM archive, 20260906.tgz) ---------------------------------

WIIF_01_A = (
    "WVID20 WIII 060034\n"
    "WIIF SIGMET 01 VALID 060035/060335 WIII-\n"
    "WIIF JAKARTA FIR VA ERUPTION MT KRAKATAU PSN S0606 E10525 VA CLD OBS\n"
    "AT 0010Z WI S0504 E10700 - S0641 E11007 - S0901 E10914 - S1000 E10501\n"
    "- S0728 E10147 - S0504 E10700 SFC/FL200 MOV E 10KT NC AND OBS AT\n"
    "0010Z WI S0504 E10700 - S0714 E10617 - S0911 E10247 - S0200 E09200 -\n"
    "S0153 E09200 - S0023 E10020 - S0504 E10700 SFC/FL500 MOV W 30KT NC=\n"
)
WIIF_01_B = (
    "WVID20 WIII 060034\n"
    "WIIF SIGMET 01 VALID 060035/060335 WIII- WIIF JAKARTA FIR VA ERUPTION\n"
    "MT KRAKATAU PSN S0606 E10525 VA CLD OBS AT 0010Z WI S0504 E10700 -\n"
    "S0641 E11007 - S0901 E10914 - S1000 E10501 - S0728 E10147 - S0504\n"
    "E10700 SFC/FL200 MOV E 10KT NC AND OBS AT 0010Z WI S0504 E10700 -\n"
    "S0714 E10617 - S0911 E10247 - S0200 E09200 - S0153 E09200 - S0023\n"
    "E10020 - S0504 E10700 SFC/FL500 MOV W 30KT NC=\n"
)
_YMMM_H07_BODY = (
    "WVAU01 YMMC 060029\n"
    "YMMM SIGMET H07 VALID 060030/060330 YMMC-\n"
    "YMMM MELBOURNE FIR MT KRAKATAU PSN S0606 E10525 VA CLD OBS WI S1033\n"
    "E10020 - S1705 E09640 - S1328 E07947 - S0249 E09032 - S0220 E09230 -\n"
    "S0912 E10248 SFC/FL500 NC AND OBS WI S0912 E10248 - S1033 E10020 -\n"
    "S1705 E09640 - S1328 E07947 - S0249 E09032 - S0220 E09230 SFC/FL500\n"
    "NC AND OBS WI S0200 E09200 - S0911 E10247 - S1031 E10025 - S1731\n"
    "E09640 - S1203 E07906 - S0251 E08640 - S0200 E09123 SFC/FL500 NC\n"
    "FCST AT 0610Z WI S0200 E09200 - S0914 E10252 - S1038 E10020 - S1916\n"
    "E09618 - S1441 E07646 - S0245 E08536 - S0200 E09016"
)
YMMM_H07_WITH_REMARK = _YMMM_H07_BODY + "\nRMK: MW=\n"
YMMM_H07 = _YMMM_H07_BODY + "=\n"
WIIF_03_CNL = (
    "WVID20 WIII 060400\n"
    "WIIF SIGMET 03 VALID 060400/062235 WIII-\n"
    "WIIF JAKARTA FIR CNL SIGMET 27 052035/062235=\n"
)
_WIIF_27 = (
    "WVID20 WIII 052035\n"
    "WIIF SIGMET 27 VALID 052035/{end} WIII-\n"
    "WIIF JAKARTA FIR VA ERUPTION MT KRAKATAU PSN S0606 E10525 VA CLD OBS\n"
    "AT 2010Z WI S0502 E10700 - S0644 E11010 - S0903 E10913 - S1000 E10505\n"
    "- S0727 E10147 - S0502 E10700 SFC/FL200 MOV E 10KT INTSF AND OBS AT\n"
    "2010Z WI S0506 E10708 - S0714 E10617 - S0911 E10247 - S0222 E09234 -\n"
    "S0023 E10020 - S0506 E10708 SFC/FL500 MOV W 30KT INTSF=\n"
)
WIIF_27_TYPO = _WIIF_27.format(end="062235")  # sent first, 26 h of validity
WIIF_27 = _WIIF_27.format(end="052235")  # the corrected copy sent a minute later
_IBU = (
    "FVAU03 ADRM 060140\n"
    "VA ADVISORY\n"
    "DTG: 20260906/0140Z\n"
    "VAAC: DARWIN\n"
    "VOLCANO: IBU 268030\n"
    "PSN: N0129 E12738\n"
    "AREA: INDONESIA\n"
    "SOURCE ELEV: 1325M AMSL\n"
    "ADVISORY NR: 2026/1010\n"
    "INFO SOURCE: HIMAWARI-9, CVGHM\n"
    "ERUPTION DETAILS: VA TO FL070 OBS AT 06/0120Z\n"
    "OBS VA DTG: 06/0120Z\n"
    "OBS VA CLD: SFC/FL070 N0129 E12743 - N0125 E12741 - N0127\n"
    "        E12712 - N0143 E12718 - N0150 E12734 MOV E 05KT\n"
    "FCST VA CLD +6 HR: 06/0720Z SFC/FL070 N0126 E12741 - N0125\n"
    "        E12737 - N0133 E12718 - N0148 E12727 - N0146 E12746\n"
    "RMK: DISCRETE VA EMISSION IDENTIFIABLE ON LATEST SATELLITE\n"
    "        IMAGERY.{mark}UPDATE OF OBSERVATION POLYGON{mark}\n"
    "NXT ADVISORY: NO LATER THAN 20260906/0740Z=\n"
)
IBU = _IBU.format(mark="***")
IBU_MANGLED = _IBU.format(mark="???")  # the same advisory through a relay without '*'
KRAKATAU_183 = (
    "FVAU04 ADRM 060030\n"
    "VA ADVISORY\n"
    "DTG: 20260906/0030Z\n"
    "VAAC: DARWIN\n"
    "VOLCANO: KRAKATAU 262000\n"
    "PSN: S0606 E10525\n"
    "AREA: INDONESIA\n"
    "SOURCE ELEV: 155M AMSL\n"
    "ADVISORY NR: 2026/183\n"
    "INFO SOURCE: HIMAWARI-9 CVGHM\n"
    "ERUPTION DETAILS: VA TO FL500 MOV W, VA TO FL200 MOV E\n"
    "OBS VA DTG: 06/0010Z\n"
    "OBS VA CLD: SFC/FL200 S0504 E10700 - S0641 E11007 - S0901\n"
    "        E10914 - S1000 E10501 - S0728 E10147 MOV E 10KT\n"
    "NXT ADVISORY: NO LATER THAN 20260906/0330Z=\n"
)
METARS = (
    "SAID31 WIII 060000\n"
    "METAR WIHH 060000Z 13003KT 5000 VA NSC 26/21 Q1015 NOSIG=\n"
    "METAR WIII 060000Z 15004KT 6000 VA FEW020 26/21 Q1014 NOSIG=\n"
)


def bulletin(text: str, hour: datetime = HOUR_00, order: int = 0) -> Any:
    return rr.Bulletin(heading=text.split("\n", 1)[0], text=text, hour=hour, order=order)


def result_of(content: bytes, feed: FeedId, at: datetime, url: str = "u") -> FetchResult:
    return FetchResult(
        feed=feed,
        url=url,
        status_code=200,
        content=content,
        content_type="application/json",
        fetched_at=at,
        sha256=sha256_bytes(content),
    )


# --- NOAAPort streaming -----------------------------------------------------------------


def _product(sequence: int, text: str) -> bytes:
    return f"\x01\r\r\n{sequence:03d} \r\r\n{text.replace(chr(10), chr(13) * 2 + chr(10))}\x03"


def _day_tarball(members: dict[str, bytes]) -> io.BytesIO:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
        for name, data in members.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    buffer.seek(0)
    return buffer


def test_noaaport_stream_keeps_va_bulletins_and_south_east_asian_collectives(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    hour_00 = b"".join(
        [
            _product(1, "FPUS51 KBOX 060000\nZONE FORECAST\n").encode(),
            _product(2, WIIF_01_A).encode(),
            _product(3, METARS).encode(),
            _product(4, "WSUS32 KKCI 060055\nCONVECTIVE SIGMET 1E\n").encode(),
            _product(5, IBU).encode(),
        ]
    )
    hour_01 = _product(6, WIIF_01_B).encode()
    stream = _day_tarball({"2026090600.txt": hour_00, "2026090601.txt": hour_01})
    monkeypatch.setattr(rr, "_READ_CHUNK", 100)  # products straddle chunk boundaries

    bulletins = list(rr.select_bulletins(rr.iter_products(stream, last_hour=HOUR_00)))

    assert [item.heading for item in bulletins] == [
        "WVID20 WIII 060034",
        "SAID31 WIII 060000",
        "FVAU03 ADRM 060140",
    ]
    assert bulletins[0].text == WIIF_01_A  # CR removed, heading first, sequence dropped
    assert bulletins[0].hour == HOUR_00
    assert bulletins[0].received_at == datetime(2026, 9, 6, 0, 34, tzinfo=UTC)
    assert [item.order for item in bulletins] == sorted(item.order for item in bulletins)


def _save_day(directory: Path, day: str, rows: list[dict], last_hour: str = "23") -> None:
    (directory / f"{day}.jsonl").write_text("".join(json.dumps(row) + "\n" for row in rows))
    summary = {"last_hour": f"{day[:4]}-{day[4:6]}-{day[6:]}T{last_hour}:00:00.000Z"}
    (directory / f"{day}.source.json").write_text(json.dumps(summary))


def test_saved_bulletins_read_back_in_arrival_order(tmp_path: Path) -> None:
    rows = [
        rr._bulletin_row(bulletin(WIIF_03_CNL, HOUR_04, 7)),
        rr._bulletin_row(bulletin(WIIF_01_A, HOUR_00, 9)),
    ]
    _save_day(tmp_path, "20260906", rows)

    read = rr.read_noaaport_dir(tmp_path)

    assert [item.heading for item in read] == ["WVID20 WIII 060034", "WVID20 WIII 060400"]
    assert read[0] == bulletin(WIIF_01_A, HOUR_00, 9)


@pytest.mark.parametrize(
    ("days", "message"),
    [
        ([("20260905", "23"), ("20260907", "23")], "not consecutive"),
        ([("20260905", "06"), ("20260906", "23")], "only the last day"),
    ],
)
def test_slot_states_need_consecutive_whole_days(
    tmp_path: Path, days: list[tuple[str, str]], message: str
) -> None:
    for day, last_hour in days:
        _save_day(tmp_path, day, [], last_hour)
    (tmp_path / "20260908.jsonl").write_text("")  # still streaming: no summary yet

    with pytest.raises(SystemExit, match="did not finish"):
        rr.read_noaaport_dir(tmp_path)
    (tmp_path / "20260908.jsonl").unlink()
    with pytest.raises(SystemExit, match=message):
        rr.read_noaaport_dir(tmp_path)


def test_copies_rewrapped_by_the_relay_merge_into_one() -> None:
    items = [
        bulletin(WIIF_01_A, order=1),
        bulletin(WIIF_01_B, order=2),
        bulletin(YMMM_H07_WITH_REMARK, order=3),
        bulletin(YMMM_H07, order=4),
        bulletin(IBU_MANGLED, order=5),
        bulletin(IBU, order=6),
    ]

    merged = rr.merge_copies(items, key=lambda item: item.body(), bulletin=lambda item: item)
    by_heading = rr.merge_copies(items, key=lambda item: item.heading, bulletin=lambda item: item)

    assert len(merged) == 5  # only the two WIIF wrappings have the same text
    kept = {item.heading: item for _, item in by_heading}
    assert kept["WVID20 WIII 060034"].order == 1
    assert kept["WVAU01 YMMC 060029"].text == YMMM_H07_WITH_REMARK  # the copy with more text
    assert "***" in kept["FVAU03 ADRM 060140"].text  # not the copy with '?'
    arrivals = [at for at, _ in by_heading]
    assert arrivals == sorted(arrivals)
    assert arrivals[0] == datetime(2026, 9, 6, 0, 29, tzinfo=UTC)


# --- VA SIGMETs wrapped in AWC isigmet JSON ---------------------------------------------


def test_sigmet_heading_fields_come_from_the_text() -> None:
    sigmet = rr.read_sigmet(bulletin(WIIF_01_B))
    cancel = rr.read_sigmet(bulletin(WIIF_03_CNL, HOUR_04))
    melbourne = rr.read_sigmet(bulletin(YMMM_H07))

    assert sigmet is not None
    assert cancel is not None
    assert melbourne is not None
    assert (sigmet.fir, sigmet.series, sigmet.mwo, sigmet.fir_name) == (
        "WIIF",
        "01",
        "WIII",
        "WIIF JAKARTA",
    )
    assert sigmet.valid_from == datetime(2026, 9, 6, 0, 35, tzinfo=UTC)
    assert sigmet.valid_to == datetime(2026, 9, 6, 3, 35, tzinfo=UTC)
    assert sigmet.cancels is None
    assert (cancel.series, cancel.cancels) == ("03", "27")
    assert cancel.valid_to == datetime(2026, 9, 6, 22, 35, tzinfo=UTC)
    assert (melbourne.fir, melbourne.series, melbourne.mwo) == ("YMMM", "H07", "YMMC")
    assert melbourne.fir_name == "YMMM MELBOURNE"


def test_wrapped_bulletins_parse_like_awc_records() -> None:
    sigmets = rr.noaaport_sigmets(
        [bulletin(WIIF_01_A, order=1), bulletin(WIIF_01_B, order=2), bulletin(YMMM_H07, order=3)],
        ["WIIF", "YMMM"],
    )
    at = datetime(2026, 9, 6, 1, tzinfo=UTC)
    [(when, records)] = rr.isigmet_snapshots(sigmets, at, at)

    assert when == at
    first = next(record for record in records if record["firId"] == "WIIF")
    assert first == {
        "icaoId": "WIII",
        "firId": "WIIF",
        "firName": "WIIF JAKARTA",
        "receiptTime": "2026-09-06T00:34:00.000Z",
        "validTimeFrom": int(datetime(2026, 9, 6, 0, 35, tzinfo=UTC).timestamp()),
        "validTimeTo": int(datetime(2026, 9, 6, 3, 35, tzinfo=UTC).timestamp()),
        "seriesId": "01",
        "hazard": "VA",
        "rawSigmet": WIIF_01_A.rstrip("\n"),
    }
    parsed = parse_sigmets(result_of(rr._json_bytes(records), FeedId.SIGMET, at))
    by_series = {sigmet.series_id: sigmet for sigmet in parsed}
    assert set(by_series) == {"01", "01 AREA 2", "H07", "H07 AREA 2", "H07 AREA 3", "H07F"}
    low, high = by_series["01"], by_series["01 AREA 2"]
    assert (low.volcano_name, low.base_ft, low.top_ft) == ("KRAKATAU", 0, 20000)
    assert (low.movement_toward_deg, low.movement_speed_kt) == (90.0, 10.0)
    assert (high.top_ft, high.movement_toward_deg, high.movement_speed_kt) == (50000, 270.0, 30.0)
    assert low.polygon is not None
    assert high.polygon is not None
    assert by_series["H07F"].observed is False  # the forecast polygon AWC splits off
    assert by_series["H07F"].polygon is not None


def test_cnl_ends_the_cancelled_sigmet_and_a_reissue_replaces_its_series() -> None:
    evening = datetime(2026, 9, 5, 20, tzinfo=UTC)
    sigmets = rr.noaaport_sigmets(
        [
            bulletin(WIIF_27_TYPO, evening, 1),
            bulletin(WIIF_27_TYPO, evening, 2),
            bulletin(WIIF_27, evening, 3),
            bulletin(WIIF_03_CNL, HOUR_04, 4),
        ],
        ["WIIF"],
    )
    start = datetime(2026, 9, 5, 20, tzinfo=UTC)
    snapshots = dict(rr.isigmet_snapshots(sigmets, start, datetime(2026, 9, 6, 6, tzinfo=UTC)))

    assert list(snapshots) == [start, datetime(2026, 9, 5, 20, 35, tzinfo=UTC), HOUR_04]
    assert snapshots[start] == []
    [record] = snapshots[datetime(2026, 9, 5, 20, 35, tzinfo=UTC)]
    assert record["seriesId"] == "27"
    assert record["validTimeTo"] == int(datetime(2026, 9, 5, 22, 35, tzinfo=UTC).timestamp())
    [cancel] = snapshots[HOUR_04]  # 27 ended long before; the CNL itself is listed
    assert cancel["seriesId"] == "03"
    [parsed] = parse_sigmets(result_of(rr._json_bytes([cancel]), FeedId.SIGMET, HOUR_04))
    assert parsed.cancelled is True


def test_a_cnl_shortens_a_sigmet_still_valid() -> None:
    sigmets = rr.noaaport_sigmets(
        [
            bulletin(WIIF_27_TYPO, datetime(2026, 9, 5, 20, tzinfo=UTC)),
            bulletin(WIIF_03_CNL, HOUR_04),
        ],
        ["WIIF"],
    )
    before = datetime(2026, 9, 6, 3, tzinfo=UTC)
    snapshots = dict(rr.isigmet_snapshots(sigmets, before, datetime(2026, 9, 6, 5, tzinfo=UTC)))

    [open_27] = snapshots[before]
    assert open_27["validTimeTo"] == int(datetime(2026, 9, 6, 22, 35, tzinfo=UTC).timestamp())
    assert [item["seriesId"] for item in snapshots[HOUR_04]] == ["03"]


def test_noaaport_sigmets_are_stored_under_the_live_isigmet_url(tmp_path: Path) -> None:
    start = datetime(2026, 9, 6, 0, tzinfo=UTC)
    records = rr.import_noaaport_sigmets(
        [bulletin(WIIF_01_A)], ["WIIF"], start, datetime(2026, 9, 6, 1, tzinfo=UTC), tmp_path
    )

    assert [record.fetched_at for record in records] == [
        start,
        datetime(2026, 9, 6, 0, 34, tzinfo=UTC),
    ]
    assert {record.url for record in records} == {
        f"{SIGMET_URL}?format={SIGMET_PARAMS['format']}&hazard={SIGMET_PARAMS['hazard']}"
    }
    assert json.loads((tmp_path / records[0].path).read_bytes()) == []


# --- Darwin VAAs under their tgftp slots ------------------------------------------------


def test_darwin_slots_hold_their_last_bulletin_before_the_window() -> None:
    later = KRAKATAU_183.replace("060030", "060330").replace("0030Z", "0330Z")
    later = later.replace("2026/183", "2026/184")
    vaas = rr.darwin_vaas(
        [
            bulletin(KRAKATAU_183, order=1),
            bulletin(IBU_MANGLED, datetime(2026, 9, 6, 1, tzinfo=UTC), 2),
            bulletin(IBU, datetime(2026, 9, 6, 1, tzinfo=UTC), 3),
            bulletin(later, datetime(2026, 9, 6, 3, tzinfo=UTC), 4),
        ]
    )
    start = datetime(2026, 9, 6, 2, tzinfo=UTC)

    states = rr.darwin_slot_states(vaas, start, datetime(2026, 9, 6, 6, tzinfo=UTC))

    assert [(at.strftime("%H%M"), vaa.slot, vaa.advisory_nr) for at, vaa in states] == [
        ("0030", 4, "2026/183"),
        ("0140", 3, "2026/1010"),
        ("0330", 4, "2026/184"),
    ]
    assert "***" in states[1][1].bulletin.text
    assert rr.advisory_runs(vaa for _, vaa in states)["KRAKATAU 262000"] == (183, 184, [])


# Real FVAU01 bulletins from 20260923.tgz: 2026/787 arrived at 07Z, and NOAAPort re-sent
# 2026/751 (14 Sep) at 11Z while replaying its backlog. Cut after the cloud lines.
DUKONO_787 = (
    "FVAU01 ADRM 230710\n"
    "VA ADVISORY\n"
    "DTG: 20260923/0710Z\n"
    "VAAC: DARWIN\n"
    "VOLCANO: DUKONO 268010\n"
    "PSN: N0142 E12754\n"
    "AREA: INDONESIA\n"
    "SOURCE ELEV: 1229M AMSL\n"
    "ADVISORY NR: 2026/787\n"
    "INFO SOURCE: HIMAWARI-9\n"
    "ERUPTION DETAILS: VA TO FL070 LAST OBS AT 22/2230Z\n"
    "EST VA DTG: 23/0650Z\n"
    "EST VA CLD: SFC/FL070 N0136 E12747 - N0146 E12742 - N0219\n"
    "        E12810 - N0200 E12849 - N0125 E12831 MOV NE 10KT\n"
    "NXT ADVISORY: NO LATER THAN 20260923/1310Z=\n"
)
DUKONO_751_RESENT = (
    "FVAU01 ADRM 141030\n"
    "VA ADVISORY\n"
    "DTG: 20260914/1030Z\n"
    "VAAC: DARWIN\n"
    "VOLCANO: DUKONO 268010\n"
    "PSN: N0142 E12754\n"
    "AREA: INDONESIA\n"
    "SOURCE ELEV: 1229M AMSL\n"
    "ADVISORY NR: 2026/751\n"
    "INFO SOURCE: HIMAWARI-9\n"
    "ERUPTION DETAILS: VA TO FL070 OBS AT 14/1010Z EXT NE\n"
    "EST VA DTG: 14/1010Z\n"
    "EST VA CLD: SFC/FL070 N0135 E12752 - N0142 E12746 - N0228\n"
    "        E12826 - N0218 E12900 - N0144 E12901 MOV NE 10KT\n"
    "NXT ADVISORY: NO LATER THAN 20260914/1630Z=\n"
)


def test_a_backlog_resent_by_the_relay_never_replaces_a_slots_newer_advisory() -> None:
    sent = bulletin(DUKONO_787, datetime(2026, 9, 23, 7, tzinfo=UTC), 1)
    resent = bulletin(DUKONO_751_RESENT, datetime(2026, 9, 23, 11, tzinfo=UTC), 2)
    later = DUKONO_787.replace("230710", "231310").replace("23/0710Z", "23/1310Z")
    later = later.replace("20260923/0710Z", "20260923/1310Z").replace("2026/787", "2026/788")
    vaas = rr.darwin_vaas([sent, resent, bulletin(later, datetime(2026, 9, 23, 13, tzinfo=UTC))])
    start, end = datetime(2026, 9, 23, 12, tzinfo=UTC), datetime(2026, 9, 27, 6, tzinfo=UTC)

    states = rr.darwin_slot_states(vaas, start, end)

    assert [(at.strftime("%d %H%M"), vaa.advisory_nr) for at, vaa in states] == [
        ("23 0710", "2026/787"),
        ("23 1310", "2026/788"),
    ]
    assert [vaa.advisory_nr for _, vaa in rr.retransmissions(vaas)] == ["2026/751"]
    assert rr.noaaport_notes([sent, resent], start, end) == [
        "Darwin bulletins that NOAAPort re-sent between 11:00Z on 23 Sep 2026 and 11:00Z on "
        "23 Sep 2026 after newer ones on the same slots (1) are left out, because a slot holds "
        "Darwin's newest advisory on its heading"
    ]


def test_notices_and_unknown_sources_share_one_number_series() -> None:
    # Darwin's 23 Sep products: NOTICE 2026/3 and 2026/7, UNKNOWN 2026/4, 2026/5 and 2026/6.
    def product(heading: str, volcano: str, number: int) -> Any:
        text = KRAKATAU_183.replace("FVAU04 ADRM 060030", heading)
        text = text.replace("KRAKATAU 262000", volcano).replace("2026/183", f"2026/{number}")
        return rr.read_darwin_vaa(bulletin(text))

    vaas = [
        product("FVAU01 ADRM 231216", "NOTICE 999999", 3),
        product("FVAU08 ADRM 231225", "UNKNOWN", 5),
        product("FVAU05 ADRM 231628", "NOTICE 999999", 7),
        product("FVAU04 ADRM 230450", "KRAKATAU 262000", 183),
    ]

    assert rr.advisory_runs(vaas) == {
        "KRAKATAU 262000": (183, 183, []),
        "NOTICE/UNKNOWN": (3, 7, [4, 6]),
    }
    # UNKNOWN 2026/4 went out at 11:14Z, before NOTICE 2026/3 and before a 12Z window.
    unknown_4 = product("FVAU08 ADRM 231114", "UNKNOWN", 4)
    assert rr.advisory_runs(vaas, [unknown_4])["NOTICE/UNKNOWN"] == (3, 7, [6])


def _krakatau(number: int, dtg: str) -> Any:
    """Advisory 2026/<number> issued at <dtg> (DDHHMM) on 5-6 Sep, from the 2026/183 text."""
    text = KRAKATAU_183.replace("060030", dtg).replace(
        "20260906/0030Z", f"202609{dtg[:2]}/{dtg[2:]}Z"
    )
    hour = datetime(2026, 9, int(dtg[:2]), int(dtg[2:4]), tzinfo=UTC)
    return bulletin(text.replace("2026/183", f"2026/{number}"), hour)


def _metars_at(dtg: str) -> Any:
    hour = datetime(2026, 9, int(dtg[:2]), int(dtg[2:4]), tzinfo=UTC)
    return bulletin(METARS.replace("060000", dtg), hour)


def test_archive_silences_and_missing_advisories_are_noted() -> None:
    bulletins = [
        *(_metars_at(dtg) for dtg in ("051600", "051630", "051700", "051730", "051800")),
        *(_metars_at(dtg) for dtg in ("052000", "052030")),
        _krakatau(173, "050430"),  # what FVAU04 held when the window opened
        _krakatau(179, "051630"),
        _krakatau(181, "052030"),
    ]
    start, end = datetime(2026, 9, 5, 16, tzinfo=UTC), datetime(2026, 9, 7, 6, tzinfo=UTC)

    gaps = rr.archive_gaps(bulletins, start, end)
    notes = rr.noaaport_notes(bulletins, start, end)

    assert gaps == [(datetime(2026, 9, 5, 18, tzinfo=UTC), datetime(2026, 9, 5, 20, tzinfo=UTC))]
    assert notes == [
        "IEM's NOAAPort archive holds no bulletin between 18:00Z on 5 Sep 2026 and 20:00Z on "
        "5 Sep 2026; SIGMETs and VAAs issued then are missing from this case",
        "Darwin advisories missing from the archive: KRAKATAU 262000 2026/180",
    ]


def test_feeds_a_case_lacks_are_named_in_its_notes(tmp_path: Path) -> None:
    records = rr.import_noaaport_sigmets(
        [bulletin(WIIF_01_A)], ["WIIF"], HOUR_00, HOUR_04, tmp_path
    ) + rr.import_darwin([bulletin(KRAKATAU_183)], HOUR_00, HOUR_04, tmp_path)

    assert rr.absent_note(records) == (
        "Not in this case, and shown as such: MAGMA VONA, JMA volcano reports, Tokyo VAAC, TAF, "
        "METAR, ADS-B, Winds, Satellite frames, Himawari HSD."
    )


def test_darwin_bulletins_are_served_from_tgftp_slot_urls(tmp_path: Path) -> None:
    start = datetime(2026, 9, 6, 0, tzinfo=UTC)
    held, record = rr.import_darwin(
        [bulletin(KRAKATAU_183)], start, start + timedelta(hours=1), tmp_path
    )

    assert record.url == DARWIN_BULLETIN_URLS[3]
    assert record.fetched_at == datetime(2026, 9, 6, 0, 30, tzinfo=UTC)
    content = (tmp_path / record.path).read_bytes()
    advisory = parse_vaa(result_of(content, FeedId.VAAC_DARWIN, record.fetched_at))
    assert advisory is not None
    assert (advisory.volcano_name, advisory.advisory_nr) == ("KRAKATAU", "2026/183")
    # FVAU04's bulletin before the window is not in the streamed day: an empty record holds
    # the slot from the start, and the Darwin parser reads it as unreadable, not as 2026/183.
    assert (held.url, held.fetched_at, held.status_code) == (record.url, start, 204)
    with pytest.raises(ValueError, match="DTG"):
        parse_vaa(result_of((tmp_path / held.path).read_bytes(), FeedId.VAAC_DARWIN, start))
    assert rr.noaaport_notes([bulletin(KRAKATAU_183)], start, start + timedelta(hours=1)) == [
        "The streamed days hold no bulletin for FVAU04 before the window, so each starts "
        "with an empty 204 record, which the poller reads as unavailable"
    ]


def test_bom_ftp_material_is_never_stored(tmp_path: Path) -> None:
    content = (
        KRAKATAU_183 + "\nCopyright Commonwealth of Australia 2011, Bureau of Meteorology\n"
    ).encode()
    with pytest.raises(SystemExit, match="BoM"):
        rr._store(
            tmp_path, FeedId.VAAC_DARWIN, DARWIN_BULLETIN_URLS[3], HOUR_00, content, 200, None
        )
    assert not (tmp_path / "raw").exists()


# --- METARs: IEM ASOS text in AWC's JSON shape ------------------------------------------

IEM_CSV = (
    "station,valid,metar\n"
    "WILL,2026-09-04 23:30,WILL 042330Z AUTO VRB02KT 2400 BR VV007 22/21 Q1015\n"
    "WIII,2026-09-05 18:30,WIII 051830Z COR 03003KT 5000 HZ VA SCT018 27/23 Q1012 NOSIG\n"
    "WIII,2026-09-05 19:00,WIII 051900Z VRB02KT 4500 HZ VA SCT018 25/23 Q1012 NOSIG\n"
    "WILL,2026-09-06 00:00,WILL 060000Z 23003KT 160V260 3100 VA NSC 23/21 Q1014\n"
    "WILL,2026-09-04 17:30,WILL 041730Z AUTO VRB01KT 7000 NCD 25/22 Q1013\n"
    "WIHH,2026-09-05 18:00,M\n"
)


def test_iem_metars_become_awc_json_the_metar_parser_reads() -> None:
    metars = rr.parse_iem_csv(IEM_CSV)
    at = datetime(2026, 9, 5, 18, 45, tzinfo=UTC)

    content = rr.metar_response(metars, ["WIII", "WILL", "WIHH"], at)
    records = json.loads(content)
    parsed = {metar.icao: metar for metar in parse_metars(result_of(content, FeedId.METAR, at))}

    assert [record["icaoId"] for record in records] == ["WIII", "WILL"]
    wiii = records[0]
    assert wiii["rawOb"] == "WIII 051830Z COR 03003KT 5000 HZ VA SCT018 27/23 Q1012 NOSIG"
    assert (wiii["visib"], wiii["wxString"], wiii["fltCat"]) == (3.11, "HZ VA", "MVFR")
    assert wiii["clouds"] == [{"cover": "SCT", "base": 1800}]
    assert parsed["WIII"].visibility_m == 5000
    assert parsed["WIII"].weather == ["HZ", "VA"]
    assert parsed["WIII"].observed_at == datetime(2026, 9, 5, 18, 30, tzinfo=UTC)
    assert parsed["WILL"].observed_at == datetime(2026, 9, 4, 23, 30, tzinfo=UTC)
    assert parsed["WILL"].ceiling_ft == 700  # VV007
    assert parsed["WILL"].flight_category == "IFR"


@pytest.mark.parametrize(
    ("raw", "visib", "weather", "category"),
    [
        ("WILL 060000Z 23003KT 160V260 3100 VA NSC 23/21 Q1014", 1.93, "VA", "IFR"),
        ("WILL 041730Z AUTO VRB01KT 7000 NCD 25/22 Q1013", 4.35, None, "MVFR"),
        ("WIII 041200Z 01003KT 9999 FEW020 29/23 Q1013 NOSIG", "6+", None, "VFR"),
    ],
)
def test_awc_metar_fields(raw: str, visib: object, weather: str | None, category: str) -> None:
    record = rr.awc_metar(rr.IemMetar(raw.split()[0], HOUR_00, raw))

    assert (record["visib"], record["wxString"], record["fltCat"]) == (visib, weather, category)


def test_iem_request_asks_once_for_every_station() -> None:
    url = rr.iem_asos_url(
        ["WILL", "WIII", "WILL"],
        datetime(2026, 9, 4, 18, tzinfo=UTC),
        datetime(2026, 9, 7, 6, tzinfo=UTC),
    )

    assert url.startswith("https://mesonet.agron.iastate.edu/cgi-bin/request/asos.py?")
    assert "station=WIII&station=WILL&year1=2026&month1=9&day1=4&hour1=18" in url
    assert "&report_type=3&report_type=4" in url


# --- winds from the Open-Meteo Historical Forecast API ----------------------------------

OPEN_METEO_HISTORICAL = {
    "latitude": -8.119508,
    "longitude": 112.94268,
    "generationtime_ms": 171.01514339447021,
    "utc_offset_seconds": 0,
    "timezone": "GMT",
    "timezone_abbreviation": "GMT",
    "elevation": 3552.0,
    "hourly_units": {"time": "iso8601", "wind_speed_500hPa": "kn", "wind_direction_500hPa": "°"},
    "hourly": {
        "time": ["2026-09-25T11:00", "2026-09-25T12:00", "2026-09-25T13:00"],
        "wind_speed_850hPa": [0.7, 0.5, 0.7],
        "wind_direction_850hPa": [315, 270, 225],
        "wind_speed_700hPa": [13.6, 12.3, 13.2],
        "wind_direction_700hPa": [242, 248, 246],
        "wind_speed_600hPa": [18.1, 20.2, 18.6],
        "wind_direction_600hPa": [304, 302, 306],
        "wind_speed_500hPa": [6.5, 2.7, 1.4],
        "wind_direction_500hPa": [217, 225, 207],
        "wind_speed_400hPa": [8.4, 8.2, 8.4],
        "wind_direction_400hPa": [148, 162, 176],
        "wind_speed_300hPa": [9.6, 11.7, 11.6],
        "wind_direction_300hPa": [62, 71, 63],
        "wind_speed_250hPa": [14.9, 16.8, 18.4],
        "wind_direction_250hPa": [2, 16, 18],
        "wind_speed_200hPa": [12.6, 13.2, 13.9],
        "wind_direction_200hPa": [12, 11, 11],
        "wind_speed_150hPa": [8.4, 8.4, 8.7],
        "wind_direction_150hPa": [148, 148, 153],
    },
}


def test_historical_wind_request_covers_the_hours_the_live_call_returns() -> None:
    live_url = "https://api.open-meteo.com/v1/forecast?" + "&".join(
        f"{key}={value}" for key, value in wind_params(-8.108, 112.922).items()
    )
    url = rr.historical_wind_url(live_url, datetime(2026, 9, 25, 12, 40, tzinfo=UTC))

    assert url.startswith("https://historical-forecast-api.open-meteo.com/v1/forecast?")
    assert "latitude=-8.11&longitude=112.92" in url
    assert "start_hour=2026-09-25T11%3A00&end_hour=2026-09-26T11%3A00" in url
    assert "past_hours" not in url
    assert "forecast_hours" not in url
    assert "wind_speed_unit=kn&timezone=GMT" in url


def test_historical_forecast_answer_parses_unchanged() -> None:
    at = datetime(2026, 9, 25, 12, tzinfo=UTC)
    content = json.dumps(OPEN_METEO_HISTORICAL).encode()

    profiles = parse_winds(result_of(content, FeedId.WINDS, at), lat=-8.108, lon=112.922)

    assert [profile.valid_at for profile in profiles] == [
        at - timedelta(hours=1),
        at,
        at + timedelta(hours=1),
    ]
    first = {level.pressure_hpa: level for level in profiles[0].levels}
    assert len(first) == 9
    assert (first[700].from_deg, first[700].speed_kt, first[700].flight_level) == (242.0, 13.6, 100)


def test_awc_history_url_adds_the_date() -> None:
    live = "https://aviationweather.gov/api/data/taf?ids=WADD,WARR&format=json"

    url = rr.awc_history_url(live, datetime(2026, 9, 25, 12, tzinfo=UTC))

    assert url == live.replace(",", "%2C") + "&date=20260925_1200"


# --- ADS-B: adsb.lol heatmap rows to /v2/point answers ----------------------------------


def _row(addr: int, lat: int, lon: int, alt: int, gs: int) -> bytes:
    return struct.pack("<iiihh", addr, lat, lon, alt, gs)


def _marker(at: datetime) -> bytes:
    ms = round(at.timestamp() * 1000)
    high, low = ms >> 32, ms & 0xFFFFFFFF
    low_signed = low - (1 << 32) if low >= 1 << 31 else low
    return struct.pack("<iiihh", rr._HEATMAP_SLICE, high, low_signed, 10000, 0)


def _info(addr: int, callsign: str) -> bytes:
    return struct.pack("<ii8s", addr, (1 << 30) + 4321, callsign.encode().ljust(8, b"\0"))


ETD = 0x8964BF
GIA = 0x8A0A73
THAI_ON_GROUND = 0x88510A
FAR_AWAY = 0x7500E4
# Real rows from adsb.lol globe_history 2026-09-05 heatmap 34 (17:00-17:30Z).
SLICES: list[tuple[str, list[bytes]]] = [
    ("17:00:00", [_info(ETD, "ETD472")]),
    ("17:23:20", [_info(ETD, "ETD473")]),
    (
        "17:28:20",
        [
            _row(GIA, -6074369, 106610665, 107, 2097),
            _row(THAI_ON_GROUND, 13687731, 100743966, -123, 138),
            _row(FAR_AWAY, 4079885, 102221011, 1219, 4631),
            _row(GIA | (1 << 24), -6074369, 106610665, 107, 2097),  # not an ICAO address
        ],
    ),
    (
        "17:28:30",
        [_row(ETD, -6063057, 106889822, 382, 3120), _row(GIA, -6062073, 106614726, 114, 2242)],
    ),
    (
        "17:28:40",
        [_row(ETD, -6063289, 106900145, 391, 3161), _row(GIA, -6052643, 106617799, 122, 2324)],
    ),
    ("17:28:50", [_row(ETD, -6062312, 106923160, 410, 3186), _info(GIA, "GIA682")]),
    (
        "17:29:00",
        [_row(ETD, -6057358, 106939102, 416, 3300), _row(GIA, -6031219, 106625946, 136, 2527)],
    ),
]


def heatmap_file() -> bytes:
    body = b""
    for clock, rows in SLICES:
        at = datetime.fromisoformat(f"2026-09-05T{clock}+00:00")
        body += _marker(at) + b"".join(rows)
    index = struct.pack("<i", len(SLICES)) + b"\0" * 12 + b"\0" * 16 * (len(SLICES) - 1)
    return gzip.compress(index + body)


def test_heatmap_rows_become_point_answers_the_adsb_parser_reads() -> None:
    heatmap = rr.decode_heatmap(heatmap_file())
    at = datetime(2026, 9, 5, 17, 29, tzinfo=UTC)

    answer = rr.point_response(heatmap, -6.101, 105.423, 250, at)

    assert answer["now"] == round(at.timestamp() * 1000)
    assert answer["total"] == 2
    etd, gia = answer["ac"]
    assert etd == {
        "hex": "8964bf",
        "flight": "ETD473",
        "alt_baro": 10400,
        "gs": 330.0,
        "track": round(initial_bearing_deg(-6.063289, 106.900145, -6.057358, 106.939102), 1),
        "lat": -6.057358,
        "lon": 106.939102,
        "seen_pos": 0.0,
        "seen": 0.0,
    }
    assert gia["flight"] == "GIA682"
    assert gia["track"] == round(
        initial_bearing_deg(-6.052643, 106.617799, -6.031219, 106.625946), 1
    )
    content = json.dumps(answer).encode()
    snapshot = parse_adsb(
        result_of(content, FeedId.ADSB, at), AdsbQueryPoint(lat=-6.101, lon=105.423, radius_nm=250)
    )
    [first, second] = snapshot.aircraft
    assert (first.callsign, first.alt_baro_ft, first.track_deg) == ("ETD473", 10400, etd["track"])
    assert first.observed_at == at
    assert second.airline is True


def test_point_answer_ages_positions_and_needs_history_for_a_track() -> None:
    heatmap = rr.decode_heatmap(heatmap_file())

    early = rr.point_response(
        heatmap, -6.101, 105.423, 250, datetime(2026, 9, 5, 17, 28, 35, tzinfo=UTC)
    )
    stale = rr.point_response(
        heatmap, -6.101, 105.423, 250, datetime(2026, 9, 5, 17, 30, 5, tzinfo=UTC)
    )
    bangkok = rr.point_response(
        heatmap, 13.69, 100.74, 50, datetime(2026, 9, 5, 17, 28, 30, tzinfo=UTC)
    )

    etd = next(entry for entry in early["ac"] if entry["hex"] == "8964bf")
    assert "track" not in etd  # 5 s of history is too little
    assert etd["seen_pos"] == 5.0
    assert stale["ac"] == []  # positions over 60 s old are dropped, as readsb does
    assert bangkok["ac"][0]["alt_baro"] == "ground"


def test_adsb_gap_marker_reads_as_a_failed_point() -> None:
    gap = result_of(b"", FeedId.ADSB, HOUR_00)

    with pytest.raises(ValueError, match="not JSON"):
        parse_adsb(gap, AdsbQueryPoint(lat=-6.101, lon=105.423, radius_nm=250))


def test_adsb_steps_cover_the_spans_and_mark_the_gaps() -> None:
    start = datetime(2026, 9, 5, 6, tzinfo=UTC)
    end = datetime(2026, 9, 7, 6, tzinfo=UTC)
    span = (datetime(2026, 9, 5, 10, tzinfo=UTC), datetime(2026, 9, 5, 19, 30, tzinfo=UTC))

    answers, gaps = rr.adsb_steps([span], start, end)

    assert answers[0] == datetime(2026, 9, 5, 10, 1, tzinfo=UTC)
    assert answers[-1] == span[1]
    assert len(answers) == 570
    assert gaps == [start, span[1] + timedelta(minutes=1)]
    slots = rr.heatmap_slots([span])
    assert (slots[0], slots[-1], len(slots)) == (span[0], datetime(2026, 9, 5, 19, tzinfo=UTC), 19)
    assert rr.ADSB_HEATMAP_URL.format(at=slots[-1], index=38).endswith(
        "2026/09/05/heatmap/38.bin.ttf"
    )


def test_point_query_reads_the_live_point_url() -> None:
    assert rr.point_query("https://api.adsb.lol/v2/point/-6.101/105.423/250") == (
        -6.101,
        105.423,
        250.0,
    )


def test_heatmap_cache_round_trips(tmp_path: Path) -> None:
    heatmap = rr.decode_heatmap(heatmap_file())

    rr._save_heatmap(tmp_path / "part.npz", heatmap)
    loaded = rr._load_heatmap(tmp_path / "part.npz")

    at = datetime(2026, 9, 5, 17, 29, tzinfo=UTC)
    assert rr.point_response(loaded, -6.101, 105.423, 250, at) == rr.point_response(
        heatmap, -6.101, 105.423, 250, at
    )


# --- probing and the command line -------------------------------------------------------


def test_probe_ticks_every_minute_inside_adsb_spans() -> None:
    start = datetime(2026, 9, 5, 6, tzinfo=UTC)
    span = (datetime(2026, 9, 5, 10, tzinfo=UTC), datetime(2026, 9, 5, 10, 5, tzinfo=UTC))

    times = rr.probe_times(start, start + timedelta(hours=6), timedelta(minutes=30), [span])

    assert len(times) == 13 + 5  # half-hourly, plus 10:01-10:05 inside the span
    assert datetime(2026, 9, 5, 10, 3, tzinfo=UTC) in times


def _backfill(*extra: str) -> argparse.Namespace:
    return rr.parse_args(
        [
            "backfill",
            "--case",
            "anak-krakatau-20260905",
            "--label",
            "test",
            "--start",
            "2026-09-05T06:00Z",
            "--end",
            "2026-09-07T06:00Z",
            *extra,
        ]
    )


def test_backfill_options_are_checked() -> None:
    args = _backfill("--noaaport-dir", "x", "--sigmet-source", "noaaport")
    assert args.fir == ["WIIF", "WAAF", "YMMM"]
    assert _backfill("--census-dir", "c").sigmet_source == "census"
    with pytest.raises(SystemExit):
        _backfill("--context", "adsb")  # needs --adsb-span
    with pytest.raises(SystemExit):
        _backfill("--with-vona")  # VONAs only come from the census
    with pytest.raises(SystemExit):
        _backfill("--context", "taf")  # AWC has no TAFs this old
    spans = _backfill(
        "--context",
        "metar,adsb",
        "--metar-source",
        "iem",
        "--adsb-span",
        "2026-09-05T10:00Z/2026-09-05T19:30Z",
    ).adsb_span
    assert spans == [
        (datetime(2026, 9, 5, 10, tzinfo=UTC), datetime(2026, 9, 5, 19, 30, tzinfo=UTC))
    ]


# --- filling a case: the fill wiring, and the probe that finds what to fill -------------


class FakeFetcher:
    """Answers archive GETs from fixtures and notes every URL asked for."""

    def __init__(self, answers: dict[str, bytes]) -> None:
        self.answers = answers
        self.urls: list[str] = []

    def get(self, url: str, *, cache: bool = True) -> tuple[int, bytes]:
        self.urls.append(url)
        for prefix, content in self.answers.items():
            if url.startswith(prefix):
                return 200, content
        raise RuntimeError(f"GET {url} failed: HTTP 404")

    def head_size(self, url: str) -> int:
        return 1_000


def filler(
    case_dir: Path, fetcher: FakeFetcher, start: datetime, end: datetime, **extra: Any
) -> Any:
    options: dict[str, Any] = {
        "metar_source": "iem",
        "adsb_spans": [],
        "cache_dir": None,
        "adsb_max_bytes": 10_000,
    }
    return rr.ContextFiller(
        case_dir=case_dir, start=start, end=end, fetcher=fetcher, **{**options, **extra}
    )


def test_iem_metars_fill_a_metar_url_every_half_hour(tmp_path: Path) -> None:
    url = "https://aviationweather.gov/api/data/metar?ids=WIII%2CWILL&format=json"
    fetcher = FakeFetcher({rr.IEM_ASOS_URL: IEM_CSV.encode()})
    start = datetime(2026, 9, 5, 18, 10, tzinfo=UTC)

    records = filler(tmp_path, fetcher, start, start + timedelta(hours=1)).records(
        FeedId.METAR, url
    )

    assert [record.fetched_at.strftime("%H%M") for record in records] == ["1800", "1830", "1900"]
    assert {record.url for record in records} == {url}
    stations = [
        [item["icaoId"] for item in json.loads((tmp_path / record.path).read_bytes())]
        for record in records
    ]
    assert stations == [["WILL"], ["WIII", "WILL"], ["WIII", "WILL"]]
    assert len(fetcher.urls) == 1  # one IEM request serves every station list


def test_winds_fill_the_live_url_hourly_from_the_archive(tmp_path: Path) -> None:
    live_url = "https://api.open-meteo.com/v1/forecast?" + "&".join(
        f"{key}={value}" for key, value in wind_params(-6.101, 105.423).items()
    )
    fetcher = FakeFetcher(
        {rr.OPEN_METEO_HISTORICAL_URL: json.dumps(OPEN_METEO_HISTORICAL).encode()}
    )
    start = datetime(2026, 9, 5, 6, tzinfo=UTC)

    records = filler(tmp_path, fetcher, start, start + timedelta(hours=2)).records(
        FeedId.WINDS, live_url
    )

    assert [record.fetched_at.hour for record in records] == [6, 7, 8]
    assert {record.url for record in records} == {live_url}
    assert "start_hour=2026-09-05T05%3A00&end_hour=2026-09-06T05%3A00" in fetcher.urls[0]
    assert len({record.path for record in records}) == 1  # one file, stored once


def test_adsb_fill_answers_inside_spans_and_marks_gaps(tmp_path: Path) -> None:
    heatmap_url = rr.ADSB_HEATMAP_URL.format(at=datetime(2026, 9, 5, 17, tzinfo=UTC), index=34)
    fetcher = FakeFetcher({heatmap_url: heatmap_file()})
    span = (datetime(2026, 9, 5, 17, 27, tzinfo=UTC), datetime(2026, 9, 5, 17, 29, tzinfo=UTC))
    start = datetime(2026, 9, 5, 17, tzinfo=UTC)
    point = "https://api.adsb.lol/v2/point/-6.101/105.423/250"

    records = filler(
        tmp_path, fetcher, start, start + timedelta(hours=1), adsb_spans=[span]
    ).records(FeedId.ADSB, point)

    by_time = {record.fetched_at.strftime("%H%M"): record for record in records}
    assert sorted(by_time) == ["1700", "1728", "1729", "1730"]
    assert (by_time["1700"].status_code, by_time["1730"].status_code) == (204, 204)
    answer = json.loads((tmp_path / by_time["1729"].path).read_bytes())
    assert [entry["flight"] for entry in answer["ac"]] == ["ETD473", "GIA682"]
    with pytest.raises(SystemExit, match="limit"):
        filler(tmp_path, fetcher, start, start, adsb_spans=[span], adsb_max_bytes=10).records(
            FeedId.ADSB, point
        )


async def test_probe_finds_the_context_urls_a_case_lacks(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    case_dir = data_dir / "replay" / "krakatau-probe"
    case_dir.mkdir(parents=True)
    for name in ("volcanoes.json", "airports.json", "routes_apac.json", "policy/policy_a.json"):
        (data_dir / name).parent.mkdir(parents=True, exist_ok=True)
        (data_dir / name).write_bytes((PROJECT_ROOT / "data" / name).read_bytes())
    start = datetime(2026, 9, 6, 0, tzinfo=UTC)
    records = rr.import_noaaport_sigmets(
        [bulletin(WIIF_01_A)], ["WIIF"], start, start + timedelta(hours=1), case_dir
    )
    case = rr.ReplayCase(
        case_id="krakatau-probe",
        label="probe test",
        recorded_from=start,
        recorded_to=start + timedelta(hours=1),
        region="java_bali",
        records=records,
    )
    (case_dir / "manifest.json").write_text(case.model_dump_json())

    missing = await rr.missing_urls(
        data_dir, case, [start + timedelta(minutes=40)], [FeedId.WINDS, FeedId.ADSB, FeedId.METAR]
    )

    assert missing["https://api.adsb.lol/v2/point/-6.101/105.423/250"] is FeedId.ADSB
    winds = [url for url, feed in missing.items() if feed is FeedId.WINDS]
    assert len(winds) == 1
    assert "latitude=-6.10&longitude=105.42" in winds[0]
    [metar] = [url for url, feed in missing.items() if feed is FeedId.METAR]
    assert "WIII" in metar
    assert "WILL" in metar
    assert all(feed in (FeedId.WINDS, FeedId.ADSB, FeedId.METAR) for feed in missing.values())
