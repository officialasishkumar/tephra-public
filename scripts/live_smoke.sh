#!/usr/bin/env bash
# Smoke-test a deployed TEPHRA from the outside: public endpoints only, no secrets, no Desk
# sign-in. deploy/cloudrun.sh runs it against a new revision before moving traffic; you can
# run it by hand or from cron/launchd with --watch. Needs only python3 (standard library).
#
#   scripts/live_smoke.sh <base-url> [--read-only] [--watch MINUTES]
#
#   --read-only   skip POST /tasks/tick and the tick-freshness check (a revision that serves no
#                 traffic receives no Scheduler ticks; never POST to a candidate)
#   --watch N     repeat every N minutes and print one timestamped line per run
#
# Optional expectations (environment): EXPECT_SHA (build commit), EXPECT_MODE (LIVE|REPLAY),
# EXPECT_CASE (replay case id), TICK_INTERVAL_S (default 60; a tick older than 3x fails).
# Exit status is non-zero when any check fails. When the build reports where it runs
# (state.cloud), the run also checks it is Cloud Run on Firestore with a revision name, that
# GET /api/audit/verify answers 200, and GET /api/evals (404 is reported, not failed).
#
# Cloud Run answers 429 or 503 while the single instance starts. A request that gets one is
# retried with backoff for up to SMOKE_RETRY_S (default 90) seconds, and SMOKE_RETRY_BUDGET_S
# (default 240) caps the waiting in one run, so a service that never comes up still fails in
# minutes. The check's line says so, for example "PASS healthz: 200, mode=REPLAY (429 for
# 20 s, then 200)". Two limits keep that from hiding a broken service:
#   - A 429 or 503 after the service has already answered in this run is not a start-up: the
#     instance went away or filled up under a running service, and real users got it too. That
#     check FAILS even when a retry then succeeds ("... after the service had answered").
#   - --watch does not retry at all (SMOKE_RETRY_S defaults to 0 there): a monitor reports
#     what a visitor gets, and a visitor's browser does not retry.
set -euo pipefail

usage() {
  echo "usage: $0 <base-url> [--read-only] [--watch MINUTES]" >&2
  exit 2
}

[ $# -ge 1 ] || usage
BASE="${1%/}"
shift
READ_ONLY=0
WATCH_MIN=""
while [ $# -gt 0 ]; do
  case "$1" in
    --read-only) READ_ONLY=1; shift ;;
    --watch)
      [ $# -ge 2 ] || usage
      WATCH_MIN="$2"; shift 2 ;;
    *) usage ;;
  esac
done
case "$BASE" in
  https://*|http://localhost*|http://127.0.0.1*) ;;
  *) echo "Refusing: <base-url> must be https:// (or http://localhost)." >&2; exit 2 ;;
esac
if [ -n "$WATCH_MIN" ] && ! [[ "$WATCH_MIN" =~ ^[1-9][0-9]*$ ]]; then
  echo "--watch takes a whole number of minutes, not '$WATCH_MIN'." >&2
  exit 2
fi

PIN_FILE="$(cd "$(dirname "$0")/.." && pwd)/tests/test_policy.py"
DEFAULT_RETRY_S=90
[ -z "$WATCH_MIN" ] || DEFAULT_RETRY_S=0

