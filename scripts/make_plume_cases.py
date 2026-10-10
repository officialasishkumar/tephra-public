"""Download the Plume Reader test cases from Tokyo VAAC's labelled archive.

The ten cases and the protocol are in research/10-gemini-capability-and-architecture-check.md
(section 5). For each advisory id this saves, under ``evals/plume/cases/<id>/``:

* ``advisory.html``   the VAA text page (the label; withheld from the model in Arm I);
* ``as_T-20.png``, ``as_T-10.png``, ``as_T.png``  three Ash RGB frames ending at OBS VA DTG;
* ``ir_T.png``        the infrared frame at OBS VA DTG;
* ``case.json``       class, VAA fields, the chosen frame URLs, the vent pixel found in
                      ``as_T.png`` (the red triangle), the FL180 wind and anything that
                      needs a human check.

Frames are picked from the advisory's frame list script by the time stamp in each file name.
Without a usable OBS time the newest frames are taken (the lists run newest first) and
``case.json`` says so.

The wind is the advisory's own ``WIND FL180 ddd/ffKT`` group. Advisories that saw ash carry
none, so for those it is Open-Meteo's 500 hPa (FL180) wind at the vent for the hour nearest
OBS VA DTG (research/10). Otherwise only the quiet cases would have a wind line, and its
presence would give the label away.

Arm T (text reconciliation) needs the Semeru texts: ``--arm-t-date`` fetches that hour's
VA SIGMET snapshot from aviationweather.gov (kept 30 days) and refuses one that holds no
Semeru SIGMET. The VONA text must be copied by hand from the MAGMA page into
``evals/plume/arm_t/vona.txt`` (MAGMA disallows crawling).

Run it yourself; it makes network requests.

    uv run python scripts/make_plume_cases.py
    uv run python scripts/make_plume_cases.py --arm-t-date 2026-09-26T23:00:00Z
"""

from __future__ import annotations

import argparse
import io
import json
import re
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import numpy as np
from PIL import Image

from tephra.config import PROJECT_ROOT
from tephra.feeds.base import USER_AGENT, FetchResult
from tephra.feeds.sigmet import SIGMET_PARAMS, SIGMET_URL
from tephra.feeds.vaac import parse_vaa
from tephra.feeds.winds import parse_winds, profile_at, wind_at_fl
from tephra.models import FeedId, VaacAdvisory
from tephra.util.hashing import sha256_bytes

BASE = "https://ds.data.jma.go.jp/svd/vaac/data"
HISTORICAL_WINDS_URL = "https://historical-forecast-api.open-meteo.com/v1/forecast"
WIND_FL = 180
WIND_HPA = 500  # PRESSURE_LEVEL_FL: 500 hPa stands for FL180

# (id, class, note) from research/10 section 5. Labels come from the advisory text.
CASES: list[tuple[str, str, str]] = [
    ("20260925_30027000_0335", "ash", "Sheveluch; high plume, night, high latitude"),
    ("20260927_30027000_0345", "ash", "Sheveluch; large, elongated"),
    ("20260921_29036000_0002", "ash", "Chikurachki; medium, partly obscured"),
    ("20260910_29039000_0001", "ash", "Alaid; daytime"),
    ("20261008_27307000_0023", "ash", "Taal; tropical night, the TEPHRA-like case"),
    ("20261008_27307000_0024", "quiet", "Taal; VA not identifiable, same scene 3 h later"),
    ("20261008_28208001_0279", "quiet", "Sakurajima; VA not identifiable / dissipated"),
    ("20260926_30027000_0343", "quiet", "Sheveluch; VA not identifiable"),
    ("20260921_29036000_0004", "quiet", "Chikurachki; not identifiable, met cloud"),
    ("20260910_29039000_0002", "quiet", "Alaid; VA not identifiable"),
]

