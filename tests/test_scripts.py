"""Tests for the ops scripts in ``scripts/`` and the deploy templates.

The scripts are not a package, so each one is loaded from its file. Nothing here reaches
the network or Gemini: HTTP goes through ``httpx.MockTransport`` and the model client is a
fake.
"""

import argparse
import csv
import importlib.util
import io
import json
import os
import re
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import httpx
import pytest
from google import genai
from google.genai import errors
from PIL import Image
from pydantic import AliasChoices

from tephra.config import PROJECT_ROOT, Settings
from tephra.feeds.adsb import AdsbPointsFailed
from tephra.models import AdsbQueryPoint

FIXTURES = PROJECT_ROOT / "tests" / "fixtures"


def _load_script(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        f"tephra_script_{name}", PROJECT_ROOT / "scripts" / f"{name}.py"
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


plume_eval = _load_script("plume_eval")
make_plume_cases = _load_script("make_plume_cases")
count_traffic = _load_script("count_traffic")


# --- plume_eval: scoring ------------------------------------------------------------------

TEN_CASES = {
    **{f"ash{n}": "ash" for n in range(1, 6)},
    **{f"quiet{n}": "quiet" for n in range(1, 6)},
}


@pytest.fixture
def eval_dirs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "evals" / "plume"
    monkeypatch.setattr(plume_eval, "ROOT", root)
    monkeypatch.setattr(plume_eval, "CASES_DIR", root / "cases")
    monkeypatch.setattr(plume_eval, "ARM_T_DIR", root / "arm_t")
    monkeypatch.setattr(plume_eval, "RAW_DIR", root / "results" / "raw")
    return root


def _answer(finding: str, confidence: str = "medium", **fields: Any) -> dict[str, Any]:
    return {
        "image_finding": finding,
        "frames_with_feature": [],
        "plume_box_2d": [],
        "drift_direction": "none",
        "top_fl": None,
        "top_fl_basis": "none",
        "horizon_h": 0,
        "confidence": confidence,
        "confidence_reason": "test",
        "sources": [{"id": "IMG-3", "used_for": "existence"}],
        "disagreements": [],
        **fields,
    }


def _write_cases(root: Path, classes: dict[str, str]) -> None:
    for case_id, label in classes.items():
        case_dir = root / "cases" / case_id
        case_dir.mkdir(parents=True)
        case = {
            "id": case_id,
            "class": label,
            "vent_px": [50, 50],
            "image_size": [100, 100],
            "wind_text": "WIND FL180 060/9KT",
        }
        (case_dir / "case.json").write_text(json.dumps(case))


def _write_runs(root: Path, prefix: str, answers: list[dict[str, Any]]) -> None:
    raw = root / "results" / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    for run, answer in enumerate(answers, start=1):
        (raw / f"{prefix}_run{run}.json").write_text(json.dumps(answer))


def _scorecard_line(root: Path, key: str) -> str:
    (scorecard,) = (root / "results").glob("scorecard-*.md")
    return next(line for line in scorecard.read_text().splitlines() if f"**{key}:**" in line)


def _right_answer(label: str) -> dict[str, Any]:
    return _answer("ash_seen" if label == "ash" else "no_ash_seen")


def test_unfinished_arm_i_is_incomplete_not_passed(eval_dirs: Path) -> None:
    """Day one of the free tier answers six of the ten cases; the rest must not score."""
    _write_cases(eval_dirs, TEN_CASES)
    for case_id in sorted(TEN_CASES)[:6]:
        _write_runs(eval_dirs, f"I_{case_id}", [_right_answer(TEN_CASES[case_id])] * 3)

    assert plume_eval.main(["--arm", "I", "--score-only"]) == 0

    existence = _scorecard_line(eval_dirs, "existence")
    assert "INCOMPLETE" in existence
    assert "PASS" not in existence


def test_existence_is_the_majority_of_ash_against_not_ash(eval_dirs: Path) -> None:
    """research/10: "ash" = ash_seen, "not ash" = anything else, majority of three runs."""
    _write_cases(eval_dirs, TEN_CASES)
    for case_id, label in TEN_CASES.items():
        _write_runs(eval_dirs, f"I_{case_id}", [_right_answer(label)] * 3)
    split = [_answer("ash_seen", "high"), _answer("no_ash_seen"), _answer("cannot_tell")]
    _write_runs(eval_dirs, "I_quiet1", split)

    plume_eval.main(["--arm", "I", "--score-only"])

    existence = _scorecard_line(eval_dirs, "existence")
    assert existence.startswith("- **existence:** 10/10 correct, 0 quiet")
    assert existence.endswith("PASS")


def test_vaa_polygon_centroid_counts_the_closing_vertex_once() -> None:
    ring = [[0.0, 1.0], [4.0, 1.0], [4.0, 2.0], [0.0, 2.0], [0.0, 1.0]]
    lat, lon = plume_eval._polygon_centroid({"type": "Polygon", "coordinates": [ring]})
    assert (lat, lon) == pytest.approx((1.5, 2.0))


SEMERU_SIGMETS = [
    {
        "seriesId": "13",
        "rawSigmet": "WVID21 WAAA 261720 WAAF SIGMET 13 VALID 261720/262320 WAAA- WAAF "
        "UJUNG PANDANG FIR VA ERUPTION MT SEMERU PSN S0806 E11255 VA CLD OBS AT 1700Z WI "
        "S0805 E11250 - S0801 E11254 - S0811 E11322 - S0826 E11323 - S0829 E11306 - "
        "S0805 E11250 SFC/FL150 MOV SE 10KT NC=",
    },
    {
        "seriesId": "14",
        "rawSigmet": "WVID21 WAAA 262320 WAAF SIGMET 14 VALID 262320/270520 WAAA- WAAF "
        "UJUNG PANDANG FIR VA ERUPTION MT SEMERU PSN S0806 E11255 VA CLD OBS AT 2300Z WI "
        "S0805 E11250 - S0801 E11254 - S0827 E11348 - S0845 E11348 - S0849 E11328 - "
        "S0805 E11250 SFC/FL150 MOV E 15KT NC=",
    },
]
VONA_PLACEHOLDER = (
    "# Paste the MAGMA VONA text for the same hour here (open the page in a browser).\n"
)
VONA_TEXT = VONA_PLACEHOLDER + (
    "VA ERUPTION MT SEMERU. Best estimate of ash-cloud top is around 15923 FT (4976 M) "
    "above sea level. Ash cloud moving to northeast.\n"
)


def _write_arm_t(root: Path, vona: str) -> None:
    arm = root / "arm_t"
    arm.mkdir(parents=True)
    (arm / "sigmets.json").write_text(json.dumps(SEMERU_SIGMETS))
    (arm / "vona.txt").write_text(vona)


def _arm_t_answer(source_a: str, source_b: str) -> dict[str, Any]:
    disagreement = {"field": "direction", "source_a": source_a, "source_b": source_b, "note": "x"}
    return _answer(
        "cannot_tell",
        top_fl=163,
        top_fl_basis="text_source",
        sources=[{"id": "SIGMET-1", "used_for": "direction"}],
        disagreements=[disagreement],
    )


@pytest.mark.parametrize(
    ("source_a", "source_b", "verdict"),
    [
        ("SIGMET-1", "VONA-1", "PASS"),
        ("VONA-1", "SIGMET-2", "PASS"),
        ("SIGMET-1", "SIGMET-2", "FAIL"),
    ],
)
def test_arm_t_counts_only_the_sigmet_vona_direction_disagreement(
    eval_dirs: Path, source_a: str, source_b: str, verdict: str
) -> None:
    _write_arm_t(eval_dirs, VONA_TEXT)
    _write_runs(eval_dirs, "T_semeru", [_arm_t_answer(source_a, source_b)] * 3)

    plume_eval.main(["--arm", "T", "--score-only"])

    assert _scorecard_line(eval_dirs, "verdict").endswith(verdict)


def test_arm_t_will_not_run_without_the_vona_text(eval_dirs: Path) -> None:
    _write_arm_t(eval_dirs, VONA_PLACEHOLDER)
    with pytest.raises(SystemExit):
        plume_eval.arm_t_inputs()


def test_no_inputs_writes_no_scorecard(eval_dirs: Path) -> None:
    assert plume_eval.main(["--score-only"]) != 0
    assert not (eval_dirs / "results").exists()


def test_eval_paths_do_not_depend_on_the_working_directory() -> None:
    assert plume_eval.ROOT == PROJECT_ROOT / "evals" / "plume"


# --- plume_eval: the Gemini call -----------------------------------------------------------


class _FakeModels:
    def __init__(self, error: Exception) -> None:
        self.error = error
        self.configs: list[dict[str, Any]] = []

    def generate_content(self, *, model: str, contents: list[Any], config: dict[str, Any]) -> Any:
        self.configs.append(config)
        raise self.error


@pytest.fixture
def fake_genai(monkeypatch: pytest.MonkeyPatch) -> Callable[[Exception], SimpleNamespace]:
    """Replace ``genai.Client`` with a fake whose every request raises ``error``."""
    monkeypatch.setenv("GEMINI_API_KEY", "test-key-not-real")
    # The Caller pins both switches; monkeypatch puts back what the process had.
    monkeypatch.setenv("GOOGLE_GENAI_USE_VERTEXAI", "FALSE")
    monkeypatch.setenv("GOOGLE_GENAI_USE_ENTERPRISE", "FALSE")

    def install(error: Exception) -> SimpleNamespace:
        client = SimpleNamespace(kwargs={}, models=_FakeModels(error))

        def factory(**kwargs: Any) -> SimpleNamespace:
            client.kwargs = kwargs
            return client

        monkeypatch.setattr(genai, "Client", factory)
        return client

    return install


def test_caller_is_pinned_to_the_gemini_api_not_vertex(
    fake_genai: Callable[[Exception], SimpleNamespace],
) -> None:
    client = fake_genai(RuntimeError("never called"))
    plume_eval.Caller("gemini-3.8-flash", max_calls=1, pause_s=0)
    assert client.kwargs["api_key"] == "test-key-not-real"
    assert client.kwargs.get("vertexai") is False


def test_api_error_skips_the_response_and_the_run_goes_on(
    fake_genai: Callable[[Exception], SimpleNamespace], tmp_path: Path
) -> None:
    body = {"error": {"code": 429, "message": "quota", "status": "RESOURCE_EXHAUSTED"}}
    fake_genai(errors.ClientError(429, body))
    caller = plume_eval.Caller("gemini-3.8-flash", max_calls=3, pause_s=0)
    raw = tmp_path / "I_case_run1.json"

    assert plume_eval.cached(raw, lambda: caller.call(plume_eval.SYSTEM_ARM_I, [])) is None
    assert not raw.exists()


def test_each_call_is_one_request_with_the_protocol_settings(
    fake_genai: Callable[[Exception], SimpleNamespace], tmp_path: Path
) -> None:
    client = fake_genai(errors.UnknownApiResponseError("Failed to parse response as JSON"))
    caller = plume_eval.Caller("gemini-3.8-flash", max_calls=3, pause_s=0)

    plume_eval.cached(tmp_path / "raw.json", lambda: caller.call(plume_eval.SYSTEM_ARM_I, []))

    (config,) = client.models.configs
    assert config["thinking_config"] == {"thinking_level": "high"}
    assert config["media_resolution"] == "MEDIA_RESOLUTION_HIGH"
    assert config["response_json_schema"] is plume_eval.SCHEMA


# --- make_plume_cases ---------------------------------------------------------------------

TAAL_ASH = "20261008_27307000_0023"  # OBS 08/1420Z, polygon SW of the vent, no WIND field
TAAL_TIMES = ["1440", "1430", "1420", "1410", "1400", "1350"]  # newest first, as JMA lists
SAKURAJIMA_QUIET = "20261008_28208001_0279"  # OBS 08/1120Z, "WIND FL180 040/1KT"
SAKURAJIMA_TIMES = ["1130", "1120", "1110", "1100", "1050"]
WIND_HOST = "historical-forecast-api.open-meteo.com"


def _frame_png() -> bytes:
    image = Image.new("RGB", (120, 90), (40, 80, 120))
    for dx in range(-2, 3):
        for dy in range(-2, 3):
            image.putpixel((60 + dx, 40 + dy), (255, 0, 0))  # the vent marker
    out = io.BytesIO()
    image.save(out, format="PNG")
    return out.getvalue()


def _frame_list(case_id: str, channel: str, times: list[str]) -> str:
    number, day = case_id.split("_")[1], case_id[:8]
    entries = [
        f'ImgSatellite[4][idx++] = new ImageInfo("{number}/09-{channel}/'
        f'{day}_{hhmm}_{day}1500_{channel}.png","");'
        for hhmm in times
    ]
    return "var idx=0;\n" + "\n".join(entries) + f"\nvar AshPicNum={len(times)};\n"


def _archive(
    case_id: str, text: bytes, times: list[str], wind: bytes | None = None
) -> tuple[httpx.Client, list[httpx.Request]]:
    """A client whose transport serves one Tokyo VAAC case and, optionally, Open-Meteo."""
    requests: list[httpx.Request] = []
    png = _frame_png()

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        path = request.url.path
        if path.endswith(f"/TextData/2026/{case_id}_Text.html"):
            return httpx.Response(200, content=text, headers={"content-type": "text/html"})
        for channel in ("as", "ir"):
            if path.endswith(f"/Sat/2026/Script/{case_id}_{channel}.js"):
                return httpx.Response(200, text=_frame_list(case_id, channel, times))
        if "/Sat/2026/Images/" in path:
            return httpx.Response(200, content=png, headers={"content-type": "image/png"})
        if request.url.host == WIND_HOST and wind is not None:
            return httpx.Response(200, content=wind, headers={"content-type": "application/json"})
        return httpx.Response(404)

    return httpx.Client(transport=httpx.MockTransport(handler)), requests


def test_ash_case_gets_the_fl180_wind_from_open_meteo(tmp_path: Path) -> None:
    """Ash advisories carry no WIND group; without one the wind line would give the label
    away (only quiet cases would have it). research/10 says use Open-Meteo for that hour."""
    text = (FIXTURES / "tokyo_vaac" / f"{TAAL_ASH}_Text.html").read_bytes()
    wind = (FIXTURES / "ops_evals" / "open_meteo_historical_taal_20261008T14.json").read_bytes()
    client, requests = _archive(TAAL_ASH, text, TAAL_TIMES, wind=wind)
    with client:
        record = make_plume_cases.build_case(client, TAAL_ASH, "ash", "Taal", tmp_path)

    assert record["wind_text"] == "WIND FL180 052/11KT"
    assert record["wind_source"] == "open-meteo"
    (wind_request,) = [request for request in requests if request.url.host == WIND_HOST]
    assert wind_request.url.params["start_hour"] == "2026-10-08T14:00"
    assert wind_request.url.params["hourly"] == "wind_speed_500hPa,wind_direction_500hPa"
    frames = [frame["url"].rsplit("/", 1)[1][:13] for frame in record["as_frames"]]
    assert frames == ["20261008_1400", "20261008_1410", "20261008_1420"]
    assert record["vent_px"] == [60, 40]
    assert record["needs_human_check"] == []


def test_quiet_case_keeps_the_advisory_wind(tmp_path: Path) -> None:
    text = (FIXTURES / "tokyo_vaac" / f"{SAKURAJIMA_QUIET}_Text.html").read_bytes()
    client, requests = _archive(SAKURAJIMA_QUIET, text, SAKURAJIMA_TIMES)
    with client:
        record = make_plume_cases.build_case(client, SAKURAJIMA_QUIET, "quiet", "Q2", tmp_path)

    assert record["wind_text"] == "WIND FL180 040/1KT"
    assert record["wind_source"] == "vaa"
    assert all(request.url.host != WIND_HOST for request in requests)


def test_unreadable_advisory_is_flagged_for_a_person_not_fatal(tmp_path: Path) -> None:
    client, _ = _archive(TAAL_ASH, b"<html><body>Service unavailable</body></html>", TAAL_TIMES)
    with client:
        record = make_plume_cases.build_case(client, TAAL_ASH, "ash", "Taal", tmp_path)

    assert "vaa: advisory text did not parse" in record["needs_human_check"]
    assert json.loads((tmp_path / TAAL_ASH / "case.json").read_text())["id"] == TAAL_ASH


def _jma_frame(vent: tuple[int, int] | None) -> bytes:
    """A frame laid out like Tokyo VAAC's: the time stamp across the top and the JMA mark at
    the bottom right are drawn in the same saturated red as the vent triangle, as thin
    strokes (each glyph a 10 x 16 outline, about a third filled, like the real ones)."""
    image = Image.new("RGB", (668, 501), (40, 140, 200))
    red = (255, 0, 0)
    for left in [*range(20, 450, 12), 610, 622, 634]:
        top = 23 if left < 450 else 476
        for x in range(left, left + 10):
            image.putpixel((x, top), red)
            image.putpixel((x, top + 15), red)
        for y in range(top, top + 16):
            image.putpixel((left, y), red)
            image.putpixel((left + 9, y), red)
    if vent is not None:
        x, y = vent
        for row in range(6):  # a filled triangle, apex up, centred on the vent
            for dx in range(-row // 2 - 1, row // 2 + 2):
                image.putpixel((x + dx, y - 3 + row), red)
    out = io.BytesIO()
    image.save(out, format="PNG")
    return out.getvalue()


def test_vent_is_the_red_triangle_not_the_red_time_stamp() -> None:
    assert make_plume_cases.find_vent(_jma_frame((457, 162))) == (457, 162)


def test_frame_without_a_vent_marker_is_left_for_a_person() -> None:
    assert make_plume_cases.find_vent(_jma_frame(None)) is None


def test_without_an_obs_time_the_newest_frames_are_taken() -> None:
    paths = [f"27307000/09-as/20261008_{hhmm}_202610081500_as.png" for hhmm in TAAL_TIMES[2:]]
    chosen, how = make_plume_cases.pick_frames(paths, None, 3)
    assert chosen == [paths[2], paths[1], paths[0]]
    assert "check by eye" in how


def test_arm_t_snapshot_without_a_semeru_sigmet_is_refused(tmp_path: Path) -> None:
    client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(204)))
    with client, pytest.raises(SystemExit):
        make_plume_cases.fetch_arm_t_sigmet(client, "2026-08-01T00:00:00Z", tmp_path / "cases")
    assert not (tmp_path / "arm_t" / "sigmets.json").exists()


