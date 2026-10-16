"""Push your airline's data to your own TEPHRA, in the tephra.airline/1 format.

Part of the setup kit made in the TEPHRA airline workspace. Standard library only.

  python3 push.py --url URL --key tph_... [--dry-run] plans --schedule flights.json \\
      --fleet fleet.json --date YYYY-MM-DD [--callsign-rule ICAO] [--tails-are-today]
  python3 push.py --url URL --key tph_... [--dry-run] positions FILE.csv|FILE.json [--stamp-now]

Make the key on your TEPHRA's Desk: account menu, Data connections, New connection. Nothing is
guessed: a flight plan with neither a callsign nor a known aircraft address is skipped, and a
position without observed_at is refused unless --stamp-now stamps it at send time (for
positions measured in the last minute only). Exit codes: 0 sent, 1 records refused, 2 usage or
HTTP error.
"""

import argparse
import contextlib
import csv
import json
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import UTC, date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

FORMAT = "tephra.airline/1"
PUSH_PATH = "/api/push/positions"
BATCH = 1000
BATCH_BYTES = 500_000
"""TEPHRA refuses a push body over 512 KiB; a batch stays under it with room to spare."""
GAP_S = 1.1
"""TEPHRA takes at most one push a second per connection."""
STAMP_MAX_AGE_S = 60
AIRLINE_CALLSIGN = re.compile(r"[A-Z]{3}[0-9][0-9A-Z]{0,3}")
"""TEPHRA checks only airline-style callsigns (designator and flight number) against the ash."""
POSITION_COLUMNS = (
    "hex",
    "callsign",
    "type_icao",
    "lat",
    "lon",
    "alt_baro_ft",
    "gs_kt",
    "track_deg",
    "observed_at",
)
NUMBERS = {"lat": float, "lon": float, "alt_baro_ft": int, "gs_kt": float, "track_deg": float}
OK, REFUSED, FAILED = 0, 1, 2


class UsageError(Exception):
    pass


def iso(value: datetime) -> str:
    value = value.astimezone(UTC)
    return value.strftime("%Y-%m-%dT%H:%M:%S.") + f"{value.microsecond // 1000:03d}Z"


# --- flight plans -----------------------------------------------------------------------


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise UsageError(f"{path}: {exc}") from None


def flies_on(row: dict[str, Any], day: date) -> bool:
    """``days`` as in SSIM: digits 1-7, 1 = Monday; absent means daily."""
    days = row.get("days")
    return days is None or str(day.isoweekday()) in str(days)


def ruled_callsign(flight_no: str, rule: str | None) -> str | None:
    """With --callsign-rule ICAO: ICAO + the flight number's trailing digits without leading
    zeros (RF0401 -> RFA401). Without the rule no callsign is made."""
    if rule is None:
        return None
    digits = re.search(r"(\d+)$", flight_no)
    if digits is None:
        return None
    return f"{rule}{int(digits.group(1))}"


def plan_records(
    schedule: dict[str, Any],
    fleet: dict[str, Any],
    day: date,
    *,
    callsign_rule: str | None,
    tails_are_today: bool,
) -> tuple[list[dict[str, Any]], list[str]]:
    """The flight plans for ``day`` and a line for each flight skipped."""
    offset = schedule.get("header", {}).get("anchor_utc_offset_h")
    if not isinstance(offset, int | float):
        raise UsageError("flights.json: header.anchor_utc_offset_h is not set")
    midnight = datetime(day.year, day.month, day.day, tzinfo=timezone(timedelta(hours=offset)))
    hexes = {
        tail["tail"]: tail["hex"]
        for tail in fleet.get("tails", [])
        if isinstance(tail, dict) and tail.get("tail") and tail.get("hex")
    }
    plans: list[dict[str, Any]] = []
    skipped: list[str] = []
    for row in schedule.get("flights", []):
        if not flies_on(row, day):
            continue
        flight_no = str(row["flight_no"])
        std = midnight + timedelta(minutes=int(row["std_min"]))
        plan: dict[str, Any] = {
            "flight": flight_no,
            "origin_icao": row["origin"],
            "dest_icao": row["dest"],
            "std": iso(std),
            "sta": iso(std + timedelta(minutes=int(row["block_min"]))),
        }
        callsign = row.get("callsign") or ruled_callsign(flight_no, callsign_rule)
        hex_id = hexes.get(row.get("tail", "")) if tails_are_today else None
        if callsign is None and hex_id is None:
            skipped.append(f"skipped {flight_no}: no callsign and no known address")
            continue
        if callsign is not None:
            plan["callsign"] = callsign
        if hex_id is not None:
            plan["hex"] = hex_id
        plans.append(plan)
    return plans, skipped


