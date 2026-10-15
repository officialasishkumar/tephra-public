"""Cloud Trace correlation: every log line written while a request is handled carries the
trace Cloud Run's front end stamped on it (``X-Cloud-Trace-Context``, or W3C
``traceparent``), in the fields Cloud Logging joins to Cloud Trace when the project is
known, else as a plain ``trace_id``. A malformed header is ignored."""

import json
import logging
from collections.abc import Iterator
from pathlib import Path
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient
from starlette.datastructures import Headers
from test_api import PIN, FakeRuntime

from tephra.api.server import JsonLogFormatter, configure_logging, create_app, request_trace
from tephra.config import Settings
from tephra.pipeline import Runtime
from tephra.store import open_store

TRACE_ID = "105445aa7843bc8bf206b12000100000"
PROJECT = "tephra-demo"
CLOUD_HEADER = {"X-Cloud-Trace-Context": f"{TRACE_ID}/1;o=1"}
W3C_HEADER = {"traceparent": f"00-{TRACE_ID}-00f067aa0ba902b7-01"}


class CapturingHandler(logging.Handler):
    def __init__(self, formatter: logging.Formatter) -> None:
        super().__init__()
        self.setFormatter(formatter)
        self.lines: list[dict[str, Any]] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.lines.append(json.loads(self.format(record)))


@pytest.fixture
def access_log() -> Iterator[CapturingHandler]:
    handler = CapturingHandler(JsonLogFormatter(project=PROJECT))
    logger = logging.getLogger("tephra.api.access")
    level = logger.level
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)
    yield handler
    logger.removeHandler(handler)
    logger.setLevel(level)


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    settings = Settings(
        _env_file=None,
        llm="stub",
        store="sqlite",
        sqlite_path=tmp_path / "tephra.sqlite3",
        cache_dir=tmp_path / "cache",
        data_dir=tmp_path / "data",
        desk_pin=PIN,
        session_secret="test-session-secret-0123456789abcdef",
        local_scheduler=False,
    )

    async def factory(settings: Settings) -> Runtime:
        return cast(Runtime, FakeRuntime(settings=settings, store=open_store(settings)))

    with TestClient(create_app(settings, runtime_factory=factory)) as test_client:
        yield test_client


def access_line(handler: CapturingHandler, path: str) -> dict[str, Any]:
    lines = [
        line for line in handler.lines if line.get("httpRequest", {}).get("requestUrl") == path
    ]
    assert len(lines) == 1, lines
    return lines[0]


def test_log_lines_carry_the_cloud_trace_of_the_request(
    client: TestClient, access_log: CapturingHandler
) -> None:
    assert client.get("/api/state", headers=CLOUD_HEADER).status_code == 200
    line = access_line(access_log, "/api/state")
    assert line["logging.googleapis.com/trace"] == f"projects/{PROJECT}/traces/{TRACE_ID}"
    assert line["logging.googleapis.com/spanId"] == "0000000000000001"
    assert line["logging.googleapis.com/trace_sampled"] is True
    assert "trace_id" not in line

    assert client.get("/api/policy", headers=W3C_HEADER).status_code == 200
    w3c = access_line(access_log, "/api/policy")
    assert w3c["logging.googleapis.com/trace"] == f"projects/{PROJECT}/traces/{TRACE_ID}"
    assert w3c["logging.googleapis.com/spanId"] == "00f067aa0ba902b7"
    assert w3c["logging.googleapis.com/trace_sampled"] is True

    assert client.get("/api/feeds").status_code == 200
    plain = access_line(access_log, "/api/feeds")
    assert not any(key.startswith("logging.googleapis.com/") for key in plain)


def test_a_malformed_trace_header_is_ignored(
    client: TestClient, access_log: CapturingHandler
) -> None:
    bad = {"X-Cloud-Trace-Context": "not-a-trace;o=1", "traceparent": "00-zz-11-01"}
    assert client.get("/api/state", headers=bad).status_code == 200
    line = access_line(access_log, "/api/state")
    assert not any(key.startswith("logging.googleapis.com/") for key in line)
    assert "trace_id" not in line
    assert line["httpRequest"]["status"] == 200


@pytest.mark.parametrize(
    ("headers", "expected"),
    [
        ({"x-cloud-trace-context": f"{TRACE_ID}/1;o=1"}, (TRACE_ID, "0000000000000001", True)),
        ({"x-cloud-trace-context": f"{TRACE_ID}/123;o=0"}, (TRACE_ID, "000000000000007b", False)),
        ({"x-cloud-trace-context": TRACE_ID}, (TRACE_ID, None, False)),
        ({"x-cloud-trace-context": TRACE_ID.upper()}, (TRACE_ID, None, False)),
        (
            {"traceparent": f"00-{TRACE_ID}-00f067aa0ba902b7-00"},
            (TRACE_ID, "00f067aa0ba902b7", False),
        ),
        ({"x-cloud-trace-context": "abc"}, None),
        ({"traceparent": f"00-{TRACE_ID}-short-01"}, None),
        ({}, None),
    ],
)
def test_the_trace_headers_are_read_as_google_documents_them(
    headers: dict[str, str], expected: tuple[str, str | None, bool] | None
) -> None:
    trace = request_trace(Headers(headers))
    if expected is None:
        assert trace is None
    else:
        assert trace is not None
        assert (trace.trace_id, trace.span_id, trace.sampled) == expected


def test_without_a_project_the_line_carries_a_plain_trace_id(
    client: TestClient,
) -> None:
    handler = CapturingHandler(JsonLogFormatter())
    logger = logging.getLogger("tephra.api.access")
    level = logger.level
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)
    try:
        assert client.get("/api/state", headers=CLOUD_HEADER).status_code == 200
    finally:
        logger.removeHandler(handler)
        logger.setLevel(level)
    line = access_line(handler, "/api/state")
    assert line["trace_id"] == TRACE_ID
    assert not any(key.startswith("logging.googleapis.com/") for key in line)


def test_configure_logging_passes_the_project_to_the_formatter() -> None:
    root = logging.getLogger()
    handlers, level = root.handlers[:], root.level
    try:
        configure_logging("INFO", project=PROJECT)
        (handler,) = root.handlers
        formatter = handler.formatter
        assert isinstance(formatter, JsonLogFormatter)
        assert formatter.project == PROJECT
        configure_logging("INFO")
        (handler,) = root.handlers
        assert cast(JsonLogFormatter, handler.formatter).project is None
    finally:
        root.handlers[:] = handlers
        root.setLevel(level)