def test_arm_t_snapshot_with_semeru_is_saved(tmp_path: Path) -> None:
    snapshot = (FIXTURES / "isigmet" / "isigmet_va.json").read_bytes()
    client = httpx.Client(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, content=snapshot))
    )
    with client:
        path = make_plume_cases.fetch_arm_t_sigmet(client, "2026-10-09T19:00:00Z", tmp_path / "x")
    assert path.read_bytes() == snapshot
    assert (path.parent / "vona.txt").read_text().startswith("#")


# --- count_traffic ------------------------------------------------------------------------


async def test_failed_poll_is_recorded_and_the_count_goes_on(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    point = AdsbQueryPoint(lat=-8.108, lon=112.922, radius_nm=250)
    outcomes: list[Any] = [AdsbPointsFailed([(point, "HTTP 429")], [], tried=1), []]

    async def fetch_aircraft(source: Any, points: Any) -> Any:
        outcome = outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr(count_traffic, "fetch_aircraft", fetch_aircraft)
    out = tmp_path / "traffic.csv"
    args = argparse.Namespace(
        volcano="semeru",
        radius=250,
        every=0.001,  # two polls 0.06 s apart
        hours=0.00003,
        top_fl=150,
        data_dir=PROJECT_ROOT / "data",
        out=out,
    )

    assert await count_traffic.run(args) == 0

    header, failed, counted = list(csv.reader(out.open()))
    assert header[-1] == "error"
    assert failed[4:7] == ["", "", ""]
    assert "HTTP 429" in failed[-1]
    assert counted[4:7] == ["0", "0", "0"]
    assert counted[-1] == ""


# --- .env.example -------------------------------------------------------------------------

ENV_EXAMPLE = PROJECT_ROOT / ".env.example"


def _env_names() -> dict[str, set[str]]:
    names: dict[str, set[str]] = {}
    for field_name, field in Settings.model_fields.items():
        alias = field.validation_alias
        if isinstance(alias, AliasChoices):
            names[field_name] = {str(choice) for choice in alias.choices}
        else:
            names[field_name] = {f"TEPHRA_{field_name.upper()}"}
    return names


def test_env_example_lists_every_setting_by_its_real_name() -> None:
    listed = set(re.findall(r"^#?\s*([A-Z][A-Z0-9_]*)=", ENV_EXAMPLE.read_text(), re.MULTILINE))
    names = _env_names()
    known = set().union(*names.values())
    assert sorted(listed - known) == []
    assert sorted(field for field, choices in names.items() if not choices & listed) == []


def test_copied_env_example_leaves_optional_secrets_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A blank line is a blank value, not "unset": a blank session secret disables the desk
    even though config.py promises a random one per process."""
    for name in list(os.environ):
        if name.startswith("TEPHRA_") or name in {"GEMINI_API_KEY", "PORT"}:
            monkeypatch.delenv(name)

    settings = Settings(_env_file=ENV_EXAMPLE)  # type: ignore[call-arg]

    assert settings.desk_pin is None
    assert settings.task_token is None
    assert settings.gemini_api_key is None
    assert settings.session_secret.get_secret_value().strip()


# --- .dockerignore ------------------------------------------------------------------------


def _docker_pattern(pattern: str) -> re.Pattern[str]:
    """Docker's matching (moby/patternmatcher): patterns are anchored at the context root,
    ``*`` and ``?`` stop at ``/``, and ``**`` spans directories."""
    regex, index = "", 0
    while index < len(pattern):
        if pattern.startswith("**", index):
            index += 2
            if pattern.startswith("/", index):
                index += 1
            regex += ".*" if index == len(pattern) else "(.*/)?"
            continue
        char = pattern[index]
        regex += {"*": "[^/]*", "?": "[^/]"}.get(char, re.escape(char))
        index += 1
    return re.compile(f"^{regex}$")


def _dockerignore_rules() -> list[tuple[bool, re.Pattern[str]]]:
    rules: list[tuple[bool, re.Pattern[str]]] = []
    for line in (PROJECT_ROOT / ".dockerignore").read_text().splitlines():
        pattern = line.strip()
        if not pattern or pattern.startswith("#"):
            continue
        exclusion = pattern.startswith("!")
        rules.append((exclusion, _docker_pattern(pattern.removeprefix("!").strip().strip("/"))))
    return rules


def _ignored(path: str, rules: list[tuple[bool, re.Pattern[str]]]) -> bool:
    """Ignored when the path or a parent directory matches; the last deciding rule wins."""
    parts = path.split("/")
    candidates = ["/".join(parts[: count + 1]) for count in range(len(parts))]
    ignored = False
    for exclusion, regex in rules:
        if exclusion != ignored:
            continue
        if any(regex.match(candidate) for candidate in candidates):
            ignored = not exclusion
    return ignored


def _replay_files() -> list[str]:
    files = ["data/replay/example-case/raw/sigmet/20260923T120000Z_0123456789ab.json"]
    for manifest in sorted((PROJECT_ROOT / "data" / "replay").glob("*/manifest.json")):
        case = json.loads(manifest.read_text())
        files.append(manifest.relative_to(PROJECT_ROOT).as_posix())
        files += [f"data/replay/{case['case_id']}/{record['path']}" for record in case["records"]]
    return files


def test_docker_context_keeps_what_the_image_runs() -> None:
    """REPLAY in the image needs each case's recorded files, not only its manifest."""
    rules = _dockerignore_rules()
    needed = [
        "pyproject.toml",
        "uv.lock",
        "README.md",
        "LICENSE",
        "tephra/main.py",
        "tephra/web/index.html",
        "tephra/web/desk.js",
        "tephra/agents/prompts/plume_reader.md",
        "data/volcanoes.json",
        "data/airports.json",
        "data/policy/policy_a.json",
        *_replay_files(),
    ]
    assert [path for path in needed if _ignored(path, rules)] == []


def test_docker_context_leaves_out_local_state_and_research() -> None:
    rules = _dockerignore_rules()
    unwanted = [
        ".venv/bin/python",
        ".state/tephra.sqlite3",
        ".env",
        ".git/HEAD",
        "research/README.md",
        "tests/test_scripts.py",
        "CLAUDE.md",
    ]
    assert [path for path in unwanted if not _ignored(path, rules)] == []


# --- deploy: which pushes deploy (deploy/deploy_paths.py) ----------------------------------

_DEPLOY_WORKFLOW = PROJECT_ROOT / ".github" / "workflows" / "deploy.yml"


def _deploy_paths() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "tephra_deploy_paths", PROJECT_ROOT / "deploy" / "deploy_paths.py"
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _deploy_rules() -> tuple[ModuleType, Any]:
    module = _deploy_paths()
    patterns = module.read_patterns(_DEPLOY_WORKFLOW.read_text(encoding="utf-8"))
    return module, module.compile_filter(patterns)


def test_deploy_paths_reads_the_same_list_github_does() -> None:
    import yaml

    workflow = yaml.safe_load(_DEPLOY_WORKFLOW.read_text(encoding="utf-8"))
    on = workflow.get("on", workflow.get(True))  # YAML 1.1 reads a bare `on` as true
    module = _deploy_paths()
    assert module.read_patterns(_DEPLOY_WORKFLOW.read_text(encoding="utf-8")) == on["push"]["paths"]


@pytest.mark.parametrize(
    ("path", "deploys"),
    [
        ("tephra/main.py", True),
        ("tephra/agents/prompts/plume_reader.md", True),
        ("data/replay/README.md", True),
        ("docs/backtest/results.json", True),
        ("docs/evals/plume_scorecard.json", True),
        ("deploy/cloudrun.sh", True),
        ("Dockerfile", True),
        ("uv.lock", True),
        ("scripts/live_smoke.sh", True),
        ("tests/test_policy.py", True),
        (".github/workflows/deploy.yml", True),
        ("README.md", False),
        ("CLAUDE.md", False),
        ("docs/ARCHITECTURE.md", False),
        ("research/18e-ask-voice-satellite-handover-ui.md", False),
        ("tests/test_scripts.py", False),
        ("scripts/plume_eval.py", False),
        ("evals/README.md", False),
        (".github/workflows/ci.yml", False),
        (".claude/skills/tephra-deploy/SKILL.md", False),
        ("tephraX/main.py", False),
    ],
)
def test_deploy_paths_filter(path: str, deploys: bool) -> None:
    module, rules = _deploy_rules()
    assert module.triggers(path, rules) is deploys


def test_deploy_paths_cover_everything_the_image_is_built_from() -> None:
    module, rules = _deploy_rules()
    # README.md and LICENSE are copied for the package metadata only; they change no behaviour.
    exempt = {"README.md", "LICENSE"}
    sources = []
    for line in (PROJECT_ROOT / "Dockerfile").read_text(encoding="utf-8").splitlines():
        words = line.split()
        if not words or words[0] != "COPY" or any(w.startswith("--from") for w in words):
            continue
        sources += [w for w in words[1:-1] if not w.startswith("--")]
    assert sources
    missing = []
    for source in sources:
        if source in exempt:
            continue
        probe = source if (PROJECT_ROOT / source).is_file() else f"{source.rstrip('/')}/x.py"
        if not module.triggers(probe, rules):
            missing.append(source)
    assert missing == []


_CLOUDRUN = PROJECT_ROOT / "deploy" / "cloudrun.sh"


def _bash_array(script: str, name: str) -> list[str]:
    match = re.search(rf"^{name}=\((.*?)\)", script, re.M | re.S)
    assert match is not None, name
    return match.group(1).split()


def test_cloudrun_forwards_the_demo_settings_when_set() -> None:
    forwarded = _bash_array(_CLOUDRUN.read_text(encoding="utf-8"), "FORWARDED")
    expected = {
        "TEPHRA_FEATURES",
        "TEPHRA_VISITOR_ACCESS",
        "TEPHRA_REPLAY_QUANTUM_S",
        "TEPHRA_RECOVERY_AUTO",
        "TEPHRA_CLOUD_REGION",
        "TEPHRA_AI_INTERACTIVE_SHARE",
        "TEPHRA_AI_ANSWER_REPLAY_KEEP_H",
    }
    assert expected <= set(forwarded)
    assert len(forwarded) == len(set(forwarded))
    # Every forwarded name is a real setting, by its env alias.
    aliases = set()
    for field in Settings.model_fields.values():
        alias = field.validation_alias
        choices = alias.choices if isinstance(alias, AliasChoices) else [alias]
        aliases.update(str(choice) for choice in choices if choice)
    env_names = {f"TEPHRA_{name.upper()}" for name in Settings.model_fields}
    assert set(forwarded) <= aliases | env_names


def test_cloudrun_says_where_the_secrets_come_from_beside_set_secrets() -> None:
    script = _CLOUDRUN.read_text(encoding="utf-8")
    env_vars = _bash_array(script, "env_vars")
    assert '"TEPHRA_SECRETS_SOURCE=secret-manager"' in env_vars
    assert '--set-secrets "$secret_refs"' in script
    assert set(_bash_array(script, "SECRETS")) == {
        "GEMINI_API_KEY",
        "TEPHRA_DESK_PIN",
        "TEPHRA_TASK_TOKEN",
        "TEPHRA_SESSION_SECRET",
    }


def test_deploy_files_the_export_keeps_do_not_address_a_judge() -> None:
    """The private runbook (dropped by the export) is the one place the word may stay."""
    hits = []
    for path in sorted((PROJECT_ROOT / "deploy").rglob("*")):
        if not path.is_file() or path.name == "RUNBOOK-private.md" or "__pycache__" in path.parts:
            continue
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if re.search(r"\bjudg", line, re.IGNORECASE):
                hits.append(f"{path.relative_to(PROJECT_ROOT)}:{number}")
    assert hits == []
    runbook = (PROJECT_ROOT / "deploy" / "RUNBOOK-private.md").read_text(encoding="utf-8")
    assert "TEPHRA_KEEP_TAG=keep-submission-20261018" in runbook
    assert "prewarm_replay.py" in runbook


def test_deploy_paths_refuses_patterns_it_cannot_match() -> None:
    module = _deploy_paths()
    with pytest.raises(ValueError, match="unsupported path pattern"):
        module.compile_filter(["tephra/**", "docs/[ab]*"])
    with pytest.raises(ValueError, match=r"no on\.push\.paths"):
        module.read_patterns("on:\n  push:\n    branches: [main]\n")


# --- live_smoke.sh: waiting out 429/503 ----------------------------------------------------


def _smoke_against(
    script: dict[str, list[int]], env: dict[str, str], state: dict[str, Any] | None = None
) -> str:
    """Run scripts/live_smoke.sh --read-only against a local server answering each path with
    the listed statuses in turn (the last one repeats); return its output."""
    import subprocess
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    state_body = json.dumps(state or {"mode": "REPLAY", "build_sha": "abc", "policy": {}}).encode()
    calls: dict[str, int] = {}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            statuses = script.get(self.path, [404])
            n = calls.get(self.path, 0)
            calls[self.path] = n + 1
            status = statuses[min(n, len(statuses) - 1)]
            body = b""
            if status == 200 and self.path == "/health":
                body = b'{"mode": "REPLAY"}'
            elif status == 200 and self.path == "/api/state":
                body = state_body
            self.send_response(status)
            if status in (429, 503):
                self.send_header("Retry-After", "1")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args: Any) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        result = subprocess.run(
            [
                "bash",
                str(PROJECT_ROOT / "scripts" / "live_smoke.sh"),
                f"http://127.0.0.1:{server.server_address[1]}",
                "--read-only",
            ],
            capture_output=True,
            text=True,
            timeout=60,
            env={"PATH": os.environ["PATH"], **env},
        )
    finally:
        server.shutdown()
    return result.stdout