run_once() {
  python3 -I - "$BASE" "$READ_ONLY" "$PIN_FILE" "$DEFAULT_RETRY_S" <<'PY'
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime

BASE, READ_ONLY, PIN_FILE = sys.argv[1], sys.argv[2] == "1", sys.argv[3]
TICK_S = int(os.environ.get("TICK_INTERVAL_S", "60"))
TIMEOUT_S = 20
RETRY_STATUSES = (429, 503)
RETRY_S = float(os.environ.get("SMOKE_RETRY_S", sys.argv[4]))
RETRY_BUDGET_S = float(os.environ.get("SMOKE_RETRY_BUDGET_S", "240"))
failures = 0
retry_waited = 0.0  # seconds spent waiting out 429/503 in this run
retry_notes = []  # what the waiting looked like, for the next line printed
retried_checks = 0  # lines that carried such a note
answered = False  # the service has answered something other than 429/503 in this run
flapped = False  # a 429/503 came after that, since the last line printed


def report(ok, name, detail):
    global failures, flapped, retried_checks
    if retry_notes:
        detail = f"{detail} ({'; '.join(retry_notes)})"
        retry_notes.clear()
        retried_checks += 1
    if flapped:
        # Not a start-up: the service had answered, then refused. Whatever the retry got.
        ok = False
        flapped = False
    if ok is None:
        print(f"WARN {name}: {detail}")
        return
    if not ok:
        failures += 1
    print(f"{'PASS' if ok else 'FAIL'} {name}: {detail}")


def retry_after_s(headers):
    try:
        return max(1.0, float(headers.get("Retry-After", "")))
    except (TypeError, ValueError):
        return None


def open_retrying(req, timeout):
    """urlopen that waits out 429/503 with backoff (see the header of this script).

    Returns the open response; raises HTTPError with the last status when that is not a
    429/503 or the time runs out. Either way a note like "429 for 20 s, then 200" is left
    for the next line printed.
    """
    global retry_waited, answered, flapped
    started = time.monotonic()
    seen = []
    pause = 2.0
    after_answer = answered
    while True:
        try:
            resp = urllib.request.urlopen(req, timeout=timeout)
            final, error = resp.status, None
        except urllib.error.HTTPError as exc:
            final, error = exc.code, exc
        if final not in RETRY_STATUSES:
            answered = True
        elif after_answer:
            flapped = True
        if error is not None and final in RETRY_STATUSES:
            left = min(RETRY_S - (time.monotonic() - started), RETRY_BUDGET_S - retry_waited)
            if left > 0:
                if final not in seen:
                    seen.append(final)
                wait = min(retry_after_s(error.headers) or pause, 15.0, left)
                error.close()
                time.sleep(wait)
                retry_waited += wait
                pause = min(pause * 2, 15.0)
                continue
        if seen:
            codes = "/".join(str(code) for code in seen)
            waited = time.monotonic() - started
            outcome = "gave up" if final in RETRY_STATUSES else f"then {final}"
            when = ", after the service had answered" if after_answer else ""
            retry_notes.append(f"{codes} for {waited:.0f} s, {outcome}{when}")
        elif final in RETRY_STATUSES:
            when = " after the service had answered" if after_answer else ""
            why = "no retries" if RETRY_S <= 0 else "the run's retry time is used up"
            retry_notes.append(f"{final}{when}, not retried: {why}")
        if error is not None:
            raise error
        return resp


def fetch(path, method="GET", data=None, timeout=TIMEOUT_S):
    """(status, headers, body bytes); an HTTP error status is returned, not raised."""
    req = urllib.request.Request(BASE + path, method=method, data=data)
    req.add_header("User-Agent", "tephra-live-smoke")
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with open_retrying(req, timeout) as resp:
            return resp.status, resp.headers, resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.headers, exc.read()


def get_json(path):
    status, _, body = fetch(path)
    if status != 200:
        raise RuntimeError(f"GET {path} -> {status}")
    return json.loads(body)


def parse_time(text):
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def newest_pin():
    with open(PIN_FILE, encoding="utf-8") as handle:
        text = handle.read()
    block = re.search(r"PINNED_HASHES = \{(.*?)\n\}", text, re.S)
    if block is None:
        raise RuntimeError(f"no PINNED_HASHES in {PIN_FILE}")
    pins = re.findall(r'"([^"]+)":\s*"([0-9a-f]{64})"', block.group(1))
    if not pins:
        raise RuntimeError(f"PINNED_HASHES in {PIN_FILE} is empty")
    return pins[-1]


def check(name, func):
    try:
        func()
    except Exception as exc:  # each check reports its own failure and the run goes on
        report(False, name, f"{type(exc).__name__}: {exc}")


def healthz():
    # Cloud Run's front end answers /healthz itself with a 404 (reserved path), so probe /health.
    status, _, body = fetch("/health")
    mode = json.loads(body).get("mode") if status == 200 else None
    report(status == 200 and bool(mode), "healthz", f"{status}, mode={mode}")


state = {}


def api_state():
    state.update(get_json("/api/state"))
    report(True, "state", f"mode={state.get('mode')}, build_sha={state.get('build_sha')}")


def tick_fresh():
    if READ_ONLY:
        report(None, "tick", "skipped in --read-only (this revision gets no Scheduler ticks)")
        return
    if "last_tick_wall_at" not in state:
        report(False, "tick", "this build does not expose last_tick_wall_at")
        return
    limit_s = 3 * TICK_S
    current = state
    deadline = time.monotonic() + limit_s
    # A new instance has ticked nothing yet: wait for its first tick, up to the same limit.
    while current.get("last_tick_wall_at") is None and time.monotonic() < deadline:
        time.sleep(10)
        current = get_json("/api/state")
    if current.get("last_tick_wall_at") is None:
        report(False, "tick", f"no tick finished within {limit_s} s of asking")
        return
    finished = parse_time(current["last_tick_wall_at"])
    age = (parse_time(current["server_time"]) - finished).total_seconds()
    report(age < limit_s, "tick", f"last tick {age:.0f} s ago (limit {limit_s} s)")


def policy():
    served = get_json("/api/policy")["policy_hash"]
    shown = state["policy"]["policy_hash"]
    version, pinned = newest_pin()
    ok = served == shown == pinned and state["policy"]["version"] == version
    report(
        ok,
        "policy",
        f"state {state['policy']['version']} {shown[:12]}, /api/policy {served[:12]}, "
        f"newest pin {version} {pinned[:12]}",
    )


def build_sha():
    expected = os.environ.get("EXPECT_SHA")
    actual = state.get("build_sha")
    if not expected:
        report(None, "build_sha", f"{actual} (EXPECT_SHA not set, not compared)")
        return
    report(actual == expected, "build_sha", f"{actual}, expected {expected}")


def store():
    if "store" not in state:
        report(None, "store", "store health not exposed by this build")
        return
    ok = state["store"].get("ok")
    report(ok is True, "store", json.dumps(state["store"])[:200])


def cloud():
    """The facts a deployed build reports about where it runs, and the two routes a reader of
    the Wall's Runs on and Track record panels reaches: the audit chain's verification and
    the evals index. GET /api/evals answers 404 until the scorecard JSON is committed; that
    is reported, not failed."""
    if not state.get("cloud"):
        # The state carries cloud: null until the build that fills it; both routes below
        # arrive with that build, so a 404 from them is reported, not failed, until then.
        report(None, "cloud", "cloud facts not exposed by this build")
        return
    facts = state["cloud"]
    platform, revision, store_kind = facts.get("platform"), facts.get("revision"), facts.get("store")
    ok = platform == "cloud-run" and bool(revision) and store_kind == "firestore"
    report(ok, "cloud", f"platform={platform}, revision={revision}, store={store_kind}")
    status = fetch("/api/audit/verify")[0]
    report(status == 200, "audit-verify", f"GET /api/audit/verify -> {status}")
    status = fetch("/api/evals")[0]
    if status == 404:
        report(None, "evals", "GET /api/evals -> 404 (no scorecard JSON in this build yet)")
    else:
        report(status == 200, "evals", f"GET /api/evals -> {status}")


def mode_and_case():
    want_mode = os.environ.get("EXPECT_MODE")
    want_case = os.environ.get("EXPECT_CASE")
    case = (state.get("replay") or {}).get("case_id")
    if want_mode:
        report(state.get("mode") == want_mode, "mode", f"{state.get('mode')}, expected {want_mode}")
    if want_case:
        report(case == want_case, "case", f"{case}, expected {want_case}")
    if not want_mode and not want_case:
        report(None, "mode", f"{state.get('mode')}, case {case} (EXPECT_MODE/EXPECT_CASE not set)")


def page(path):
    status, headers, body = fetch(path)
    csp = headers.get("Content-Security-Policy")
    detail = f"{status}, CSP {'present' if csp else 'MISSING'}"
    report(status == 200 and bool(csp), f"page {path}", detail)
    if status != 200:
        return
    assets = sorted(set(re.findall(r'(?:href|src)="(/static/[^"#?]+)', body.decode("utf-8"))))
    bad = []
    for asset in assets:
        code = fetch(asset)[0]
        if code != 200:
            bad.append(f"{asset} -> {code}")
    detail = f"{len(assets)} checked" + (f"; {', '.join(bad)}" if bad else "")
    report(not bad, f"assets {path}", detail)


def events():
    req = urllib.request.Request(BASE + "/api/events", headers={"User-Agent": "tephra-live-smoke"})
    with open_retrying(req, 30) as resp:
        started = time.monotonic()
        kind = resp.headers.get("Content-Type", "")
        if not kind.startswith("text/event-stream"):
            report(False, "events", f"Content-Type {kind!r}")
            return
        while time.monotonic() - started < 30:
            line = resp.readline()
            if not line:
                break
            if line.startswith(b"event:"):
                name = line.decode("utf-8").split(":", 1)[1].strip()
                waited = time.monotonic() - started
                report(True, "events", f"first event '{name}' after {waited:.0f} s")
                return
    report(False, "events", "no event within 30 s")


def airline_session():
    """Read-only: with onboard on, the deploy's session secret reached the service."""
    body = get_json("/api/airline/session")
    accounts = body.get("accounts")
    if "onboard" in state.get("features", []):
        report(accounts is True, "airline session", f"accounts={accounts} (onboard is on)")
    else:
        report(accounts is False, "airline session", f"accounts={accounts} (onboard is off)")


def tick_refused():
    if READ_ONLY:
        report(None, "tick-auth", "skipped in --read-only (never POST to a candidate)")
        return
    status = fetch("/tasks/tick", method="POST", data=b"{}")[0]
    report(status in (401, 403), "tick-auth", f"POST /tasks/tick without the token -> {status}")


check("healthz", healthz)
check("state", api_state)
if state:
    check("tick", tick_fresh)
    check("policy", policy)
    check("build_sha", build_sha)
    check("store", store)
    check("mode", mode_and_case)
    check("cloud", cloud)
else:
    report(False, "state checks", "skipped: GET /api/state failed")
check("page /", lambda: page("/"))
check("page /demo", lambda: page("/demo"))
check("page /onboard", lambda: page("/onboard"))
check("page /desk", lambda: page("/desk"))
check("airline session", airline_session)
check("events", events)
check("tick-auth", tick_refused)
waited = f"; waited out 429/503 for {retry_waited:.0f} s in {retried_checks} check(s)" if retried_checks else ""
print(f"{'OK' if failures == 0 else 'FAILED'}: {failures} failed check(s) against {BASE}{waited}")
sys.exit(1 if failures else 0)
PY
}

if [ -z "$WATCH_MIN" ]; then
  run_once
  exit $?
fi

while true; do
  stamp="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  if output="$(run_once 2>&1)"; then
    echo "$stamp OK $BASE"
  else
    echo "$stamp FAILED $BASE"
    echo "$output" | grep -v '^PASS' | sed 's/^/    /'
  fi
  sleep "$((WATCH_MIN * 60))"
done