_IMAGE_PATH = re.compile(r"""["']([^"']+\.(?:png|jpg|jpeg|gif))["']""", re.IGNORECASE)
_STAMP = re.compile(r"(20\d{2})(\d{2})(\d{2})[_-]?(\d{2})(\d{2})")
_VAA_WIND = re.compile(r"WIND\s+FL(\d{3})\s+(\d{3})/(\d{1,3})KT")
# Measured on the Taal 2026/23 frames (668 x 501): the marker is 6-8 px across and 55-67 %
# filled; each time-stamp glyph is 10-19 x 16 px and 24-39 % filled.
_VENT_PIXELS = (8, 400)
_VENT_MIN_FILL = 0.45


def _get(client: httpx.Client, url: str) -> httpx.Response:
    response = client.get(url)
    response.raise_for_status()
    return response


def _stamp(path: str) -> datetime | None:
    match = _STAMP.search(path)
    if not match:
        return None
    year, month, day, hour, minute = (int(g) for g in match.groups())
    try:
        return datetime(year, month, day, hour, minute, tzinfo=UTC)
    except ValueError:
        return None


def pick_frames(paths: list[str], obs: datetime | None, count: int) -> tuple[list[str], str]:
    """The ``count`` frames ending at the OBS time, oldest first, plus how they were chosen.

    Tokyo VAAC frame lists run newest first, so the fallbacks take the newest frames.
    """
    stamped = sorted((s, p) for p in paths if (s := _stamp(p)) is not None)
    if obs is not None:
        before = [(s, p) for s, p in stamped if s <= obs]
        if len(before) >= count:
            return [p for _, p in before[-count:]], "by file-name time stamp <= OBS VA DTG"
    if len(stamped) >= count:
        how = "NEWEST FRAMES (OBS VA DTG unknown or before the frames): check by eye"
        return [p for _, p in stamped[-count:]], how
    return paths[:count][::-1], "FIRST FRAMES LISTED (no usable time stamps): check by eye"


def find_vent(png: bytes) -> tuple[int, int] | None:
    """Centre of the red triangle Tokyo VAAC draws on the vent, or None.

    The frame's time stamp and the JMA mark are drawn in the same saturated red, so the
    marker is told apart by shape: it is a solid blob, while letters are thin strokes that
    fill a third of their box at most.
    """
    rgb = np.asarray(Image.open(io.BytesIO(png)).convert("RGB")).astype(int)
    red = (rgb[..., 0] > 200) & (rgb[..., 1] < 80) & (rgb[..., 2] < 80)
    best: tuple[float, list[tuple[int, int]]] | None = None
    for blob in _blobs(red):
        ys, xs = zip(*blob, strict=True)
        width, height = max(xs) - min(xs) + 1, max(ys) - min(ys) + 1
        fill = len(blob) / (width * height)
        solid = _VENT_PIXELS[0] <= len(blob) <= _VENT_PIXELS[1] and fill >= _VENT_MIN_FILL
        if solid and min(width, height) >= 4 and (best is None or fill > best[0]):
            best = (fill, blob)
    if best is None:
        return None
    ys, xs = zip(*best[1], strict=True)
    return round(sum(xs) / len(xs)), round(sum(ys) / len(ys))


def _blobs(mask: np.ndarray) -> list[list[tuple[int, int]]]:
    """8-connected groups of set pixels, each as ``(y, x)`` pairs."""
    todo = set(zip(*(axis.tolist() for axis in np.nonzero(mask)), strict=True))
    blobs: list[list[tuple[int, int]]] = []
    while todo:
        stack, blob = [todo.pop()], []
        while stack:
            y, x = stack.pop()
            blob.append((y, x))
            for neighbour in ((y + dy, x + dx) for dy in (-1, 0, 1) for dx in (-1, 0, 1)):
                if neighbour in todo:
                    todo.remove(neighbour)
                    stack.append(neighbour)
        blobs.append(blob)
    return blobs


def to_png(content: bytes) -> bytes:
    """Gemini does not take GIF; store every frame as PNG."""
    out = io.BytesIO()
    Image.open(io.BytesIO(content)).convert("RGB").save(out, format="PNG")
    return out.getvalue()


