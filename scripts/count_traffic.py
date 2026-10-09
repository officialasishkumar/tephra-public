"""Count aircraft near a volcano over time, to decide whether the per-flight demo moment
can be live or must be a labelled replay (research/09: night traffic near Java is thin).

Polls adsb.lol's point API every ``--every`` minutes for ``--hours`` hours and writes one
CSV row per poll: UTC time, local solar hour, aircraft count, airborne count (alt_baro
above 1,000 ft) and how many are at or below ``--top-fl`` (could meet ash under that top).

Run it yourself; it makes network requests.

    uv run python scripts/count_traffic.py --volcano semeru --radius 250 --every 15 --hours 8
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import sys
import tempfile
from pathlib import Path

from tephra.feeds.adsb import fetch_aircraft, merge_aircraft
from tephra.feeds.base import HttpSource
from tephra.feeds.volcanoes import load_volcanoes
from tephra.geo.units import fl_to_ft, haversine_km, solar_hour
from tephra.models import AdsbQueryPoint
from tephra.util import timeutil

_NM_TO_KM = 1.852
_AIRBORNE_FT = 1000


async def run(args: argparse.Namespace) -> int:
    volcano = load_volcanoes(args.data_dir).resolve(args.volcano)
    if volcano is None:
        raise SystemExit(f"unknown volcano {args.volcano!r} (see data/volcanoes.json)")
    point = AdsbQueryPoint(lat=volcano.lat, lon=volcano.lon, radius_nm=args.radius)
    top_ft = fl_to_ft(args.top_fl)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    new_file = not args.out.exists()
    polls = max(1, int(args.hours * 60 // args.every) + 1)
    with tempfile.TemporaryDirectory(prefix="tephra-traffic-") as tmp, args.out.open("a") as fh:
        writer = csv.writer(fh)
        if new_file:
            writer.writerow(
                [
                    "utc",
                    "solar_hour",
                    "volcano",
                    "radius_nm",
                    "aircraft",
                    "airborne",
                    "at_or_below_top",
                ]
            )
        source = HttpSource(cache_dir=Path(tmp))
        try:
            for n in range(polls):
                at = timeutil.now()
                snapshots = await fetch_aircraft(source, [point])
                aircraft = [
                    a
                    for a in merge_aircraft(snapshots)
                    if haversine_km(volcano.lat, volcano.lon, a.lat, a.lon)
                    <= args.radius * _NM_TO_KM
                ]
                airborne = [a for a in aircraft if (a.alt_baro_ft or 0) > _AIRBORNE_FT]
                low = [a for a in airborne if (a.alt_baro_ft or 0) <= top_ft]
                row = [
                    timeutil.to_iso(at),
                    f"{solar_hour(volcano.lon, at):.1f}",
                    volcano.id,
                    args.radius,
                    len(aircraft),
                    len(airborne),
                    len(low),
                ]
                writer.writerow(row)
                fh.flush()
                print(", ".join(str(value) for value in row))
                if n < polls - 1:
                    await asyncio.sleep(args.every * 60)
        finally:
            await source.aclose()
    print(f"wrote {args.out}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Count aircraft near a volcano over time.")
    parser.add_argument("--volcano", required=True, help="id, name or GVP number")
    parser.add_argument("--radius", type=int, default=250, help="nm, at most 250")
    parser.add_argument("--every", type=float, default=15.0, help="minutes between polls")
    parser.add_argument("--hours", type=float, default=6.0)
    parser.add_argument("--top-fl", type=int, default=150, help="ash top to compare against")
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    parser.add_argument("--out", type=Path, default=Path(".state/traffic.csv"))
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    if not 0 < args.radius <= 250:
        parser.error("--radius must be 1-250 nm")
    return asyncio.run(run(args))


if __name__ == "__main__":
    raise SystemExit(main())
