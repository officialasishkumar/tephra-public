"""Scratch: decompress the leading part of a whole-disk HSD .bz2 (range-downloaded) and compute BTD near a point.
Usage: python3 -I partial_btd.py OUT.png LAT LON HALF f13 f14 f15
"""
import sys, bz2, struct, zlib, numpy as np
out, lat, lon, half = sys.argv[1], float(sys.argv[2]), float(sys.argv[3]), int(sys.argv[4])
def read_partial(p):
    rest = open(p,'rb').read(); parts = []
    while rest:
        dec = bz2.BZ2Decompressor()
        try: parts.append(dec.decompress(rest))
        except Exception: break
        if not dec.eof: break
        rest = dec.unused_data
    raw = b''.join(parts)
    e = '<' if raw[5]==0 else '>'; off=0; blk={}
    while True:
        n=raw[off]; ln = struct.unpack(e+'I', raw[off+1:off+5])[0] if n==10 else struct.unpack(e+'H', raw[off+1:off+3])[0]
        blk[n]=raw[off:off+ln]; off+=ln
        if n==11: break
    _, ncol, nline, _ = struct.unpack(e+'HHHB', blk[2][3:10])
    sub_lon, cfac, lfac, coff, loff = struct.unpack(e+'dIIff', blk[3][3:27])
    band, wl, vb, errc, outc, slope, icpt = struct.unpack(e+'HdHHHdd', blk[5][3:35])
    c0,c1,c2,C0,C1,C2,c,h,k = struct.unpack(e+'9d', blk[5][35:107]); _,_,fl = struct.unpack(e+'BBH', blk[7][3:7])
    avail = (len(raw)-off)//(2*ncol)
    cnt = np.frombuffer(raw, dtype=e+'u2', offset=off, count=ncol*avail).reshape(avail, ncol)
    bad=(cnt==errc)|(cnt==outc); lam=wl*1e-6; I=(cnt.astype(np.float64)*slope+icpt)*1e6
    with np.errstate(all='ignore'): Te=(h*c/(k*lam))/np.log(2*h*c**2/(lam**5*I)+1)
    Tb=(c0+c1*Te+c2*Te**2).astype(np.float32); Tb[bad]=np.nan
    return Tb, dict(sub_lon=sub_lon,cfac=cfac,lfac=lfac,coff=coff,loff=loff,fl=fl,nline=nline), avail, band
def ll2lc(lat, lon, nav):
    lat, lon = np.radians(lat), np.radians(lon); sub=np.radians(nav['sub_lon'])
    clat=np.arctan(0.993305616*np.tan(lat)); rl=6356.7523/np.sqrt(1-0.00669438444*np.cos(clat)**2)
    r1=42164-rl*np.cos(clat)*np.cos(lon-sub); r2=-rl*np.cos(clat)*np.sin(lon-sub); r3=rl*np.sin(clat); rn=np.sqrt(r1**2+r2**2+r3**2)
    return nav['loff']+np.degrees(np.arcsin(-r3/rn))*2**-16*nav['lfac'], nav['coff']+np.degrees(np.arctan(-r2/r1))*2**-16*nav['cfac']
T = {}
for p in sys.argv[5:8]:
    tb, nav, avail, band = read_partial(p); T[band] = tb; print('band', band, 'lines decoded', avail, 'of', nav['nline'])
n = min(t.shape[0] for t in T.values())
line, col = ll2lc(lat, lon, nav); r=int(round(line))-nav['fl']; cc=int(round(col))-1
r0=max(r-half,0); r1=min(r+half,n); c0=max(cc-half,0); c1=cc+half
d=(T[14][:n]-T[15][:n])[r0:r1,c0:c1]; d2=(T[13][:n]-T[15][:n])[r0:r1,c0:c1]; t13=T[13][:n][r0:r1,c0:c1]
print(f'Raikoke window lines {r0+1}-{r1} cols {c0+1}-{c1}: B14-B15 min {np.nanmin(d):+.2f} median {np.nanmedian(d):+.2f}; px<-1K {int(np.nansum(d<-1))}, px<-0.5K {int(np.nansum(d<-0.5))} of {np.isfinite(d).sum()}; B13-B15 min {np.nanmin(d2):+.2f} px<-1K {int(np.nansum(d2<-1))}; B13 min {np.nanmin(t13):.1f}K')
def cmap_btd(v):
    v=np.clip(v,-3,5); rgb=np.zeros(v.shape+(3,),np.uint8); ng=v<0; t=np.where(ng,-v/3,v/5)
    rgb[...,0]=np.where(ng,(255*(1-t)).astype(int),255); rgb[...,1]=np.where(ng,(255*(1-t*0.6)).astype(int),(255*(1-t*0.7)).astype(int)); rgb[...,2]=np.where(ng,255,(255*(1-t)).astype(int))
    rgb[np.isnan(v)]=0; return rgb
g=np.clip((300-np.nan_to_num(t13,nan=300))/100*255,0,255).astype(np.uint8)
img=np.concatenate([cmap_btd(d), np.stack([g,g,g],-1)],axis=1)
H,W,_=img.shape; raw=b''.join(b'\x00'+img[i].tobytes() for i in range(H))
ch=lambda t,dd: struct.pack('>I',len(dd))+t+dd+struct.pack('>I',zlib.crc32(t+dd)&0xffffffff)
open(out,'wb').write(b'\x89PNG\r\n\x1a\n'+ch(b'IHDR',struct.pack('>IIBBBBB',W,H,8,2,0,0,0))+ch(b'IDAT',zlib.compress(raw,6))+ch(b'IEND',b'')); print('wrote', out, W, H)
