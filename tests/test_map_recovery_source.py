"""The map survives a resize and the stream reopens (SPEC T09 A1, A2/B04): source checks on
``wall/map.js``, ``wall.js`` and ``connect.js``. MapLibre 4.7 died inside an easing frame when a
camera move started while another eased or the container resized mid-frame, and an EventSource
closed by an HTTP error was never reopened."""

import re
from pathlib import Path

WEB = Path(__file__).resolve().parents[1] / "tephra" / "web"


def _read(rel: str) -> str:
    return (WEB / rel).read_text(encoding="utf-8")


def _method(source: str, name: str) -> str:
    """The body of a class method or function ``name`` (brace-balanced from its first ``{``)."""
    match = re.search(rf"^\s*(?:async\s+)?(?:function\s+)?{name}\s*\([^)]*\)\s*\{{", source, re.M)
    assert match, f"no method or function {name}"
    depth, i = 0, match.end() - 1
    for i in range(match.end() - 1, len(source)):
        if source[i] == "{":
            depth += 1
        elif source[i] == "}":
            depth -= 1
            if depth == 0:
                break
    return source[match.start() : i + 1]


def test_a_resize_stops_the_easing_before_resizing_and_reframing() -> None:
    body = _method(_read("wall/map.js"), "onResized")
    assert "isMoving()" in body
    assert "stop()" in body
    assert body.index("stop()") < body.index("resize()") < body.index("frame(")


def test_resizes_are_settled_before_the_map_is_told() -> None:
    source = _read("wall/map.js")
    observer = re.search(r"new ResizeObserver\(\(\) => \{(.*?)\}\)\.observe\(container\)", source)
    assert observer, "no ResizeObserver on the container"
    assert "clearTimeout" in observer.group(1)
    assert "setTimeout" in observer.group(1)
    assert "onResized()" in observer.group(1)


def test_frame_stops_a_running_move_before_fitting() -> None:
    body = _method(_read("wall/map.js"), "frame")
    stop = re.search(r"if \(this\.map\.isMoving\(\)\) this\.map\.stop\(\);", body)
    assert stop, "frame() never stops a running move"
    assert stop.start() < body.index("cameraForBounds(")
    assert stop.start() < body.index("easeTo(")
    assert stop.start() < body.index("fitBounds(")


def test_an_easing_crash_rebuilds_the_map_once_where_it_was() -> None:
    source = _read("wall/map.js")
    assert "const MAP_CRASH = /_onEaseFrame|already running/;" in source
    on_error = _method(source, "onError")
    assert "MAP_CRASH.test(msg)" in on_error
    assert "this.recover()" in on_error
    recover = _method(source, "recover")
    assert "this._recovered" in recover.split("\n")[1], "recover() is not guarded by _recovered"
    steps = ("getCenter()", "getZoom()", "this.map.remove()", "this.attachMap(")
    for step in (*steps, "this.update(this.D)", "this.frame({ animate: false })"):
        assert step in recover, step
    assert 'this.onNote?.("map", "Map restarted after an error")' in recover
    # the crash is thrown from requestAnimationFrame: the window's error event reaches onError too
    window = r'window\.addEventListener\("error".*MAP_CRASH\.test\(msg\).*this\.onError'
    assert re.search(window, source)


def test_the_wall_reopens_a_closed_stream_and_backs_off() -> None:
    wall = _read("wall.js")
    assert 'from "./wall/stream.js"' in wall
    on_error = re.search(r"es\.onerror = \(\) => \{(.*?)\n  \};", wall, re.S)
    assert on_error, "no es.onerror block"
    assert "shouldReopen(es.readyState)" in on_error.group(1)
    assert "dropStream(es); scheduleReopen(); return;" in on_error.group(1)
    assert "if (es.readyState !== EventSource.OPEN) streamLost();" in on_error.group(1)
    lost = _method(wall, "streamLost")
    assert "scheduleReopen()" in lost
    reopen = _method(wall, "scheduleReopen")
    assert "conn.backoff = nextRetryMs(conn.backoff)" in reopen
    assert "!conn.source && !conn.paused" in reopen
    assert "conn.backoff = 0" in _method(wall, "openStream").split("es.onerror")[0]
    load = _method(wall, "load")
    assert "if (!conn.source || shouldReopen(conn.source.readyState)) openStream();" in load


def test_connect_reopens_a_closed_stream_after_five_seconds() -> None:
    connect = _read("connect.js")
    assert 'from "./wall/stream.js"' in connect
    stream = _method(connect, "openStream")
    assert "source.onerror" in stream
    assert "shouldReopen(source.readyState)" in stream
    assert "setTimeout(openStream, STREAM_RETRY_MS)" in stream


def test_the_streams_only_reopen_on_the_closed_state() -> None:
    stream = _read("wall/stream.js")
    assert "export const shouldReopen = (readyState) => readyState === 2;" in stream
    assert "export const STREAM_RETRY_MS = 5000;" in stream