# --- positions --------------------------------------------------------------------------


def read_positions(path: Path) -> list[dict[str, Any]]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise UsageError(f"{path}: {exc}") from None
    if path.suffix.lower() == ".json":
        try:
            data = json.loads(text)
        except ValueError as exc:
            raise UsageError(f"{path}: {exc}") from None
        rows = data.get("positions", []) if isinstance(data, dict) else data
        if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
            raise UsageError(f"{path}: expected a list of position objects")
        return [tidy(row) for row in rows]
    reader = csv.DictReader(text.splitlines())
    missing = [c for c in POSITION_COLUMNS[:-1] if c not in (reader.fieldnames or [])]
    if missing:
        raise UsageError(f"{path}: missing columns {', '.join(missing)}")
    return [tidy(row) for row in reader]


def tidy(row: dict[str, Any]) -> dict[str, Any]:
    """Only the format's keys; empty cells left out; numbers as numbers where they parse
    (TEPHRA refuses what does not, with its reason)."""
    record: dict[str, Any] = {}
    for key in POSITION_COLUMNS:
        value = row.get(key)
        if value is None or (isinstance(value, str) and not value.strip()):
            continue
        if isinstance(value, str):
            value = value.strip()
            if key in NUMBERS:
                with contextlib.suppress(ValueError):
                    value = NUMBERS[key](value)
        record[key] = value
    return record


def stamp(
    rows: list[dict[str, Any]], path: Path, *, stamp_now: bool, now: datetime
) -> tuple[list[dict[str, Any]], list[str], int]:
    """Positions with a time keep it. Without one a position is refused here, unless
    --stamp-now stamps it with the send time; that refuses a file written over a minute ago,
    which would make old positions look current."""
    if stamp_now:
        age_s = now.timestamp() - path.stat().st_mtime
        if age_s > STAMP_MAX_AGE_S:
            raise UsageError(
                f"{path.name} was written {round(age_s / 60)} min ago: --stamp-now would make "
                "old positions look current"
            )
    kept: list[dict[str, Any]] = []
    refused: list[str] = []
    stamped = 0
    for number, row in enumerate(rows, start=1):
        if "observed_at" in row:
            kept.append(row)
        elif stamp_now:
            kept.append({**row, "observed_at": iso(now)})
            stamped += 1
        else:
            refused.append(f"row {number}: no observed_at; add it or use --stamp-now")
    return kept, refused, stamped


def unchecked(rows: list[dict[str, Any]]) -> int:
    return sum(1 for r in rows if AIRLINE_CALLSIGN.fullmatch(str(r.get("callsign", ""))) is None)


# --- sending ----------------------------------------------------------------------------


def batches(records: list[dict[str, Any]], section: str) -> list[dict[str, Any]]:
    """At most BATCH records and BATCH_BYTES of JSON each."""
    out: list[list[dict[str, Any]]] = []
    size = 0
    for record in records:
        cost = len(json.dumps(record).encode("utf-8")) + 2
        if not out or len(out[-1]) >= BATCH or size + cost > BATCH_BYTES:
            out.append([])
            size = len(json.dumps({"format": FORMAT, section: []}))
        out[-1].append(record)
        size += cost
    return [{"format": FORMAT, section: chunk} for chunk in out]


