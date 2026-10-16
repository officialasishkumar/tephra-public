"""The setup kit's push.py: flight plans from a schedule, positions from a file, nothing guessed,
and old positions never stamped as current. Runs the tool against a fake ``urlopen``."""

import importlib.util
import io
import json
import os
import time
import urllib.error
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from tephra.api.server import WEB_DIR
from tephra.config import MAX_PUSH_BODY_BYTES
from tephra.models import _AIRLINE_CALLSIGN

TOOL = WEB_DIR / "kit" / "push.py"
MONDAY, TUESDAY = "2026-10-19", "2026-10-20"
KEY = "tph_" + "k" * 32


def load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("kit_push", TOOL)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def push(monkeypatch: pytest.MonkeyPatch) -> Any:
    module = load()
    module.sent = []
    module.events = []

    class Answer(io.BytesIO):
        def __enter__(self) -> "Answer":
            return self

        def __exit__(self, *_: object) -> None:
            self.close()

    def urlopen(request: Any, timeout: float) -> Answer:
        batch = json.loads(request.data)
        module.sent.append((request.full_url, dict(request.header_items()), batch))
        module.events.append(("send", len(batch.get("positions", batch.get("flight_plans", [])))))
        positions = batch.get("positions", [])
        result = {
            "accepted": len(positions),
            "rejected": [],
            "in_ash": [],
            "plans_taken": len(batch.get("flight_plans", [])),
        }
        return Answer(json.dumps(result).encode())

    monkeypatch.setattr(module.urllib.request, "urlopen", urlopen)
    monkeypatch.setattr(module.time, "sleep", lambda s: module.events.append(("sleep", s)))
    return module


def write(path: Path, data: Any) -> Path:
    path.write_text(json.dumps(data) if not isinstance(data, str) else data)
    return path


@pytest.fixture
def schedule(tmp_path: Path) -> tuple[Path, Path]:
    flights = {
        "header": {"label": "Ring of Fire Air schedule", "anchor_utc_offset_h": 7},
        "flights": [
            {"flight_no": "RFA101", "origin": "WARR", "dest": "WIII", "std_min": 300,
             "block_min": 80, "tail": "PK-RFA", "callsign": "RFA101"},
            {"flight_no": "RF0401", "origin": "WIII", "dest": "WADD", "std_min": 60,
             "block_min": 110, "tail": "PK-RFB", "days": "135"},
            {"flight_no": "RFA7", "origin": "WIII", "dest": "WARR", "std_min": 1500,
             "block_min": 90, "tail": "PK-RFC"},
        ],
    }  # fmt: skip
    fleet = {
        "tails": [
            {"tail": "PK-RFA", "type": "A320", "seats": 180, "hex": "8a0412"},
            {"tail": "PK-RFB", "type": "B738", "seats": 189, "hex": "8a0413"},
            {"tail": "PK-RFC", "type": "AT76", "seats": 0},
        ]
    }
    return write(tmp_path / "flights.json", flights), write(tmp_path / "fleet.json", fleet)


def plans_args(paths: tuple[Path, Path], day: str, *extra: str) -> list[str]:
    flights, fleet = paths
    return ["--url", "http://tephra.local/", "--key", KEY, "plans", "--schedule", str(flights),
            "--fleet", str(fleet), "--date", day, *extra]  # fmt: skip


def plans_sent(push: Any) -> list[dict[str, Any]]:
    return [plan for _, _, batch in push.sent for plan in batch["flight_plans"]]


def test_the_callsign_rule_is_the_one_tephra_checks() -> None:
    assert load().AIRLINE_CALLSIGN.pattern == _AIRLINE_CALLSIGN.pattern


