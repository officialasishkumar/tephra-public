# Reading volcano notices in any language: research for TEPHRA

Date: 2026-10-11. Nothing in the repo was edited, no project code was run, and gcloud was not used. Sources I fetched directly are marked CONFIRMED. Anything else is marked UNVERIFIED or REPORTED. I skimmed `research/05`, `17`, `06`, `tephra/feeds/vona.py` and `docs/DATA-LICENCES.md` first and do not repeat them. I rely on their finding that MAGMA is RED: "All Rights Reserved", `robots.txt` Disallow, and no public API.

**Corrections to the brief**
- GeoNet NZ is licensed **CC BY 3.0 NZ**, not 4.0. CONFIRMED: https://www.geonet.org.nz/policy and https://api.geonet.org.nz/.
- JMA's own terms page says content may be used under the Public Data License (PDL) 1.0, "unless a rights notice says otherwise". It does not itself say "CC BY compatible". The Digital Agency's licence text states that compatibility. CONFIRMED: https://www.jma.go.jp/jma/kishou/info/coment.html and https://www.digital.go.jp/resources/open_data/public_data_license_v1.0.
- The PHIVOLCS data policy **prohibits redistribution** and public forecasting by non-PHIVOLCS parties. CONFIRMED: https://wovodat.phivolcs.dost.gov.ph/user/policy.
- The public Telegram preview of MAGMA's "Notifikasi Letusan" channel shows its last post on 2025-07-11. Treat it as dormant. CONFIRMED at https://t.me/s/MagmaIndonesia; the cause is UNVERIFIED.

---

## 1. The VONA standard

- **Current status.** ICAO now says information on volcanic activity or ash in the atmosphere *should* be issued by a State Volcano Observatory (SVO) as a VONA. That is a new Recommended Practice, and the template must be followed precisely so the message is machine readable. Requirements are in Annex 3. The template and means of compliance are in PANS-MET (Doc 10157). Guidance is in the Handbook on the IAVW (Doc 9766). CONFIRMED: WOVO/ICAO slides, https://wovo.iavceivolcano.org/content/uploads/sites/20/2026/02/2025-12-evolution-of-the-vona-final.pdf. The ICAO flyer itself (https://www.icao.int/sites/default/files/METP/Documents/IAVW%20docs/VONA_Flyer_for_SVOs_30-March-2026.pdf) returned 403 to my fetch.
- **Fields, new format.** The slides' example below is ICAO's own (Shishaldin 2023), the same as the USGS notice in §2.5. Field order and meaning:

| Field | Meaning |
|---|---|
| (header) | WMO header such as `WMAK01 PAVO`, then the word `VONA` |
| `DTG` | `YYYYMMDD/HHMMZ` |
| `VOLCANO` | Name plus Smithsonian number, e.g. `SHISHALDIN 311360` |
| `PSN` | Position, `N5445 W16358` |
| `AREA` | Region |
| `SOURCE ELEV` | `9373FT AMSL` |
| `NOTICE NR` | `2023/50` |
| `CURRENT COLOUR CODE`, `PREVIOUS COLOUR CODE` | Aviation colour codes |
| `SVO` | Issuing observatory |
| `ACT STS` | Activity status, e.g. `ERUPTION OCCURRED`, `NIL` |
| `ONSET` | `YYYYMMDD/HHMMZ` |
| `DUR` | Duration, e.g. `ONGOING CONS` |
| `VA CLD HGT` | `40000FT AMSL`, or `NO VA CLD PRODUCED` |
| `HGT SOURCE` | Source of the cloud height, e.g. `SATELLITE` |
| `MOV` | Cloud movement direction |
| `CTC` | Contact |
| `RMK` | Remarks |
| `NXT NOTICE` | "A NEW VONA WILL BE ISSUED IF COND CHANGE SIGNIFICANTLY OR IF THE COLOUR CODE CHANGES" |

- **Other points in the same slides.**
  - A new **UNASSIGNED** colour is for poorly monitored volcanoes.
  - A status indicator marks test or exercise messages.
  - Ranges for eruption source parameters are encouraged in `RMK`.
  - VONAs should be sent in both TAC (alphanumeric) and IWXXM (ICAO XML).
  - Resuspended ash can be reported, and the colour code should not change for weather-driven resuspension.
