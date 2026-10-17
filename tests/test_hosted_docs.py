"""What the hosted pages' documents say (SPEC hosted §8 H6): the privacy page and the docs say the
airline's model key is stored sealed and shown only as its last four, the Not built list is in
docs/HOSTED.md, no file H6 wrote carries a forbidden or retired word, and the deploy notes keep
hosting off: cloudrun.sh parses, mounts TEPHRA_KEY_SECRET only when asked, forwards the hosted
limits, and .github/workflows/deploy.yml is unchanged."""

import re
import shutil
import subprocess
from pathlib import Path

import pytest

from tests.test_glossary import RETIRED

ROOT = Path(__file__).resolve().parents[1]
PRIVACY = (ROOT / "tephra/web/privacy.html").read_text(encoding="utf-8")
HOSTED = (ROOT / "docs/HOSTED.md").read_text(encoding="utf-8")
README = (ROOT / "deploy/README.md").read_text(encoding="utf-8")
FLAT = " ".join(HOSTED.split())
BASE = "bc3fac9"  # the tree H6 started from: lines already there are not H6's to police
CLOUDRUN = ROOT / "deploy/cloudrun.sh"
H6_FILES = [
    "docs/HOSTED.md",
    "docs/GLOSSARY.md",
    "docs/ONBOARDING.md",
    "docs/UI-DESIGN.md",
    "deploy/README.md",
    "deploy/cloudrun.sh",
    "tephra/web/privacy.html",
    "tephra/web/admin.html",
    "tephra/web/admin.js",
    "tephra/web/admin.css",
    "tephra/web/workspace.html",
    "tephra/web/workspace.js",
    "tephra/web/workspace/golive.js",
    "tephra/web/workspace/join.js",
    "tephra/web/workspace/overview.js",
    "tephra/web/workspace/feeds.js",
    "tephra/web/workspace/api.js",
    "tephra/web/account-nav.js",
    "tephra/web/onboard/pages.js",
    "tephra/web/product.css",
    *sorted(
        str(p.relative_to(ROOT)) for p in (ROOT / "tests/fixtures/hosted").glob("[wa][od]*/*.json")
    ),
]


def _forbidden() -> list[tuple[re.Pattern[str], list[str]]]:
    """deploy/public/forbidden.txt's line patterns, each with the path prefixes it allows."""
    rules: list[tuple[re.Pattern[str], list[str]]] = []
    for raw in (ROOT / "deploy/public/forbidden.txt").read_text(encoding="utf-8").splitlines():
        line = re.split(r"\s+#", raw)[0].strip()
        if not line or line.startswith("#") or line.startswith("path:"):
            continue
        if line.startswith("allow:") and rules:
            rules[-1][1].extend(line[len("allow:") :].split())
            continue
        rules.append((re.compile(line), []))
    return rules


def test_the_model_key_is_said_sealed_and_shown_as_its_last_four() -> None:
    assert (
        "only sealed (encrypted with AES-256-GCM) and shown only as its last four characters"
        in PRIVACY
    )
    assert "sealed with AES-256-GCM" in FLAT
    assert "shown only as its last four (`••••x9Qa`)" in FLAT
    assert "makes every sealed key unreadable" in README


def test_the_privacy_page_says_what_who_and_how_it_is_deleted() -> None:
    # its own fold, as every section of the notice (owner, 17 Oct 2026: "nobody is going to read
    # so much")
    section = PRIVACY.split('<details id="hosted" class="pfold">')[1].split("</details>")[0]
    assert "<summary><h2>Hosted airlines</h2></summary>" in section
    for words in (
        "members' emails and the names they chose",
        "its policy versions",
        "the airline's record",
        "only its ops managers see members' emails",
        "never its drafts, people or key",
        "from 7 days after suspending it",
        "a tombstone with its code, its name and the times it was set up and deleted stays",
        "TEPHRA sends no email, and emails are not checked",
    ):
        assert words in section, words


def test_hosted_md_has_the_states_roles_limits_and_not_built() -> None:
    for heading in (
        "## 1. What an airline gets",
        "## 2. States",
        "## 3. Roles",
        "## 4. Keys",
        "## 5. Limits, allowances and pauses",
        "## 6. Not built",
    ):
        assert heading in HOSTED, heading
    not_built = HOSTED.split("## 6. Not built")[1].split("## 7.")[0]
    for item in (
        "no email is sent",
        "Password reset by email",
        "Two-factor sign-in",
        "Ollama on hosted TEPHRA",
        "Regions other than",
        "Recovery re-planning",
        "flights.json",
        "Policy B",
        "More than 3 airlines",
        "Re-sealing keys",
        "Persisted feed statistics",
        "A grace window",
    ):
        assert item in not_built, item
    assert "It is **off** on the deployed demo" in FLAT


