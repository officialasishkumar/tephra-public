"""Scratch: wide-area BTD view from already-downloaded HSD segments; writes a PNG (pure numpy+zlib).
Usage: python3 -I wide_png.py OUT.png LAT LON HALF_PX file_B14 file_B15 file_B13
"""
import sys, zlib, struct, bz2, numpy as np
sys.path.insert(0, '/nonexistent')
out, lat, lon, half = sys.argv[1], float(sys.argv[2]), float(sys.argv[3]), int(sys.argv[4])
files = sys.argv[5:8]
def read(p):
    raw = bz2.decompress(open(p,'rb').read()); e = '<' if raw[5]==0 else '>'
    off=0; blk={}
    while True:
        n=raw[off]; ln = struct.unpack(e+'I', raw[off+1:off+5])[0] if n==10 else struct.unpack(e+'H', raw[off+1:off+3])[0]
        blk[n]=raw[off:off+ln]; off+=ln
        if n==11: break
    _, ncol, nline, _ = struct.unpack(e+'HHHB', blk[2][3:10])
    sub_lon, cfac, lfac, coff, loff = struct.unpack(e+'dIIff', blk[3][3:27])
    band, wl, vb, errc, outc, slope, icpt = struct.unpack(e+'HdHHHdd', blk[5][3:35])
    c0,c1,c2,C0,C1,C2,c,h,k = struct.unpack(e+'9d', blk[5][35:107]); _,_,fl = struct.unpack(e+'BBH', blk[7][3:7])
    cnt = np.frombuffer(raw, dtype=e+'u2', offset=off, count=ncol*nline).reshape(nline, ncol)
    bad = (cnt==errc)|(cnt==outc); lam = wl*1e-6; I=(cnt.astype(np.float64)*slope+icpt)*1e6
    with np.errstate(all='ignore'): Te=(h*c/(k*lam))/np.log(2*h*c**2/(lam**5*I)+1)
    Tb=(c0+c1*Te+c2*Te**2).astype(np.float32); Tb[bad]=np.nan
    return Tb, dict(sub_lon=sub_lon,cfac=cfac,lfac=lfac,coff=coff,loff=loff,fl=fl)
def ll2lc(lat, lon, nav):
    lat, lon = np.radians(lat), np.radians(lon); sub=np.radians(nav['sub_lon'])
    clat=np.arctan(0.993305616*np.tan(lat)); rl=6356.7523/np.sqrt(1-0.00669438444*np.cos(clat)**2)
    r1=42164-rl*np.cos(clat)*np.cos(lon-sub); r2=-rl*np.cos(clat)*np.sin(lon-sub); r3=rl*np.sin(clat); rn=np.sqrt(r1**2+r2**2+r3**2)
    return nav['loff']+np.degrees(np.arcsin(-r3/rn))*2**-16*nav['lfac'], nav['coff']+np.degrees(np.arctan(-r2/r1))*2**-16*nav['cfac']
def inv(line, col, nav):
    x=np.radians((col-nav['coff'])*2**16/nav['cfac']); y=np.radians((line-nav['loff'])*2**16/nav['lfac'])
    a=np.cos(y)**2+1.006739501*np.sin(y)**2; b=42164*np.cos(x)*np.cos(y); sd=np.sqrt(np.maximum(b**2-a*1737122264,0)); sn=(b-sd)/a
    s1=42164-sn*np.cos(x)*np.cos(y); s2=sn*np.sin(x)*np.cos(y); s3=-sn*np.sin(y)
    return np.degrees(np.arctan(1.006739501*s3/np.sqrt(s1**2+s2**2))), np.degrees(np.arctan(s2/s1))+nav['sub_lon']
b14, nav = read(files[0]); b15, _ = read(files[1]); b13, _ = read(files[2])
line, col = ll2lc(lat, lon, nav); r=int(round(line))-nav['fl']; cc=int(round(col))-1
r0=max(r-half,0); r1=min(r+half,b14.shape[0]); c0=max(cc-half,0); c1=min(cc+half,b14.shape[1])
d = (b14-b15)[r0:r1, c0:c1]; t13 = b13[r0:r1, c0:c1]
neg = d < -1.0
print(f'window lines {r0+nav["fl"]}-{r1-1+nav["fl"]} cols {c0+1}-{c1}: px BTD14-15<-1K: {int(np.nansum(neg))}, <-0.5K: {int(np.nansum(d<-0.5))}, min {np.nanmin(d):+.2f}, median {np.nanmedian(d):+.2f}; B13 min {np.nanmin(t13):.1f}K; px B13<230K: {int(np.nansum(t13<230))}')
if neg.any():
    yy, xx = np.nonzero(neg)
    la, lo = inv(yy+r0+nav['fl'], xx+c0+1, nav)
    print(f'  negative px lat range {la.min():.2f}..{la.max():.2f}, lon range {lo.min():.2f}..{lo.max():.2f}, centroid {la.mean():.2f},{lo.mean():.2f}')
# render: left = BTD diverging (-3..+5), right = B13 grey (200..300K)
def cmap_btd(v):
    v = np.clip(v, -3, 5); rgb = np.zeros(v.shape+(3,), np.uint8)
    neg = v < 0; t = np.where(neg, -v/3, v/5)
    rgb[...,0] = np.where(neg, (255*(1-t)).astype(int), 255); rgb[...,1] = np.where(neg, (255*(1-t*0.6)).astype(int), (255*(1-t*0.7)).astype(int)); rgb[...,2] = np.where(neg, 255, (255*(1-t)).astype(int))
    rgb[np.isnan(v)] = 0; return rgb
g = np.clip((300-np.nan_to_num(t13, nan=300))/100*255, 0, 255).astype(np.uint8)
img = np.concatenate([cmap_btd(d), np.stack([g,g,g],-1)], axis=1)
# vent marker
vr, vc = r-r0, cc-c0
for dy in range(-4,5): 
    for im_off in (0, d.shape[1]):
        if 0<=vr+dy<img.shape[0]: img[vr+dy, im_off+vc] = (0,200,0)
        if 0<=vc+dy<d.shape[1]: img[vr, im_off+vc+dy] = (0,200,0)
H, W, _ = img.shape
raw = b''.join(b'\x00'+img[i].tobytes() for i in range(H))
def chunk(t, data): return struct.pack('>I', len(data))+t+data+struct.pack('>I', zlib.crc32(t+data)&0xffffffff)
png = b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR', struct.pack('>IIBBBBB', W, H, 8, 2, 0, 0, 0))+chunk(b'IDAT', zlib.compress(raw, 6))+chunk(b'IEND', b'')
open(out,'wb').write(png); print('wrote', out, W, H)
