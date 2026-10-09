"""Scratch probe: parse a Himawari Standard Data (HSD v1.3) segment with only numpy + stdlib.
Reports header facts, decompress/calibrate timing and memory, and the lat/lon footprint.
Usage: python3 -I hsd_probe.py FILE.DAT.bz2 [FILE2.DAT.bz2]
"""
import bz2, sys, time, struct, resource
import numpy as np

def parse(buf):
    off = 0
    blocks = {}
    # block 1
    b1 = buf[0:282]
    bo = b1[5]
    e = '<' if bo == 0 else '>'
    total_hdr = struct.unpack(e + 'I', b1[70+0:70+4])[0] if False else None
    # walk blocks generically: each block = I1 number, I2 length (block 10 uses I4 length)
    while True:
        num = buf[off]
        if num == 10:
            ln = struct.unpack(e + 'I', buf[off+1:off+5])[0]
        else:
            ln = struct.unpack(e + 'H', buf[off+1:off+3])[0]
        blocks[num] = buf[off:off+ln]
        off += ln
        if num == 11:
            break
    hdr_len = off
    b1 = blocks[1]
    info = {}
    info['satellite'] = b1[6:22].split(b'\0')[0].decode()
    info['center'] = b1[22:38].split(b'\0')[0].decode()
    info['area'] = b1[38:42].decode()
    info['timeline'] = struct.unpack(e + 'H', b1[44:46])[0]
    obs_start, obs_end, ctime = struct.unpack(e + 'ddd', b1[46:70])
    info['obs_start_mjd'] = obs_start; info['obs_end_mjd'] = obs_end; info['file_creation_mjd'] = ctime
    info['format_version'] = b1[82:114].split(b'\0')[0].decode(errors='replace')
    b2 = blocks[2]
    bits, ncol, nline, comp = struct.unpack(e + 'HHHB', b2[3:10])
    info.update(ncol=ncol, nline=nline, compression_flag=comp)
    b3 = blocks[3]
    sub_lon, cfac, lfac, coff, loff = struct.unpack(e + 'dIIff', b3[3:27])
    info.update(sub_lon=sub_lon, cfac=cfac, lfac=lfac, coff=coff, loff=loff)
    b5 = blocks[5]
    band, wl, vbits, err_c, out_c, slope, icpt = struct.unpack(e + 'HdHHHdd', b5[3:35])
    c0, c1, c2, C0, C1, C2, c, h, k = struct.unpack(e + 'ddddddddd', b5[35:107])
    info.update(band=band, wavelength_um=wl, valid_bits=vbits, slope=slope, intercept=icpt)
    cal = dict(wl=wl, slope=slope, icpt=icpt, c0=c0, c1=c1, c2=c2, c=c, h=h, k=k, err=err_c, out=out_c)
    b7 = blocks[7]
    nseg, segno, first_line = struct.unpack(e + 'BBH', b7[3:7])
    info.update(total_segments=nseg, segment_no=segno, first_line=first_line)
    return info, cal, hdr_len, e

def to_bt(counts, cal):
    mask = (counts == cal['err']) | (counts == cal['out'])
    rad = counts.astype(np.float32) * cal['slope'] + cal['icpt']
    lam = cal['wl'] * 1e-6
    I = rad.astype(np.float64) * 1e6  # W m-2 sr-1 um-1 -> W m-2 sr-1 m-1
    with np.errstate(invalid='ignore', divide='ignore'):
        Te = (cal['h'] * cal['c'] / (cal['k'] * lam)) / np.log(2 * cal['h'] * cal['c']**2 / (lam**5 * I) + 1)
    Tb = cal['c0'] + cal['c1'] * Te + cal['c2'] * Te**2
    Tb = Tb.astype(np.float32)
    Tb[mask] = np.nan
    return Tb

def latlon_to_linecol(lat, lon, info):
    lat = np.radians(lat); lon = np.radians(lon)
    sub = np.radians(info['sub_lon'])
    clat = np.arctan(0.993305616 * np.tan(lat))
    rl = 6356.7523 / np.sqrt(1 - 0.00669438444 * np.cos(clat)**2)
    r1 = 42164 - rl * np.cos(clat) * np.cos(lon - sub)
    r2 = -rl * np.cos(clat) * np.sin(lon - sub)
    r3 = rl * np.sin(clat)
    rn = np.sqrt(r1**2 + r2**2 + r3**2)
    x = np.degrees(np.arctan(-r2 / r1))
    y = np.degrees(np.arcsin(-r3 / rn))
    col = info['coff'] + x * 2**-16 * info['cfac']
    line = info['loff'] + y * 2**-16 * info['lfac']
    return line, col

def main():
    res = {}
    for path in sys.argv[1:]:
        t0 = time.perf_counter()
        raw = bz2.decompress(open(path, 'rb').read())
        t1 = time.perf_counter()
        info, cal, hdr_len, e = parse(raw)
        counts = np.frombuffer(raw, dtype=e + 'u2', offset=hdr_len, count=info['ncol'] * info['nline']).reshape(info['nline'], info['ncol'])
        t2 = time.perf_counter()
        bt = to_bt(counts, cal)
        t3 = time.perf_counter()
        print(path.split('/')[-1])
        for kk, v in info.items():
            print(f'  {kk}: {v}')
        print(f'  header_bytes: {hdr_len}  decompressed_bytes: {len(raw)}')
        print(f'  t_decompress_s: {t1-t0:.2f}  t_parse_s: {t2-t1:.3f}  t_calibrate_s: {t3-t2:.2f}')
        print(f'  BT stats K: min {np.nanmin(bt):.1f} median {np.nanmedian(bt):.1f} max {np.nanmax(bt):.1f}')
        res[info['band']] = (info, bt)
    ru = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    print('peak RSS MB (macOS reports bytes):', ru / 1e6)
    info = next(iter(res.values()))[0]
    fl = info['first_line']; nl = info['nline']
    print(f'segment lines {fl}..{fl+nl-1}')
    for name, lat, lon in [('Krakatau', -6.10, 105.42), ('Java W corner', -6.0, 105.0), ('Java/Bali SE corner', -9.0, 116.0),
                           ('Semeru', -8.108, 112.92), ('Lewotobi', -8.542, 122.775), ('Halmahera Dukono', 1.693, 127.894),
                           ('Ibu', 1.488, 127.63), ('Sakurajima', 31.593, 130.657), ('Bali Agung', -8.343, 115.508),
                           ('Ruang', 2.30, 125.37), ('Kanlaon', 10.412, 123.132)]:
        line, col = latlon_to_linecol(lat, lon, info)
        seg = int((line - 1) // 550) + 1
        print(f'  {name:22s} lat {lat:7.3f} lon {lon:8.3f} -> line {line:7.1f} col {col:7.1f} -> 2km FLDK segment S{seg:02d}10')
    if 13 in res and 15 in res:
        btd = res[13][1] - res[15][1]
        line0, col0 = latlon_to_linecol(-8.108, 112.92, info)
        r = int(round(line0)) - fl; cc = int(round(col0)) - 1
        win = btd[max(r-100,0):r+100, max(cc-100,0):cc+100]
        print('BTD B13-B15 around Semeru 200x200 px: min %.2f p01 %.2f median %.2f; fraction < -1 K: %.4f; fraction < 0 K: %.4f' % (
            np.nanmin(win), np.nanpercentile(win, 1), np.nanmedian(win), np.nanmean(win < -1), np.nanmean(win < 0)))
        print('BTD whole segment: fraction < -1 K: %.4f; fraction < 0 K: %.4f' % (np.nanmean(btd < -1), np.nanmean(btd < 0)))

main()