- **Update frequency (new).** A VONA must be updated:
  - on any colour-code change;
  - at least every 24 h while Red;
  - at least every 7 days while Orange;
  - at least twice a month while Yellow.
- **Designated SVOs, APAC.** Japan, Indonesia, PNG, NZ, India and China, among others. Only designated SVOs should issue VONAs. The Philippines is **not** on the 18 Nov 2025 list in the slides. UNVERIFIED whether that reflects a real gap or only the slide's omission. A 2016 ICAO paper says PHIVOLCS provides VONAs to VAAC Tokyo (REPORTED, search snippet of an ICAO APAC paper whose PDF returned 403: https://www.icao.int:443/APAC/Meetings/2016 METIEWG14/IPC1 - AI.2 - Monthly VONA Issuance drill between PHIVOCS and VAAC Tokyo.pdf).
- **Licence.** The ICAO documents are copyrighted. Reproduce only field names, which are facts, not the Handbook text.

## 2. Observatories in APAC and how they publish

### 2.1 Indonesia: PVMBG / MAGMA

- **Web.** The VONA list is English-only HTML at https://magma.esdm.go.id/v1/vona. The page says VONAs "are disseminated via email to national and international stakeholders", that "Other interested parties can avail of them through email subscription", and that "All notifications are publicly available online". CONFIRMED 2026-10-11. No subscribe link or form exists on the page, and I found no official signup instructions anywhere. **Official email signup: not found. UNVERIFIED.**
- **Indonesian-language feed.** https://magma.esdm.go.id/v1/gunung-api/informasi-letusan lists one-line eruption notices. They carry the observer's name and a "Notifikasi Letusan Telegram" link. Observer names are personal data; omit them.
- **Telegram.** The channel https://t.me/MagmaIndonesia has 3.73K subscribers and its last public post is dated 2025-07-11. It is probably not a live source.
- **Indonesian example text** (short quotes, MAGMA copyright):
  - "Terjadi erupsi G. Ibu pada hari Minggu, 11 Oktober 2026, pukul 19:59 WIT. Visual letusan tidak teramati. Erupsi ini terekam di seismograf dengan amplitudo maksimum 28 mm dan durasi 69 detik."
  - "…Tinggi kolom letusan teramati ± 4000 m di atas puncak (± 5584 m di atas permukaan laut). Kolom abu teramati berwarna kelabu dengan intensitas tebal ke arah barat dan barat laut…" (Telegram, 2025-07-11).
- **Activity report page.** https://magma.esdm.go.id/v1/gunung-api/laporan is the Laporan Aktivitas, in Indonesian, with Level III (Siaga) and so on.
- **Time zones.** WIB = UTC+7, WITA = UTC+8, WIT = UTC+9. The suffix must be parsed, not assumed.
- **Licence.** "Copyright 2026 © All Rights Reserved. MAGMA Indonesia" and `robots.txt` Disallow (`research/05`). RED, so no real fixtures in the public repo, and live use only with permission or via email.

### 2.2 Philippines: PHIVOLCS

- **Web.** Bulletins are bilingual HTML in the WOVOdat portal. The list is https://wovodat.phivolcs.dost.gov.ph/bulletin/list-of-bulletin. Each volcano has a Filipino and an English version, e.g. https://wovodat.phivolcs.dost.gov.ph/bulletin/activity-kvo?bid=16878&lang=en (`lang=en` gives English, omit it for Filipino). Volcanoes are Taal, Kanlaon, Mayon, Bulusan, Pinatubo and Hibok-hibok.
- **Format.** A fixed "Summary of 24Hr Observation" card with these labelled fields: Alert Level, Eruption, Activity, Seismicity, Sulfur Dioxide Flux, Plume, Ground Deformation, Recommendation. The map is an image.
- **Real example, English** (11 Oct 2026, quoted for illustration only):
  - "Eruption: 1 moderately explosive eruption (2 minutes long); Activity: 1 ash emission event (161 minutes long); Seismicity: 10 volcanic earthquakes; Sulfur Dioxide Flux: Average: 802 tonnes/day; Maximum: 4656 tonnes/day (10 October 2026); Plume: 6000 meters tall; voluminous emission; southwest and north-northeast drift".
  - Recommendation: "Should not be allowed … Flying any aircraft close to the volcano".
