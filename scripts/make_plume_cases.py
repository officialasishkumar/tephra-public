"""Download the Plume Reader test cases from Tokyo VAAC's labelled archive.

The ten cases and the protocol are in research/10-gemini-capability-and-architecture-check.md
(section 5). For each advisory id this saves, under ``evals/plume/cases/<id>/``:

* ``advisory.html``   the VAA text page (the label; withheld from the model in Arm I);
* ``as_T-20.png``, ``as_T-10.png``, ``as_T.png``  three Ash RGB frames ending at OBS VA DTG;
* ``ir_T.png``        the infrared frame at OBS VA DTG;
* ``case.json``       class, VAA fields, the chosen frame URLs, the vent pixel found in
                      ``as_T.png`` (the red triangle) and anything that needs a human check.

Frames are picked from the advisory's frame list script by the time stamp in each file name;
if a name carries no stamp the last three frames are used and ``case.json`` says so.

Arm T (text reconciliation) needs the Semeru texts: ``--arm-t-date`` fetches that hour's
VA SIGMET snapshot from aviationweather.gov (kept 30 days). The VONA text must be copied by
hand from the MAGMA page into ``evals/plume/arm_t/vona.txt`` (MAGMA disallows crawling).

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
from datetime import UTC, datetime
from pathlib import Path

import httpx
import numpy as np
from PIL import Image

from tephra.feeds.base import USER_AGENT, FetchResult
from tephra.feeds.sigmet import SIGMET_PARAMS, SIGMET_URL
from tephra.feeds.vaac import parse_vaa
from tephra.models import FeedId
from tephra.util.hashing import sha256_bytes

BASE = "https://ds.data.jma.go.jp/svd/vaac/data"

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
    """The ``count`` frames ending at the OBS time, oldest first, plus how they were chosen."""
    stamped = [(s, p) for p in paths if (s := _stamp(p)) is not None]
    if obs is not None and len(stamped) >= count:
        before = sorted((s, p) for s, p in stamped if s <= obs)
        if len(before) >= count:
            return [p for _, p in before[-count:]], "by file-name time stamp <= OBS VA DTG"
    return paths[-count:], "LAST FRAMES (no usable time stamps): check by eye"


def find_vent(png: bytes) -> tuple[int, int] | None:
    """Centroid of saturated red pixels: Tokyo VAAC marks the vent with a red triangle."""
    rgb = np.asarray(Image.open(io.BytesIO(png)).convert("RGB")).astype(int)
    red = (rgb[..., 0] > 200) & (rgb[..., 1] < 80) & (rgb[..., 2] < 80)
    ys, xs = np.nonzero(red)
    if len(xs) < 3:
        return None
    return round(float(xs.mean())), round(float(ys.mean()))


def to_png(content: bytes) -> bytes:
    """Gemini does not take GIF; store every frame as PNG."""
    out = io.BytesIO()
    Image.open(io.BytesIO(content)).convert("RGB").save(out, format="PNG")
    return out.getvalue()


def build_case(client: httpx.Client, case_id: str, label: str, note: str, out: Path) -> dict:
    year = case_id[:4]
    case_dir = out / case_id
    case_dir.mkdir(parents=True, exist_ok=True)
    text_url = f"{BASE}/TextData/{year}/{case_id}_Text.html"
    text = _get(client, text_url)
    (case_dir / "advisory.html").write_bytes(text.content)
    vaa = parse_vaa(
        FetchResult(
            feed=FeedId.VAAC_TOKYO,
            url=text_url,
            status_code=text.status_code,
            content=text.content,
            content_type=text.headers.get("content-type"),
            fetched_at=datetime.now(UTC),
            sha256=sha256_bytes(text.content),
        )
    )
    obs = vaa.observation.valid_at if vaa and vaa.observation else None
    checks: list[str] = []
    record: dict = {"id": case_id, "class": label, "note": note, "text_url": text_url}
    for channel, count, names in (("as", 3, ["as_T-20", "as_T-10", "as_T"]), ("ir", 1, ["ir_T"])):
        script_url = f"{BASE}/Sat/{year}/Script/{case_id}_{channel}.js"
        paths = _IMAGE_PATH.findall(_get(client, script_url).text)
        if len(paths) < count:
            raise RuntimeError(f"{script_url}: only {len(paths)} frames listed")
        chosen, how = pick_frames(paths, obs, count)
        if how.startswith("LAST"):
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
        wind = re.search(r"WIND\s+FL(\d{3})\s+(\d{3})/(\d{1,3})KT", vaa.raw_text)
        record["wind_text"] = wind.group(0) if wind else None
    else:
        checks.append("vaa: advisory text did not parse")
    record["needs_human_check"] = checks
    (case_dir / "case.json").write_text(json.dumps(record, indent=2))
    return record


def fetch_arm_t_sigmet(client: httpx.Client, when: str, out: Path) -> Path:
    arm_dir = out.parent / "arm_t"
    arm_dir.mkdir(parents=True, exist_ok=True)
    response = client.get(SIGMET_URL, params={**SIGMET_PARAMS, "date": when})
    response.raise_for_status()
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
    parser.add_argument("--out", type=Path, default=Path("evals/plume/cases"))
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