def _fetch_result(feed: FeedId, url: str, response: httpx.Response) -> FetchResult:
    return FetchResult(
        feed=feed,
        url=url,
        status_code=response.status_code,
        content=response.content,
        content_type=response.headers.get("content-type"),
        fetched_at=datetime.now(UTC),
        sha256=sha256_bytes(response.content),
    )


def _read_vaa(url: str, response: httpx.Response) -> VaacAdvisory | None:
    """The advisory, or None when the page is not a readable VAA (flagged for a person)."""
    try:
        return parse_vaa(_fetch_result(FeedId.VAAC_TOKYO, url, response))
    except ValueError:
        return None


def open_meteo_wind(client: httpx.Client, lat: float, lon: float, at: datetime) -> str:
    """Open-Meteo's FL180 wind for the hour nearest ``at``, written like the VAA group
    ``WIND FL180 ddd/ffKT`` (the direction it blows from, knots)."""
    hour = at.replace(minute=0, second=0, microsecond=0)
    params = {
        "latitude": f"{lat:.2f}",
        "longitude": f"{lon:.2f}",
        "hourly": f"wind_speed_{WIND_HPA}hPa,wind_direction_{WIND_HPA}hPa",
        "wind_speed_unit": "kn",
        "timezone": "GMT",
        "start_hour": f"{hour:%Y-%m-%dT%H:%M}",
        "end_hour": f"{hour + timedelta(hours=1):%Y-%m-%dT%H:%M}",
    }
    response = client.get(HISTORICAL_WINDS_URL, params=params)
    response.raise_for_status()
    result = _fetch_result(FeedId.WINDS, str(response.url), response)
    profile = profile_at(parse_winds(result, lat=lat, lon=lon), at)
    if profile is None:
        raise ValueError("no hourly winds in the response")
    level = wind_at_fl(profile, WIND_FL)
    return f"WIND FL{WIND_FL} {round(level.from_deg) % 360:03d}/{round(level.speed_kt)}KT"


def _wind(
    client: httpx.Client, vaa: VaacAdvisory, obs: datetime | None, checks: list[str]
) -> tuple[str | None, str | None]:
    """``(wind_text, wind_source)``: the advisory's own group, else Open-Meteo's."""
    group = _VAA_WIND.search(vaa.raw_text)
    if group is not None:
        return group.group(0), "vaa"
    if obs is None or vaa.volcano_lat is None or vaa.volcano_lon is None:
        checks.append("wind: no WIND group, OBS time or vent position; set wind_text by hand")
        return None, None
    try:
        return open_meteo_wind(client, vaa.volcano_lat, vaa.volcano_lon, obs), "open-meteo"
    except (httpx.HTTPError, ValueError) as exc:
        checks.append(f"wind: Open-Meteo FL{WIND_FL} wind unavailable ({exc}); set it by hand")
        return None, None


