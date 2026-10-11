# Airline network disruption recovery when an airport or airspace closes for volcanic ash, plus crew and passenger messaging

Researched 2026-10-11 for TEPHRA. I did not edit the repo, run project code or use gcloud. I ran one scratch CP-SAT prototype of my own in the session scratchpad.

Tags: [C] means I opened the source. [S] means a search-result summary or secondary source only. UNVERIFIED means not confirmed.

Sources I could not open, so claims from them are [S] or UNVERIFIED: icao.int (403), hukumonline, mkri.id, the Senate APBR PDF, ANA and JAL pages (403 or timeout), and the full Doc 9974 PDF.

---

## 0. Bottom line

1. **A real, very recent Java closure exists and should anchor the pitch.** On 5–7 Sep 2026 Anak Krakatau ash closed Soekarno-Hatta (CGK), Halim (HLP), Bandung and Radin Inten II. Eight airports halted, more than 270,000 passengers were stranded, and Lion Group cancelled 275 flights in one day. It is not in the earlier research files. Details are in section 1.
2. **Recovery should be a small deterministic optimiser, not an LLM.** An arc-based CP-SAT model (optional flight nodes in a multi-circuit) solved 40–80 free flights to proven optimality in under 1 s. It took 1–4 s for 75–100 flights, but 150 flights did not converge in 2 s. This is measured on my own synthetic instance (section 2.5). The fix is a frozen-window decomposition, so only about 40–100 flights are free.
3. **Gemini's role is explanation and drafting.** It explains the solver's plan and drafts messages from fixed templates, with code validating that required fields are present and no invented numbers appear. With about 20 requests/day on the stronger model, Gemini should not be on the solve path.
4. **Indonesia's PM 89/2015 (primary text, OCR'd) sets concrete notice rules.** Cancellation is "category 6": the airline must move the passenger to the next flight or refund the full ticket, with no cash compensation. Weather and technical-operational causes need an official letter from BMKG or the airport authority. Ash is not listed by name. Details are in section 4.
5. **Indonesian FTL limits are readable from the CASR 121 Amdt 12 PDF (May 2017):** 14 h flight duty in 24 h, 15 h with a flight engineer, and an unforeseen-circumstances extension of up to +3 h for domestic carriers. Japan's numbers are UNVERIFIED.

---

## 1. Real ash closure events

### 1.1 Anak Krakatau, Java, 5–7 Sep 2026 (new)

