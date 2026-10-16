"""Push aircraft positions into TEPHRA from any computer, as an airline's system would.

Needs only the Python standard library. It downloads TEPHRA's sample file (real recorded flights
at their recorded fixes, their flight plans and pilot reports), then every few seconds moves each
flight along its own track at its own ground speed and pushes to ``/api/push/positions`` with
your connection's key: the plans every minute, the pilot reports once. Times
follow TEPHRA's active clock (read from ``/api/state``), so it works in REPLAY too.

    python scripts/push_sample.py --url https://<your TEPHRA> --key tph_... [--every 5]

Your own feed would send your aircraft instead of the sample's; the format is in the sample file
and at ``/api/connect/schema.json``.
"""

import argparse
import json
import math
import sys
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime

EARTH_KM = 6371.0088


def get_json(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=20) as res:
        return json.load(res)


def tephra_now(base: str) -> datetime:
    state = get_json(f"{base}/api/state")
    return datetime.fromisoformat(state["now"].replace("Z", "+00:00"))


def moved(lat: float, lon: float, track: float, km: float) -> tuple[float, float]:
    d, t = km / EARTH_KM, math.radians(track)
    p1, l1 = math.radians(lat), math.radians(lon)
    p2 = math.asin(math.sin(p1) * math.cos(d) + math.cos(p1) * math.sin(d) * math.cos(t))
    l2 = l1 + math.atan2(
        math.sin(t) * math.sin(d) * math.cos(p1), math.cos(d) - math.sin(p1) * math.sin(p2)
    )
    return math.degrees(p2), (math.degrees(l2) + 540) % 360 - 180


def push(base: str, key: str, batch: dict) -> dict:
    req = urllib.request.Request(
        f"{base}/api/push/positions",
        data=json.dumps(batch).encode(),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=20) as res:
        return json.load(res)


def main() -> int:
    parser = argparse.ArgumentParser(description="Push aircraft positions into TEPHRA.")
    parser.add_argument(
        "--url", required=True, help="TEPHRA's address, e.g. https://tephra.example"
    )
    parser.add_argument("--key", required=True, help="the key from the Desk's Data connections")
    parser.add_argument("--every", type=float, default=5.0, help="seconds between pushes")
    parser.add_argument("--minutes", type=float, default=30.0, help="stop after this long")
    args = parser.parse_args()
    base = args.url.rstrip("/")
    sample = get_json(f"{base}/api/connect/sample.json")
    fixes = sample["positions"]
    plans, reports = sample.get("flight_plans", []), sample.get("pilot_reports", [])
    offset = tephra_now(base) - datetime.now(UTC)
    started = time.monotonic()
    print(f"pushing {len(fixes)} flights, {len(plans)} plans, {len(reports)} pilot reports")
    pushes = 0
    while time.monotonic() - started < args.minutes * 60:
        pushes += 1
        elapsed_h = (time.monotonic() - started) / 3600
        at = datetime.now(UTC) + offset
        positions = []
        for fix in fixes:
            km = (fix.get("gs_kt") or 0) * 1.852 * elapsed_h
            lat, lon = moved(fix["lat"], fix["lon"], fix.get("track_deg") or 0, km)
            iso = at.isoformat(timespec="milliseconds").replace("+00:00", "Z")
            positions.append(
                {**fix, "lat": round(lat, 5), "lon": round(lon, 5), "observed_at": iso}
            )
        # the plans with the first push and every minute after; the pilot reports once, 15 s in
        batch = {"format": "tephra.airline/1", "positions": positions}
        if pushes % max(1, round(60 / args.every)) == 1:
            batch["flight_plans"] = plans
        if pushes == 4:
            batch["pilot_reports"] = [{**r, "observed_at": iso} for r in reports]
        try:
            result = push(base, args.key, batch)
            ash, refused = len(result["in_ash"]), len(result["rejected"])
            taken = f"plans {result['plans_taken']}  reports {result['reports_taken']}"
            print(f"{at:%H%MZ}  +{result['accepted']}  ash {ash}  {taken}  refused {refused}")
        except urllib.error.HTTPError as exc:
            print(f"push refused: HTTP {exc.code} {exc.read().decode()[:200]}", file=sys.stderr)
            if exc.code == 401:
                return 1
        time.sleep(args.every)
    return 0


if __name__ == "__main__":
    sys.exit(main())