def test_hosted_md_follows_the_declutter() -> None:
    """Owner, 17 Oct 2026: the setup kit is dropped and the decision-support sentence is not page
    chrome; the SHADOW stamp and the Switch to LIVE dialog keep their honesty words."""
    assert "The footer keeps today's sentence" not in FLAT
    assert "Private to <name> and TEPHRA staff" in FLAT
    assert "own TEPHRA" not in FLAT
    assert "setup kit" not in FLAT.lower()
    assert "every SHADOW draft keeps its stamp" in FLAT
    assert "the places line beside Start says it" in FLAT


def test_the_glossary_and_the_honesty_table_name_the_new_words() -> None:
    glossary = (ROOT / "docs/GLOSSARY.md").read_text(encoding="utf-8")
    for word in ("| SHADOW |", "| LIVE |", "| Ops manager |", "| TEPHRA staff |"):
        assert word in glossary, word
    ui = (ROOT / "docs/UI-DESIGN.md").read_text(encoding="utf-8")
    table = ui.split("### 11.1 Honesty labels (exact)")[1].split("### 11.2")[0]
    for row in (
        "| SHADOW (hosted airline, page level) |",
        "| Shadow · not for use (data level) |",
        "| Emails are not checked |",
        "| Private |",
        "| Unpaid-tier data use |",
    ):
        assert row in table, row


@pytest.mark.skipif(
    not (ROOT / "deploy/public/forbidden.txt").is_file(),
    reason="the export lists are not in the public copy",
)
def test_no_forbidden_or_retired_word_in_h6_files() -> None:
    rules = _forbidden()
    hits = []
    for rel in H6_FILES:
        base = subprocess.run(
            ["git", "show", f"{BASE}:{rel}"], cwd=ROOT, capture_output=True, text=True, check=False
        )
        old = set(base.stdout.splitlines()) if base.returncode == 0 else set()
        for n, line in enumerate((ROOT / rel).read_text(encoding="utf-8").splitlines(), 1):
            if line in old:
                continue
            for pattern, allowed in rules:
                if pattern.search(line) and not any(rel.startswith(a.rstrip("*")) for a in allowed):
                    hits.append(f"{rel}:{n} {pattern.pattern}")
    assert hits == []
    for rel in (
        "docs/HOSTED.md",
        "tephra/web/admin.js",
        "tephra/web/workspace/golive.js",
        "tephra/web/workspace/join.js",
        "tephra/web/privacy.html",
    ):
        text = (ROOT / rel).read_text(encoding="utf-8")
        assert not [w for w in RETIRED if w in text], rel


def test_pages_say_airline_never_tenant() -> None:
    for rel in (
        "tephra/web/admin.js",
        "tephra/web/workspace/golive.js",
        "tephra/web/workspace/join.js",
        "tephra/web/workspace/overview.js",
        "tephra/web/privacy.html",
    ):
        text = (ROOT / rel).read_text(encoding="utf-8")
        strings = (
            re.findall(r'"(?:\\.|[^"\\])*"|`(?:\\.|[^`\\])*`', text)
            if rel.endswith(".js")
            else [re.sub(r"<[^>]+>", " ", text)]
        )
        words = [s for s in strings if not s.startswith(('"/', "`/"))]
        assert not [s for s in words if re.search(r"\btenants?\b", s, re.I)], rel


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash is not installed")
def test_cloudrun_parses_and_mounts_the_key_secret_only_when_asked() -> None:
    subprocess.run(["bash", "-n", str(CLOUDRUN)], check=True)
    script = CLOUDRUN.read_text(encoding="utf-8")
    assert (
        'if [ "${TEPHRA_MOUNT_KEY_SECRET:-0}" = 1 ]; then\n  SECRETS+=(TEPHRA_KEY_SECRET)\nfi'
        in script
    )
    forwarded = re.search(r"^FORWARDED=\((.*?)\)", script, re.M | re.S).group(1).split()  # type: ignore[union-attr]
    for name in (
        "MAX_TENANTS",
        "TICK_BUDGET_S",
        "READS_CAP",
        "WRITES_CAP",
        "DELETES_CAP",
        "TENANT_SHARE",
        "BLOB_PUTS_CAP",
        "RSS_LIMIT_MB",
        "PUSH_GAP_S",
        "STREAMS_PER_TENANT",
    ):
        assert f"TEPHRA_HOSTED_{name}" in forwarded, name


@pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
def test_the_deploy_workflow_is_unchanged_and_names_no_hosted() -> None:
    workflow = ROOT / ".github/workflows/deploy.yml"
    diff = subprocess.run(
        ["git", "diff", "--quiet", "HEAD", "--", str(workflow)], cwd=ROOT, check=False
    )
    assert diff.returncode == 0
    assert "hosted" not in workflow.read_text(encoding="utf-8")