def test_plans_skip_what_has_no_callsign_and_no_known_address(
    push: Any, schedule: tuple[Path, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    code = push.main(plans_args(schedule, TUESDAY))
    out = capsys.readouterr().out

    assert code == 1
    assert [p["flight"] for p in plans_sent(push)] == ["RFA101"]
    assert "skipped RFA7: no callsign and no known address" in out
    assert "plans taken 1 · refused 0" in out
    url, headers, batch = push.sent[0]
    assert url == "http://tephra.local/api/push/positions"
    assert headers["Authorization"] == f"Bearer {KEY}"
    assert batch["format"] == "tephra.airline/1"


def test_times_follow_the_anchor_offset_and_days_follow_ssim(
    push: Any, schedule: tuple[Path, Path]
) -> None:
    push.main(plans_args(schedule, MONDAY, "--callsign-rule", "rfa"))
    monday = {p["flight"]: p for p in plans_sent(push)}

    assert monday["RFA101"]["std"] == "2026-10-18T22:00:00.000Z"  # 05:00 at UTC+7
    assert monday["RFA101"]["sta"] == "2026-10-18T23:20:00.000Z"
    assert monday["RFA7"]["std"] == "2026-10-19T18:00:00.000Z"  # 25:00 local, the next day
    assert monday["RF0401"]["callsign"] == "RFA401"
    assert monday["RFA7"]["callsign"] == "RFA7"
    push.sent.clear()
    push.main(plans_args(schedule, TUESDAY, "--callsign-rule", "RFA"))
    assert "RF0401" not in {p["flight"] for p in plans_sent(push)}


def test_addresses_are_sent_only_when_the_tails_fly_that_day(
    push: Any, schedule: tuple[Path, Path]
) -> None:
    push.main(plans_args(schedule, MONDAY))
    without = plans_sent(push)
    push.sent.clear()
    push.main(plans_args(schedule, MONDAY, "--tails-are-today"))
    with_tails = {p["flight"]: p for p in plans_sent(push)}

    assert [p["flight"] for p in without] == ["RFA101"]
    assert all("hex" not in p for p in without)
    assert "callsign" not in without[0] or without[0]["callsign"] == "RFA101"
    assert with_tails["RFA101"]["hex"] == "8a0412"
    assert with_tails["RF0401"]["hex"] == "8a0413"
    assert "callsign" not in with_tails["RF0401"]
    assert "RFA7" not in with_tails


def test_a_schedule_without_its_offset_is_refused(push: Any, tmp_path: Path) -> None:
    flights = write(tmp_path / "f.json", {"header": {"anchor_utc_offset_h": None}, "flights": []})
    fleet = write(tmp_path / "fl.json", {"tails": []})
    assert push.main(plans_args((flights, fleet), MONDAY)) == 2
    assert push.sent == []


POSITIONS_CSV = (
    "hex,callsign,type_icao,lat,lon,alt_baro_ft,gs_kt,track_deg,observed_at\n"
    "8a0412,RFA1654,A320,-6.21,106.4,35000,450,90,2026-10-16T09:00:00.000Z\n"
    "8a0413,PKRFB,B738,-6.3,106.5,12000,,,\n"
)


def test_positions_without_a_time_are_refused_unless_stamped_now(
    push: Any, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    file = write(tmp_path / "positions.csv", POSITIONS_CSV)
    refused = push.main(["--url", "http://t", "--key", KEY, "positions", str(file)])
    out = capsys.readouterr().out
    [(_, _, first)] = push.sent
    push.sent.clear()
    stamped = push.main(["--url", "http://t", "--key", KEY, "positions", str(file), "--stamp-now"])
    out_stamped = capsys.readouterr().out
    [(_, _, second)] = push.sent

    assert refused == 1
    assert "row 2: no observed_at; add it or use --stamp-now" in out
    assert [p["hex"] for p in first["positions"]] == ["8a0412"]
    assert first["positions"][0] == {
        "hex": "8a0412", "callsign": "RFA1654", "type_icao": "A320", "lat": -6.21, "lon": 106.4,
        "alt_baro_ft": 35000, "gs_kt": 450.0, "track_deg": 90.0,
        "observed_at": "2026-10-16T09:00:00.000Z",
    }  # fmt: skip
    assert stamped == 0
    assert "Stamped 1 positions with the send time" in out_stamped
    assert "1 positions have no airline-style callsign" in out_stamped
    assert second["positions"][0]["observed_at"] == "2026-10-16T09:00:00.000Z"  # kept
    assert second["positions"][1]["observed_at"].endswith("Z")
    assert "gs_kt" not in second["positions"][1]


def test_stamping_refuses_a_file_written_minutes_ago(push: Any, tmp_path: Path) -> None:
    file = write(tmp_path / "positions.csv", POSITIONS_CSV)
    old = time.time() - 14 * 60
    os.utime(file, (old, old))

    code = push.main(["--url", "http://t", "--key", KEY, "positions", str(file), "--stamp-now"])

    assert code == 2
    assert push.sent == []


def test_big_files_go_in_batches_of_a_thousand_a_second_apart(push: Any, tmp_path: Path) -> None:
    rows = [
        {"hex": f"{i:06x}", "callsign": "RFA1", "lat": 0, "lon": 0, "alt_baro_ft": 1000,
         "observed_at": "2026-10-16T09:00:00.000Z"}
        for i in range(2500)
    ]  # fmt: skip
    file = write(tmp_path / "positions.json", rows)

    assert push.main(["--url", "http://t", "--key", KEY, "positions", str(file)]) == 0
    gap = ("sleep", push.GAP_S)
    assert push.events == [("send", 1000), gap, ("send", 1000), gap, ("send", 500)]
    assert push.GAP_S >= 1.1


def test_a_dry_run_sends_nothing(
    push: Any, schedule: tuple[Path, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    code = push.main(["--dry-run", *plans_args(schedule, MONDAY)])
    assert push.sent == []
    assert code == 1  # RFA7 skipped
    assert "Dry run: nothing was sent." in capsys.readouterr().out


def test_an_http_refusal_exits_2(
    push: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def refuse(request: Any, timeout: float) -> Any:
        body = io.BytesIO(b'{"error": "unauthenticated", "detail": "A live connection key"}')
        raise urllib.error.HTTPError(request.full_url, 401, "Unauthorized", {}, body)  # type: ignore[arg-type]

    monkeypatch.setattr(push.urllib.request, "urlopen", refuse)
    file = write(tmp_path / "positions.csv", POSITIONS_CSV)
    assert push.main(["--url", "http://t", "--key", KEY, "positions", str(file)]) == 2
    assert "push refused: HTTP 401 A live connection key" in capsys.readouterr().err


def test_batches_fit_the_push_body_limit() -> None:
    tool = load()
    records = [{"hex": f"{n:06x}", "callsign": "RFA101", "note": "x" * 600} for n in range(1500)]
    out = tool.batches(records, "positions")

    assert [r for b in out for r in b["positions"]] == records
    assert all(len(json.dumps(b).encode("utf-8")) <= tool.BATCH_BYTES for b in out)
    assert tool.BATCH_BYTES < MAX_PUSH_BODY_BYTES
    small = tool.batches([{"hex": "8a0412"}] * 2500, "positions")
    assert [len(b["positions"]) for b in small] == [1000, 1000, 500]
