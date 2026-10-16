"""The setup kit (SPEC-v2 §9), made in the browser by ``tephra/web/workspace/kit.js`` and
``workspace/zip.js``, run under Node: its airline.env parses as TEPHRA's own Settings for each
model provider, its policy.json is a valid operator policy that keeps the ILLUSTRATIVE label, the
zip opens, the secrets are fresh each time, and no template holds an invented row. Skipped when
Node is not installed.
"""

import base64
import io
import json
import os
import shutil
import subprocess
import zipfile
from pathlib import Path
from typing import Any

import pytest

from tephra.config import REGIONS, Settings
from tephra.models import OperatorPolicy
from tephra.policy import load_policy

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "tephra" / "web"
DRAFT = ROOT / "tests" / "fixtures" / "airline" / "draft.json"
NODE = shutil.which("node")
MODULES = [
    "workspace/kit.js",
    "workspace/zip.js",
    "workspace/api.js",
    "onboard/draft.js",
    "onboard/pages.js",
    "wall/util.js",
]
# Real airport positions (lon, lat) for the fixture's network: Jakarta, Surabaya, Bali.
POSITIONS = {"WIII": [106.6559, -6.1256], "WARR": [112.7869, -7.3798], "WADD": [115.1672, -8.7482]}

pytestmark = pytest.mark.skipif(NODE is None, reason="Node is not installed")

RUNNER = """
import { readFileSync } from "node:fs";
import { buildKit, makeSecrets, envLines } from "./workspace/kit.js";
import { makeZip, crc32 } from "./workspace/zip.js";
import { toAnswers } from "./onboard/pages.js";
const input = JSON.parse(readFileSync("input.json", "utf8"));
const draft = JSON.parse(readFileSync("draft.json", "utf8"));
const now = new Date("2026-10-16T10:58:00Z");
const b64 = (bytes) => Buffer.from(bytes).toString("base64");
const out = {};
for (const variant of input.variants) {
  const d = structuredClone(draft);
  d.values.assistant = variant.assistant;
  const answers = toAnswers(d);
  const view = {
    id: "AL-0123456789ab", version: 1, status: "pending", status_label: "Pending verification",
    email: "ops@rfa.example", answers, steps: [], editable: true,
  };
  const files = buildKit({
    airline: view, policy: input.policy, positions: input.positions, regions: input.regions,
    known: new Set(Object.keys(input.positions)), now, origin: "https://tephra.example",
    secrets: makeSecrets(globalThis.crypto), geminiKey: variant.key, ollamaUrl: variant.url,
    files: variant.files ? input.files : {}, pushTool: input.pushTool,
  });
  out[variant.name] = { files, zip: b64(makeZip(files, now)) };
}
out.secrets = [0, 1, 2].map(() => makeSecrets(globalThis.crypto));
const odd = { path: "tephra-kit-rfa/Ñandú Air · notes.md", text: "Søk ✓\\n" };
out.unicodeZip = b64(makeZip([odd], now));
out.crc = crc32(new TextEncoder().encode("The quick brown fox jumps over the lazy dog"));
out.partial = envLines({ airline: { name: "Ring of Fire Air", icao: "RFA" } }, {});
process.stdout.write(JSON.stringify(out));
"""

FLIGHTS = {
    "header": {"label": "Ring of Fire Air test day", "anchor_utc_offset_h": 7},
    "flights": [
        {
            "flight_no": "RFA101",
            "origin": "WARR",
            "dest": "WIII",
            "std_min": 300,
            "block_min": 80,
            "tail": "PK-RFA",
        }
    ],
}
CREWS = {"crews": [{"crew_id": "C1", "base": "WIII", "report_min": 285}]}
VARIANTS = [
    {
        "name": "gemini",
        "assistant": {
            "provider": "gemini",
            "model": "gemini-3.8-flash",
            "model_lite": "gemma-4-31b-it",
        },
        "key": "AIza-test-key-123",
        "url": None,
        "files": True,
    },
    {
        "name": "gemini_nokey",
        "assistant": {
            "provider": "gemini",
            "model": "gemini-9-pro",
            "model_lite": "gemini-3.5-flash-lite",
        },
        "key": "",
        "url": None,
        "files": False,
    },
    {
        "name": "ollama",
        "assistant": {"provider": "ollama", "model": "gemma4:e4b", "model_lite": "gemma4:e2b"},
        "key": "AIza-never",
        "url": "http://10.0.0.5:11434",
        "files": False,
    },
    {
        "name": "none",
        "assistant": {"provider": "none", "model": None, "model_lite": None},
        "key": "",
        "url": None,
        "files": False,
    },
]


