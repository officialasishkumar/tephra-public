# JMA volcano XML fixtures

Source: Japan Meteorological Agency website (https://www.data.jma.go.jp/developer/index.html).
Published under the Public Data License 1.0 (PDL 1.0), terms at
https://www.jma.go.jp/jma/kishou/info/coment.html. The files are saved byte for byte, so
they are JMA's own text, not edited. TEPHRA's parser reads them (`tephra/feeds/jma_volcano.py`)
and shows what it derived as TEPHRA's, not JMA's, work.

Fetched on 2026-10-11 with `curl`, a descriptive User-Agent and one request per file.

| File | URL | What it is |
|---|---|---|
| `eqvol.xml` | https://www.data.jma.go.jp/developer/xml/feed/eqvol.xml | Atom feed "高頻度（地震火山）" as served at the fetch (29 entries: 28 VFVO53 and one VXSE53 earthquake report) |
| `20261008050115_0_VFVO52_400000.xml` | https://www.data.jma.go.jp/developer/xml/data/20261008050115_0_VFVO52_400000.xml | 噴火に関する火山観測報: Sakurajima eruption, plume 6800 FT |
| `20261011140052_0_VFVO53_010000.xml` | https://www.data.jma.go.jp/developer/xml/data/20261011140052_0_VFVO53_010000.xml | 降灰予報（定時）: Kirishima (Shinmoedake) |
| `20261008020006_0_VFVO50_010000.xml` | https://www.data.jma.go.jp/developer/xml/data/20261008020006_0_VFVO50_010000.xml | 噴火警報・予報: Bayonnaise Rocks |
| `20261009070326_0_VFVO51_400000.xml` | https://www.data.jma.go.jp/developer/xml/data/20261009070326_0_VFVO51_400000.xml | 火山の状況に関する解説情報: Aso |
| `20261008050149_0_VFVO60_010000.xml` | https://www.data.jma.go.jp/developer/xml/data/20261008050149_0_VFVO60_010000.xml | 推定噴煙流向報: Sakurajima |

No real 噴火速報 (VFVO56) was available. The tests build one from the VFVO52 layout in code.

Do not refresh these files in place; if the format changes, add a new dated fixture.