def build_case(client: httpx.Client, case_id: str, label: str, note: str, out: Path) -> dict:
    year = case_id[:4]
    case_dir = out / case_id
    case_dir.mkdir(parents=True, exist_ok=True)
    text_url = f"{BASE}/TextData/{year}/{case_id}_Text.html"
    text = _get(client, text_url)
    (case_dir / "advisory.html").write_bytes(text.content)
    vaa = _read_vaa(text_url, text)
    obs = vaa.observation.valid_at if vaa and vaa.observation else None
    checks: list[str] = []
    record: dict = {"id": case_id, "class": label, "note": note, "text_url": text_url}
    for channel, count, names in (("as", 3, ["as_T-20", "as_T-10", "as_T"]), ("ir", 1, ["ir_T"])):
        script_url = f"{BASE}/Sat/{year}/Script/{case_id}_{channel}.js"
        paths = _IMAGE_PATH.findall(_get(client, script_url).text)
        if len(paths) < count:
            raise RuntimeError(f"{script_url}: only {len(paths)} frames listed")
        chosen, how = pick_frames(paths, obs, count)
        if how.endswith("check by eye"):
            checks.append(f"{channel}: {how}")
        record[f"{channel}_frames"] = []
        for name, path in zip(names, chosen, strict=True):
            url = (
                path if path.startswith("http") else f"{BASE}/Sat/{year}/Images/{path.lstrip('/')}"
            )
            png = to_png(_get(client, url).content)
            (case_dir / f"{name}.png").write_bytes(png)
            record[f"{channel}_frames"].append({"name": name, "url": url})
    vent = find_vent((case_dir / "as_T.png").read_bytes())
    if vent is None:
        checks.append("vent: no red triangle found in as_T.png; set vent_px by hand")
    record["vent_px"] = list(vent) if vent else None
    with Image.open(case_dir / "as_T.png") as image:
        record["image_size"] = list(image.size)
    if vaa is not None:
        layer = vaa.observation.layers[0] if vaa.observation and vaa.observation.layers else None
        record["vaa"] = {
            "advisory_nr": vaa.advisory_nr,
            "volcano": vaa.volcano_name,
            "volcano_lat": vaa.volcano_lat,
            "volcano_lon": vaa.volcano_lon,
            "obs_valid_at": obs.isoformat() if obs else None,
            "not_identifiable": bool(vaa.observation and vaa.observation.not_identifiable),
            "top_ft": layer.top_ft if layer else None,
            "polygon": layer.polygon.model_dump() if layer and layer.polygon else None,
            "movement_toward_deg": layer.movement_toward_deg if layer else None,
            "remarks": vaa.remarks,
        }
        record["wind_text"], record["wind_source"] = _wind(client, vaa, obs, checks)
    else:
        checks.append("vaa: advisory text did not parse")
    record["needs_human_check"] = checks
    (case_dir / "case.json").write_text(json.dumps(record, indent=2))
    return record


def semeru_sigmet_count(content: bytes) -> int:
    """Semeru SIGMETs in an isigmet JSON snapshot (an empty 204 body holds none)."""
    try:
        records = json.loads(content or b"[]")
    except json.JSONDecodeError:
        return 0
    if not isinstance(records, list):
        return 0
    return sum(
        isinstance(record, dict) and "SEMERU" in str(record.get("rawSigmet", ""))
        for record in records
    )


def fetch_arm_t_sigmet(client: httpx.Client, when: str, out: Path) -> Path:
    response = client.get(SIGMET_URL, params={**SIGMET_PARAMS, "date": when})
    response.raise_for_status()
    if not semeru_sigmet_count(response.content):
        raise SystemExit(
            f"The VA SIGMET snapshot for {when} holds no Semeru SIGMET (aviationweather.gov "
            "keeps 30 days); pick another hour."
        )
    arm_dir = out.parent / "arm_t"
    arm_dir.mkdir(parents=True, exist_ok=True)
    path = arm_dir / "sigmets.json"
    path.write_bytes(response.content)
    vona = arm_dir / "vona.txt"
    if not vona.exists():
        vona.write_text(
            "# Paste the MAGMA VONA text for the same hour here (open the page in a browser).\n"
        )
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Download the Plume Reader test cases.")
    parser.add_argument("--out", type=Path, default=PROJECT_ROOT / "evals" / "plume" / "cases")
    parser.add_argument("--only", action="append", help="case id to fetch (repeatable)")
    parser.add_argument("--arm-t-date", help="UTC time for the Arm T SIGMET snapshot")
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    with httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=30.0) as client:
        for case_id, label, note in CASES:
            if args.only and case_id not in args.only:
                continue
            try:
                record = build_case(client, case_id, label, note, args.out)
            except (httpx.HTTPError, RuntimeError) as exc:
                print(f"{case_id}: FAILED ({exc})")
                continue
            flags = "; ".join(record["needs_human_check"]) or "ok"
            print(f"{case_id} [{label}]: {flags}")
        if args.arm_t_date:
            print(f"Arm T SIGMETs -> {fetch_arm_t_sigmet(client, args.arm_t_date, args.out)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
