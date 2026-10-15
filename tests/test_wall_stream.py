"""The Wall's stream reopen logic, ``tephra/web/wall/stream.js``, run under Node: the wait between
tries doubles from 5 s to a minute and starts again after a good open, and only a source the browser
has given up on (EventSource.CLOSED) is replaced by the page. Skipped when Node is not installed."""

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

WALL = Path(__file__).resolve().parents[1] / "tephra" / "web" / "wall"
NODE = shutil.which("node")

RUNNER = """
import { nextRetryMs, shouldReopen, STREAM_RETRY_MS } from "./wall/stream.js";
const waits = [];
let prev = 0;
for (let i = 0; i < 7; i++) { prev = nextRetryMs(prev); waits.push(prev); }
process.stdout.write(JSON.stringify({
  waits,
  afterGoodOpen: nextRetryMs(0),
  afterUndefined: nextRetryMs(undefined),
  reopen: [0, 1, 2].map((s) => shouldReopen(s)),
  retryMs: STREAM_RETRY_MS,
}));
"""

pytestmark = pytest.mark.skipif(NODE is None, reason="Node is not installed")


@pytest.fixture(scope="module")
def stream(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    root = tmp_path_factory.mktemp("stream")
    (root / "wall").mkdir()
    shutil.copy(WALL / "stream.js", root / "wall" / "stream.js")
    (root / "package.json").write_text('{"type": "module"}', encoding="utf-8")
    (root / "run.mjs").write_text(RUNNER, encoding="utf-8")
    result = subprocess.run(
        [str(NODE), "run.mjs"], cwd=root, capture_output=True, text=True, timeout=60, check=True
    )
    return json.loads(result.stdout)


def test_the_wait_doubles_from_five_seconds_to_a_minute(stream: dict[str, Any]) -> None:
    assert stream["waits"] == [5000, 10000, 20000, 40000, 60000, 60000, 60000]


def test_a_good_open_starts_the_waits_again(stream: dict[str, Any]) -> None:
    assert stream["afterGoodOpen"] == 5000
    assert stream["afterUndefined"] == 5000
    assert stream["retryMs"] == 5000


def test_only_a_closed_source_is_reopened_by_the_page(stream: dict[str, Any]) -> None:
    # EventSource.CONNECTING (0) is the browser's own retry; OPEN (1) needs nothing; CLOSED (2)
    # after an HTTP error is never retried by the browser
    assert stream["reopen"] == [False, False, True]
