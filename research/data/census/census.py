#!/usr/bin/env python3
"""TEPHRA contradiction census (research file 14).

Standard library only. Reads the raw downloads under raw/ (see manifest.tsv)
and writes tables to out/. Run with the interpreter in isolated mode, passing
the census directory as the only argument:

    python3 -I census.py research/data/census

Sources parsed
  raw/magma/vona_p*.html        MAGMA Indonesia VONA list pages (magma.esdm.go.id/v1/vona?page=N)
  raw/darwin/ftp/IDY41*.txt     Darwin VAAC advisory texts (ftp://ftp.bom.gov.au/anon/gen/vaac/2026/)
  raw/tokyo/text/*_Text.html    Tokyo VAAC advisory texts (ds.data.jma.go.jp/svd/vaac/data/TextData/2026/)
  raw/sigmet/awc_isigmet_va_*.json  hourly snapshots of VA SIGMETs valid at each hour
                                (aviationweather.gov/api/data/isigmet?format=json&hazard=va&date=...)

All definitions used for the published numbers are written next to the code
that computes them (search for "DEF:").
"""
import csv
import datetime as dt
import glob
import html
import json
import math
import os
import re
import statistics
import sys
from collections import Counter, defaultdict

UTC = dt.timezone.utc
BASE = sys.argv[1] if len(sys.argv) > 1 else os.getcwd()
RAW = os.path.join(BASE, "raw")
OUT = os.path.join(BASE, "out")
os.makedirs(OUT, exist_ok=True)

# DEF: census window = exactly 30 days ending at the time the MAGMA and BoM
# archives were downloaded (2026-10-09 ~19:30Z).
WIN_START = dt.datetime(2026, 9, 9, 19, 0, tzinfo=UTC)
WIN_END = dt.datetime(2026, 10, 9, 19, 0, tzinfo=UTC)

# JAPAC FIRs whose VA SIGMETs are kept (Indonesia, PNG, Philippines, Japan, Pacific neighbours).
JAPAC_FIRS = {"WAAF", "WIIF", "AYPM", "RPHI", "RJJJ", "WMFC", "VVHM", "VVHN", "RCAA",
              "YMMM", "YBBB", "NZZO", "NFFF", "AGGG", "NVVV", "ANAU", "WSJC", "VTBB"}

COMPASS = {"N": 0, "NNE": 22.5, "NE": 45, "ENE": 67.5, "E": 90, "ESE": 112.5, "SE": 135,
           "SSE": 157.5, "S": 180, "SSW": 202.5, "SW": 225, "WSW": 247.5, "W": 270,
           "WNW": 292.5, "NW": 315, "NNW": 337.5}
WORD_DIR = {"north": "N", "northeast": "NE", "east": "E", "southeast": "SE", "south": "S",
            "southwest": "SW", "west": "W", "northwest": "NW",
            "north-northeast": "NNE", "east-northeast": "ENE", "east-southeast": "ESE",
            "south-southeast": "SSE", "south-southwest": "SSW", "west-southwest": "WSW",
            "west-northwest": "WNW", "north-northwest": "NNW"}


def canon(name):
    """Map the different spellings in VONA / VAA / SIGMET to one volcano key."""
    n = html.unescape(name).upper()
    n = re.sub(r"\b\d{6}\b", "", n)
    n = re.sub(r"^\s*MT\.?\s+", "", n).strip()
    if "LEWOTOBI" in n:
        return "LEWOTOBI PEREMPUAN" if "PEREMPUAN" in n else "LEWOTOBI LAKI-LAKI"
    if "LEWOTOLOK" in n:
        return "ILI LEWOTOLOK"
    if "KRAKATAU" in n:
        return "ANAK KRAKATAU"
    if "SAKURAJIMA" in n:
        return "SAKURAJIMA"
    return re.sub(r"\s+", " ", n).strip()


def ang(a, b):
    d = abs(a - b) % 360
    return min(d, 360 - d)


def fmt(t):
    return t.strftime("%Y-%m-%d %H:%MZ") if t else ""


def pct(n, d):
    return f"{n}/{d} ({100.0 * n / d:.0f}%)" if d else f"{n}/0 (n/a)"


def quantile(vals, q):
    """Nearest-rank percentile (no interpolation)."""
    if not vals:
        return None
    s = sorted(vals)
    k = max(1, math.ceil(q * len(s)))
    return s[k - 1]