- **Volcano and alert level.** Anak Krakatau has been at Level III (Siaga) since 2 July, with continuous eruption from 23:07 local on 5 Sep. [C: https://bernama.com/bm/news.php?id=2603597]
- **Sunday 6 Sep, CGK.**
  - CGK closed 01:30–05:30 after a paper test (12:35–01:05) showed ash dispersal.
  - The closure was extended to 09:30 after a second test.
  - 209 flights and 22,798 passengers were disrupted. International: 16 cancelled, 7 postponed, 5 rescheduled. Domestic: 4 cancelled and 1 diverted.
  - The DG of Civil Aviation said the focus was on restoring schedules given knock-on effects on aircraft rotations, aircraft availability and terminal capacity. [C: same Bernama URL]
- **Monday 7 Sep.**
  - NOTAM closed CGK from 08:28 WIB and HLP from 08:16, both with estimated reopening at 18:00. Lion Group cancelled 275 flights (Lion Air, Batik Air, Batik Air Malaysia, Super Air Jet). [S: https://katadata.co.id/berita/industri/6a9e64e75b0e7/lion-air-group-batalkan-275-penerbangan-halim-dan-soekarno-hatta-hari-ini]
  - Another outlet gave 281. Kontan's CGK-only split was Batik 130, Super Air Jet 85 and Lion Air 35, totalling 250. [C: https://industri.kontan.co.id/news/abu-vulkanik-anak-krakatau-ganggu-penerbangan-250-pesawat-batal]
  - Citilink listed CGK, HLP, Husein Sastranegara (BDO) and Radin Inten II (TKG) as closed, offering free reschedule or full refund. [C: same Kontan URL]
  - Eight airports halted over the weekend. More than 240 flights at CGK were cancelled or delayed on Monday morning alone. More than 270,000 passengers were stranded cumulatively since 5 Sep. A small south-Sumatra airport reopened at 09:00 Monday. [C: https://kuwaittimes.com/article/49337/world/jakarta-airport-extends-closure-as-volcanic-ash-lingers/]
- **Garuda.** It cancelled all flights to and from CGK, BDO and TKG until 24:00 WIB on 7 Sep. Passengers could reschedule free or take a full refund via the contact centre, a sales office or the original agent. Flights resumed in stages "after each airport is declared operational". [C: https://www.rctiplus.com/news/detail/ekonomi/5467806/garuda-indonesia-batalkan-semua-penerbangan-jakarta--bandung-dan-lampung-hingga-senin-malam]
- **Kualanamu.** 20 flights to CGK/HLP were cancelled. [S: https://www.rctiplus.com/news/detail/nasional/5467211/terimbas-erupsi-gunung-anak-krakatau--20-penerbangan-kualanamu-jakarta-dibatalkan]
- **Not found.** No source gave diversion destinations, so which alternates airlines actually used is UNVERIFIED.

### 1.2 Bali, Lewotobi Laki-laki (2024–2025)

- **Nov 2024.**
  - Ngurah Rai's general manager said 80 flights were cancelled 4–12 Nov. [S: via https://says.com/my/news/flights-in-bali-cancelled-after-mount-lewotobi-s-volcanic-eruption]
  - On 13 Nov, Jetstar and Virgin Australia cancelled all Denpasar flights. Qantas only "disrupted" flights and notified customers directly. AirAsia also cancelled. [C: https://www.aljazeera.com/economy/2024/11/13/airlines-cancel-bali-flights-after-volcano-spews-ash-miles-into-the-sky]
  - Bali airport said airlines were giving passengers refund, reschedule or reroute options. [S: Garuda/Lewotobi search]
  - Labuan Bajo (Komodo) had all departures cancelled again on 10 Nov. [S: https://ekonomi.bisnis.com/read/20241110/98/1814688/imbas-erupsi-lewotobi-seluruh-penerbangan-dari-bandara-komodo-kembali-dibatalkan]
- **17–18 Jun 2025: the airport stayed open but flights were cancelled anyway.**
  - By 16:00 WITA, 87 flights were affected (66 international, 21 domestic).
  - The airport did not close. A paper test at 15:00 WITA found no ash, and NOTAM A1704/25 said the airport was operating normally.
  - Many airlines cancelled out of caution. The airport opened a helpdesk for refund, reschedule and reroute, and provided water and rest areas. [C: https://www.metrotvnews.com/read/kewCM58J-abu-vulkanik-lewotobi-sampai-bali-87-penerbangan-di-bandara-ngurah-rai-dibatalkan]
- **7 Jul 2025.**
  - 24 cancellations. Jetstar cancelled 16, Virgin Australia 6, and AirAsia 2 to Labuan Bajo.
  - Qantas delayed but did not cancel. The airport said ash did not affect Bali airspace. [S: https://thenightly.com.au/australia/bali-flights-cancelled-as-mount-lewotobi-laki-laki-eruption-causes-holiday-chaos-c-19283750 ; https://mataram.antaranews.com/berita/468229/lewotobi-eruption-24-flights-cancelled-at-bali-airport]
- **2 Aug 2025.** The Bali impact was 6 delays and 1 postponement. At Kupang, 14 routes were cancelled, mostly Wings Air; the Kupang–Ende route was cancelled four times in one day. [C: https://www.cnnindonesia.com/nasional/20250802190607-20-1258014/status-awas-lewotobi-erupsi-18-km-banyak-penerbangan-dibatalkan]
- **Takeaway for the model.** Airlines cancel pre-emptively even when the airport is open. That is why "operator discretion" needs a per-airline decision field.

### 1.3 Bali, Agung (Nov 2017) and Raung (Jul 2015)

- **Agung, Nov 2017.**
  - The Ngurah Rai closure began at 07:00 on 27 Nov and ran 24 h, then was extended. It reopened at 14:28 on 29 Nov when winds pushed ash toward Lombok.
  - Over 400 flights and 59,000 passengers were affected. The Ministry of Transport figure was at least 445 flights cancelled.
  - Jetstar had cancelled flights on the Saturday and Sunday before, while Qantas kept flying.
  - Lombok closed and reopened intermittently. [S: https://bali.antaranews.com/en/berita/123125/grid.html ; https://www.philstar.com/world/2017/11/28/1763294/erupting-volcano-shuts-bali-airport-2nd-day ; https://www.travelpulse.com/news/impacting-travel/bali-airport-reopens-as-volcano-looms]
  - Garuda cancelled 88 flights to Bali. [S: https://wartaekonomi.co.id/read162417/bandara-bali-ditutup-garuda-batalkan-88-penerbangan]
- **Raung, 9–12 Jul 2015.**
  - Airport operator figures: 414 flights and 39,715 passengers affected across 9–12 Jul. [S: https://en.tempo.co/amp/683465/39715-passengers-in-denpasar-affected-by-mt-raungs-eruption]
  - Garuda cancelled 112 flights on 10 Jul, 31 on 11 Jul, and all Denpasar flights on 12 Jul. Full operations resumed around 10:30 on 12 Jul. A third closure came on 22 Jul. [S: search summary, sources include https://www.thejakartapost.com/news/2015/07/11/bali-airport-reopens-after-days-closure-due-ash-cloud-official]

### 1.4 Manado, Ruang (Apr 2024)

- **Closure.** Sam Ratulangi closed 17–18 Apr and reopened 22 Apr at 12:01 WITA, per an ICAO APAC paper snippet; the paper itself returned 403. [S: https://www.icao.int/sites/default/files/APAC/Meetings/2024/2024%20ATMSG-12/4-Information%20Papers/IP08-Contingency-Plan-for-Volcanic-Ash-at-Mount-Ruang-Indonesia.pdf] Closure times differ by source.
- **Cancellations.** Lion Group cancelled 27 flights (Jakarta, Surabaya, Makassar, Ambon, Gorontalo, Kao, Ternate) and said it would "accommodate the requests of affected passengers regarding the change of flight schedules". Three days after the eruption the airport recorded 40 cancellations affecting 5,577 passengers. [C: https://en.tempo.co/read/1858621/mount-ruang-eruption-forces-lion-air-group-to-cancel-27-flights]
- **Official stance.** The airport authority called it force majeure and urged airlines to offer refunds, rebooking or rerouting. [S: https://en.tempo.co/read/1858111/ruang-volcano-eruption-flights-from-soekarno-hatta-airport-to-manado-canceled]

### 1.5 Japan (Sakurajima, KOJ) and Philippines

- **Japan.**
  - 16 Nov 2025: 30 flights cancelled at Kagoshima, ash up to 4.4 km, no airline named. [S: https://www.timeslive.co.za/news/world/2025-11-17-japans-sakurajima-volcano-erupts-ashfall-cancels-flights/]
  - A May eruption cancelled 25 flights, with JAL and Skymark cancelling and one JAL flight diverted mid-route. This is a single source, so UNVERIFIED, and the year was inferred as 2026. [S: https://www.thestandard.com.hk/world/article/302640/Japans-Sakurajima-volcano-erupts-violently-disrupting-flights-and-travel]
  - Kagoshima operations are often possible during eruptions. J-AIR said it landed safely in Jul 2024 and cited the ash's different composition. [S: JAL search result summary]
- **Philippines, Taal, 12–14 Jan 2020.**
  - NAIA was suspended from 18:00 on 12 Jan. Departures resumed at 10:00 on 13 Jan and arrivals at 12:00. Flightradar24 showed nearly 400 cancellations on 13 Jan, and some flights diverted to Clark. [S: https://abs-cbn.com/business/01/12/20/naia-flights-put-on-hold-due-to-taal-ash-explosion]
  - Clark then cancelled 7 regional flights because of ash.
- **Philippines, Kanlaon.**
  - 3–4 Jun 2024: 66 flights grounded and 5,057 passengers affected at 09:45. Cebu Pacific cancelled 14 flights and PAL Express 13. Bacolod-Silay closed in the morning. [S: https://loyaltylobby.com/2024/06/04/massive-eruption-of-mt-kanlaon-volcano-in-the-philippines-affects-regional-flights-observe-cancellations/]
  - Dec 2024: cancellations and diversions to Mactan-Cebu. May 2025: Cebu Pacific precautionary cancellations because of ash in surrounding airspace.
  - CAAP issued temporary flight restrictions up to 11,000 ft around Kanlaon and Taal in Oct 2025. [S: https://tribune.net.ph/2025/10/13/caap-restricts-flights-near-active-volcanoes]

### 1.6 How airlines respond (pattern)

| Response | Evidence |
|---|---|
| Cancel whole airport or region until a stated time | Garuda CGK/BDO/TKG until 24:00 (2026); Jetstar and Virgin all DPS (2024) |
| Cancel then restore in stages after each airport is declared operational | Garuda (2026) |
| Delay instead of cancel | Qantas at DPS (Jul 2025) |
| Divert | CGK 1 domestic diversion (6 Sep 2026); NAIA to Clark (2020); Kanlaon to Mactan-Cebu (2024); JAL mid-route (2026, UNVERIFIED) |
| Free reschedule or full refund | Garuda, Citilink (2026); Lion "accommodate schedule change" (2024) |
| Ferry / tail swap | Not documented publicly in any source I found, so UNVERIFIED as an observed practice |
| Cancel while the airport is open | 18 Jun 2025 Bali: NOTAM said normal, 87 flights affected |

---

## 2. Disruption recovery algorithms

### 2.1 Literature

- **Surveys.**
  - Ball, Barnhart, Nemhauser and Odoni (2007), "Air transportation: Irregular operations and control", is a Handbook of OR chapter.
  - Clausen, Larsen, Larsen and Rezanova (2010), Computers & Operations Research 37:809–821.
  - Hassan, Santos and Vink (2021), Computers & Operations Research 127:105137.
  - [S: via https://www.engineering.org.cn/engi/EN/10.1016/j.eng.2020.08.021 for the Su et al. 2021 review of recovery models]
- **Aircraft recovery model families** [C: https://www.engineering.org.cn/engi/EN/10.1016/j.eng.2020.08.021]:
  - Arc-based time-space networks (Thengvall, Bard and Yu 2000), with discrete delay copies such as 10/30/60 min.
  - Path-based models with column generation.
  - Operations modelled: cancellation, ground delay, swapping and maintenance rescheduling.
- **Reported run times** [C: same URL]:

| Study | Instance | Time |
|---|---|---|
| Vink et al. 2020 | 100 aircraft, 600 flights, selection algorithm | 22 s average (full ILP about 10 min) |
| Aktürk et al. 2014 | 207 flights, 60 aircraft | 196 s |
| Liang et al. 2018 | 638 flights, 44 aircraft | 356 s |
| Thengvall et al. 2001 | 1,434 flights, 12 fleets | 1,838 s |

- **Integrated aircraft-crew-passenger recovery (arXiv 2510.26831, 2025).** [C: https://arxiv.org/html/2510.26831v1]
  - It uses an iterative MILP on a time-space network, then a greedy plus genetic-algorithm stage for passengers.
  - Instance sizes: 608 flights, 85 aircraft, 162 crew groups, and 44k–55k tickets.
  - Per-iteration solve took 34–54 s, and the full run about 9–10 minutes with Gurobi or CBC.
  - Practical lesson: even research systems are minutes, not seconds, at real airline scale.
- **TU Delft** targets under one minute for dynamic aircraft recovery. [S: https://research.tudelft.nl/en/publications/dynamic-aircraft-recovery-problem-an-operational-decision-support]
- **CP-SAT specific.** I found no published airline-recovery CP-SAT benchmark [S]. Greedy heuristics are used in practice, but I found no primary source on their share of practice (UNVERIFIED).

### 2.2 OR-tools / CP-SAT suitability

- **Licence and install.** ortools 9.15.6755 (2026-01-14) is Apache-2.0, with CPython 3.12 wheels for macOS arm64 and manylinux x86-64 and aarch64. `pip install ortools` works. [C: https://pypi.org/project/ortools/]
- **Integer-only.** Scale money to whole dollars and time to minutes. Optional intervals and routing constraints are supported. [S: https://developers.google.com/optimization/reference/python/sat/python/cp_model]

### 2.3 Formulation for 50–150 flights and 20–40 tails (recommended)

**Data.** Flights F with scheduled departure s_f, block b_f, origin, destination and pax_f. Tails K. Turn time T. Maximum delay D, for example 360 min.

**Variables.**
- `skip[f]` is a Bool. True means cancelled.
- `st[f]` is an Int, the departure time.
  - Its domain is [s_f, s_f + D] with closure windows removed. A departure at the closed airport is forbidden in [c0, c1], and an arrival at it is forbidden when st + b falls in the window. This is done with `Domain.from_intervals(...).complement()`, so the closure needs no extra constraints.
  - Cancelled flights are pinned to `st = s_f` so they add no delay cost.
- `tail[f]` is an Int in [0, K-1].
- `fs[f]` is the crew duty start of the chain containing f.
- Arc literals, all passed to `AddMultipleCircuit(arcs)` with depot 0:
  - self-loop `(f,f)` is the cancellation literal;
  - depot to f start arcs `s[k,f]` for tail k, only where the tail's position equals the flight's origin;
  - f to depot end arcs `e[f]`;
  - successor arcs `a[i,j]` with dest_i = orig_j, pruned to successors scheduled within about 3 h of arrival plus the original successor;
  - ferry arcs `(i,j)` for dest_i ≠ orig_j, capped at the 2 nearest-in-time per flight.

**Constraints.**
1. Per arc: `st_j ≥ st_i + b_i + T` (ferry: `+ ferry_block + T`), `tail_j = tail_i`, `fs_j = fs_i`.
2. Start arc for tail k on flight f: `tail_f = k` and `fs_f = st_f − 60` (report time). Each tail has at most one start arc.
3. Crew duty cap on all non-skipped flights: `st_f + b_f + 30 ≤ fs_f + 13·60`. This is planning headroom under CASR 121.472's 14 h (section 3).
4. Maintenance-due tails must end at a maintenance base: for flights whose destination is not one, `e[f] ⇒ tail_f ≠ k`.
5. Airport curfew or operating window is a domain restriction on `st`, same as the closure.

**Objective in USD (integer):**

| Term | Value | Basis |
|---|---|---|
| Delay | per minute: 25 + 0.4 × (0.85 × pax) | Eurocontrol 2022 avg: €17.78/min at-gate, €46.69 taxi, €82.95 en-route [S: https://www.eurocontrol.int/publication/evaluating-true-cost-airlines-one-minute-airborne-or-ground-delay]; A4A values passenger time at $47/h [S: https://www.airlines.org/dataset/u-s-passenger-carrier-delay-costs/]. Mix is my engineering choice, UNVERIFIED. |
| Cancel | pax × 0.85 LF × $85 average fare + $1,500 handling (about $12k at 150 pax) | Placeholder, UNVERIFIED |
| Tail swap | $300 per start arc where the tail differs from the original | Placeholder |
| Ferry | $100 per block minute + $500 | A4A 2024 block-minute $100.76: crew $35.23, fuel $33.06, maintenance $18.30, ownership $10.19 [S: https://www.airlines.org/dataset/u-s-passenger-carrier-delay-costs/] |
| Night-stop | $0 at maintenance bases, $800 at a line station, $1,500 elsewhere | Placeholder |

### 2.4 Greedy heuristic (seed and fallback)

- Keep each flight on its original tail.
- Push each departure past the closure window, and cancel when delay exceeds D, crew FDP is exceeded, or the aircraft is not at the flight's origin.
- This is the warm start via `AddHint`, and also the fallback if CP-SAT returns nothing.
- In my runs the greedy cost on the 30-tail instance was $583k with 41 cancellations.

### 2.5 My measured prototype (synthetic, not the repo's data)

- **Setup.** Seven Indonesian airports, 5–6 legs per tail, DPS closed 10:00–16:00, 8 workers, 10-core Apple Silicon, CP-SAT 9.15. The code is at `<scratch>/cpsat/rec.py`.
- **Results** (seed 2, WIN=120 min successor window, 2 ferry arcs per flight):

| Flights | Tails | Arcs | Result | Time |
|---|---|---|---|---|
| 40 | 10 | 285 | OPTIMAL | 0.05 s |
| 60 | 15 | 462 | OPTIMAL | 0.08–0.21 s |
| 80 | 20 | 693 | OPTIMAL | 0.5–0.8 s |
| 75 | 15 | 674 | OPTIMAL | 1.08 s (FEASIBLE at 1–2 s; the 1–2 s cap was too short) |
| 100 | 25 | 905 | OPTIMAL | 3.65 s (FEASIBLE at 1–2 s, gap about 8%) |
| 150 | 30 | about 1,800 | FEASIBLE only | Bound stayed about 40–50% below the incumbent at 2–5 s |

- **Not validated.** The hint from my greedy was sometimes rejected, because the CP-SAT result at 2 s was occasionally worse than the greedy cost. I did not debug this.
- **Conclusion.** Use a frozen horizon: free only flights departing from now to the closure end plus about 3–4 h, which gives about 40–100 flights. Freeze flights already airborne or departing within about 30 min. Use a 2 s time limit and fall back to the greedy plan if status is not OPTIMAL or FEASIBLE.

---

## 3. Constraints

- **Indonesian crew duty.** CASR 121 Amdt 12, May 2017, Subpart Q. This is the 2017 edition, so UNVERIFIED as current. [C: https://imsis-djpu.dephub.go.id/assets/file/casr/CASR%20Part%20121%20Amdt.%2012%20-%20Certification%20and%20Operating%20Requirements%20Domestic,%20Flag%20and%20Supplemental%20Air%20Carrier.pdf]
  - 121.472(a): flight duty time in any 24 h may not exceed 14 h, or 15 h if the aircraft needs a flight engineer. Flight duty runs from report to termination of flight.
  - 121.472(c): one-pilot augmentation extends to 16 h, with 12 h maximum flight-deck duty and +2 h added to rest.
  - 121.472(d): split duty requires a 4 h rest in suitable accommodation, with the extension capped at 3 h.
  - 121.472(f): for domestic carriers, an unforeseen operational circumstance beyond carrier control allows up to +3 h consecutive. Conditions: crew rest extended by the overrun, crew opinion that safety is not affected, and a PIC report.
  - 121.475: reserve crew need at least 8 h of rest in 24 h, with 24 h notice.
  - 121.481: two-pilot crews may fly 9 h or less in any 24 consecutive hours without a rest period. Limits are 1,050 h per 12 months, 110 h per calendar month and 30 h per 7 days, plus 9 consecutive hours' rest in the 24 h before a flight segment completes.
  - 121.471: relieve the crew from duty for at least 24 consecutive hours in any 7 days.
- **Japan FTL.** I could not retrieve the limits. JCAB sets government upper limits, with carriers specifying lower values. The phase-in of science-based fatigue rules ran from Oct 2019 to Dec 2022. [S: https://www.icao.int/Meetings/a40/Documents/WP/wp_445_en.pdf] The numbers are UNVERIFIED. Make the limits configurable per carrier in data.
- **Minimum turn.** 35–45 min for narrowbody, and 40 min as default, is UNVERIFIED (no primary source found). Make it a per-type, per-airport parameter.
- **Maintenance and night-stop.** Doc 9974 calls for post-encounter inspections, and an AML entry when an ash encounter is actual or suspected. [C: https://www.copac.es/wp-content/uploads/2021/09/ICAO-Guidance-on-Flight-Operations-and-Volcanic-Ash.pdf] Model flagged tails as must-end-at-maintenance-base.
- **Airport curfews.** I did not verify any (DPS, CGK). Default to 24 h open and add an `open_utc/close_utc` window per airport. A claim that CGK is 24 h is UNVERIFIED.
- **MEL.** Doc 9974 Appendix 2 lists dispatch-restriction candidates for ash ops: air conditioning packs, engine bleeds, pressurization, electrical distribution, air data computers, standby instruments, navigation, de-icing, engine-driven generators, APU, ACAS, TAWS, autoland and oxygen. [C: copac.es URL above] Add a `mel_ash_restricted` flag on tails.

---

## 4. Passenger rights and notices

### 4.1 Indonesia: PM 89/2015

Read from the BPK PDF by OCR (scanned, so minor OCR errors possible). [C: https://peraturan.bpk.go.id/Download/94165/PM_89_TAHUN_2015.pdf]

- **Pasal 3: categories.**
  - Category 1: 30–60 min delay. 2: 61–120. 3: 121–180. 4: 181–240. 5: over 240. 6: cancellation.
- **Pasal 5: causes.**
  - Airline management factors cover pilot or cabin crew lateness, catering, ground handling, waiting for passengers or connections, and aircraft not ready.
  - **Technical-operational** (5(3)) means airport conditions: the departure or destination airport cannot be used, runway or access disrupted (cracked, flooded, fire), take-off or landing queues or slot time, or refuelling delay.
  - **Weather** (5(4)) lists heavy rain, flood, lightning, storm, fog, **smoke (asap)**, visibility below minimum, and wind above maximum. Volcanic ash is not named. Closure for ash most naturally fits "airport cannot be used" under 5(3)(a).
  - **Other** (5(5)) covers causes outside the other three, for example riots. It is open-ended.
  - 5(6)–(7): the airline must provide an official letter from the relevant agency. That is the airport authority for technical-operational causes and BMKG for weather.
- **Pasal 6(2).** The airline is exempt from compensation liability for delays under 5(3), (4) and (6).
- **Pasal 7(3): notice timing.**
  - Delay: reason and certainty of departure given directly by phone, SMS or announcement no later than 45 min before scheduled departure, or from when the delay is first known.
  - Cancellation: information at least 7 calendar days before the flight.
  - Weather delay: information can be given from when the weather disturbance is known.
  - Reschedule: at least 24 h before the flight.
- **Pasal 8.** The airline must have a GM or Station Manager-level person with full authority at the airport. They must be empathetic, ease re-planning, and help with transfer to other flights or airlines.
- **Pasal 9: compensation.**
  - Category 1: soft drink. Category 2: drink and snack box. Category 3: drink and heavy meal. Category 4: drink, snack box and heavy meal. Category 5: Rp 300,000 cash.
  - **Category 6 (cancellation):** transfer to the next flight or refund the full ticket.
  - Categories 2–5: the passenger may be moved to the next flight or take a full refund.
  - Compensation must be given actively by the staff.
- **Pasal 10.**
  - Cash purchases are refunded in cash when the passenger reports.
  - Card purchases are refunded to the card within 30 calendar days.
  - Transfer is at no extra charge, including class upgrades. A class downgrade must refund the difference.
  - For delays over 6 h where the passenger needs lodging, the airline must provide accommodation.
- **Pasal 11.** The airline must have an SOP for delay management in Indonesian, approved by the DG.
- **Interpretation.** Alvin Lie says force majeure means no obligation for meals, drinks or accommodation, and the passenger can still cancel for a full refund. [C: https://katadata.co.id/amp/berita/industri/6aa110265da59/bandara-ditutup-imbas-abu-vulkanik-begini-ketentuan-pembatalan-penerbangan] That reading conflicts with Pasal 10(4)'s lodging duty for delays over 6 h, which Pasal 6(2) does not obviously override. This is unresolved, so expose it as a dispatcher-selected policy.
- **Status.** The government defended the compensation rules in a Constitutional Court judicial review in Jul 2026 (case 190/PUU-XXIV/2026). [S: https://www.gebrak.id/2026/07/pemerintah-pertahankan-aturan.html] I did not check for a ruling, so UNVERIFIED.

### 4.2 Philippines: Air Passenger Bill of Rights (Joint DOTC-DTI AO 1 s.2012)

[S: https://www.moneymax.ph/lifestyle/blog/air-passenger-rights] The primary text was not retrieved, so verify against the official text.
- Cancellation 24 h or more before ETD: the carrier notifies, and the passenger chooses rebook or refund.
- Cancellation under 24 h: the carrier endorses to another carrier at no fare difference.
- Delay of 3+ h not caused by the carrier: refreshments and meals, free calls, texts and emails, and rebook, refund or endorsement.
- Delay of 6+ h caused by the carrier: treated as a cancellation, with additional compensation at least equal to the delayed sector's value.
- Force majeure, safety or security cancellations: full fare refund.
- Compensation is payable within 15 days.

### 4.3 Japan

- I found no statutory compensation regime. ANA states that for flights disrupted by bad weather or natural disasters, extra travel and lodging costs are the customer's own, and only carrier-caused disruption is covered. [S: ANA search result summary of https://www.ana.co.jp/ja/jp/guide/reservation/refund/domestic/irregular_support/]
- Both ANA and JAL give fee-free change (振替) and refund when disruption is expected, regardless of the actual operating status. ANA's mechanism is the "NCF" mark in flight status. [S: same summary]
- JAL domestic: one free change, with later changes under fare rules. Ticket purchased via an agent must be handled through that agent. [S: https://www.jal.co.jp/en/dom/change/irregular_refund.html (403; search summary)]
- JAL and ANA pages do not name volcanic ash explicitly. [S]

### 4.4 Example airline notices

| Airline | Content | URL |
|---|---|---|
| Garuda (Bahasa, 6–7 Sep 2026) | Scope (all CGK/BDO/TKG flights), cut-off 24:00 WIB, "ubah jadwal tanpa biaya tambahan atau full refund sesuai ketentuan", contact centre 0804 1 807 807 / 021 2351 9999, sales office, original agent, staged resumption "setelah masing-masing bandara dinyatakan dapat beroperasi" | https://www.rctiplus.com/news/detail/ekonomi/5467806/garuda-indonesia-batalkan-semua-penerbangan-jakarta--bandung-dan-lampung-hingga-senin-malam [C] |
| Citilink (Bahasa, 2026) | Lists closed airports, free reschedule and full refund | https://industri.kontan.co.id/news/abu-vulkanik-anak-krakatau-ganggu-penerbangan-250-pesawat-batal [C] |
| Lion Group (Bahasa, 2026) | Cancellation scope by brand, safety wording, follows the civil aviation authority's NOTAM notice | https://katadata.co.id/berita/industri/6a9e64e75b0e7/lion-air-group-batalkan-275-penerbangan-halim-dan-soekarno-hatta-hari-ini [S] |
| AirAsia | Tells guests to check flight status in the app and by email; flights cancelled or rescheduled (Jun 2025) | https://thesun.my/malaysia-news/airasia-cancels-reschedules-flights-following-mount-lewotobi-eruption-DO14297848 [S] |
| ANA / JAL (Japanese) | General irregular-operations pages above. I found no volcano-specific JAL or ANA notice. | |

---

## 5. Crew briefing content for ash operations

- **Doc 9974 Appendix 2.** [C: https://www.copac.es/wp-content/uploads/2021/09/ICAO-Guidance-on-Flight-Operations-and-Volcanic-Ash.pdf]
  - Flight planning: a safety risk assessment for flights into forecast-contaminated areas or known-contaminated aerodromes, with the process flexible enough to re-plan at short notice.
  - Departure, destination and alternates: degree of contamination, performance requirements, maintenance considerations, and fuel for rerouting and extended holding.
  - Routing policy: shortest time over or in the area, hazards, and drift-down and emergency descent considerations.
  - Diversion policy: maximum distance from a suitable alternate, availability of alternates outside the contaminated area, and policy after an encounter.
  - Crew SOPs: monitoring ash areas, ATC communications, engine and systems monitoring, recognising ash, in-flight indications, encounter procedure, unreliable airspeed, engine-out and relight, escape routes, and operations to and from contaminated aerodromes.
  - AML entry for any actual or suspected encounter, and confirmation before the next flight that related maintenance is complete.
  - Reporting: VAR for an airborne encounter, post-flight VAR, reporting non-encounters, and a mandatory occurrence report where required.
- **Enhanced flight watch.** Monitor VAA, VAR/AIREP, SIGMET, NOTAM and ASHTAM, and give operations and crews plots of the affected area. [S: copac.es copy]
- **Encounter indicators (Doc 9974 text via an unedited copy).** [S: https://www.preventionweb.net/files/25588_9974unediteden1.pdf, cited through search results; I could not open it directly]
  - Acrid or sulphur smell, haze in the cabin, engine surging, torching or flameout, a white glow at the engine inlet, pitot-fouled airspeed fluctuation, pressurisation changes, and St Elmo's fire.
  - Any one indicator is enough to act.
  - Weather radar cannot detect ash.
- **Actions.** This is a Boeing-based summary on a USGS page, so treat it as UNVERIFIED against any operator QRH: idle thrust if altitude permits, autothrottle off, reverse course or descending 180° turn out of the cloud (do not climb), engine and wing anti-ice on, and air-conditioning packs on. Monitor EGT, and fly attitude and power if airspeed is unreliable. [S: https://volcanoes.usgs.gov/volcanic_ash/ash_clouds_air_routes_recommendations.html] IFALPA and the FAA AIM are consistent on idle thrust and reversing course. [S: https://www.angleofattack.com/aim/chapter-7/7-6-10/] I did not find an Airbus QRH procedure.

---

## 6. Free schedule data and licences

| Source | Licence | Redistribute in public repo? |
|---|---|---|
| OurAirports (airports.csv has id, ident, type, name, lat/lon, elevation, iso_country, iso_region, municipality, scheduled_service, icao_code, iata_code, gps_code, etc.) | Public domain per the project; the GitHub mirror shows the Unlicense. [C: https://github.com/davidmegginson/ourairports-data ; the about page had an expired certificate, so the public-domain wording is [S] via https://ourairports.com/about.html] | Yes |
| VRS standing-data routes | Repo licence is CC0-1.0 [C: https://github.com/vradarserver/standing-data]. The data is built from VRS user submissions and ACARS extraction, so contributor rights are UNVERIFIED. | Likely yes, with that caveat |
| OpenFlights airports/airlines/routes | ODbL plus the Database Contents License. Attribution and share-alike for public derived works are required. The route data is "of historical value only", with updates ceased June 2014. Some airline data may carry GFDL terms. [C: https://openflights.org/data] | Only with attribution and share-alike. Avoid; routes.dat is stale. |

- **VRS route file format.** Files live at `routes/schema-01/<first letter>/<ICAO airline code>-all.csv`, with columns `Callsign,Code,Number,AirlineCode,AirportCodes`. The rows contain no times, for example `GIA101,GIA,101,GIA,WIPP-WIII` or `LNI10,LNI,10,LNI,WIII-WADD`. [C: raw GitHub files, fetched during this session]
- **Use.** VRS gives realistic origin-destination pairs. Block times and departure times must be synthesised. Compute distance from OurAirports coordinates and set block = great-circle km ÷ 750 km/h × 60 + about 25 min (my estimate).

---

## 7. Recommendation for TEPHRA

### 7.1 Architecture

1. A deterministic planner builds plans. A CP-SAT recovery model (section 2.3) takes the closure windows derived from the VA SIGMET and Tokyo/Darwin VAA polygons (inflated by Gemini's widening only), and returns a flight-level plan. The dispatcher approves.
2. **Scenario runs.** Run three scenarios at once: `closure_ends_c1`, `+3h` and `+6h`, because closure end times were repeatedly extended in the real events (CGK 05:30 to 09:30 to 18:00).
3. **Gemini** (about 20 requests/day on the stronger model):
   - one call per scenario to write a rationale paragraph from structured solver output;
   - optional polish of Bahasa or Japanese message text;
   - a validator rejects any output that lacks required template fields or contains numbers not in the input.
4. Offer a "paper-test says no ash but airlines cancelled anyway" toggle in the model: a per-airline `cancel_if_airport_open` flag. The Bali 18 Jun 2025 event showed this behaviour.

### 7.2 Frozen horizon and size

- Free: flights with scheduled departure between now and (closure end + 3–4 h). Frozen: airborne flights and those within 30 min.
- Target 40–100 free flights. Time limit 2 s, 8 workers. Warm start with the greedy plan. If status is not OPTIMAL or FEASIBLE, use the greedy plan and label it "heuristic".

### 7.3 Objective weights (USD, tunable in config)

| Term | Default | Notes |
|---|---|---|
| Delay per minute | 25 + 0.4 × 0.85 × pax | Placeholder mix of Eurocontrol/A4A figures |
| Cancel | 0.85 × pax × 85 + 1,500 | Placeholder |
| Swap per flight | 300 | Placeholder |
| Ferry | 100 per block minute + 500 | A4A 2024 block-minute cost $100.76 |
| Night-stop | 0 / 800 / 1,500 | Maintenance base / line station / other |
| Max delay D | 360 min | Beyond this, cancel |
| Turn | 40 min | UNVERIFIED |
| Crew planning FDP | 13 h hard | Against CASR 121.472's 14 h |

### 7.4 Data files to create for fictional RFA

All files go in the repo as CSV or JSON, committed with synthetic data only.
- **`airports.csv`.** `icao,iata,name,lat,lon,elev_ft,open_utc,close_utc,maint_base,line_station,alt_for` (derived from OurAirports; public domain).
- **`fleet.csv`.** `tail,type,seats,home_base,maint_due_utc,must_end_at,mel_ash_restricted,hours_since_check`. Use 30 A320-family tails split across CGK, SUB and DPS.
- **`flights.csv`.** `flight_no,origin,dest,std_utc,block_min,tail,pax_booked,seats,avg_fare_usd,pair_id,rotation_seq,frozen,status`. Build 120–150 flights by choosing route pairs from VRS Indonesian carrier files, then synthesising bank-structured departure times.
- **`crews.csv`.** `crew_id,role,base,report_utc,fdp_start_utc,flight_time_24h,flight_time_7d,flight_time_28d,reserve`. Start with crew paired to tails. Add a deadhead option later.
- **`pax_itineraries.csv`.** `pnr,flights[],pax,priority,connecting,contact_channel,language`. Use it for reaccommodation: assign to the earliest feasible alternative flight with seats, same-day first.
- **`disruptions.json`.** `notam_id,airport,start_utc,end_utc,source,reason,official_letter_ref`.
- **`policy.json`.** Per-airline flags and the passenger-regime selector: ID, JP or PH, lodging policy, refund channel.

### 7.5 Message templates: required content

**Passenger notice** (Bahasa Indonesia, Japanese and English variants). Fields are drawn from PM 89 Pasal 5–10 and the APBR points above:
- Flight number, date, route, and status (cancelled, delayed or rescheduled).
- Reason in plain words ("volcanic ash, airport closed by NOTAM [id], period [start–end local]") and the official letter reference (Pasal 5(6)–(7)).
- New time, or "next update at HH:MM local".
- Options: free change or rebook with no fare difference, or full refund to the original payment method. Cash refunds are immediate and card refunds within 30 days (Pasal 10). Add the contact channel and the channel through which the ticket was bought.
- Airport assistance: helpdesk location, water and rest area, and lodging only if the policy says so (the Pasal 10(4) conflict above).
- A statement of what is not owed under force majeure ("no cash compensation under PM 89 Pasal 6(2)"), phrased neutrally and reviewed by a human.
- Advice not to travel to the airport if cancelled, timestamp, message version, and an "approved by" line (human approval).
- Timing rules: delay notices at least 45 min before departure or when known, reschedules at least 24 h before, weather causes as soon as known (Pasal 7(3)).

**Crew briefing notice** (ACARS or briefing sheet):
- Current closure window and source (NOTAM/SIGMET/VAA IDs and times), alternates outside the contaminated area, fuel for rerouting and holding, diversion policy, MEL restrictions, and the revised FDP status, including any 121.472(f) extension with PIC report.
- Encounter indicators and the operator's QRH reference. Any wording beyond the Doc 9974 indicator list must be marked "verify against operator QRH".
- Reporting reminders: VAR, AML entry, MOR.

### 7.6 Pitch facts to use

- 5–7 Sep 2026 Java closure: 8 airports, more than 270,000 passengers stranded, 275 Lion Group cancellations in one day, Garuda cancelling all CGK/BDO/TKG until 24:00. [https://kuwaittimes.com/article/49337/world/jakarta-airport-extends-closure-as-volcanic-ash-lingers/ ; https://www.rctiplus.com/news/detail/ekonomi/5467806/garuda-indonesia-batalkan-semua-penerbangan-jakarta--bandung-dan-lampung-hingga-senin-malam]
- Closure end times shifted several times (CGK 05:30 to 09:30, then to 18:00), which is why recovery runs scenarios rather than one plan. [https://bernama.com/bm/news.php?id=2603597]
- Bali Jun 2025: the airport stayed open, yet 87 flights were affected. [https://www.metrotvnews.com/read/kewCM58J-abu-vulkanik-lewotobi-sampai-bali-87-penerbangan-di-bandara-ngurah-rai-dibatalkan]

### 7.7 Unverified or open items

- Japan FTL numbers; airport curfews (DPS, CGK); minimum turn times.
- Whether CASR 121 Amdt 12 (2017) is the current amendment.
- The Constitutional Court ruling on the PM 89 compensation rules.
- Primary text of the Philippine APBR.
- Real diversion airports and any ferry or tail-swap practice in the Sept 2026 CGK event.
- The VRS route data's contributor licensing.
- All USD weights are placeholders until RFA's own numbers exist.
- Prototype timings come from my synthetic instance on a 10-core Mac and will differ on Cloud Run or a free-tier VM.
