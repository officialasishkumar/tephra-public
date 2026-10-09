"""Scratch: compute split-window BTD statistics around a volcano for one Himawari FLDK timeline.
Usage: python3 -I btd_case.py OUTDIR BUCKET YYYYMMDD HHMM SEG LAT LON HALF_WINDOW_PX
"""
import bz2, struct, sys, os, urllib.request, time
import numpy as np
outdir, bucket, ymd, hhmm, seg, lat, lon, half = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4], int(sys.argv[5]), float(sys.argv[6]), float(sys.argv[7]), int(sys.argv[8])
sat = 'H09' if bucket.endswith('9') else 'H08'
def fetch(band):
    fn = f'HS_{sat}_{ymd}_{hhmm}_B{band:02d}_FLDK_R20_S{seg:02d}10.DAT.bz2'
    url = f'https://{bucket}.s3.amazonaws.com/AHI-L1b-FLDK/{ymd[:4]}/{ymd[4:6]}/{ymd[6:]}/{hhmm}/{fn}'
    p = os.path.join(outdir, fn)
    if not os.path.exists(p):
        urllib.request.urlretrieve(url, p)
    return p, os.path.getsize(p)
def read(p):
    raw = bz2.decompress(open(p, 'rb').read())
    e = '<' if raw[5] == 0 else '>'
    off = 0; blk = {}
    while True:
        n = raw[off]
        ln = struct.unpack(e+'I', raw[off+1:off+5])[0] if n == 10 else struct.unpack(e+'H', raw[off+1:off+3])[0]
        blk[n] = raw[off:off+ln]; off += ln
        if n == 11: break
    _, ncol, nline, _ = struct.unpack(e+'HHHB', blk[2][3:10])
    sub_lon, cfac, lfac, coff, loff = struct.unpack(e+'dIIff', blk[3][3:27])
    band, wl, vb, errc, outc, slope, icpt = struct.unpack(e+'HdHHHdd', blk[5][3:35])
    c0, c1, c2, C0, C1, C2, c, h, k = struct.unpack(e+'9d', blk[5][35:107])
    nseg, segno, fl = struct.unpack(e+'BBH', blk[7][3:7])
    s0, s1 = struct.unpack(e+'dd', blk[1][46:62])
    cnt = np.frombuffer(raw, dtype=e+'u2', offset=off, count=ncol*nline).reshape(nline, ncol)
    bad = (cnt == errc) | (cnt == outc)
    lam = wl * 1e-6
    I = (cnt.astype(np.float64) * slope + icpt) * 1e6
    with np.errstate(all='ignore'):
        Te = (h*c/(k*lam)) / np.log(2*h*c**2/(lam**5*I) + 1)
    Tb = (c0 + c1*Te + c2*Te**2).astype(np.float32); Tb[bad] = np.nan
    nav = dict(sub_lon=sub_lon, cfac=cfac, lfac=lfac, coff=coff, loff=loff, fl=fl)
    return Tb, nav, (s0, s1)
def ll2lc(lat, lon, nav):
    lat, lon = np.radians(lat), np.radians(lon); sub = np.radians(nav['sub_lon'])
    clat = np.arctan(0.993305616*np.tan(lat)); rl = 6356.7523/np.sqrt(1-0.00669438444*np.cos(clat)**2)
    r1 = 42164 - rl*np.cos(clat)*np.cos(lon-sub); r2 = -rl*np.cos(clat)*np.sin(lon-sub); r3 = rl*np.sin(clat)
    rn = np.sqrt(r1**2+r2**2+r3**2)
    x = np.degrees(np.arctan(-r2/r1)); y = np.degrees(np.arcsin(-r3/rn))
    return nav['loff'] + y*2**-16*nav['lfac'], nav['coff'] + x*2**-16*nav['cfac']
import datetime
mjd = lambda m: (datetime.datetime(1858,11,17)+datetime.timedelta(days=m)).strftime('%H:%M:%S')
tb = {}; nbytes = 0
for b in (11, 13, 14, 15):
    p, sz = fetch(b); nbytes += sz
    tb[b], nav, (s0, s1) = read(p)
line, col = ll2lc(lat, lon, nav)
r = int(round(line)) - nav['fl']; cc = int(round(col)) - 1
sl = (slice(max(r-half, 0), r+half), slice(max(cc-half, 0), cc+half))
d1315 = (tb[13]-tb[15])[sl]; d1415 = (tb[14]-tb[15])[sl]; d1113 = (tb[11]-tb[13])[sl]; b13 = tb[13][sl]
def frac(a, t): return float(np.nanmean(a < t))
print(f'{ymd} {hhmm} seg S{seg:02d} scan {mjd(s0)}-{mjd(s1)} UTC | bytes 4 bands {nbytes/1e6:.1f} MB | window {2*half}x{2*half} px around ({lat},{lon}) line {line:.0f} col {col:.0f}')
print(f'  B13 BT: min {np.nanmin(b13):.1f} K, p05 {np.nanpercentile(b13,5):.1f}, median {np.nanmedian(b13):.1f}; at vent {tb[13][r, cc]:.1f} K')
for name, a in (('B13-B15', d1315), ('B14-B15', d1415)):
    print(f'  {name}: min {np.nanmin(a):+.2f} p01 {np.nanpercentile(a,1):+.2f} median {np.nanmedian(a):+.2f} | frac<0 {frac(a,0):.4f} frac<-0.5 {frac(a,-0.5):.4f} frac<-1 {frac(a,-1):.4f} | px<-1: {int(np.nansum(a < -1))}')
# pixels with negative BTD that are warmer than 230 K (cold-top false alarms excluded) and within 50 px of vent
r0=max(r-half,0); c0_=max(cc-half,0); yy, xx = np.mgrid[r0:r0+d1415.shape[0], c0_:c0_+d1415.shape[1]]
near = (np.hypot(yy-r, xx-cc) <= 50)
m = (d1415 < -0.5) & near
print(f'  within 100 km of vent: px with B14-B15 < -0.5 K: {int(np.nansum(m))}; with B13-B15 < -0.5 K: {int(np.nansum((d1315 < -0.5) & near))}; B11-B13 median {np.nanmedian(d1113):+.2f}')