# ----------------------------------------------------------------------------
# MAGMA VONA
# ----------------------------------------------------------------------------
def parse_magma():
    vonas = {}
    for f in sorted(glob.glob(os.path.join(RAW, "magma", "vona_p*.html"))):
        t = open(f, encoding="utf-8", errors="replace").read()
        for chunk in t.split('<div class="timeline-item">')[1:]:
            m_time = re.search(r"<small>(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d) UTC</small>", chunk)
            m_col = re.search(r'class="btn btn-sm (?:bg|btn)-\w+"[^>]*>\s*(\w+)\s*</a>', chunk)
            m_title = re.search(r'<p class="timeline-title"><a href="#">(.*?)</a>', chunk, re.S)
            m_text = re.search(r'<p class="timeline-text">(.*?)</p>', chunk, re.S)
            m_id = re.search(r"/v1/vona/(\d+)\?signature=", chunk)
            if not (m_time and m_title and m_text and m_id):
                continue
            title = html.unescape(m_title.group(1)).strip()
            vname, _, code = title.rpartition(" - ")
            text = re.sub(r"\s+", " ", html.unescape(m_text.group(1))).strip()
            issued = dt.datetime.strptime(m_time.group(1), "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)
            # DEF: VONA height = the METRE value x 3.28084. MAGMA's printed feet use a factor of 3.2
            # (e.g. "13363 FT (4176 M)"), which understates the height by about 2.5%.
            top = re.search(r"ash-cloud top is around (\d+) FT \((\d+) M\) above sea level", text)
            above = re.search(r"or (\d+) FT \((\d+) M\) above summit", text)
            # DEF: VONA direction. "moving to X" -> bearing of X; "moving from X to Y" (a sector)
            # -> mid-bearing of the sector X..Y.
            mdir = re.search(r"Ash cloud moving (?:from ([a-z\-]+) to ([a-z\-]+)|to ([a-z\-]+))", text)
            dirkey = None
            if mdir:
                if mdir.group(3):
                    k = WORD_DIR.get(mdir.group(3))
                    dirkey = COMPASS[k] if k else None
                else:
                    a, b = WORD_DIR.get(mdir.group(1)), WORD_DIR.get(mdir.group(2))
                    if a and b:
                        x, y = COMPASS[a], COMPASS[b]
                        d = ((y - x + 540) % 360) - 180
                        dirkey = (x + d / 2.0) % 360
            first = text.split(".")[0]
            vonas[m_id.group(1)] = dict(
                id=m_id.group(1), issued=issued, volcano=canon(vname), volcano_raw=vname,
                code=code, colour=(m_col.group(1) if m_col else "").capitalize(),
                activity=first,
                is_eruption=first.lower().startswith("eruption"),
                ash_observed=bool(top),
                not_observed=("Ash-cloud is not observed" in text) and not top,
                top_ft=round(int(top.group(2)) * 3.28084) if top else None,
                top_ft_printed=int(top.group(1)) if top else None,
                top_m=int(top.group(2)) if top else None,
                above_summit_ft=int(above.group(1)) if above else None,
                dir=dirkey, dir_text=(mdir.group(0) if mdir else None), text=text)
    return list(vonas.values())


# ----------------------------------------------------------------------------
# VAA (Darwin FTP text and Tokyo HTML text)
# ----------------------------------------------------------------------------
KEYS = ["DTG", "VAAC", "VOLCANO", "PSN", "AREA", "SOURCE ELEV", "SUMMIT ELEV", "ADVISORY NR",
        "INFO SOURCE", "AVIATION COLOUR CODE", "ERUPTION DETAILS", "OBS VA DTG", "OBS VA CLD",
        "EST VA DTG", "EST VA CLD", "FCST VA CLD +6 HR", "FCST VA CLD +12 HR",
        "FCST VA CLD +18 HR", "RMK", "NXT ADVISORY"]


def parse_vaa_text(txt, src_file, centre_hint):
    fields = {}
    cur = None
    for line in txt.splitlines():
        s = line.strip()
        if not s:
            continue
        m = re.match(r"^([A-Z +0-9]+?):\s?(.*)$", s)
        if m and m.group(1).strip() in KEYS:
            cur = m.group(1).strip()
            fields[cur] = m.group(2).strip()
        elif cur and line[:1] in (" ", "\t"):
            fields[cur] += " " + s
        elif cur and cur not in ("NXT ADVISORY",) and not s.startswith("Copyright") and "bom.gov.au" not in s \
                and "Users of these" not in s and "conditions described" not in s and not s.startswith("532"):
            # Tokyo text has no indentation for continuation lines
            if not re.match(r"^(FV[A-Z]{2}\d\d|VA ADVISORY)", s):
                fields[cur] += " " + s
    if "DTG" not in fields or "VOLCANO" not in fields:
        return None
    dtg = dt.datetime.strptime(fields["DTG"][:14], "%Y%m%d/%H%MZ").replace(tzinfo=UTC)
    obs = fields.get("OBS VA CLD", "") or fields.get("EST VA CLD", "")
    whole = " ".join(fields.values())
    tops = [int(x) for x in re.findall(r"(?:SFC|FL\d{3})/FL(\d{3})", obs)]
    tops += [int(x) for x in re.findall(r"(?<![/\d])FL(\d{3})(?![/\d])", re.sub(r"WINDS?.*$", "", obs))
             if not re.search(r"/FL", obs)]
    movs = re.findall(r"MOV ([NSEW]{1,3})\b(?: (\d+)KT)?", obs)
    stnr = "STNR" in obs
    not_ident = "VA NOT IDENTIFIABLE FM SATELLITE DATA" in re.sub(r"\s+", " ", whole)
    not_ident_obs = "NOT IDENTIFIABLE" in obs
    nxt = fields.get("NXT ADVISORY", "")
    m_nxt = re.search(r"(\d{8}/\d{4})Z", nxt)
    nxt_time = dt.datetime.strptime(m_nxt.group(1), "%Y%m%d/%H%M").replace(tzinfo=UTC) if m_nxt else None
    has_polygon = bool(re.search(r"[NS]\d{4} [EW]\d{5}", obs))
    flat = re.sub(r"\s+", " ", whole)
    # times cited in ERUPTION DETAILS, e.g. "REPORTED AT 24/2356Z", "OBS AT 23/1700Z", "AT 20260922/2230Z"
    cited = []
    for m in re.finditer(r"(?:(\d{4})(\d\d))?(\d\d)/(\d\d)(\d\d)Z", fields.get("ERUPTION DETAILS", "")):
        y = int(m.group(1)) if m.group(1) else dtg.year
        mo = int(m.group(2)) if m.group(2) else dtg.month
        day = int(m.group(3))
        try:
            c = dt.datetime(y, mo, day, int(m.group(4)), int(m.group(5)), tzinfo=UTC)
        except ValueError:
            continue
        if c > dtg + dt.timedelta(hours=1):  # day belongs to previous month
            pm = (dtg.replace(day=1) - dt.timedelta(days=1))
            try:
                c = c.replace(year=pm.year, month=pm.month)
            except ValueError:
                continue
        cited.append(c)
    return dict(
        cited_all=sorted(cited),
        est=("EST VA CLD" in fields), xref=("PLEASE SEE" in flat),
        # DEF: three not-identifiable counts. 'exact' = the Tokyo wording the task names;
        # 'darwin' = Darwin's wording "VA NOT IDENTIFIABLE ON SATELLITE IMAGERY" (any reason);
        # 'any' = the words NOT IDENTIFIABLE anywhere in the advisory.
        not_ident_exact=("VA NOT IDENTIFIABLE FM SATELLITE DATA" in flat),
        not_ident_darwin=("VA NOT IDENTIFIABLE ON SATELLITE IMAGERY" in flat),
        not_ident_any=bool(re.search(r"NOT IDENTIFIABLE", flat)),
        cited_max=max(cited) if cited else None,
        file=os.path.basename(src_file), centre=(fields.get("VAAC", centre_hint) or centre_hint).strip(),
        dtg=dtg, volcano=canon(fields["VOLCANO"]), volcano_raw=fields["VOLCANO"],
        advisory_nr=fields.get("ADVISORY NR", ""), info_source=fields.get("INFO SOURCE", ""),
        eruption_details=fields.get("ERUPTION DETAILS", ""), obs=obs,
        top_fl=max(tops) if tops else None, dir=movs[0][0] if movs else None,
        dirs=[d for d, _ in movs], stnr=stnr, depicts_ash=has_polygon and not not_ident_obs,
        not_identifiable=not_ident, not_identifiable_obs=not_ident_obs,
        final=("NO FURTHER ADVISORIES" in nxt), nxt=nxt, nxt_time=nxt_time,
        rmk=fields.get("RMK", ""), psn=fields.get("PSN", ""))


def parse_vaas():
    vaas = []
    for f in sorted(glob.glob(os.path.join(RAW, "darwin", "ftp", "IDY41*.txt"))):
        v = parse_vaa_text(open(f, encoding="utf-8", errors="replace").read(), f, "DARWIN")
        if v:
            vaas.append(v)
    for f in sorted(glob.glob(os.path.join(RAW, "tokyo", "text", "*_Text.html")) +
                    glob.glob(os.path.join(RAW, "darwin", "jma_backup", "*_Text.html"))):
        t = open(f, encoding="utf-8", errors="replace").read()
        t = re.sub(r"<br\s*/?>", "\n", t, flags=re.I)
        t = html.unescape(re.sub(r"<[^>]+>", "", t))
        v = parse_vaa_text(t, f, "TOKYO")
        if v:
            vaas.append(v)
    # drop non-volcano notices and duplicates (same centre, volcano, DTG, advisory nr)
    seen, out = set(), []
    for v in vaas:
        if v["volcano"] in ("NOTICE", "UNKNOWN") or v["volcano"].startswith("NOTICE"):
            continue
        if v["xref"]:  # DEF: Darwin pointer messages ("PLEASE SEE FVFE01 RJTD ...") are not advisories
            continue
        k = (v["centre"], v["volcano"], v["dtg"], v["advisory_nr"])
        if k in seen:
            continue
        seen.add(k)
        out.append(v)
    return out


# ----------------------------------------------------------------------------
# SIGMET (AWC hourly snapshots)
# ----------------------------------------------------------------------------
def parse_sigmets():
    by_raw = {}
    ok_snapshots = []
    for f in sorted(glob.glob(os.path.join(RAW, "sigmet", "awc_isigmet_va_*.json"))):
        try:
            d = json.load(open(f))
        except Exception:
            continue
        if not isinstance(d, list):
            continue
        snap = dt.datetime.strptime(os.path.basename(f)[15:28], "%Y%m%d_%H%M").replace(tzinfo=UTC)
        ok_snapshots.append(snap)
        for x in d:
            if not isinstance(x, dict):
                continue
            raw = (x.get("rawSigmet") or "").strip()
            key = re.sub(r"\s+", " ", raw)
            rec = by_raw.get(key)
            vt = dt.datetime.fromtimestamp(x["validTimeTo"], UTC) if x.get("validTimeTo") else None
            if rec is None:
                by_raw[key] = dict(x=x, valid_to_min=vt, snaps=[snap])
            else:
                rec["snaps"].append(snap)
                if vt and (rec["valid_to_min"] is None or vt < rec["valid_to_min"]):
                    rec["valid_to_min"] = vt
    sigs = []
    for key, rec in by_raw.items():
        x = rec["x"]
        fir = x.get("firId") or ""
        if fir not in JAPAC_FIRS:
            continue
        raw = key
        m_v = (re.search(r"VA ERUPTION (?:MT |MOUNT )?(.+?) PSN", raw) or re.search(r"VA CLD .*? MT (.+?) PSN", raw)
               or re.search(r"\bFIR (?:VA )?(?:MT |MOUNT )(.+?) PSN", raw))
        is_cnl = bool(re.search(r"\bCNL SIGMET\b", raw))
        m_cnl = re.search(r"CNL SIGMET (\w+) (\d{6})/(\d{6})", raw)
        m_hdr = re.search(r"SIGMET (\w+) VALID (\d{6})/(\d{6})", raw)
        vf = dt.datetime.fromtimestamp(x["validTimeFrom"], UTC)
        vt = rec["valid_to_min"]
        top = x.get("top")
        if top is None:
            m_top = re.search(r"(?:SFC|FL\d{3})/FL(\d{3})", raw) or re.search(r"\bFL(\d{3})\b", raw)
            top = int(m_top.group(1)) * 100 if m_top else None
        m_mov = re.search(r"MOV ([NSEW]{1,3})\b", raw)
        sigs.append(dict(
            fir=fir, series=(m_hdr.group(1) if m_hdr else x.get("seriesId")), raw=raw,
            volcano=canon(m_v.group(1)) if m_v else None, valid_from=vf, valid_to=vt,
            issued=dt.datetime.fromisoformat(x["receiptTime"].replace("Z", "+00:00")) if x.get("receiptTime") else vf,
            top_ft=top, dir=(m_mov.group(1) if m_mov else None), obs=(" OBS AT " in raw),
            fcst_only=(" FCST AT " in raw and " OBS AT " not in raw), cnl=is_cnl,
            cnl_series=(m_cnl.group(1) if m_cnl else None)))
    # apply cancellations: a CNL SIGMET ends the referenced series at the CNL's valid_from
    for c in [s for s in sigs if s["cnl"]]:
        for s in sigs:
            if not s["cnl"] and s["fir"] == c["fir"] and s["series"] == c["cnl_series"] \
                    and s["valid_from"] <= c["valid_from"] < (s["valid_to"] or c["valid_from"]):
                s["valid_to"] = c["valid_from"]
                if c["volcano"] is None:
                    c["volcano"] = s["volcano"]
    return sigs, sorted(ok_snapshots)


# ----------------------------------------------------------------------------
# Coverage helpers
# ----------------------------------------------------------------------------
def vaa_intervals(vaas):
    """DEF (VAA in force): a VAA is in force from its DTG until the earliest of: the next VAA for
    the same volcano from the same centre; its 'NXT ADVISORY: NO LATER THAN' time; DTG + 6 h.
    A VAA whose NXT ADVISORY is 'NO FURTHER ADVISORIES' ends coverage at its own DTG."""
    by = defaultdict(list)
    for v in vaas:
        by[(v["centre"], v["volcano"])].append(v)
    for k, lst in by.items():
        lst.sort(key=lambda v: v["dtg"])
        for i, v in enumerate(lst):
            ends = [v["dtg"] + dt.timedelta(hours=6)]
            if i + 1 < len(lst):
                ends.append(lst[i + 1]["dtg"])
            if v["nxt_time"]:
                ends.append(v["nxt_time"])
            v["end"] = v["dtg"] if v["final"] else min(ends)


def vaa_in_force(vb, volcano, t):
    best = None
    for v in vb.get(volcano, []):
        if v["dtg"] <= t < v["end"] and (best is None or v["dtg"] > best["dtg"]):
            best = v
    return best


def sig_in_force(sb, volcano, t):
    act = [s for s in sb.get(volcano, []) if s["valid_from"] <= t < (s["valid_to"] or t)]
    return max(act, key=lambda s: s["valid_from"]) if act else None


def sig_overlaps(sb, volcano, a, b):
    return [s for s in sb.get(volcano, []) if s["valid_from"] < b and (s["valid_to"] or s["valid_from"]) > a]


def first_vaa_after(vb, volcano, t, hours=24, pred=None):
    c = [v for v in vb.get(volcano, []) if t <= v["dtg"] <= t + dt.timedelta(hours=hours) and (pred is None or pred(v))]
    return min(c, key=lambda v: v["dtg"]) if c else None


def first_sig_after(sb, volcano, t, hours=24):
    c = [s for s in sb.get(volcano, []) if t <= s["valid_from"] <= t + dt.timedelta(hours=hours)]
    return min(c, key=lambda s: s["valid_from"]) if c else None


def mins(a, b):
    return (a - b).total_seconds() / 60.0


def vona_event_time(v):
    m = re.search(r"(\d{8})/(\d{4})Z", v["code"])
    if m:
        return dt.datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M").replace(tzinfo=UTC)
    return v["issued"]


def bucket_angles(pairs):
    c = Counter()
    for a in pairs:
        c["n"] += 1
        if a > 45:
            c[">45"] += 1
        if a >= 90:
            c[">=90"] += 1
        if a >= 135:
            c[">=135"] += 1
    return dict(c)


def dm(tok):
    """'S0806' -> -8.1, 'E11255' -> 112.9167 (degrees and minutes)."""
    h, n = tok[0], tok[1:]
    deg, mn = (int(n[:-2]), int(n[-2:]))
    x = deg + mn / 60.0
    return -x if h in "SW" else x


def polygons(obs):
    """All closed rings in an OBS/EST VA CLD field, as [(lat, lon), ...]."""
    rings = []
    for part in re.split(r"(?:SFC|FL\d{3})/FL\d{3}", obs)[1:]:
        pts = [(dm(a), dm(b)) for a, b in re.findall(r"([NS]\d{4}) ([EW]\d{5})", part)]
        if len(pts) >= 3:
            rings.append(pts)
    return rings


def inside(lat, lon, ring):
    c = False
    n = len(ring)
    for i in range(n):
        (y1, x1), (y2, x2) = ring[i], ring[(i + 1) % n]
        if (y1 > lat) != (y2 > lat) and lon < (x2 - x1) * (lat - y1) / (y2 - y1) + x1:
            c = not c
    return c


def along(lat, lon, bearing_deg, km):
    """Flat-earth offset; adequate for <= 50 km near the equator."""
    b = math.radians(bearing_deg)
    return (lat + km * math.cos(b) / 111.2, lon + km * math.sin(b) / (111.2 * math.cos(math.radians(lat))))


# ----------------------------------------------------------------------------
def main():
    vonas_all = parse_magma()
    vaas_all = parse_vaas()
    sigs_all, snaps = parse_sigmets()
    vaa_intervals(vaas_all)
    vb = defaultdict(list)
    for v in vaas_all:
        vb[v["volcano"]].append(v)
    for k in vb:
        vb[k].sort(key=lambda v: v["dtg"])
    sb = defaultdict(list)
    for s in sigs_all:
        if s["volcano"] and not s["cnl"]:
            sb[s["volcano"]].append(s)

    inwin = lambda t: WIN_START <= t < WIN_END
    vonas = sorted([v for v in vonas_all if inwin(v["issued"])], key=lambda v: v["issued"])
    vaas = sorted([v for v in vaas_all if inwin(v["dtg"])], key=lambda v: v["dtg"])
    sigs = sorted([s for s in sigs_all if not s["cnl"] and inwin(s["valid_from"])], key=lambda s: s["valid_from"])
    sig_cover = (snaps[0], snaps[-1]) if snaps else (None, None)

    report = {"window": [fmt(WIN_START), fmt(WIN_END)],
              "sigmet_snapshots_ok": [fmt(snaps[0]), fmt(snaps[-1]), len(snaps)] if snaps else None,
              "magma_vona_total_in_window": len(vonas), "vaa_total_in_window": len(vaas),
              "sigmet_total_in_window": len(sigs)}

    rows = []
    for v in vonas:
        t = v["issued"]
        te = vona_event_time(v)
        vk = v["volcano"]
        vaa_now = vaa_in_force(vb, vk, t)
        sig_now = sig_in_force(sb, vk, t)
        vaa_next = first_vaa_after(vb, vk, t, 24)
        vaa_next_ash = first_vaa_after(vb, vk, t, 24, lambda w: w["depicts_ash"])
        # DEF (reflected): the first VAA issued after the VONA whose ERUPTION DETAILS cite a
        # report/observation time at or after the VONA's event time (i.e. built on information at
        # least as new as the VONA).
        vaa_reflect = first_vaa_after(vb, vk, t, 24, lambda w: w["cited_max"] is not None and w["cited_max"] >= te - dt.timedelta(minutes=5))
        sig_next = first_sig_after(sb, vk, t, 24)
        # DEF (comparison VAA): the VAA in force at the VONA time; if none, the first VAA issued
        # within 3 h after the VONA. Same rule for the comparison SIGMET.
        cmp_vaa = vaa_now or (vaa_next if vaa_next and mins(vaa_next["dtg"], t) <= 180 else None)
        cmp_sig = sig_now or (sig_next if sig_next and mins(sig_next["valid_from"], t) <= 180 else None)
        cmp_ash = cmp_vaa if (cmp_vaa and cmp_vaa["depicts_ash"]) else None
        r = dict(vona_id=v["id"], issued=fmt(t), event=fmt(te), volcano=vk, colour=v["colour"], code=v["code"],
                 activity=v["activity"], ash_observed=v["ash_observed"], not_observed=v["not_observed"],
                 eruption_ash=v["activity"].lower().startswith("eruption with volcanic ash"),
                 vona_top_ft=v["top_ft"], vona_top_ft_printed=v["top_ft_printed"], vona_top_m=v["top_m"], vona_dir_deg=v["dir"], vona_dir_text=v["dir_text"],
                 vaa_in_force=bool(vaa_now), vaa_in_force_depicts_ash=bool(vaa_now and vaa_now["depicts_ash"]),
                 vaa_in_force_dtg=fmt(vaa_now["dtg"]) if vaa_now else "",
                 vaa_in_force_nr=vaa_now["advisory_nr"] if vaa_now else "",
                 vaa_in_force_age_min=round(mins(t, vaa_now["dtg"])) if vaa_now else None,
                 vaa_in_force_info_age_min=round(mins(te, vaa_now["cited_max"])) if vaa_now and vaa_now["cited_max"] else None,
                 sigmet_in_force=bool(sig_now), sigmet_window_covered=bool(sig_cover[0] and sig_cover[0] <= t <= sig_cover[1] + dt.timedelta(hours=1)),
                 next_vaa_dtg=fmt(vaa_next["dtg"]) if vaa_next else "",
                 next_vaa_lag_min=round(mins(vaa_next["dtg"], t)) if vaa_next else None,
                 next_vaa_depicting_ash_lag_min=round(mins(vaa_next_ash["dtg"], t)) if vaa_next_ash else None,
                 reflect_vaa_dtg=fmt(vaa_reflect["dtg"]) if vaa_reflect else "",
                 reflect_vaa_nr=vaa_reflect["advisory_nr"] if vaa_reflect else "",
                 reflect_lag_min=round(mins(vaa_reflect["dtg"], t)) if vaa_reflect else None,
                 next_sigmet_lag_min=round(mins(sig_next["valid_from"], t)) if sig_next else None,
                 cmp_vaa_dtg=fmt(cmp_vaa["dtg"]) if cmp_vaa else "",
                 cmp_vaa_nr=cmp_vaa["advisory_nr"] if cmp_vaa else "",
                 cmp_vaa_top_ft=(cmp_ash["top_fl"] * 100 if cmp_ash and cmp_ash["top_fl"] else None),
                 cmp_vaa_dir=(cmp_ash["dir"] if cmp_ash else None),
                 cmp_vaa_est=bool(cmp_ash and cmp_ash["est"]),
                 cmp_sig_top_ft=(cmp_sig["top_ft"] if cmp_sig else None),
                 cmp_sig_dir=(cmp_sig["dir"] if cmp_sig else None),
                 cmp_sig_issued=fmt(cmp_sig["valid_from"]) if cmp_sig else "",
                 cmp_sig_id=(cmp_sig["fir"] + " " + str(cmp_sig["series"])) if cmp_sig else "")
        # DEF (VONA cited): some VAA issued within 24 h after the VONA cites the VONA's event time
        # (+-2 min) in ERUPTION DETAILS, i.e. the VAAC used that VONA as a ground report.
        r["cited_by_vaa"] = next((w["advisory_nr"] for w in vb.get(vk, []) if t - dt.timedelta(minutes=5) <= w["dtg"] <= t + dt.timedelta(hours=24)
                                  and any(abs(mins(c, te)) <= 2 for c in w["cited_all"])), "")
        r["dir_diff_vaa"] = round(ang(r["vona_dir_deg"], COMPASS[r["cmp_vaa_dir"]])) if r["vona_dir_deg"] is not None and r["cmp_vaa_dir"] else None
        r["dir_diff_sig"] = round(ang(r["vona_dir_deg"], COMPASS[r["cmp_sig_dir"]])) if r["vona_dir_deg"] is not None and r["cmp_sig_dir"] in COMPASS else None
        # DEF (downwind cover): for an ash VONA with a direction, take points 5, 10 and 20 km from the
        # vent (VAA PSN) along the VONA's direction and test whether each lies inside any ash polygon
        # of the comparison VAA. "Outside" means the official area does not cover where the observatory
        # says the ash is heading, at that distance.
        for km in (5, 10, 20):
            r[f"pt{km}_in_vaa"] = None
        if r["vona_dir_deg"] is not None and cmp_ash and cmp_ash["psn"]:
            m_p = re.search(r"([NS]\d{4}) ([EW]\d{5})", cmp_ash["psn"])
            rings = polygons(cmp_ash["obs"])
            if m_p and rings:
                la, lo = dm(m_p.group(1)), dm(m_p.group(2))
                for km in (5, 10, 20):
                    y, x = along(la, lo, r["vona_dir_deg"], km)
                    r[f"pt{km}_in_vaa"] = any(inside(y, x, g) for g in rings)
        # DEF (direction after update): VONA direction vs the MOV of the first VAA that reflects it.
        r["dir_diff_reflect"] = (round(ang(r["vona_dir_deg"], COMPASS[vaa_reflect["dir"]]))
                                 if r["vona_dir_deg"] is not None and vaa_reflect and vaa_reflect["dir"] in COMPASS else None)
        rows.append(r)
    with open(os.path.join(OUT, "vona_vs_official.csv"), "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    volcs = sorted(set([v["volcano"] for v in vonas] + [v["volcano"] for v in vaas] +
                       [s["volcano"] for s in sigs if s["volcano"]]))
    per = {}
    for vk in volcs:
        R = [r for r in rows if r["volcano"] == vk]
        A = [v for v in vaas if v["volcano"] == vk]
        S = [s for s in sigs if s["volcano"] == vk]
        ash = [r for r in R if r["ash_observed"]]
        nob = [r for r in R if r["not_observed"]]
        onset = [r for r in ash if not r["vaa_in_force"]]
        onset_lags = [r["next_vaa_lag_min"] for r in onset if r["next_vaa_lag_min"] is not None]
        upd = [r for r in ash if r["vaa_in_force"]]
        upd_lags = [r["next_vaa_lag_min"] for r in upd if r["next_vaa_lag_min"] is not None]
        refl = [r["reflect_lag_min"] for r in ash if r["reflect_lag_min"] is not None]
        info_age = [r["vaa_in_force_info_age_min"] for r in upd if r["vaa_in_force_info_age_min"] is not None]
        hcmp = [r for r in ash if r["vona_top_ft"] and r["cmp_vaa_top_ft"]]
        scmp = [r for r in ash if r["vona_top_ft"] and r["cmp_sig_top_ft"]]
        dpairs = [r["dir_diff_vaa"] for r in ash if r["dir_diff_vaa"] is not None]
        spairs = [r["dir_diff_sig"] for r in ash if r["dir_diff_sig"] is not None]
        # DEF (SIGMET without VAA): VA SIGMET for the volcano with no VAA for it issued in the 6 h
        # before or 1 h after the SIGMET's start of validity (final 'NO FURTHER ADVISORIES' VAAs count).
        sig_no_vaa = [s for s in S if not [v for v in vb.get(vk, []) if s["valid_from"] - dt.timedelta(hours=6) <= v["dtg"] <= s["valid_from"] + dt.timedelta(hours=1)]]
        # DEF (VAA without SIGMET): VAA depicting an ash area with no VA SIGMET for the volcano valid at
        # any time within 1 h either side of the VAA DTG. Only counted while SIGMET snapshots exist.
        vaa_ash = [v for v in A if v["depicts_ash"]]
        vaa_ash_cov = [v for v in vaa_ash if sig_cover[0] and sig_cover[0] <= v["dtg"] <= sig_cover[1]]
        vaa_no_sig = [v for v in vaa_ash_cov if not sig_overlaps(sb, vk, v["dtg"] - dt.timedelta(hours=1), v["dtg"] + dt.timedelta(hours=1))]
        # DEF (SIGMET vs VAA): compare each SIGMET with the VAA issued closest in time within +-60 min.
        svt, svd, svsame, svpairs = [], [], 0, []
        for s in S:
            near = [v for v in vb.get(vk, []) if abs(mins(v["dtg"], s["valid_from"])) <= 60 and v["depicts_ash"]]
            if not near:
                continue
            a = min(near, key=lambda v: abs(mins(v["dtg"], s["valid_from"])))
            svpairs.append((s, a))
            if a["top_fl"] and s["top_ft"]:
                svt.append(s["top_ft"] - a["top_fl"] * 100)
            if a["dir"] and s["dir"] in COMPASS:
                svd.append(ang(COMPASS[a["dir"]], COMPASS[s["dir"]]))
        # DEF (VAA closed, SIGMET open): a VAA that says NO FURTHER ADVISORIES while a VA SIGMET for the
        # same volcano is in force at the VAA DTG or starts within 15 min after it, and that SIGMET stays
        # valid for at least 60 min after the VAA DTG.
        closed_open = []
        for v in A:
            if not v["final"]:
                continue
            cands = [x for x in sb.get(vk, []) if (x["valid_from"] <= v["dtg"] < (x["valid_to"] or v["dtg"]))
                     or (v["dtg"] <= x["valid_from"] <= v["dtg"] + dt.timedelta(minutes=15))]
            if any((x["valid_to"] or x["valid_from"]) >= v["dtg"] + dt.timedelta(minutes=60) for x in cands):
                closed_open.append(v)
        per[vk] = dict(
            vaa_final_n=sum(1 for v in A if v["final"]), vaa_closed_sigmet_open=len(closed_open),
            vaa_closed_sigmet_open_cov=sum(1 for v in A if v["final"] and sig_cover[0] and sig_cover[0] <= v["dtg"] <= sig_cover[1]),
            vonas=len(R), vonas_ash=len(ash), vonas_not_observed=len(nob),
            vonas_eruption_not_observed=sum(1 for r in nob if r["activity"].lower().startswith("eruption")),
            colours=dict(Counter(r["colour"] for r in R)),
            vaas=len(A), vaas_darwin=sum(1 for v in A if v["centre"].startswith("DARWIN")),
            vaas_tokyo=sum(1 for v in A if v["centre"].startswith("TOKYO")),
            vaas_depicting_ash=len(vaa_ash), vaas_est=sum(1 for v in A if v["est"]),
            vaas_not_ident_exact=sum(1 for v in A if v["not_ident_exact"]),
            vaas_not_ident_darwin=sum(1 for v in A if v["not_ident_darwin"]),
            vonas_eruption=sum(1 for r in R if r["activity"].lower().startswith("eruption")),
            h_exceed_printed_ft=sum(1 for r in hcmp if r["vona_top_ft_printed"] > r["cmp_vaa_top_ft"]),
            vaas_not_ident_any=sum(1 for v in A if v["not_ident_any"]),
            vaas_final=sum(1 for v in A if v["final"]),
            vaas_cvghm_source=sum(1 for v in A if re.search(r"CVGHM|VONA", v["info_source"])),
            sigmets=len(S),
            vonas_eruption_ash=sum(1 for r in R if r["eruption_ash"]),
            onset_eruption_ash=[(r["issued"], r["next_vaa_lag_min"]) for r in onset if r["eruption_ash"]],
            onset_n=len(onset), onset_with_vaa_24h=len(onset_lags), onset_no_vaa_24h=len(onset) - len(onset_lags),
            onset_lags=sorted(onset_lags),
            update_n=len(upd), update_lag_median_min=statistics.median(upd_lags) if upd_lags else None,
            update_lag_p90_min=quantile(upd_lags, 0.9),
            reflect_n=len(refl), reflect_lag_median_min=statistics.median(refl) if refl else None,
            reflect_lag_p90_min=quantile(refl, 0.9), reflect_none_24h=len(ash) - len(refl),
            info_age_median_min=statistics.median(info_age) if info_age else None,
            info_age_p90_min=quantile(info_age, 0.9),
            notobs_cited_by_vaa=sum(1 for r in nob if r["cited_by_vaa"]),
            ash_cited_by_vaa=sum(1 for r in ash if r["cited_by_vaa"]),
            notobs_while_vaa=sum(1 for r in nob if r["vaa_in_force"]),
            notobs_while_vaa_ash=sum(1 for r in nob if r["vaa_in_force_depicts_ash"]),
            notobs_while_sig=sum(1 for r in nob if r["sigmet_in_force"]),
            notobs_while_either=sum(1 for r in nob if r["vaa_in_force"] or r["sigmet_in_force"]),
            h_cmp=len(hcmp), h_exceed=sum(1 for r in hcmp if r["vona_top_ft"] > r["cmp_vaa_top_ft"]),
            h_exceed_1k=sum(1 for r in hcmp if r["vona_top_ft"] > r["cmp_vaa_top_ft"] + 1000),
            h_inside=sum(1 for r in hcmp if r["vona_top_ft"] <= r["cmp_vaa_top_ft"]),
            h_margin_median_ft=statistics.median([r["cmp_vaa_top_ft"] - r["vona_top_ft"] for r in hcmp]) if hcmp else None,
            s_cmp=len(scmp), s_exceed=sum(1 for r in scmp if r["vona_top_ft"] > r["cmp_sig_top_ft"]),
            s_exceed_1k=sum(1 for r in scmp if r["vona_top_ft"] > r["cmp_sig_top_ft"] + 1000),
            s_inside=sum(1 for r in scmp if r["vona_top_ft"] <= r["cmp_sig_top_ft"]),
            dir_vona_vaa=bucket_angles(dpairs), dir_vona_sig=bucket_angles(spairs),
            dir_vona_reflect=bucket_angles([r["dir_diff_reflect"] for r in ash if r["dir_diff_reflect"] is not None]),
            pt5_tested=sum(1 for r in ash if r["pt5_in_vaa"] is not None), pt5_out=sum(1 for r in ash if r["pt5_in_vaa"] is False),
            pt10_out=sum(1 for r in ash if r["pt10_in_vaa"] is False), pt20_out=sum(1 for r in ash if r["pt20_in_vaa"] is False),
            pt10_out_dir_gt45=sum(1 for r in ash if r["pt10_in_vaa"] is False and (r["dir_diff_vaa"] or 0) > 45),
            h_exceed_500=sum(1 for r in hcmp if r["vona_top_ft"] > r["cmp_vaa_top_ft"] + 500),
            sigmet_without_vaa=len(sig_no_vaa), vaa_ash_covered_by_snapshots=len(vaa_ash_cov),
            vaa_ash_without_sigmet=len(vaa_no_sig),
            sig_vs_vaa_top_n=len(svt), sig_vs_vaa_top_same=sum(1 for d in svt if d == 0),
            sig_vs_vaa_top_diff_gt1k=sum(1 for d in svt if abs(d) > 1000),
            sig_vs_vaa_dir=bucket_angles(svd), sig_vs_vaa_pairs=len(svpairs),
            # DEF: SIGMET text says 'VA CLD OBS' while the matched VAA used 'EST VA CLD' (VAAC could not see it)
            sig_obs_from_est_vaa=sum(1 for x, a in svpairs if x["obs"] and a["est"]),
            ex_onset=[(r["issued"], r["code"], r["colour"], r["vona_top_ft"], r["vona_dir_text"], r["next_vaa_dtg"], r["next_vaa_lag_min"], r["sigmet_in_force"], r["next_sigmet_lag_min"]) for r in onset],
            ex_h_exceed=[(r["issued"], r["vona_top_ft"], r["cmp_vaa_top_ft"], r["cmp_vaa_nr"]) for r in hcmp if r["vona_top_ft"] > r["cmp_vaa_top_ft"]],
            ex_sig_no_vaa=[(fmt(s["valid_from"]), s["fir"], s["series"], s["top_ft"], s["dir"], s["raw"][:160]) for s in sig_no_vaa][:12],
            ex_vaa_no_sig=[(fmt(v["dtg"]), v["advisory_nr"], v["top_fl"], v["dir"]) for v in vaa_no_sig][:12])
    report["per_volcano"] = per

    # DEF (observatory report -> VAA/SIGMET, Tokyo area): Tokyo VAAs whose ERUPTION DETAILS say
    # "ERUPTED AT <t>" or "ERUPTION AT <t> ... REPORTED" (a JMA or PHIVOLCS ground report). Group by
    # (volcano, t); lag = first VAA DTG minus t; SIGMET lag = first VA SIGMET for the volcano whose
    # validity starts in [t - 5 min, t + 3 h] minus t.
    tl = defaultdict(list)
    for v in vaas:
        if not v["centre"].startswith("TOKYO"):
            continue
        m = re.search(r"ERUPT(?:ED|ION) AT (\d{8})/(\d{4})Z", v["eruption_details"])
        if not m:
            continue
        t0 = dt.datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M").replace(tzinfo=UTC)
        tl[(v["volcano"], t0)].append(v)
    tok = defaultdict(lambda: dict(n=0, vaa_lags=[], sig_lags=[], sig_none=0, first_vaa_not_ident=0))
    for (vk, t0), lst in sorted(tl.items(), key=lambda kv: kv[0][1]):
        first = min(lst, key=lambda v: v["dtg"])
        e = tok[vk]
        e["n"] += 1
        e["vaa_lags"].append(round(mins(first["dtg"], t0)))
        e["first_vaa_not_ident"] += int(first["not_ident_any"])
        ss = [x for x in sb.get(vk, []) if t0 - dt.timedelta(minutes=5) <= x["valid_from"] <= t0 + dt.timedelta(hours=3)]
        if ss:
            e["sig_lags"].append(round(mins(min(x["valid_from"] for x in ss), t0)))
        else:
            e["sig_none"] += 1
    for vk, e in tok.items():
        for k in ("vaa_lags", "sig_lags"):
            L = e[k]
            e[k.replace("lags", "median")] = statistics.median(L) if L else None
            e[k.replace("lags", "p90")] = quantile(L, 0.9)
    report["tokyo_report_lag"] = tok
    report["all_onset"] = [(k, x) for k, p in per.items() for x in p["ex_onset"]]

    # pooled numbers over all volcanoes that had VONAs
    pooled = Counter()
    for k, p in per.items():
        for kk, vv in p.items():
            if isinstance(vv, int) and not isinstance(vv, bool) and not re.search(r"median|p90|max", kk):
                pooled[kk] += vv
    ash_rows = [r for r in rows if r["ash_observed"]]
    refl = [r["reflect_lag_min"] for r in ash_rows if r["reflect_lag_min"] is not None]
    upd = [r["next_vaa_lag_min"] for r in ash_rows if r["vaa_in_force"] and r["next_vaa_lag_min"] is not None]
    age = [r["vaa_in_force_info_age_min"] for r in ash_rows if r["vaa_in_force_info_age_min"] is not None]
    pooled_extra = dict(reflect_median=statistics.median(refl) if refl else None, reflect_p90=quantile(refl, 0.9), reflect_n=len(refl),
                        update_median=statistics.median(upd) if upd else None, update_p90=quantile(upd, 0.9), update_n=len(upd),
                        info_age_median=statistics.median(age) if age else None, info_age_p90=quantile(age, 0.9), info_age_n=len(age),
                        dir_vona_vaa=bucket_angles([r["dir_diff_vaa"] for r in ash_rows if r["dir_diff_vaa"] is not None]),
                        dir_vona_sig=bucket_angles([r["dir_diff_sig"] for r in ash_rows if r["dir_diff_sig"] is not None]))
    report["pooled"] = dict(pooled)
    report["pooled_extra"] = pooled_extra

    with open(os.path.join(OUT, "vaas.csv"), "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["dtg", "centre", "volcano", "advisory_nr", "info_source", "top_fl", "dir", "depicts_ash", "est",
                    "not_ident_exact", "not_ident_darwin", "not_ident_any", "final", "end", "cited_max", "eruption_details", "file"])
        for v in vaas:
            w.writerow([fmt(v["dtg"]), v["centre"], v["volcano"], v["advisory_nr"], v["info_source"], v["top_fl"],
                        v["dir"], v["depicts_ash"], v["est"], v["not_ident_exact"], v["not_ident_darwin"], v["not_ident_any"], v["final"],
                        fmt(v.get("end")), fmt(v["cited_max"]), v["eruption_details"], v["file"]])
    with open(os.path.join(OUT, "sigmets.csv"), "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["valid_from", "valid_to", "fir", "series", "volcano", "top_ft", "dir", "obs", "cnl", "raw"])
        for s in sorted(sigs_all, key=lambda s: s["valid_from"]):
            w.writerow([fmt(s["valid_from"]), fmt(s["valid_to"]), s["fir"], s["series"], s["volcano"], s["top_ft"],
                        s["dir"], s["obs"], s["cnl"], s["raw"]])
    with open(os.path.join(OUT, "vonas.csv"), "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["issued", "id", "volcano", "colour", "code", "ash_observed", "not_observed", "top_ft", "top_ft_printed", "top_m",
                    "above_summit_ft", "dir_deg", "dir_text", "text"])
        for v in vonas:
            w.writerow([fmt(v["issued"]), v["id"], v["volcano"], v["colour"], v["code"], v["ash_observed"],
                        v["not_observed"], v["top_ft"], v["top_ft_printed"], v["top_m"], v["above_summit_ft"], v["dir"], v["dir_text"], v["text"]])
    with open(os.path.join(OUT, "summary.json"), "w") as fh:
        json.dump(report, fh, indent=1, default=str)

    # markdown table for the write-up
    cols = [("VONAs", "vonas"), ("eruption VONAs", "vonas_eruption"), ("ash VONAs", "vonas_ash"), ("'not observed' VONAs", "vonas_not_observed"),
            ("VAAs", "vaas"), ("VAAs with ash area", "vaas_depicting_ash"), ("EST (not satellite-seen) VAAs", "vaas_est"),
            ("'VA NOT IDENTIFIABLE FM SATELLITE DATA'", "vaas_not_ident_exact"), ("'VA NOT IDENTIFIABLE ON SATELLITE IMAGERY' (Darwin)", "vaas_not_ident_darwin"), ("any 'NOT IDENTIFIABLE'", "vaas_not_ident_any"),
            ("VA SIGMETs", "sigmets")]
    with open(os.path.join(OUT, "per_volcano_table.md"), "w") as fh:
        fh.write("| Volcano | " + " | ".join(c for c, _ in cols) + " |\n|---|" + "---|" * len(cols) + "\n")
        for vk, p in sorted(per.items(), key=lambda kv: -(kv[1]["vonas"] + kv[1]["vaas"] + kv[1]["sigmets"])):
            if p["vonas"] + p["vaas"] + p["sigmets"] < 3:
                continue
            fh.write("| " + vk.title() + " | " + " | ".join(str(p[k]) for _, k in cols) + " |\n")
    print("window", report["window"], "sigmet snapshots", report["sigmet_snapshots_ok"])
    print("VONAs", len(vonas), "VAAs", len(vaas), "SIGMETs", len(sigs))
    order = sorted(per.items(), key=lambda kv: -(kv[1]["vonas"] + kv[1]["vaas"] + kv[1]["sigmets"]))
    for vk, p in order:
        q = {k: v for k, v in p.items() if not k.startswith("ex_")}
        print(vk, json.dumps(q, default=str))
    print("TOKYO_REPORT_LAG", json.dumps({k: {kk: vv for kk, vv in e.items() if not kk.endswith("lags")} for k, e in report["tokyo_report_lag"].items()}))
    print("POOLED", json.dumps(report["pooled"]))
    print("POOLED_EXTRA", json.dumps(pooled_extra))


if __name__ == "__main__":
    main()