@pytest.fixture(scope="module")
def kit(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    tmp = tmp_path_factory.mktemp("kit")
    for rel in MODULES:
        (tmp / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(WEB / rel, tmp / rel)
    (tmp / "package.json").write_text('{"type": "module"}', encoding="utf-8")
    (tmp / "run.mjs").write_text(RUNNER, encoding="utf-8")
    shutil.copy(DRAFT, tmp / "draft.json")
    policy = load_policy(ROOT / "data").model_dump(mode="json")
    data = {
        "variants": VARIANTS,
        "policy": policy,
        "positions": POSITIONS,
        "regions": [r.model_dump(mode="json") for r in REGIONS.values()],
        "files": {"flights": json.dumps(FLIGHTS), "crews": json.dumps(CREWS)},
        "pushTool": (WEB / "kit" / "push.py").read_text(encoding="utf-8"),
    }
    (tmp / "input.json").write_text(json.dumps(data), encoding="utf-8")
    result = subprocess.run(
        [str(NODE), "run.mjs"], cwd=tmp, capture_output=True, text=True, timeout=60, check=True
    )
    return json.loads(result.stdout)


def _file(kit: dict[str, Any], variant: str, name: str) -> str:
    return next(f["text"] for f in kit[variant]["files"] if f["path"] == f"tephra-kit-rfa/{name}")


def _settings(env_text: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Settings:
    for name in list(os.environ):
        if name.startswith(("TEPHRA_", "GEMINI_", "GOOGLE_")):
            monkeypatch.delenv(name, raising=False)
    path = tmp_path / "airline.env"
    path.write_text(env_text, encoding="utf-8")
    return Settings(_env_file=path)


def test_the_kit_holds_the_nine_files(kit: dict[str, Any]) -> None:
    names = [f["path"] for f in kit["gemini"]["files"]]
    assert names == [
        f"tephra-kit-rfa/{n}"
        for n in (
            "airline.env",
            "policy.json",
            "fleet.json",
            "flights.json",
            "crews.json",
            "network.json",
            "answers.json",
            "push.py",
            "CHECKLIST.md",
        )
    ]
    assert _file(kit, "gemini", "push.py") == (WEB / "kit" / "push.py").read_text(encoding="utf-8")


def test_gemini_env_parses_and_the_key_is_only_in_airline_env(
    kit: dict[str, Any], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env = _file(kit, "gemini", "airline.env")
    s = _settings(env, tmp_path, monkeypatch)
    assert s.llm == "gemini"
    assert s.model == "gemini-3.8-flash"
    assert s.model_lite == "gemma-4-31b-it"
    assert s.gemini_api_key is not None
    assert s.gemini_api_key.get_secret_value() == "AIza-test-key-123"
    assert s.fleet_prefixes == frozenset({"RFA", "RFX"})
    assert s.fleet_hexes == frozenset({"8a0412", "8a0413", "8a0415"})
    assert s.network_airports == frozenset({"WIII", "WARR", "WADD"})
    assert s.policy_file == "policy/airline.json"
    assert s.features == frozenset({"connect", "crew"})
    assert s.region == "java_bali"
    assert s.recovery_auto is False
    assert s.mode.value == "LIVE"
    assert s.visitor_access == "off"
    others = [f["text"] for f in kit["gemini"]["files"] if not f["path"].endswith("airline.env")]
    assert not any("AIza-test-key-123" in t for t in others)
    assert env.startswith(
        "# TEPHRA for Ring of Fire Air (RFA), made in the workspace on 2026-10-16.\n"
    )
    assert "# Status on https://tephra.example: Pending verification.\n" in env
    assert "Decision support only." in env


def test_gemini_without_a_key_says_so_and_an_unknown_model_is_flagged(kit: dict[str, Any]) -> None:
    env = _file(kit, "gemini_nokey", "airline.env")
    assert "\nGEMINI_API_KEY=\n" in env
    assert "Paste your own Google AI Studio key" in env
    assert (
        "gemini-9-pro has no row in TEPHRA's free-tier table: it is never called (AI UNAVAILABLE)"
        in env
    )
    assert "gemini-3.5-flash-lite has no row" not in env
    check = _file(kit, "gemini_nokey", "CHECKLIST.md")
    assert "AI UNAVAILABLE" in check
    assert "TEPHRA does not start without it" in check


def test_ollama_and_no_model_envs_parse(
    kit: dict[str, Any], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env = _file(kit, "ollama", "airline.env")
    s = _settings(env, tmp_path, monkeypatch)
    assert (s.llm, s.model, s.model_lite, s.ollama_url) == (
        "ollama",
        "gemma4:e4b",
        "gemma4:e2b",
        "http://10.0.0.5:11434",
    )
    assert "GEMINI_API_KEY" not in env
    assert not any("AIza-never" in f["text"] for f in kit["ollama"]["files"])
    env = _file(kit, "none", "airline.env")
    s = _settings(env, tmp_path, monkeypatch)
    assert s.llm == "stub"
    assert "TEPHRA_LLM=stub  # NO MODEL: code checks only" in env
    assert "TEPHRA_MODEL=" not in env


def test_policy_json_is_a_valid_operator_policy_with_the_changes(kit: dict[str, Any]) -> None:
    active = load_policy(ROOT / "data").model_dump(mode="json")
    raw = json.loads(_file(kit, "gemini", "policy.json"))
    policy = OperatorPolicy.model_validate(raw)
    assert policy.policy_id == "RFA-POLICY-A"
    assert policy.version == "2026.10.1"
    assert policy.label == active["label"] == "ILLUSTRATIVE, not an airline SRA"
    assert policy.title == "Ring of Fire Air operator policy A (from onboarding, ILLUSTRATIVE)"
    assert policy.risk_owner == "Director of Flight Operations"
    assert policy.sra_ref == "RFA-SRA-VA-01 rev 3"
    margin = raw["exposure"]["vertical_margin_ft"]
    assert margin["value"] == 3000
    assert (
        margin["source"]
        == "Set by the operator: SRA 4.2: wider vertical margin near ash. Policy A had 2000 ft."
    )
    assert margin["citation_ids"] == active["exposure"]["vertical_margin_ft"]["citation_ids"]
    assert raw["reroute"] == active["reroute"]
    assert raw["citations"] == active["citations"]


def test_fleet_network_and_schedule_files(kit: dict[str, Any]) -> None:
    fleet = json.loads(_file(kit, "gemini", "fleet.json"))
    assert fleet["tails"][0] == {
        "tail": "PK-RFA",
        "type": "A320",
        "seats": 180,
        "home_base": "WIII",
        "hex": "8a0412",
    }
    assert fleet["tails"][1] == {"tail": "PK-RFB", "type": "A320", "seats": 180, "hex": "8a0413"}
    assert all("crew_id" not in t for t in fleet["tails"])
    network = json.loads(_file(kit, "gemini", "network.json"))
    assert network["airports"][0] == {"icao": "WIII", "alternates": ["WIHH"]}
    assert json.loads(_file(kit, "gemini", "flights.json")) == FLIGHTS
    assert json.loads(_file(kit, "gemini", "crews.json")) == CREWS
    # without the files in this browser the templates hold no row
    flights = json.loads(_file(kit, "ollama", "flights.json"))
    assert flights == {
        "header": {"label": "Ring of Fire Air schedule (fill in)", "anchor_utc_offset_h": None},
        "flights": [],
    }
    assert json.loads(_file(kit, "ollama", "crews.json")) == {"crews": []}
    assert "## The schedule formats" in _file(kit, "ollama", "CHECKLIST.md")
    answers = json.loads(_file(kit, "gemini", "answers.json"))
    assert answers["airline_id"] == "AL-0123456789ab"
    assert answers["workspace"] == "https://tephra.example/workspace"


def test_checklist_has_eight_steps_and_the_honesty_lines(kit: dict[str, Any]) -> None:
    check = _file(kit, "gemini", "CHECKLIST.md")
    steps = [line for line in check.splitlines() if line.startswith("- [ ] **")]
    assert len(steps) == 8
    assert "drafts name each flight by an RFA number of the fictional Ring of Fire Air" in steps[0]
    assert "Policy B" in steps[0]
    assert "recovery re-planning for your network" in steps[0]
    assert "cp tephra-kit-rfa/airline.env .env" in check
    assert "cp tephra-kit-rfa/policy.json data/policy/airline.json" in check
    assert "--stamp-now" in check
    assert "Data connections" in check


def test_the_zip_opens_and_names_are_utf8(kit: dict[str, Any]) -> None:
    for variant in ("gemini", "none"):
        z = zipfile.ZipFile(io.BytesIO(base64.b64decode(kit[variant]["zip"])))
        assert z.testzip() is None
        assert z.read("tephra-kit-rfa/fleet.json").decode() == _file(kit, variant, "fleet.json")
    z = zipfile.ZipFile(io.BytesIO(base64.b64decode(kit["unicodeZip"])))
    assert z.testzip() is None
    assert z.namelist() == ["tephra-kit-rfa/Ñandú Air · notes.md"]
    assert z.read(z.namelist()[0]).decode() == "Søk ✓\n"
    assert kit["crc"] == 0x414FA339


def test_secrets_are_fresh_and_long_enough(kit: dict[str, Any]) -> None:
    pins = [s["pin"] for s in kit["secrets"]]
    assert len(set(pins)) == 3
    for s in kit["secrets"]:
        assert len(s["pin"]) == 14
        assert s["pin"][4] == s["pin"][9] == "-"
        assert set(s["pin"].replace("-", "")) <= set("ABCDEFGHJKMNPQRSTVWXYZ23456789")
        assert len(s["session_secret"]) == 43
        assert len(s["task_token"]) == 43
    assert len({s["session_secret"] for s in kit["secrets"]}) == 3


def test_a_partial_answer_adds_only_its_own_lines(kit: dict[str, Any]) -> None:
    lines = kit["partial"]
    assert lines[0].startswith("# TEPHRA for Ring of Fire Air (RFA), made in the workspace on ")
    assert not any(
        line.startswith(
            (
                "TEPHRA_FLEET_PREFIXES",
                "TEPHRA_FLEET_HEXES",
                "TEPHRA_NETWORK_AIRPORTS",
                "TEPHRA_LLM",
                "TEPHRA_REGION",
            )
        )
        for line in lines
    )
    assert "TEPHRA_DESK_PIN=<made when you download>" in lines