def _line(output: str, check: str) -> str:
    return next(line for line in output.splitlines() if f" {check}: " in line)


def test_smoke_waits_out_a_start_up_429_and_says_so() -> None:
    out = _smoke_against({"/health": [429, 429, 200]}, {})
    line = _line(out, "healthz")
    assert line.startswith("PASS healthz: 200, mode=REPLAY (429 for ")
    assert line.endswith(", then 200)")
    assert "waited out 429/503" in out.splitlines()[-1]


def test_smoke_fails_a_429_after_the_service_had_answered() -> None:
    out = _smoke_against({"/health": [200], "/api/state": [429, 200]}, {})
    assert _line(out, "healthz").startswith("PASS healthz")
    line = _line(out, "state")
    assert line.startswith("FAIL state: ")
    assert "then 200, after the service had answered" in line


def test_smoke_without_retries_reports_the_429() -> None:
    out = _smoke_against({"/health": [429, 200]}, {"SMOKE_RETRY_S": "0"})
    line = _line(out, "healthz")
    assert line.startswith("FAIL healthz: 429")
    assert "not retried: no retries" in line


_OK_ROUTES = {"/health": [200], "/api/state": [200]}
_CLOUD_STATE: dict[str, Any] = {
    "mode": "REPLAY",
    "build_sha": "abc",
    "policy": {},
    "cloud": {"platform": "cloud-run", "revision": "tephra-00123-abc", "store": "firestore"},
}