def send(url: str, key: str, batch: dict[str, Any]) -> dict[str, Any]:
    request = urllib.request.Request(
        url.rstrip("/") + PUSH_PATH,
        data=json.dumps(batch).encode("utf-8"),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        result: dict[str, Any] = json.loads(response.read().decode("utf-8"))
    return result


def error_detail(exc: urllib.error.HTTPError) -> str:
    """TEPHRA's error body says why (``detail``); anything else is shown as the reason."""
    try:
        body = json.loads(exc.read().decode("utf-8"))
    except (OSError, ValueError):
        return str(exc.reason)
    return str(body.get("detail", exc.reason)) if isinstance(body, dict) else str(exc.reason)


def report(result: dict[str, Any], section: str) -> str:
    refused = len(result.get("rejected", []))
    if section == "flight_plans":
        line = f"plans taken {result.get('plans_taken', 0)} · refused {refused}"
    else:
        line = (
            f"taken {result.get('accepted', 0)} · in the ash {len(result.get('in_ash', []))} · "
            f"refused {refused}"
        )
    reasons = [
        f"  {problem.get('section')}[{problem.get('index')}] {problem.get('reason')}"
        for problem in result.get("rejected", [])
    ]
    return "\n".join([line, *reasons])


def push_all(args: argparse.Namespace, records: list[dict[str, Any]], section: str) -> int:
    """Each batch sent at least GAP_S after the last; 1 when TEPHRA refused any record."""
    refused = False
    for number, batch in enumerate(batches(records, section)):
        if args.dry_run:
            print(json.dumps(batch, indent=2))
            continue
        if number:
            time.sleep(GAP_S)
        try:
            result = send(args.url, args.key, batch)
        except urllib.error.HTTPError as exc:
            print(f"push refused: HTTP {exc.code} {error_detail(exc)}", file=sys.stderr)
            return FAILED
        except (urllib.error.URLError, OSError, ValueError) as exc:
            print(f"push failed: {exc}", file=sys.stderr)
            return FAILED
        print(report(result, section))
        refused = refused or bool(result.get("rejected"))
    if args.dry_run:
        print("Dry run: nothing was sent.")
    return REFUSED if refused else OK


def run_plans(args: argparse.Namespace) -> int:
    try:
        day = date.fromisoformat(args.date)
    except ValueError:
        raise UsageError("--date must be YYYY-MM-DD") from None
    plans, skipped = plan_records(
        read_json(Path(args.schedule)),
        read_json(Path(args.fleet)),
        day,
        callsign_rule=args.callsign_rule,
        tails_are_today=args.tails_are_today,
    )
    for line in skipped:
        print(line)
    if not plans:
        print("No flight plan to send.")
        return REFUSED if skipped else OK
    status = push_all(args, plans, "flight_plans")
    return max(status, REFUSED if skipped else OK)


def run_positions(args: argparse.Namespace) -> int:
    path = Path(args.file)
    rows = read_positions(path)
    kept, refused, stamped = stamp(rows, path, stamp_now=args.stamp_now, now=datetime.now(UTC))
    for line in refused:
        print(line)
    if stamped:
        print(
            f"Stamped {stamped} positions with the send time: use only for positions measured "
            "in the last minute."
        )
    if no_callsign := unchecked(kept):
        print(
            f"{no_callsign} positions have no airline-style callsign: TEPHRA takes them but does "
            "not check them against the ash."
        )
    if not kept:
        print("No position to send.")
        return REFUSED if refused else OK
    status = push_all(args, kept, "positions")
    return max(status, REFUSED if refused else OK)


def parser() -> argparse.ArgumentParser:
    top = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    top.add_argument("--url", required=True, help="your TEPHRA, e.g. http://localhost:8080")
    top.add_argument("--key", required=True, help="the connection key (tph_...)")
    top.add_argument("--dry-run", action="store_true", help="print the batches, send nothing")
    commands = top.add_subparsers(dest="command", required=True)
    plans = commands.add_parser("plans", help="flight plans for one day of flights.json")
    plans.add_argument("--schedule", required=True, help="flights.json")
    plans.add_argument("--fleet", required=True, help="fleet.json")
    plans.add_argument("--date", required=True, help="YYYY-MM-DD")
    plans.add_argument("--callsign-rule", help="your ICAO designator, to make callsigns")
    plans.add_argument(
        "--tails-are-today",
        action="store_true",
        help="the schedule's tails are the aircraft flying that day (sends their addresses)",
    )
    positions = commands.add_parser("positions", help="positions from a CSV or JSON file")
    positions.add_argument("file", help="FILE.csv or FILE.json")
    positions.add_argument(
        "--stamp-now", action="store_true", help="stamp positions with no time at send time"
    )
    return top


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    rule = getattr(args, "callsign_rule", None)
    if rule is not None:
        args.callsign_rule = rule.strip().upper()
        if re.fullmatch(r"[A-Z]{3}", args.callsign_rule) is None:
            print("--callsign-rule must be a 3-letter ICAO designator", file=sys.stderr)
            return FAILED
    try:
        return run_plans(args) if args.command == "plans" else run_positions(args)
    except UsageError as exc:
        print(exc, file=sys.stderr)
        return FAILED


if __name__ == "__main__":
    sys.exit(main())