- **Same bulletin, Filipino.** "ANTAS NG ALERTO 2 … moderately explosive eruption (2 minuto ang haba) … Plume 6000 metrong taas; malakas na pagsingaw; napadpad sa timog-kanluran at hilagang-hilagang-silangan … Ipagbawal … Paglipad ng anumang aircraft malapit sa tuktok ng bulkan". The headings are Filipino but the observation labels stay in English, which makes this a good mixed-language test.
- **Feeds.** WordPress `/feed/` exists on https://www.phivolcs.dost.gov.ph/feed/, but it carries procurement posts, not volcano bulletins (CONFIRMED). I found no RSS, API or email list for bulletins. Alert levels are also on the WOVOdat header.
- **VONA.** I found no public PHIVOLCS VONA page. The Philippines' NOTAMs come from CAAP (REPORTED, news: https://tribune.net.ph/2025/10/13/caap-restricts-flights-near-active-volcanoes). VAAC Tokyo or Darwin advisories carry the aviation product.
- **Licence.** Data policy updated 2020-07-01: data users must register, cite DOST-PHIVOLCS, must not publicly forecast ongoing unrest, and "Redistribution or charging for access … is prohibited". RED. Display only as a short cited quote with a link, never in the repo.

### 2.3 Japan: JMA

- **Feeds.** Atom feeds with no registration (https://www.data.jma.go.jp/developer/index.html; pull guide https://xml.kishou.go.jp/xmlpull.html):
  - https://www.data.jma.go.jp/developer/xml/feed/eqvol.xml (high-frequency). At fetch time it held only VFVO53 (降灰予報（定時）) and VFVO51 plus quake items.
  - https://www.data.jma.go.jp/developer/xml/feed/eqvol_l.xml (long-term). At fetch time it held VFVO50 ×2, 51 ×26, 52 ×32, 53 ×784 and 60 ×32 entries.
  - Entries link to `https://www.data.jma.go.jp/developer/xml/data/{YYYYMMDDhhmmss}_0_{CODE}_{office}.xml`.
- **Data type codes.**

| Code | Meaning | Status |
|---|---|---|
| VFVO50 | 噴火警報・予報 | CONFIRMED by fetch |
| VFVO51 | 火山の状況に関する解説情報 | CONFIRMED by fetch |
| VFVO52 | 噴火に関する火山観測報 | CONFIRMED by fetch |
| VFVO53 | 降灰予報（定時） | CONFIRMED by fetch |
| VFVO60 | 推定噴煙流向報 | CONFIRMED by fetch |
| VFVO56 | 噴火速報 | REPORTED (JMA technical info no. 429 and no. 50101 via search); sender offices RJTD, JPSP, JPSN, JPFK |
| VFVO54, VFVO55 | 降灰予報 variants (速報/詳細, presumed) | Names UNVERIFIED |

- **噴火速報.**
  - The template is one sentence: "火山名 ○○山 噴火速報 … ＜○○山で噴火が発生＞ ○○山で、令和△△年△△月△△日△△時△△分頃、噴火が発生しました。" (CONFIRMED: https://www.jma.go.jp/jma/kishou/know/kazan/funkasokuho/funkasokuho_toha.html.)
  - It carries only the volcano name and the time. It is issued a few times a year and was absent from the feeds I read. There is no real example to pull.
  - A 2023 test message had Control/Status 訓練 (REPORTED, in the JMA notice PDF).
- **Real fixture 1, VFVO52 (噴火に関する火山観測報).** https://www.data.jma.go.jp/developer/xml/data/20261008050115_0_VFVO52_400000.xml (CONFIRMED, 2.6 KB).
  - Text: "火 山：桜島 日 時：2026年10月08日13時53分(080453UTC) 現 象：噴火".
  - Structured elements:
    - `Area/Name` 桜島, code 506;
    - `Coordinate` `+3135.55+13039.40+1117/`;
    - `CraterName` 南岳山頂火口;
    - `EventDateTimeUTC` 2026-10-08T04:53:00Z;
    - `PlumeHeightAboveCrater` 1000 m;
    - `PlumeHeightAboveSeaLevel` 6800 FT;
    - `PlumeDirection` 直上;
    - `OtherObservation` "噴煙量：中量".
  - It is fully structured and needs no LLM.
- **Real fixture 2, VFVO53 (降灰予報・定時).** https://www.data.jma.go.jp/developer/xml/data/20261011140052_0_VFVO53_010000.xml (CONFIRMED). The headline is "現在、霧島山（新燃岳）は噴火警戒レベル２（火口周辺規制）です。霧島山（新燃岳）で噴火が発生した場合には、１２日０９時から１２時までは火口から西方向に降灰が予想されます。". It also has municipality lists with codes and plume polygons.
- **Real fixture 3, VFVO50.** https://www.data.jma.go.jp/developer/xml/data/20261008020006_0_VFVO50_010000.xml (CONFIRMED, 5 KB). It is a warning lowering for Bayonnaise Rocks (ベヨネース列岩): "＜ベヨネース列岩に噴火予報（活火山であることに留意）：警報解除を発表＞".
- **Real fixture 4, VFVO51 (解説情報).** https://www.data.jma.go.jp/developer/xml/data/20261009070326_0_VFVO51_400000.xml (CONFIRMED). Aso. Headline "＜火口周辺警報（噴火警戒レベル２、火口周辺規制）が継続＞", followed by `VolcanoActivity` paragraphs. Free text in body elements is where an LLM could help.
- **Real fixture 5, VFVO60.** https://www.data.jma.go.jp/developer/xml/data/20261008050149_0_VFVO60_010000.xml (CONFIRMED). The Sakurajima plume flow direction and speed table by altitude, in metres, degrees and speed units. Units UNVERIFIED.
- **Structure.** The root is `Report`, in `http://xml.kishou.go.jp/jmaxml1/`. It has `Control`, `Head` and `Body`. Head holds `Title`, `ReportDateTime`, `TargetDateTime`, `EventID`, `InfoType`, `Serial`. Body holds `VolcanoInfo`, `VolcanoInfoContent` or `VolcanoObservation`. JMA's own volcano code is the `Area/Code` (506 Sakurajima, 503 Aso, 551 Shinmoedake).
- **Licence.** JMA terms (https://www.jma.go.jp/jma/kishou/info/coment.html):
  - Content may be used under PDL 1.0.
  - Credit as "出典：気象庁ホームページ（URL）".
  - State any edit separately: "気象庁「…」（URL）を加工して作成".
  - Do not present edited material as if the government produced it.
  - Some content is restricted by individual laws, namely Weather Service Act Art. 17(1) and Art. 23.
  - PDL 1.0 is stated by the Digital Agency to be compatible with CC BY 4.0 (https://www.digital.go.jp/resources/open_data/public_data_license_v1.0).
  - The developer page gives no specific XML licence. It disclaims responsibility and warns of delays and discontinuation, and links 利用上の留意事項 (https://www.data.jma.go.jp/developer/ryuui.pdf, whose text I could not read).
- **Weather Service Act caution.** A repeated, continuing public forecast needs a permit under Art. 17 (REPORTED, via search of JMA seminar PDFs). TEPHRA does not forecast. The Gemini cone is labelled "decision support, proxy fleet, not an advisory" and is shown only to a dispatcher. Do not republish JMA text as TEPHRA's own forecast. This is general information, not legal advice. UNVERIFIED for this use.

### 2.4 Russia: KVERT

- VONAs go by email to the Yelizovo airport meteorological centre and the Tokyo, Anchorage, Washington, Montreal and Darwin VAACs. They are also posted at http://www.kscnet.ru/ivs/kvert/, which now redirects to http://kvert.febras.net/index_eng.php. Copies appear on a public mailing-list archive, https://list.avo.alaska.edu/hyperkitty/list/avo_kvert@list.avo.alaska.edu/thread/IU555LPXRDPUZNYN5QHAUXE63MPJZ5AQ (REPORTED, search snippets). Notices were in the older English format (`Issued: 20220826/2341Z`). The new-template status is UNVERIFIED.
- I could not read the KVERT site (connection refused or empty). Subscription and licence are UNVERIFIED.

### 2.5 USA: AVO / HVO via USGS HANS

- **Open JSON API, no key.** CONFIRMED by calling it:
  - `GET https://volcanoes.usgs.gov/hans-public/api/notice/recent` lists recent notices.
  - `GET .../api/notice/getVonasWithinLastYear` returned 99 VONAs, with `vona_data`, `vona_url`, `color_code`, `alert_level`, `volcano_cd`, `vnum`, lat/lon.
  - `GET .../api/notice/getNoticeFormatted/{notice_identifier}/{json|html|text|sms}` returns the notice.
  - The docs also list CAP and RSS feeds (https://volcanoes.usgs.gov/hans-public/resources), with a warning that the API may change.
- **Real new-format VONA** (Kīlauea 2026-10-06, in TAC): https://volcanoes.usgs.gov/hans-public/api/notice/getNoticeFormatted/DOI-USGS-HVO-2026-10-06T18:56:12+00:00/text. This is the 2026 ICAO-aligned layout (CONFIRMED):
```
VOLCANO OBSERVATORY NOTICE FOR AVIATION (VONA)WMPA01 PHVO 061920
VONA
DTG:20261006/1920Z
VOLCANO:KILAUEA 332010
PSN:N1925 W15517
AREA: HAWAII
SOURCE ELEV:4091FT AMSL
NOTICE NR:2026/64
CURRENT COLOUR CODE:ORANGE
PREVIOUS COLOUR CODE: ORANGE
SVO:HAWAIIAN VOLCANO OBSERVATORY
ACT STS:NIL
ONSET:NIL
DUR:NIL
VA CLD HGT: NO VA CLD PRODUCED
HGT SOURCE: NO VA CLD PRODUCED
MOV:NO VA CLD PRODUCED
CTC:HVO DUTY SCIENTIST: 808-785-3144
RMK:SHALLOW INTRUSION OCCURED BENEATH HALEMAʻUMAʻU (SUMMIT OF KĪLAUEA VOLCANO) SEP
30–OCT 1. AT PRESENT, MINOR SPATTERING AT BOTH N AND S VENTS. THESE MAY OR MAY NOT
LEAD TO EPISODE 55 HIGH FOUNTAINS. HVO IS CAREFULLY MONITORING THE ONGOING ACTIVITY.
NXT NOTICE: A NEW VONA WILL BE ISSUED IF COND CHANGE SIGNIFICANTLY OR IF THE COLOR CODE CHANGES
NNNN
```
- USGS's announcement says the new VONA has all-caps text, aviation terminology and a machine-readable version (REPORTED, search snippet of https://www.usgs.gov/programs/VHP/news/usgs-launch-updated-aviation-focused-volcano-notices-march-2026; the page returned empty to my fetch).
- **Licence.** USGS-authored data is public domain, with a request to acknowledge USGS. Some third-party items on the site are copyrighted (https://www.usgs.gov/faqs/are-usgs-reports-copyrighted, via search snippet; I did not open the copyright page itself). The VONA text above is a US-government product. Very likely safe as a fixture with credit "Source: USGS HVO". The strict reading is a one-line check of the official policy.
- **Why it matters.** This is the ICAO-standard TAC text, so a parser written against it also works for any SVO using the new template.

### 2.6 New Zealand: GeoNet / GNS

- **API.** `GET https://api.geonet.org.nz/volcano/val` gives the volcanic alert level (VAL) as GeoJSON (`Accept: application/vnd.geo+json;version=2`). `GET .../volcano/quake/{volcanoID}` also exists. **No bulletin endpoint** is listed (CONFIRMED: https://api.geonet.org.nz/). Bulletins (VABs) are on https://www.geonet.org.nz/volcano/vab.
- **Aviation.** GNS Science sets the Aviation Colour Code. VONA is not in GeoNet's API (UNVERIFIED).
- **Licence.** "Copyright Earth Sciences New Zealand … licensed under a Creative Commons Attribution 3.0 New Zealand License", plus a disclaimer (CONFIRMED). Redistribution with attribution is allowed.
- **Relevance.** Outside TEPHRA's three regions. Low priority.

### 2.7 Papua New Guinea: RVO

- RVO monitors the country's volcanoes. I found no public RVO feed, mailing list or VONA page. Reports reach the public through the Smithsonian/USGS Weekly Report and the Darwin VAAC (REPORTED, e.g. https://www.preventionweb.net/news/view/17248). Not usable as a direct feed. All details UNVERIFIED.

### 2.8 Licence-safe fixtures for a public repo

| Source | Verdict | Condition |
|---|---|---|
| JMA XML (VFVO50/51/52/53/60) | GREEN | Credit JMA, note any edit. PDL 1.0 |
| USGS HVO/AVO VONA | GREEN (likely) | Credit USGS; third-party images excluded |
| GeoNet NZ | GREEN | CC BY 3.0 NZ attribution |
| MAGMA (any language) | RED | Write synthetic text in the same wording |
| PHIVOLCS | RED | Same; no redistribution |
| KVERT, RVO | UNVERIFIED | Do not ship |

## 3. Email ingestion, lawfully and simply

- **Is there an official signup?** For MAGMA, the page says an email subscription exists but gives no route. The existing research treats it as the lawful route. The next step for the user is a short email to PVMBG/MAGMA (the contact route is on their site, not looked up here). UNVERIFIED that it works or how fast it arrives. Recipients must be aviation stakeholders; a hackathon use may need explicit permission.
- **Simplest demo path (recommended).**
  1. Use a **dedicated personal mailbox**, never the work Gmail.
  2. For the demo, add an `/ingest/email` endpoint that takes raw `.eml` text or pasted text.
  3. Run the same parser and extractor on it as on every other source.
  4. Replay a synthetic `.eml` in the video.
- **Live option A: Gmail API, polling.** CONFIRMED at https://developers.google.com/workspace/gmail/api/reference/quota: "All standard use … is available at no additional cost". The daily threshold is 80,000,000 units per project, with 6,000 units per user per minute. `messages.list` costs 5 units, `messages.get` 20, `history.list` 2, `watch` 100. Google plans charges for exceeding quota "later in 2026", so it is free within quota. Polling `history.list` every 60 s uses about 2,900 units a day. Push needs Pub/Sub plus watch renewal every 7 days (REPORTED), so avoid it. The Gmail MCP/OAuth route is for the user to set up, since TEPHRA must not use gcloud on this Mac.
- **Live option B: Cloudflare Email Routing + Email Worker → webhook.** Inbound routing is free and unlimited. The Worker POSTs the raw message to TEPHRA, and `postal-mime` parses it (REPORTED: https://developers.cloudflare.com/email-service/platform/pricing/). It needs a domain the user owns and DNS changes. Skip unless they have a domain.
- **Live option C: IMAP with an app password.** Fine for a demo, but it keeps a credential on the server. Avoid for any hosted deployment.
- **Compliance.** Store only the notice body, not sender details. Show "Source: PVMBG/MAGMA via email subscription". Do not republish the raw email in the repo.

## Recommendation for TEPHRA

### Parse deterministically first, use Gemini only where no structure exists

- **JMA XML (VFVO50/51/52/53/60):** parse the XML with a small parser. No Gemini call. Map `EventDateTimeUTC`, `Area/Code`, `Name`, `Coordinate` and `PlumeHeightAboveSeaLevel` (FT) straight to the schema.
- **USGS HANS VONA text:** regex on the TAC fields in §1. No Gemini call. The same parser handles any SVO using the new template, including a future Indonesian, PNG or NZ one.
- **MAGMA HTML:** keep the existing `vona.py` parser.
- **Gemini flash-lite only for free text:**
  - MAGMA Indonesian-language lines;
  - PHIVOLCS bulletins (Filipino and English);
  - email bodies;
  - JMA 解説情報 paragraphs, if wanted.
  - Budget: flash-lite is about 500 requests a day. Use at most about 150 a day for extraction, dedupe by SHA-256 of the normalised text, cache the result, and run one notice per call. Keep the 20-a-day gemini-3.8-flash for the hazard cone.

### Schema

- **Output model:** reuse and extend `Vona`. Add `language` (`en`, `id`, `ja`, `fil`), `source_kind` (`magma_html`, `jma_xml`, `usgs_tac`, `phivolcs_html`, `email`), `evidence` and `derived`. Check that `AviationColor` includes UNASSIGNED.
- **ICAO fields to carry:** `dtg`, `volcano_name`, `volcano_number`, `psn`, `area`, `source_elev_ft`, `notice_nr`, `current_colour`, `previous_colour`, `svo`, `act_sts`, `onset`, `dur`, `va_cld_hgt_ft`, `hgt_source`, `mov`, `ctc`, `rmk`, `nxt_notice`, `status` (test or operational).
- **Extension fields:** `alert_level_local` (e.g. PHIVOLCS 2, PVMBG III Siaga, JMA 噴火警戒レベル), `so2_t_per_day`, `plume_height_above_summit_m`, `crater_name`.

### Keeping facts verifiable

1. **Evidence spans.** Gemini returns, for each field, `{value, evidence}`. `evidence` must be a verbatim substring of the source text.
2. **Normalise before comparing.** Apply Unicode NFKC, so full-width digits `１２` become `12`, and drop thousands separators.
3. **Numbers.** Every extracted number must appear in its evidence string. Reject the field if it does not.
4. **Dates.** A time with a zone suffix is converted deterministically: WIB −7, WITA −8, WIT −9, JST −9, UTC 0. Flag `derived=true`. The model never converts.
5. **Heights.** Metres to feet use the existing `m_to_ft` (×3.28084), flagged `derived`. Use the source's metre figure, as `vona.py` does (MAGMA's feet are ×3.2).
6. **Enums.** Colour code and ash observed/not observed must match a regex hit in the text ("tidak teramati" → not observed, "not observed", 噴煙…). Anything the model cannot back with a span becomes `null`.
7. **No inference.** Never convert PHIVOLCS "voluminous emission" into an ash height. A field the source does not state stays `null`.
8. **Gate.** A notice that fails verification is shown to the dispatcher as raw text with a "not verified" badge and never feeds the cone or the flight plans.

### Fixtures to ship in the public repo

- **Ship (GREEN):** JMA VFVO52 Sakurajima, VFVO53 Kirishima, VFVO50 Bayonnaise and VFVO51 Aso (URLs in §2.3), credited "Source: JMA website" with a note that TEPHRA parses them. Also the USGS Kīlauea VONA text above, credited to USGS HVO.
- **Synthetic (write by hand, same wording and structure):**
  - Indonesian: a MAGMA-style "Terjadi erupsi G. … pukul … WIB … ± … m di atas puncak (± … m di atas permukaan laut)" line, with an invented volcano state, invented numbers and no observer name.
  - Filipino and English: a Kanlaon-style 24-hour card, invented numbers.
  - Name them `synthetic_*` so the history check in `docs/DATA-LICENCES.md` can tell them apart.
- **Never ship:** real MAGMA or PHIVOLCS text, or screenshots of either.

### Source priority for the demo

1. JMA XML for Kyushu (Sakurajima, Kirishima, Aso, Suwanosejima): deterministic, GREEN, live, no key.
2. MAGMA for Java and Halmahera: existing parser, off by default (`TEPHRA_VONA_LIVE=false`), email as the lawful route.
3. PHIVOLCS: out of TEPHRA's three regions. Mention it as an extension in the video, without ingesting it.
4. USGS HVO: a fixture and a test of the ICAO parser, not a live source.

### Credits line to add

"Volcano notices: JMA (PDL 1.0), PVMBG/MAGMA Indonesia via email subscription, USGS. Edited and parsed by TEPHRA, not original text."

### Open items for the user

- Email PVMBG/MAGMA to ask for the subscription route and permission.
- Confirm with JMA, or a lawyer, the Art. 17 position if TEPHRA ever displays a derived forecast.
- Re-fetch JMA's data type code list (https://xml.kishou.go.jp/) to confirm the names of VFVO54 and VFVO55.