def test_smoke_skips_the_cloud_checks_when_the_build_has_no_cloud_facts() -> None:
    out = _smoke_against({"/health": [200], "/api/state": [200]}, {})
    assert _line(out, "cloud").startswith("WARN cloud: cloud facts not exposed")
    assert " audit-verify: " not in out
    assert " evals: " not in out


def test_smoke_checks_cloud_run_firestore_audit_verify_and_reports_missing_evals() -> None:
    routes = {**_OK_ROUTES, "/api/audit/verify": [200], "/api/evals": [404]}
    out = _smoke_against(routes, {}, _CLOUD_STATE)
    assert _line(out, "cloud") == (
        "PASS cloud: platform=cloud-run, revision=tephra-00123-abc, store=firestore"
    )
    assert _line(out, "audit-verify") == "PASS audit-verify: GET /api/audit/verify -> 200"
    assert _line(out, "evals").startswith("WARN evals: GET /api/evals -> 404")


def test_smoke_fails_a_local_platform_a_broken_verify_and_a_broken_evals() -> None:
    state = {**_CLOUD_STATE, "cloud": {"platform": "local", "revision": None, "store": "sqlite"}}
    routes = {**_OK_ROUTES, "/api/audit/verify": [500], "/api/evals": [500]}
    out = _smoke_against(routes, {}, state)
    assert _line(out, "cloud").startswith("FAIL cloud: platform=local")
    assert _line(out, "audit-verify").startswith("FAIL audit-verify: ")
    assert _line(out, "evals") == "FAIL evals: GET /api/evals -> 500"


async def test_count_model_calls_asks_nothing_again_on_a_second_loop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The offline counter of model asks (no model, no network): a second loop of the same
    replay window asks no model again; every answer is the same model's, checked again."""
    from tephra.agents import duty_officer, exposure_planner

    for module in (exposure_planner, duty_officer):  # the script swaps in its stand-ins
        monkeypatch.setattr(module, "_run_agent", module._run_agent)
    script = _load_script("count_model_calls")
    args = argparse.Namespace(
        case="anak-krakatau-20260905",
        start=datetime(2026, 9, 5, 12, 0, tzinfo=UTC),
        minutes=6,
        loops=2,
        loop_offset_s=30,
    )
    result = await script.count(args)
    first, second = result["loops"]
    assert first["flight_planner"] > 0
    assert first["drafter"] > 0
    assert sum(second.values()) < sum(first.values()) / 4
    assert result["answers"]["flight_planner hit"] > 0
