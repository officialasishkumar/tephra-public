# 02 — History and costs of volcanic ash in aviation, 1982–2025 (lens: history)


Method and limits, stated up front:
- I ran 35 web searches (listed in the Search log). The 36th was refused because the session's shared search budget ran out, so some leads could not be followed up. Every remaining check was done by opening known URLs with WebFetch or curl.
- The Smithsonian Global Volcanism Program site (volcano.si.edu) returned "Smithsonian site temporarily unavailable" on 2026-10-10, so its weekly reports could not be opened directly [CONFIRMED: https://volcano.si.edu/volcano.cfm?vn=263280, accessed 2026-10-10].
- ICAO meeting papers on icao.int (VAAC management reports, SIGMET test results) sit behind a Cloudflare challenge that blocked both WebFetch and curl. Their content below comes from search-result snippets only and is tagged REPORTED with "(snippet; page not opened)".
- I did not run gcloud, any Google Cloud tool, or any project code.
- Second check, 2026-10-10: two adversarial verifiers re-checked 14 key claims. Claims that held carry [CONFIRMED-X2: url]; corrected claims carry a "[verified 2026-10-10: ...]" note; see "Verification log (2026-10-10)" at the end.

---

## Bottom line

1. **The problem is real, recurring, and concentrated in the region the entry targets.** Between 2014 and 2025, ash from Indonesian volcanoes shut Java's airports (Kelud 2014), Bali (Raung 2015, Rinjani 2015, Agung 2017), Manado (Ruang 2024) and Maumere, and caused repeated Bali cancellations (Lewotobi 2024–25). Single events cost hundreds of flights and tens of thousands of passengers (Agung 2017: at least 445 flights cancelled and 59,000 travellers affected by 27 Nov, two days before the airport reopened). Sources for each figure are in the table and event notes below.
2. **Official sources disagreeing or going blind is well documented, but nobody has measured how often it happens.** Peer-reviewed work shows large gaps between eruption heights reported from the ground, from aircraft and from satellites (Tupper & Kinoshita 2003; Tupper et al. 2007). It also shows satellites failing to see ash that an airliner actually flew through (Kelut/Kelud 2014, Kristiansen et al. 2015). Event records show observatory and VAAC heights differing by several kilometres (Lewotobi 2024, Sangeang Api 2014; Semeru 2020 is snippet-only and unverified by the second check). I found no study that measures how often VONA, VAA and SIGMET disagree.
3. **After 2010 the rules moved the decision to the operator.** ICAO's EUR/NAT contingency plan says "Operation through any area where volcanic ash is forecast is at the discretion of the operator". ICAO Doc 9974 (2012) builds the operator safety-risk-assessment framework. Both support a dispatcher-centred tool.
4. **The biggest risk to the pitch is not a missing problem.** It is that some "contradictions" are only apparent. Heights may be given above the summit in one product and above sea level in another; ash may sit in different altitude bands; two VAACs may each cover part of the same cloud. Code can resolve these without Gemini. Gemini's role has to be the part that is left over after code has normalised everything. That residue is real: at Lewotobi in November 2024 the summit datum explains only about 1.6 km of a roughly 7 km gap between PVMBG and the Darwin VAAC, so normalisation does not remove the disagreement [verified 2026-10-10: both checks PARTLY; see Lewotobi notes and C1].
5. **Withdrawn: the prior brief's EUR 1.3 billion figure is not wrong.** An earlier draft of this file said it "matches no source". The second check found the opposite. IATA's "more than US$1.7 billion" in lost airline revenue (21 April 2010) is about €1.3 billion at April 2010 rates, and BBC News (21 Apr 2010, via Wikipedia) and the EC JRC "Science for DRM 2020" case study (citing Bolić & Sivčev 2011) both give "€1.3 billion". The UK CAA log records the airlines' own estimate as "in the order of €1.4 billion". Use "about €1.3 bn (IATA: more than US$1.7 bn lost revenue to 20 Apr 2010)" [verified 2026-10-10: both checks PARTLY on K9; https://drmkc.jrc.ec.europa.eu/portals/0/Knowledge/ScienceforDRM2020/Files/supercasestudy_03.pdf]. Do not put "the brief is wrong" in the deck or video; a judge who checks it would find the opposite.

---

## Chronological table

Tags: C = CONFIRMED (I opened it); R = REPORTED (secondary, or a search snippet); U = UNVERIFIED. The full tag with URL is in the event notes below; the table shows only the kind of tag, to keep it readable.

| Date | Volcano (state) | What happened to flights | Numbers | Disagreement / late / missing source documented | Tags |
|---|---|---|---|---|---|
| 24 Jun 1982 | Galunggung (Indonesia) | BA Flight 9, a Boeing 747 at FL370 south of Java, lost all four engines at night, restarted near 13,500 ft and landed at Jakarta Halim | 263 on board, no deaths | No ash warning system existed. The dry ash cloud did not show on weather radar, and it was night | C |
| 13 Jul 1982 | Galunggung | Singapore Airlines 747 shut down three engines in the same area. Indonesia then closed the airspace and rerouted airways | — | Airspace closed only after the second encounter | C |
| 15 Dec 1989 | Redoubt (Alaska, USA) | KLM 867, a 747, lost all four engines 150 miles from the volcano and dropped from 27,900 to 13,300 ft before restart | US$80 million in repairs | Encounter came 10 h after the eruption began | C |
| 1987–1998 | IAVW / VAACs | ICAO adopts the IAVW provisions (1987). Nine VAACs are set up in the 1990s. Their role enters Annex 3 by Amendment 71, applicable 5 Nov 1998 | 9 VAACs | — | C (nine, 1990s), R (1987, 1998) |
| 1953–2009 | Worldwide | USGS compilation of aircraft–ash encounters | 129 incidents; 94 confirmed; 79 with damage; 26 severe; 9 with in-flight engine shutdown; about 2 damaging per year since 1976 | Most damaging encounters within 24 h of ash onset or < 1,000 km from the volcano | C |
| 14 Apr – May 2010 | Eyjafjallajökull (Iceland) | By 18 Apr, commercial flights stopped in the airspace of 23 European countries; over 300 airports (75% of the network) closed | > 100,000 flights cancelled; about 7 million passengers affected (Oxford Economics) or about 10 million (Eurocontrol, via UK CAA and EC JRC); IATA: > US$1.7 bn (about €1.3 bn) lost airline revenue; GDP loss US$4.7 bn in week 1, US$5.0 bn to 24 May | Model-based closure vs airline test flights ("models were wrong" — IATA) | C |
| 21–25 May 2011 | Grímsvötn (Iceland) | Scotland, then northern Germany (Bremen, Hamburg, Berlin) | About 450 flights cancelled in German airspace on 25 May; about 1,200 in total (ATC Network) | Met Office "red zone" vs Ryanair test flight at FL410 and BA test flight that "found nothing". Ryanair's first flight was about 20,000 ft above the forecast ash (altitude-band mismatch); BA reportedly flew 45 min inside the red zone and found nothing (an in-zone null result) | C |
| Jun 2011 | Puyehue-Cordón Caulle (Chile) | Ash circled the southern hemisphere; Australia and New Zealand cancelled flights twice | > 60,000 passengers stranded (mid-June); > 120,000 disrupted (21 Jun); Qantas > 200 cancellations in one day | Airlines took different decisions on the same information: some grounded, others flew "under and around the plume"; Perth airport open while airlines cancelled | C |
| 13–15 Feb 2014 | Kelud/Kelut (Indonesia) | Seven airports plus Cilacap airstrip closed; all Java airports except Jakarta shut | 43 domestic schedules disrupted at Bali alone | A Perth–Jakarta airliner (route from the WMO poster, not the GRL abstract) flew under the main ash cloud and through ash (modelled peak 9 ± 3 mg/m³) that satellite data could not directly observe. AVHRR saw no ash on 15 Feb when IASI did | C |
| 30 May – 2 Jun 2014 | Sangeang Api (Indonesia) | Bima and Darwin airports shut; Darwin reopened by 1 Jun | Darwin flights cancelled > 1 day | Observatory first reported a 3 km plume; the VAAC said 10 km (FL350); satellites 12–14 km | C (NASA), R (3 vs 10 km) |
| 9 Jul – Aug 2015 | Raung (Indonesia) | Bali, Lombok, Banyuwangi, Jember and one more airport closed; Bali shut repeatedly (fourth closure by Aug) | About 250 (AJ, 10 Jul), about 300 Bali (Fri), at least 900 regional (NASA) | Published plume heights differ: 12,460 ft (AP) vs up to 6 km (NASA) | C |
| 3–6 Nov 2015 | Rinjani (Indonesia) | Bali Ngurah Rai, Lombok and Banyuwangi airports closed | 692 flights cancelled or delayed (AP via Inquirer) | — | C (closures), R (692) |
| 21–29 Nov 2017 | Agung (Indonesia) | Some airlines cancelled Australia/NZ flights before the closure; Bali airport closed 26/27 Nov to 7 a.m. 29 Nov; ten alternative airports prepared | At least 445 flights cancelled, 59,000 travellers affected as of the afternoon of Mon 27 Nov (AP, via Fox; a snapshot, not the event total) | Height descriptions differ: 1.5–4 km above summit (Wikipedia) vs ash "reached heights of 30,000 feet" (Fox) | C |
| 22–23 Dec 2018 | Anak Krakatau (Indonesia) | Darwin VAAC: ash SFC/FL550 moving SW 30 kt | — | On 23 Dec 0823Z, mid-event, Darwin VAAC said Tokyo VAAC had taken over its area north of 20°S (reason not stated) | C |
| 12–13 Jan 2020 | Taal (Philippines) | Manila NAIA: all flights suspended; partial reopening 13 Jan | About 240 flights, about 60,000 passengers (Inquirer) | — | C (suspension), R (numbers) |
| 15–20 Jan 2022 | Hunga Tonga–Hunga Ha'apai (Tonga) | Fua'amotu runway buried in 5–10 cm of ash; aid flights repeatedly delayed | — | — | C |
| 11–15 Apr 2023 | Shiveluch (Russia) | Ash drifted over the Bering Sea and into Alaska | 23 Alaska Airlines cancellations by 7 a.m. 13 Apr; > 100 flights cancelled that week | — | C |
| 17–30 Apr 2024 | Ruang (Indonesia) | Manado Sam Ratulangi closed (18 Apr, again 30 Apr); Malaysia Airlines suspended KL–Sabah/Sarawak flights; disruption at Kota Kinabalu, about 1,100 km away | 9 flights affected at first closure (Reuters); at least 7 airports closed by late April (R) | Agency gave ash at 2–2.5 km while flights 1,100 km away were disrupted (no satellite height found) | C, R |
| 3–14 Nov 2024 | Lewotobi Laki-laki (Indonesia) | Jetstar and Virgin Australia cancelled all Bali flights on 13 Nov; AirAsia and some Qantas flights cancelled; Bali airport not reported closed | 80 Bali cancellations 4–12 Nov (Reuters, R) | PVMBG up to 8 km above summit (about 9.6 km a.s.l.) and a plume to 10 km (datum not stated) vs Darwin VAAC some plumes to 16.8 km a.s.l. (7–8 Nov). Datum explains only about 1.6 km of the gap; not matched to the same plume or time | C, R |
| 20–21 Mar 2025 | Lewotobi Laki-laki | Jetstar cancelled Australia–Bali flights; Bali airport still operating (Reuters-reported spokesperson, paraphrased by Al Jazeera) | 7 international cancellations | Airline cancelled while the airport stayed open | C |
| 17–18 Jun 2025 | Lewotobi Laki-laki | Bali: Singapore Airlines, Jetstar, AirAsia (Labuan Bajo) cancellations; Maumere airport closed | At least 32 Bali flights cancelled | Emirates and Etihad flights to Bali ran on schedule the same day | C |
| 7 Jul 2025 | Lewotobi Laki-laki | Qantas, Jetstar and Virgin cancelled several Australia–Bali flights | Ash to 18 km | — | C |
| 7–14 Aug 2025 | Klyuchevskoy (Russia) | KVERT aviation code red; ash to 9.5 km a.s.l. | — | Tokyo VAAC gave SFC/FL270 and noted that VAAC Anchorage issues a separate VAA for "OTHER VA (FL360)" from the same volcano | C |
| 2011–2024 (and Aug 2026) | Etna (Italy) | Repeated Catania closures, usually ≤ 1 day; Aug 2026: hundreds of flights cancelled or rerouted, Malta affected | — | — | R |

---

## Event notes with full evidence tags

### 1982 — BA009 and SQ, Galunggung
- On 24 June 1982, British Airways Flight 9 (Boeing 747-236B G-BDXH), on the Kuala Lumpur–Perth leg of London–Auckland, lost all four engines at FL370 south of Java [CONFIRMED: https://en.wikipedia.org/wiki/British_Airways_Flight_9, accessed 2026-10-10].
- 263 people were on board (248 passengers, 15 crew). Engine four restarted near 13,500 ft and the aircraft landed at Halim Perdanakusuma, Jakarta. My arithmetic puts the altitude lost before restart at about 23,500 ft [CONFIRMED: same URL, accessed 2026-10-10].
- Why the crew had no warning: "Because the ash cloud was dry, it did not appear on the weather radar". The page also says volcanic ash was "not recognized as a risk for jets at that time", and the encounter was at night [CONFIRMED: same URL, accessed 2026-10-10].
- On 13 July 1982 a Singapore Airlines 747 was "forced to shut down three of its engines" in the same area. Only after that did Indonesia close the airspace, reroute airways and set up an ash watch [CONFIRMED: same URL, accessed 2026-10-10].
- Judgement: in the region TEPHRA targets, the first official response came only after a second near-loss in 19 days. That is a historical example of a late official product.

### 1989 — KLM867, Redoubt
- On 15 December 1989 a KLM Boeing 747 "dropped from an altitude of 27,900 feet to 13,300 feet" after all four engines flamed out in ash from Redoubt, "150 miles away". The volcano "had begun erupting 10 hours earlier", and the plane "required $80 million in repairs" [CONFIRMED: https://pubs.usgs.gov/fs/fs030-97, accessed 2026-10-10].
- The same USGS fact sheet says "At least 15 aircraft (including KLM Flight 867) have been damaged since 1980" on North Pacific routes, against about 80 encounters worldwide in that period. The page was last modified in 2004 [CONFIRMED: same URL, accessed 2026-10-10].
- 245 people were on board [REPORTED: https://en.wikipedia.org/wiki/KLM_Flight_867 (snippet; page not opened)]. The aviation colour code was developed during the Redoubt eruption [REPORTED: https://www.uaf.edu/news/archives/news-archives-2010-2021/redoubts-big-impact-30-years-ago.php (snippet; page not opened)].

### 1987–1998 — the IAVW and the nine VAACs
- "As of 2019, there are nine Volcanic Ash Advisory Centers": Anchorage, Buenos Aires, Darwin, London, Montreal, Tokyo, Toulouse, Washington, Wellington. ICAO set them up under the IAVW, and "The centers were set up in the 1990s ... following incidents" including BA9 and KLM867 [CONFIRMED: https://en.wikipedia.org/wiki/Volcanic_Ash_Advisory_Centre, accessed 2026-10-10].
- The ICAO Council adopted the first IAVW amendments to the Annexes and PANS in March 1987, and VAAC responsibilities entered Annex 3 by Amendment 71, applicable 5 November 1998 [REPORTED: https://www.preventionweb.net/news/international-airways-volcano-watch-system-effective-ensuring-safety-air-transport and https://www.icao.int/sites/default/files/Meetings/AMC/MA/2002/cnsmet_sg6/wp16.pdf (snippets; ICAO page returned 403)].
- The Darwin VAAC "have worked in partnership with PVMBG since 1993". From 2018, VONAs on MAGMA were "received in real time (a first for VAAC Darwin)" (letter from the VAAC Darwin manager, 26 February 2018) [CONFIRMED: https://publicadministration.un.org/unpsa/Portals/0/UNPSA_Submitted_Docs/2018/4E384934-AAB8-4FE4-888A-7CE9231FCDF7/VAAC_Darwin_MAGMA_Letter.pdf?ver=2018-02-26-044107-637, accessed 2026-10-10]. Judgement: before MAGMA, Indonesian ground reports reached the VAAC with a delay. The letter implies this but gives no number.

### 1953–2009 baseline — USGS Data Series 545
- "Of the 129 reported incidents, 94 incidents are confirmed ash encounters, with 79 of those having various degrees of airframe or engine damage". "Twenty-six ... involved significant to very severe damage ... including nine encounters with engine shutdown during flight." "Most of the damaging encounters occurred within 24 hours of the onset of ash production or at distances less than 1,000 kilometers from the source volcanoes." [CONFIRMED-X2: https://pubs.usgs.gov/publication/ds545] The data end in 2009; the second check did not look for a newer compilation (search budget exhausted).
- Damaging encounters have averaged about two per year since 1976 [CONFIRMED-X2: https://pubs.usgs.gov/publication/ds545] [verified 2026-10-10: the source-check read "approximately 2 per year" in the abstract].
- USGS and DLR have extended the database to 2010–2016, with an overview in NATO STO proceedings (May 2017); in 2017 a full USGS publication was "in preparation" [CONFIRMED: https://old.wmo.int/aemp/sites/default/files/WMO-IUGG_VASAG-7_Aircraft-VA-encounter-update.pdf, accessed 2026-10-10]. I did not find the 2010–2016 counts.

### 2010 — Eyjafjallajökull
- The eruption began on 14 April 2010. ICAO's "zero tolerance" advice "led directly to a sequence of decisions that reduced air traffic flow ... to a 'zero rate'". "By 18 April, commercial aviation movement through the airspace of 23 European countries had ceased ... Over 300 airports, representing 75% of the European network, closed." (UK CAA, Report of Proceedings, 5 May 2010) [CONFIRMED-X2: https://www.caa.co.uk/media/td4caq0n/teleconferences-log.pdf] The same document says "more than 100,000 flights were cancelled affecting ... around 10 million passengers" (citing Eurocontrol) and "The airlines estimate their losses in the order of €1.4 billion" [verified 2026-10-10: second check].
- How the concentration limits were set. "On 20 April, the aircraft and engine manufacturers determined that their aircraft and engines would tolerate operations in an ash density of 2x10-3g/m3." Before that, the London VAAC had used "a predicted ash density of 2x10-4g/m3 as the limit of the extant 'no fly' zone". European authorities "elected to adopt the 2 x 10-3 limit and to also apply a 60 nautical mile buffer", and added an "Enhanced Procedures Zone" between 2x10-4 and 2x10-3 g/m³ [CONFIRMED-X2: https://www.caa.co.uk/media/td4caq0n/teleconferences-log.pdf].
- In May 2010 a three-zone system ("an inner no fly zone, a time limited zone and an enhanced procedures zone") was introduced. Aircraft could use the time-limited zone "with the approval of their regulatory authorities and engine and airframe manufacturers" (Irish Aviation Authority, 17 May 2010) [CONFIRMED: https://www.iaa.ie/news/2015/11/13/new-updated-safety-zones-announced-by-iaa, accessed 2026-10-10]. The no-fly threshold "moved to 4000 micrograms per cubic meter in May 2010, with time-limited flying allowed between 2000 and 4000" [CONFIRMED: https://www.atc-network.com/atc-news/volcanic-dj-vu-how-well-did-we-do-on-the-second-try, accessed 2026-10-10].
- The formal definitions (EASA SIB 2010-17R4, issued 24 May 2011): Low contamination is > 0.2 × 10⁻³ and ≤ 2 × 10⁻³ g/m³ (cyan). Medium is > 2 × 10⁻³ and < 4 × 10⁻³ g/m³ (grey). High is ≥ 4 × 10⁻³ g/m³ (red) [CONFIRMED: https://ad.easa.europa.eu/blob/SIB_201017R4_Flight_in_Volcanic_Ash.pdf/SIB_2010-17R4_1, accessed 2026-10-10].
- ICAO EUR Doc 019 / NAT Doc 006 Part II (December 2010) defines the Area of High Contamination as "equal to or greater than 4x10-3 g/m3, or areas of contaminated airspace where no ash concentration guidance is available". It states: "These suggested procedures are not intended to establish or confirm a safe level of ash concentration ... Operation through any area where volcanic ash is forecast is at the discretion of the operator." It adds: "All modeled ash concentrations are subject to a level of uncertainty relative to errors in the estimation of the eruption strength" [CONFIRMED-X2: https://www.caa.gov.mk/wp-content/uploads/2019/11/eur-doc-019-nat-006-december-2010.pdf]. Cite it as the December 2010 edition. Later editions of EUR Doc 019 and any later Annex 3 changes (for example quantitative VA information) were not checked, so do not present the 2010 low/medium/high zone wording as current rules [verified 2026-10-10: icao.int and skybrary blocked].
- Costs, IATA (21 April 2010): "cost airlines more than $1.7 billion in lost revenue through Tuesday"; "lost revenues reached $400 million per day" on 17–19 April; "At the worst, the crisis impacted 29% of global aviation and affected 1.2 million passengers a day" [CONFIRMED-X2: https://www.iata.org/en/pressroom/pressroom-archive/2010-press-releases/2010-04-21-01/]. In euros this is about €1.3 billion, the figure the prior brief used [verified 2026-10-10: both checks PARTLY; the quotes are exact, but the earlier claim that they contradict "EUR 1.3 billion" was wrong. BBC, 21 Apr 2010 (via Wikipedia, "Air travel disruption after the 2010 Eyjafjallajökull eruption"): "around €1.3 billion (£1.1 billion, US$1.7 billion)"; EC JRC Science for DRM 2020 super case study 3: "an estimated EUR 1.3 billion loss of revenue for the airlines (Bolić and Sivčev, 2011)"; the USD/EUR rate of about 1.34 is the verifier's recollection, not checked].
- Costs, Oxford Economics, "The Economic Impacts of Air Travel Restrictions Due to Volcanic Ash", "A report prepared for Airbus". It estimates "seven million passengers were affected". Global aviation losses "in the first week tallied US$2.6 billion"; net of deferred travel "US$2.2 billion". "The total impact on global GDP caused by the first week's disruption amounts to approximately US$4.7 billion", rising to "US$5.0 billion lost GDP through 24 May, 2010". For 15–21 April, "more than 100,000 fewer flights traversed European airspace than in the previous week, a 53% fall". Its table gives Europe a net aviation impact of $1,370,066,110 [CONFIRMED-X2: https://controverses.minesparis.psl.eu/public/promo10/promo10_G11/data/documents/Volcanic-Update.pdf (copy of the report)]. Scope caution: the same report also says "Total losses for the aviation industry and destinations in Europe amounted to US$2.2 billion for the week", so US$2.2 bn appears with two different scopes (global net aviation; Europe aviation plus destinations). Name the scope each time. Eurocontrol (via the UK CAA log and EC JRC) puts affected passengers at about 10 million, against Oxford Economics' 7 million; give both or attribute clearly [verified 2026-10-10: second check].
- Eurocontrol STATFOR: 104,000 flights cancelled over the 8-day crisis (48% of expected traffic, peaking at 80% on 18 April), about 10 million passengers, plus about 7,000 more cancellations in May [REPORTED: https://www.eurocontrol.int/archive_download/all/node/10542 (snippet; page returned 403)]. A DLR conference paper put airline losses at €1.5–2.5 billion [REPORTED: https://openpolar.no/Record/ftdlr:oai:elib.dlr.de:95545 (snippet; page not opened)].
- The disagreement on record. IATA: "Airspace was being closed based on theoretical models not on facts." "Test flights by our members showed that the models were wrong." [CONFIRMED-X2: https://www.iata.org/en/pressroom/pressroom-archive/2010-press-releases/2010-04-21-01/]. The CAA report notes "a paucity of credible data on the specific ash densities encountered" [CONFIRMED: CAA URL above, accessed 2026-10-10].

### 2011 — Grímsvötn
- Eurocontrol estimated "approximately 450 flights were cancelled in German airspace, mainly affecting the airports in Bremen, Hamburg and Berlin on 25-May-2011" (CAPA, 26 May 2011). Ryanair asked the UK CAA to "accept that these UK predictions are simply works of fiction" [CONFIRMED: https://centreforaviation.com/news/grimsvtn-volcanic-ash-crisis-eases-103945, accessed 2026-10-10].
- Ryanair flew an empty aircraft from Glasgow Prestwick to 41,000 ft over Inverness, Aberdeen and Edinburgh and reported "no visible volcanic ash cloud". The CAA replied: "We know for definite that the first flight went nowhere near the red zone." BA flew in the red zone for 45 minutes and "found nothing" (Willie Walsh) (Channel 4 FactCheck, 25 May 2011) [CONFIRMED: https://channel4.com/news/factcheck/factcheck-icelandic-roulette-as-airlines-defy-volcanic-ash, accessed 2026-10-10]. The CAA said Ryanair's 41,000 ft "put it 20,000 feet higher than where the Met Office thought the volcanic ash would be" (NATS radar data). Walsh said BA flew "at different altitudes" and sent the filters to a lab; no lab result was found. The CAA had "not looked at" Ryanair's second flight [verified 2026-10-10: both checks PARTLY; BA is sourced to Channel 4 and press coverage, not ATC Network].
- An independent analysis (Metron Aviation, 30 May 2011) explains Ryanair's result. The Met Office forecasts came in "three altitude bands (surface to FL200, FL200-FL350, and FL350-FL550)". The red zones were in the lowest band, and the upper band showed none near the UK, so Ryanair at FL410 matched the forecast for that band. The author counted "about 1200 flights" cancelled. This page mentions only Ryanair, not BA [CONFIRMED (Ryanair part only): https://www.atc-network.com/atc-news/volcanic-dj-vu-how-well-did-we-do-on-the-second-try, accessed 2026-10-10].
- A later analysis found "good agreement with the location and timing of ash-affected areas predicted by the Met Office model" [REPORTED: all-geo.org/volcan01010, "Grímsvötn 2011 (Part 2)", via the second check; not opened by me].
- EASA revised its ash bulletin twice during the event, R3 on 23 May and R4 on 24 May 2011 [CONFIRMED: EASA SIB URL above, accessed 2026-10-10].
- Judgement (revised 2026-10-10): the Ryanair "contradiction" was an altitude-band and track mismatch, not a forecast shown to be wrong. BA's 45-minute in-zone flight is different: by Walsh's account it was an in-zone null result. So the case is one mismatch plus one possible forecast false positive, not "largely" a mismatch. Use it in the pitch as an example of airlines misreading altitude bands, and note that red zones can also over-warn, which cuts both ways for a tool whose cone never shrinks. See Conflicts, C1 and C8.

### 2011 — Puyehue-Cordón Caulle
- In mid-June 2011 VOA reported "More than 60,000 passengers have already been stranded". The page shows a 13 June 2011 photo caption and says the disruption was in its "fourth day Wednesday"; the article's exact date is [UNVERIFIED]. Virgin Australia said the cloud "would be too low to avoid" on Perth flights; Qantas and Jetstar also cancelled Perth; "The Perth airport says it is open and urged passengers to check with airlines" [CONFIRMED: https://voanews.com/a/chilean-volcano-still-causing-widespread-flight-disruptions-123902784/140779.html, accessed 2026-10-10].
- On 21 June 2011, Qantas and Virgin Australia cancelled flights "disrupting the travel plans of more than 120,000 passengers". Qantas expected to be "cancelling in excess of 200 flights on Wednesday". When the cloud first arrived, it caused "some airlines to ground all flights to affected areas while others chose to divert their planes under and around the plume". The cloud base was "below 6,000 metres on Tuesday, lower than last week's floor of 8,100 metres" [CONFIRMED: https://www.aljazeera.com/amp/news/2011/6/21/ash-cloud-grounds-flights-across-australia, accessed 2026-10-10].
- Exact eruption date: [UNVERIFIED] (searched only as part of a combined query).
- Judgement: airlines made different operating decisions on the same public information. Each operator's own judgement was decisive, which is the dispatcher's job that TEPHRA supports.

### 2014 — Kelud (Kelut)
- "Mount Kelut (Indonesia) erupted explosively around 15:50 UT on 13 February 2014." "Modeled ash concentrations along the flight track of a commercial aircraft that encountered the ash cloud indicate that it flew under the main ash cloud and encountered maximum ash concentrations of 9±3 mg m-3, mean concentrations of 2±1 mg m-3 over a period of 10-11 min". "Satellite data could not be used directly to observe the ash cloud encountered by the aircraft, whereas inverse modeling revealed its presence." (Kristiansen, Prata, Stohl, Carn 2015, GRL 42:588–596) [CONFIRMED-X2: https://digitalcommons.mtu.edu/michigantech-p/3343]. The abstract says only "a commercial aircraft" and does not name the route. The stronger hook is that the aircraft "flew under the main ash cloud" (which lidar and inversion put at 16–17 km): the ash it met was below the satellite-visible cloud [verified 2026-10-10: both checks].
- The aircraft was a "Commercial flight from Perth to Jakarta". It "Took off from Perth 02:25 LT", "Encoutered [sic] the ash cloud around 05:10 LT" and "Landed safely in Jakarta 05:50 LT". A slide reads "Satellite ash retrievals troublesome" [CONFIRMED-X2: https://old.wmo.int/aemp/sites/default/files/P-22_KRISTIANSEN.pdf] [verified 2026-10-10: the source-check downloaded the poster and confirmed the route; the recency check could not open the GRL full text. Cite this poster, not the GRL abstract, for "Perth–Jakarta"]. The airline is not named. I did not find an ATSB or KNKT report on it [UNVERIFIED].
- Kylling (2016, AMT 9:2103–2117): the ash "was detectable on 13–14 February in the infrared with the reverse absorption technique", and IASI "observed the ash cloud also on 15 February when AVHRR did not detect any ash signal". Concurrent ice clouds affect detection; best-fitting ash-plus-ice models hold about 12 times less ash than ash-only models [CONFIRMED-X2: https://amt.copernicus.org/articles/9/2103/2016/]. That these limits also apply to a Gemini read of satellite images is our inference, not the paper's claim [verified 2026-10-10].
- Closures. As of 10:00 local on 15 Feb, seven airports were closed (Juanda Surabaya, Adi Sumarmo Solo, Adi Sucipto Yogyakarta, Abdulrahman Saleh Malang, Ahmad Yani Semarang, Husein Sastranegara Bandung) plus Tunggul Wulung airstrip, Cilacap [CONFIRMED: https://en.republika.co.id/berita/n10yzw/seven-airports-closed-due-to-volcanic-ash-from-mt-kelud, accessed 2026-10-10]. "Apart from Jakarta, all airports on the island of Java were completely closed on Friday". Yogyakarta was "blanketed by 2 centimeters of ash", and the eruption sent material "17 kilometers into the air" [CONFIRMED: https://www.thejakartapost.com/news/2014/02/15/mt-kelud-eruption-paralyzes-java, accessed 2026-10-10]. "At least 43 domestic flight schedules at Ngurah Rai airport in Bali have been disrupted" [CONFIRMED: https://jatim.antaranews.com/berita/127089/flights-halted-due-to-mt-kelud-eruption, accessed 2026-10-10].
- Early public height figures differed widely. An EPA photo caption said ash and rocks rose "over 3,000 metre into the air", while the NBC text said "10 miles into the air" [CONFIRMED: https://www.nbcnews.com/news/world/airports-closed-thousands-forced-flee-indonesia-volcano-erupts-n30196, accessed 2026-10-10]. Lidar and inversion put most ash at 16–17 km [CONFIRMED: MTU abstract above].
- Judgement: this is the strongest single piece of APAC evidence for TEPHRA's premise. A scheduled airliner flew through ash at concentrations above the 4 mg/m³ "High" threshold, and satellites could not directly see that ash.

### 2014 — Sangeang Api
- "Ash drifted southeast, shutting down airports in Bima, Indonesia, and Darwin, Australia. Service to Darwin resumed by June 1, but Bima remained shut down as of June 2". A satellite-based tool "estimated that the plume reached an altitude of at least 12 to 14 kilometers" [CONFIRMED: https://science.nasa.gov/earth/earth-observatory/sangeang-api-erupts-83799, accessed 2026-10-10].
- CVGHM's first report put the plume at 3 km, while the first VAAC report, based on satellite and the Indonesian met office, put it at 10 km (FL350) [REPORTED: https://www.sciencedirect.com/science/article/pii/S037702732030113X (snippet; page returned 403)].
- More than 30 flights were cancelled and international flights rerouted [REPORTED: https://gulfnews.com/amp/story/world%2Foceania%2Fvolcanic-ash-halts-flights-to-north-australian-city-1.1341288 (snippet; page not opened)].

### 2015 — Raung
- On 10 July 2015, five airports closed, "causing about 250 flights to be cancelled" and "stranding thousands of holidaymakers"; Garuda cancelled all flights to and from the affected airports [CONFIRMED: https://www.aljazeera.com/news/2015/7/10/five-indonesia-airports-closed-as-volcano-erupts, accessed 2026-10-10].
- On 12 July Bali closed again. "About 300 flights to and from Bali were cancelled Friday". "Australian carriers Jetstar and Virgin said they were cancelling some flights to Bali today, while ... Garuda confirmed all its flights would be axed until 4pm" [CONFIRMED: https://www.malaymail.com/news/world/2015/07/12/volcanic-ash-closes-bali-airport-again-travel-chaos-back/931937, accessed 2026-10-10].
- NASA: "At least 900 airplane flights into and out of Bali and other regional airports were cancelled"; the plume "wafted as high as 6 kilometers (20,000 feet)" [CONFIRMED: https://science.nasa.gov/earth/earth-observatory/eruption-of-raung-volcano-86213, accessed 2026-10-10]. AP: Raung "blasted ash and debris 12,460 feet into the air" [CONFIRMED: https://www.nbcnews.com/news/world/eruption-indonesian-volcano-closes-five-airports-sparks-travel-chaos-n389796, accessed 2026-10-10].
- By August, Bali had closed for the fourth time [REPORTED: https://www.malaymail.com/news/world/2015/08/06/more-travel-misery-from-fourth-bali-airport-closure/947019 (snippet; page not opened)].

### 2015 — Rinjani
- On 4 November 2015, AP reported that ash forced "the closure of two airports and international airlines canceled flights to tourist hotspot Bali, stranding thousands" [CONFIRMED: https://www.foxnews.com/world/volcanic-eruption-forces-closure-of-2-airports-in-indonesia-stranding-thousands-in-bali.print, accessed 2026-10-10].
- In total 692 international and domestic flights were cancelled or delayed over Tuesday–Thursday. Virgin Australia cancelled all Bali flights for two days, and AirAsia said up to 67 Bali flights would not proceed [REPORTED: https://newsinfo.inquirer.net/736862/volcanic-eruption-closes-3-indonesian-airports/amp and https://www.malaymail.com/news/world/2015/11/05/mount-rinjani-volcano-ngurah-rai-airport-shut-for-second-day/999763 (snippets; pages not opened)].

### 2017 — Agung
- In late November 2017 the plume rose "about 1.5–4 km above the summit crater ... leading some airlines to cancel flights bound for Australia and New Zealand". Ngurah Rai was closed on 26 November 2017 [REPORTED: https://en.wikipedia.org/wiki/Mount_Agung (opened 2026-10-10; secondary)].
- "As of Monday afternoon local time, at least 445 flights were canceled and 59 thousand travelers affected. An airport spokesman confirmed those numbers on Tuesday, AP reports." The same article says ash "has reached heights of 30,000 feet" [CONFIRMED-X2: https://www.foxnews.com/travel/tourists-trapped-in-bali-for-a-second-day-as-volcano-threatens-to-spill-over-slopes.amp]. These figures are a snapshot as of the afternoon of Monday 27 Nov 2017, not event totals; the airport stayed closed until 29 Nov, so final numbers are likely higher. No later full-event total was found [verified 2026-10-10: both checks].
- The airport was to stay closed "until 7 a.m. local time on November 29". "Ten alternative airports have been prepared for airlines to divert inbound flights" [CONFIRMED: https://globalnews.ca/news/3884387/bali-volcano-airport-closed-mount-agung-eruption/, accessed 2026-10-10].
- About 120,000 tourists were stranded (AFP) [REPORTED: search snippet citing AFP; source page not identified].

### 2018 — Anak Krakatau (not on the lens list, added because it shows a gap in official cover)
- Darwin VAAC advisory 2018/370 (23 Dec 2018, 1101Z): "OBS VA CLD: SFC/FL550 ... MOV SW 30KT"; source HIMAWARI-8 [CONFIRMED: https://ds.data.jma.go.jp/svd/vaac/data/TextData/2018/20181223_26200000_0370_Text.html, accessed 2026-10-10].
- Earlier that day (0823Z) Darwin had issued a notice: "VAAC TOKYO HAS ASSUMED RESPONSIBILITY FOR ISSUING VAA TO THE VAAC DARWIN AREA OF RESPONSIBILITY NORTH OF LATITUDE 20S" [CONFIRMED: https://ds.data.jma.go.jp/svd/vaac/data/TextData/2018/20181223_99999902_0003_Text.html, accessed 2026-10-10]. Why the handover happened is not stated [UNVERIFIED]. It shows that the responsible centre can change in the middle of a major eruption, which a dispatcher tool must follow.

### 2020 — Taal
- On 12 January 2020, PHIVOLCS said Taal "blasted steam, ash and pebbles up to 10 to 15 kilometers". "All departing and arriving international and domestic flights were suspended 'due to volcanic ash in the vicinity of the airport' and nearby air routes, the Civil Aviation Authority of the Philippines said" [CONFIRMED: https://www.pbs.org/newshour/world/volcano-erupts-near-manila-villagers-flee-airport-shut, accessed 2026-10-10].
- About 60,000 passengers were affected and 240 flights held up. Partial operations resumed on 13 January (departures 10 a.m., arrivals noon) [REPORTED: https://newsinfo.inquirer.net/1212301/naia-resumes-partial-operations-on-jan-13-amid-taal-volcano-eruption/amp (snippet; page behind Cloudflare)].

### 2022 — Hunga Tonga–Hunga Ha'apai
- The Fua'amotu runway was "once buried in five to 10 cm of volcanic ash". Australian and New Zealand military aircraft were ready "for days", but departure was "repeatedly delayed" because ash threatened jets, including by "melting and accumulating in the engines" (Al Jazeera, 19 Jan 2022) [CONFIRMED: https://www.aljazeera.com/news/2022/1/19/tonga-runway-cleared-for-emergency-aid-flights, accessed 2026-10-10].
- I found no record of Wellington VAAC performance problems for this event [UNVERIFIED].

### 2023 — Shiveluch; 2025 — Klyuchevskoy (North Pacific)
- Shiveluch erupted "just after midnight on Tuesday" (11 April 2023) and spread ash over "108,000sq km". KVERT's branch director said "The ash reached 20km" [CONFIRMED: https://www.aljazeera.com/amp/news/2023/4/11/shiveluch-volcano-erupts-in-russia-sending-ash-20km-high, accessed 2026-10-10].
- By 7 a.m. Alaska time on 13 April, Alaska Airlines had cancelled 23 flights and "might need to cancel additional flights" [CONFIRMED: https://cbsnews.com/news/flights-canceled-alaska-russian-volcano-eruption-ash-cloud-shiveluch, accessed 2026-10-10]. "A total of more than 100 flights to, from and within Alaska were canceled this week" (15 April) [CONFIRMED: https://news.yahoo.com/alaska-flights-largely-back-normal-220400582.html, accessed 2026-10-10].
- On 7 August 2025 the Klyuchevskoy aviation code was raised "from orange to red". "Satellite data shows ash rising up to 9.5 km above sea level", and KVERT warned of explosions to 10 km "potentially affecting international and low-flying aircraft" [CONFIRMED: https://www.newsonair.gov.in/russia-raises-aviation-alert-to-red-as-klyuchevskoy-volcano-eruption-intensifies-in-kamchatka, accessed 2026-10-10].
- Tokyo VAAC 2025/107 (14 Aug 2025, 0433Z) reads "OBS VA CLD: SFC/FL270", "AVIATION COLOUR CODE: NIL". Its RMK says "VAAC ANCHORAGE ALSO ISSUES VAA FOR OTHER VA(FL360) FROM THIS VOLCANO" [CONFIRMED: https://www.data.jma.go.jp/vaac/data/TextData/2025/20250814_30026000_0107_Text.html, accessed 2026-10-10]. Judgement: one cloud system, two VAACs, two products at different levels, and a colour-code field reading NIL one week after KVERT went red. A dispatcher has to merge these by hand.
- A 2007 Klyuchevskoy eruption diverted several North Pacific flights [REPORTED: AVO, via search snippet; source page not opened]. Anchorage VAAC issued code red warnings in August 2025 and western Alaska flights were cancelled [REPORTED: https://earthobservatory.nasa.gov/images/154670/ash-streams-from-klyuchevskaya-sopka (snippet; page not opened)].

### 2024 — Ruang
- The agency said the "initial eruption sent an ash column two kilometres (1.2 miles) into the sky, with the second eruption pushing it to 2.5 kilometres". Sam Ratulangi was closed "until at least Thursday evening 'due to the spread of volcanic ash which could endanger flight safety'". Malaysia Airlines suspended KL–Sabah/Sarawak flights on 18 April 2024. There was "significant disruption to flights to and from Kota Kinabalu", which is "just over 1,100 kilometres" from Ruang [CONFIRMED: https://www.aljazeera.com/amp/news/2024/4/18/11000-evacuated-in-northern-indonesia-as-ruang-volcano-erupts, accessed 2026-10-10].
- The ministry reported "nine flights affected so far" (Reuters, 18 April 2024) [CONFIRMED: https://www.deccanherald.com/amp/story/world%2Findonesia-closes-airport-in-manado-due-to-volcano-eruption-2983445, accessed 2026-10-10].
- On 30 April 2024 AirNav closed the airport again over "Ruang volcanic ash", and at least seven airports in the region were closed by late April [REPORTED: https://www.malaymail.com/news/world/2024/04/30/indonesias-ruang-volcano-erupts-again-alert-status-at-highest/131628 (snippet; page returned 403)].
- Judgement: the published observatory height (2–2.5 km) does not fit with disruption 1,100 km away, which implies higher ash. I could not find the VAAC heights because GVP was down and searches had run out [UNVERIFIED].

### 2024–2025 — Lewotobi Laki-laki
- November 2024. GVP weekly report for 6–12 Nov 2024, as quoted by a layperson blog: PVMBG plumes on 7 Nov (1010–1200) "rose as high as 8 km above the summit"; on 8 Nov (1355) a dense plume "rose as high as 10 km", with no datum stated in that sentence; elsewhere "9 km above the summit". "During 7-8 November the Darwin VAAC reported that some of the ash plumes rose as high as 16.8 km (55,000 ft) a.s.l. based on satellite data", and elsewhere "15.2 km (50,000 ft) a.s.l." [REPORTED: https://flighttowonder.com/2024/01/21/guest-videos-indonesias-mount-lewotobi/ (opened 2026-10-10; quotes GVP weekly report 6–12 Nov 2024)]. [verified 2026-10-10: both checks PARTLY. The primary GVP page (WVAR20241106-264180) returned 403 / "temporarily unavailable", so this stays secondary. With a summit of about 1.6 km a.s.l. (verifier's recollection, not checked), 8 km above the summit is about 9.6 km a.s.l., leaving a gap of about 5–7 km to 16.8 km a.s.l. The datum explains only about 1.6 km of it. The two figures are not matched to the same plume or time; most of the gap comes from method and timing (ground visual vs satellite cloud-top).]
- 13 November 2024: Jetstar and Virgin Australia cancelled all Denpasar flights. Jetstar said it is "not safe to operate flights to and from Bali". Qantas reported "disrupted" flights; AirAsia flights were cancelled; PVMBG gave ash "up to 10km". The article does not say the airport closed [CONFIRMED: https://www.aljazeera.com/economy/2024/11/13/airlines-cancel-bali-flights-after-volcano-spews-ash-miles-into-the-sky, accessed 2026-10-10].
- March 2025: the eruption began "at 10:56pm local time on Thursday night"; ash rose "more than 8km". Jetstar cancelled Australia–Bali flights, and "the gateway was still operating despite seven cancelled international flights" [CONFIRMED-X2: https://www.aljazeera.com/news/2025/3/21/indonesian-volcano-sends-ash-cloud-8km-high-some-flights-cancelled]. This is Al Jazeera's paraphrase of what an airport spokesperson told Reuters, not a direct airport quote [verified 2026-10-10].
- June 2025: an "11km" column. "At least 32 flights to and from Bali were cancelled". Singapore Airlines cancelled four Denpasar–Singapore flights. Maumere's Frans Seda airport closed "to ensure the safety of the passengers" (AirNav) [CONFIRMED: https://www.aljazeera.com/news/2025/6/18/dozens-of-bali-flights-cancelled-after-indonesia-volcano-erupts, accessed 2026-10-10]. The same day, "Emirates and Etihad flights from the UAE to Bali were running on schedule" [CONFIRMED: https://gulfnews.com/business/tourism/volcano-eruption-in-indonesia-emirates-etihad-flights-to-bali-unaffected-1.500168017, accessed 2026-10-10].
- 7 July 2025: ash "as high as 18 kilometres", and Australian carriers cancelled several Bali flights [CONFIRMED: https://www.deccanherald.com/world/australian-airlines-cancel-several-flights-from-australia-to-bali-after-volcanic-eruption-3618900, accessed 2026-10-10].
- Judgement (inference, not a source claim): in March 2025 the airport was open while one carrier cancelled, and in June 2025 Gulf carriers flew while Singapore and Australian carriers cancelled. These are decisions made flight by flight and carrier by carrier. Some of the divergence comes from route geometry (westbound Gulf routes avoid ash drifting east), not from disagreement about the ash.

### Etna (repeated)
- "Sometimes, volcanic ash from volcanic eruptions from nearby Mount Etna lead to short-term closures of the airport (usually no more than one day)" [REPORTED: https://en.wikipedia.org/wiki/Catania%E2%80%93Fontanarossa_Airport (opened 2026-10-10)].
- January 2011–February 2012 brought closures "on several occasions". In 2021, ash clouds "over 10 km ... closing Sicilian airports". Catania closed on 4 July 2024 and reopened the next day; on 14 August 2024 there was a 9.5 km ash cloud. In August 2026, "hundreds of flights at Catania-Fontanarossa Airport [were] cancelled or rerouted", Malta flights were affected, and operations resumed on 15 August "after the volcanic aviation alert was downgraded from red to orange" (citing Reuters, 11–15 August 2026) [REPORTED: https://en.wikipedia.org/wiki/Mount_Etna (opened 2026-10-10)].
- Judgement: Etna is the well-instrumented counter-example (INGV observatory, Toulouse VAAC, European concentration rules). Closures there are short and routine, so Etna is not TEPHRA's problem case.

### 2026 checks on prior-pack items (outside the 1982–2025 lens)
- Anak Krakatau, September 2026: the continuous eruption began "at 11:07 p.m. local time on Friday" and lasted "about 25 hours". Soekarno-Hatta was suspended and the closure "extended several times". "At least 373 flights were affected as of 10:35 a.m. Sunday. At Soekarno-Hatta alone, 202 flights were affected, including 167 cancellations." Singapore Airlines and Scoot cancelled [CONFIRMED: https://www.cnbc.com/2026/09/07/flights-canceled-jakarta-airport-anak-krakatau-eruption-disrupts-regional-travel-volcano.html, accessed 2026-10-10]. The pack's mention of Qantas was not in the part I extracted [UNVERIFIED].
- Tokyo VAAC 2026/249, Sakurajima (25 Sep 2026, 1252Z): "ERUPTED AT 20260925/1236Z FL080 EXTD E", then "OBS VA CLD: VA NOT IDENTIFIABLE FM SATELLITE DATA", all forecasts "NOT AVBL", and "NXT ADVISORY: NO FURTHER ADVISORIES" [CONFIRMED: https://ds.data.jma.go.jp/svd/vaac/data/TextData/2026/20260925_28208001_0249_Text.html, accessed 2026-10-10]. The pack's claim that a SIGMET was open at that moment was not checked [UNVERIFIED].
- Darwin VAAC 2026/1081, Ibu (23 Sep 2026, 1419Z), confirms the pack's advisory number. It lists the cloud under "OBS VA CLD: SFC/FL070", yet the remark says "VA NOT IDENTIFIABLE ON SATELLITE IMAGERY. REGULAR GROUND REPORTS INDICATE INTERMITTENT DISCRETE ERUPTIONS ARE ONGOING. HEIGHT AND MOVEMENT BASED ON SATELLITE IMAGERY. VA AREA IS AN ESTIMATED AREA." [CONFIRMED-X2: https://ds.data.jma.go.jp/svd/vaac/data/TextData/2026/20260923_26803000_1081_Text.html] [verified 2026-10-10: both checks. The page is a Tokyo VAAC (JMA) mirror of a Darwin advisory, INFO SOURCE "HIMAWARI-9 CVGHM". The one remark says both "VA NOT IDENTIFIABLE ON SATELLITE IMAGERY" and "HEIGHT AND MOVEMENT BASED ON SATELLITE IMAGERY", and the polygon is labelled OBS although the remark calls it estimated: internal tension in a single official product, and a good fit for an LLM-parsing demo]. The list page shows Dukono 2026/788 the same day, and shows that this mirror holds only advisories issued while Tokyo was backing up Darwin [CONFIRMED: https://ds.data.jma.go.jp/svd/vaac/data/vaac_darwin_list.html, accessed 2026-10-10].

---

## Cost summary

| Event | Measure | Figure | Source tag |
|---|---|---|---|
| KLM867, 1989 | Repair cost, one aircraft | US$80 million | [CONFIRMED: https://pubs.usgs.gov/fs/fs030-97, accessed 2026-10-10] |
| Eyjafjallajökull 2010 | Airline revenue lost to 20 Apr | > US$1.7 billion (about €1.3 bn) | [CONFIRMED-X2: https://www.iata.org/en/pressroom/pressroom-archive/2010-press-releases/2010-04-21-01/] |
| Eyjafjallajökull 2010 | Airlines' own loss estimate | "in the order of €1.4 billion" | [CONFIRMED-X2: https://www.caa.co.uk/media/td4caq0n/teleconferences-log.pdf] |
| Eyjafjallajökull 2010 | Passengers affected | about 7 million (Oxford Economics) vs about 10 million (Eurocontrol) | [CONFIRMED-X2: Oxford Economics PDF below; CAA log above] |
| Eyjafjallajökull 2010 | Peak daily airline revenue loss | US$400 million/day (17–19 Apr) | same |
| Eyjafjallajökull 2010 | Global aviation losses, week 1, gross / net (the report also uses US$2.2 bn for "aviation industry and destinations in Europe"; name the scope) | US$2.6 bn / US$2.2 bn | [CONFIRMED-X2: https://controverses.minesparis.psl.eu/public/promo10/promo10_G11/data/documents/Volcanic-Update.pdf] |
| Eyjafjallajökull 2010 | Europe net aviation impact, week 1 | US$1.37 bn | same |
| Eyjafjallajökull 2010 | Global GDP loss | US$4.7 bn (week 1); US$5.0 bn (to 24 May) | same |
| Eyjafjallajökull 2010 | Airline losses (DLR) | €1.5–2.5 bn | [REPORTED: https://openpolar.no/Record/ftdlr:oai:elib.dlr.de:95545 (snippet)] |
| Agung 2017 | Flights / travellers, snapshot as of Mon 27 Nov afternoon | ≥ 445 / 59,000 | [CONFIRMED-X2: Fox/AP URL above] |
| Raung 2015 | Flights cancelled (regional) | ≥ 900 | [CONFIRMED: NASA URL above] |
| Rinjani 2015 | Flights cancelled or delayed | 692 | [REPORTED: Inquirer AP (snippet)] |
| Puyehue 2011 | Passengers disrupted (one day) | > 120,000 | [CONFIRMED: Al Jazeera 21 Jun 2011 URL above] |
| Anak Krakatau 2026 | Flights affected | ≥ 373 | [CONFIRMED: CNBC URL above] |

What I did not find: any cost figure in money for an Asia-Pacific ash event (Agung, Raung, Kelud, Lewotobi). APAC impact can be stated only as flights and passengers [not found; searches 13, 20, 21, 23, 26–28].

---

## Evidence that official sources contradict each other

TEPHRA's premise is that official sources disagree, arrive late, or are missing, so a model that reads and reconciles them adds value. The record below is grouped by type of failure, and each type gets a strength grade.

### Type A — Heights disagree between ground, air and satellite (grade: STRONG)
- Peer-reviewed. "There is a great variation in reported eruption heights between different observations. There are particular difficulties with the under-reporting of eruption heights from the ground." (Tupper & Kinoshita, SW Pacific) [CONFIRMED: https://un-spider.org/fr/node/4757, accessed 2026-10-10].
- Peer-reviewed, Manam 2004–05 (PNG; Tupper, Itikarai, Richards, Prata, Carn, Rosenfeld 2007, Weather and Forecasting 22(1):175–191): "An unprecedented set of pilot reports were obtained; ground-, air-, and satellite-observed eruption heights differed greatly" [CONFIRMED-X2: https://cris.huji.ac.il/en/publications/facing-the-challenges-of-the-international-airways-volcano-watch-/]. The same abstract says "Satellite postanalysis and satellite CO2 slicing techniques give consistent heights", so the satellite methods agreed with each other [verified 2026-10-10].
- Tupper & Wunderman 2009, "Reducing discrepancies in ground and satellite-observed eruption heights", JVGR 186:22–31, exists as a whole paper on this problem [CONFIRMED (title only): https://avo.alaska.edu/explore/reference/4548, accessed 2026-10-10]. Its content is [UNVERIFIED].
- Event records:
  - Lewotobi 2024: PVMBG up to 8 km above summit (about 9.6 km a.s.l.) vs VAAC 15.2–16.8 km a.s.l.; a gap of about 5–7 km after datum correction, not matched in time [REPORTED: flighttowonder/GVP] [verified 2026-10-10: PARTLY, secondary source only].
  - Sangeang Api 2014: 3 km (CVGHM) vs 10 km (VAAC) vs 12–14 km (satellite tool) [REPORTED: ScienceDirect snippet; CONFIRMED: NASA].
  - Semeru, August 2020: a VONA reported an eruption to 25,000 ft, but "on satellite imagery the activity was observed to 12,000ft" [REPORTED: https://www.icao.int/sites/default/files/APAC/Meetings/2021/2021%20MET%20SG%2025/4-Information%20Papers/IP08_AI.5_AUS_VAAC-Darwin-Management-Report.pdf (snippet; page blocked)] (unverified by second check). The snippet behind search 35 also mentions "VAAC estimated 30,000 ft" and pilot reports, so the VAAC's own estimate may differ from the 12,000 ft satellite figure. Do not quote 25,000 vs 12,000 ft in the deck until the paper is opened in a browser.
  - Raung 2015: 12,460 ft (AP) vs 6 km (NASA) [CONFIRMED].
  - Ruang 2024: 2–2.5 km stated while ash disrupted flights 1,100 km away [CONFIRMED facts; inference mine].
- Sinabung: radar heights exceeded HYSPLIT, and "the direction of volcanic ash distribution is different from Volcanic Observatory Notice for Aviation (VONA) observations" (Heningtiyas et al. 2025) [CONFIRMED: https://journal.ugm.ac.id/ijg/article/view/96391, accessed 2026-10-10].
- Caveat: part of each gap is a matter of reference datum. PVMBG often reports height above the summit; VAACs report above sea level or as flight level. Code can remove that part, but only that part: at Lewotobi 2024 it removes about 1.6 km of a 5–7 km gap. The rest is a real disagreement (method, timing, which plume) that the tool should flag, not claim to resolve [verified 2026-10-10].

### Type B — Satellites miss ash that is there (grade: STRONG)
- Kelut 2014: an airliner flew under the main ash cloud and met ash that "Satellite data could not be used directly to observe" [CONFIRMED-X2: https://digitalcommons.mtu.edu/michigantech-p/3343].
- Kelud, 15 Feb 2014: AVHRR "did not detect any ash signal" while IASI did; ice clouds interfere [CONFIRMED-X2: https://amt.copernicus.org/articles/9/2103/2016/].
- Manam: "A remote lightning detection network could not detect the eruption clouds". "A strategy of gradual advisory cessation at the end of each event generally worked well but failed where numerical modeling and satellite observation were insufficient" [CONFIRMED-X2: https://cris.huji.ac.il/en/publications/facing-the-challenges-of-the-international-airways-volcano-watch-/]. Note that the strategy "generally worked well"; the failures were the exceptions [verified 2026-10-10].
- Current products state the limitation outright: "VA NOT IDENTIFIABLE FM SATELLITE DATA" (Sakurajima 2026/249) and "VA NOT IDENTIFIABLE ON SATELLITE IMAGERY ... HEIGHT AND MOVEMENT BASED ON SATELLITE IMAGERY. VA AREA IS AN ESTIMATED AREA" (Ibu 2026/1081, under an "OBS VA CLD" label) [CONFIRMED-X2 for Ibu: https://ds.data.jma.go.jp/svd/vaac/data/TextData/2026/20260923_26803000_1081_Text.html; CONFIRMED for Sakurajima: JMA URL above].
- Policy response: from 21 March 2024, VAAC Darwin issues VAAs on ground reports with an estimated polygon marked EST rather than OBS, "even if the VA is not yet visible on satellite imagery" [REPORTED: https://www.icao.int/sites/default/files/APAC/Meetings/2025/2025%20MET%20SG29/4-Information%20Papers/IP08-AI.5-AUS-VAAC-MANAGEMENT-REPORT.pdf (snippet; page blocked)]. The Ibu 2026/1081 advisory (ground reports, ash not identifiable, area estimated, yet labelled OBS) may not fit this policy. Check the exact policy wording before calling it non-compliance; see C9.

### Type C — Forecast model vs in-situ observation (grade: MODERATE)
- 2010: IATA said "Test flights by our members showed that the models were wrong" [CONFIRMED]. The CAA noted "a paucity of credible data on the specific ash densities encountered" [CONFIRMED].
- 2011: the Met Office red zone vs Ryanair and BA test flights [CONFIRMED]. Ryanair's first flight was an altitude-band mismatch, about 20,000 ft above the forecast ash (CAA, via Channel 4) [CONFIRMED: ATC Network; Channel 4]. BA reportedly flew 45 minutes inside the red zone and "found nothing" (Walsh, via Channel 4), with no lab result published; a later analysis found the Met Office model broadly matched the observed ash [REPORTED: all-geo.org volcan01010] [verified 2026-10-10: both checks PARTLY].
- Kelud 2014 runs the other way: the model found ash that satellites missed [CONFIRMED].
- Grade reason: well documented, but partly an argument about thresholds and altitude bands rather than about whether ash was present.

### Type D — Products missing, late, or switching hands (grade: MODERATE)
- Semeru, August 2020: a VONA arrived by email "but the VONA didn't appear on the Indonesian Magma/VONA website"; the forecaster issued an urgent initial advisory while waiting for satellite imagery [REPORTED: ICAO MET SG/25 IP08 (snippet)] (unverified by second check; the ICAO PDF returned 403 to both checkers).
- Anak Krakatau, 23 Dec 2018: Darwin handed its area north of 20°S to Tokyo mid-event [CONFIRMED: JMA URLs above].
- Sakurajima 2026/249: an eruption to FL080 was reported, yet the product carries no forecast and "NO FURTHER ADVISORIES" [CONFIRMED].
- APAC SIGMET tests. 2024: MWO Makassar "was not able to participate in the Volcanic Ash SIGMET test" because of volcano activity, and headings and priorities were wrong. 2025: some test messages "have still not been received by all RODBs", and MWO Port Moresby sent test SIGMETs by email [REPORTED: https://www.icao.int/sites/default/files/APAC/Meetings/2025/2025%20METIE%20WG23/3-Working%20Papers/WP15_AI3_JPN_RESULTS-OF-SIGMET-TESTS-2024-TC-and-VA-revision-1.pdf and https://www.icao.int/sites/default/files/APAC/Meetings/2026/2026%20MET-IE%20WG-24/3.%20Working%20Papers/WP10_AI3_JPN_RESULTS-OF-SIGMET-TESTS-2025-TC-AND-VA.pdf (snippets; pages blocked)].
- 1982: Indonesia closed the airspace only after the second 747 encounter [CONFIRMED: BA9 Wikipedia].

### Type E — SIGMET vs VAA mismatch (grade: WEAK–MODERATE; least directly evidenced)
- ICAO's APAC group debated in 2023 "whether MWOs should issue VA SIGMET without VA cloud or not"; "It was advised in the meeting that a SIGMET would not be required". The guidance later recommended issuing a VA SIGMET "in consideration of the case that the eruption cannot be detected by satellite data" [REPORTED: https://www.icao.int/sites/default/files/APAC/Meetings/2023/2023%20MET%20SG%2027/3-Working%20Papers/WP10_AI.4_AHG_UPDATE-TO-REGIONAL-SIGMET-GUIDE.pdf (snippet; page blocked)].
- In the ICAO Middle East region (2025): "there was also a mismatch in the height of the ash being indicated within the SIGMET and what was written in the VAA/VAG" [REPORTED: https://www.icao.int/sites/default/files/MID/MeetingDocs/2025/MET%20capabilities%20and%20MIDANPIRG%20MET%20Sub-Group/Documentation%20-%20MET%20SG13/WP-07.pdf (snippet; page blocked)].
- Judgement: for APAC, ICAO itself treats a SIGMET with no VAA cloud as an open procedural question, so whether a SIGMET exists can vary by MWO. The prior pack's 25 Sep 2026 example (SIGMET open, VAAC silent) fits this pattern, but I could not verify it here.

### Type F — Operators take different decisions on the same information (grade: STRONG for existence)
- Puyehue 2011: "some airlines ... ground all flights ... while others chose to divert their planes under and around the plume"; Perth airport was open while airlines cancelled [CONFIRMED].
- Lewotobi, March 2025: the airport was "still operating" while Jetstar cancelled [CONFIRMED]. June 2025: Emirates and Etihad flew on schedule while Singapore Airlines and Jetstar cancelled [CONFIRMED].
- Raung 2015: Jetstar and Virgin cancelled "some" Bali flights while Garuda cancelled all of them until 4 p.m. [CONFIRMED].

### Overall grade
- **That official sources disagree, go blind or go missing: STRONG.** Three peer-reviewed papers (Tupper & Kinoshita; Tupper et al. 2007; Kristiansen et al. 2015) and one more (Kylling 2016) support it, together with confirmed VAA texts and several event records. The second check (2026-10-10) confirmed Tupper et al. 2007, Kristiansen et al. 2015, Kylling 2016 and the Ibu 2026/1081 text, so the grade stands. The ICAO meeting-paper items (Semeru 2020, the Darwin EST policy, the SIGMET tests) remain snippet-only.
- **How often it happens: NOT ESTABLISHED.** I found no study giving a rate of VONA–VAA–SIGMET disagreement in Indonesia or the APAC region [not found; searches 32–35].
- **That a disagreement directly caused an unsafe or costly decision: WEAK.** The documented APAC encounter (Kelud 2014) was caused by satellites not seeing the ash, not by sources disagreeing. The documented costs come from closures, not from disagreement.
- Net: the evidence supports "official ash information is often uncertain, incomplete and inconsistent, and the dispatcher decides". It supports less well "contradiction is the main hazard". The pitch should lead with gaps and uncertainty, with contradiction as one visible form of them.

---

## Conflicts with our idea

**C1 — Some "contradictions" are only apparent, and code resolves them without Gemini. Grade: MODERATE (was SERIOUS; downgraded 2026-10-10 because the second check showed the residue after normalisation is large).**
- Evidence:
  - Grímsvötn 2011: the Met Office red zone vs Ryanair at FL410 was an altitude-band mismatch; the CAA said the flight was about 20,000 ft above the forecast ash [CONFIRMED: ATC Network; Channel 4]. BA's in-zone flight is not explained this way (see C8).
  - Lewotobi 2024: PVMBG heights above the summit vs VAAC heights above sea level [REPORTED: GVP via flighttowonder]. The datum explains only about 1.6 km of a 5–7 km gap [verified 2026-10-10: PARTLY]. This case now argues against C1: it is a disagreement that normalisation does not remove.
  - Klyuchevskoy 2025: two VAACs cover different levels of the same cloud [CONFIRMED: JMA].
- Why it matters: if the demo shows Gemini "reconciling" a height gap that is a change of datum, a technical judge will say a few lines of code do the same. Equally, a demo that claims to "reconcile" Lewotobi by fixing the datum would overclaim; present it as a disagreement the tool flags after normalisation, not one it resolves.
- What must change: normalise datums (summit vs AMSL vs FL), times, altitude bands and areas of responsibility in deterministic code first, and show that step on screen. Gemini's job starts at what is left:
  - free-text remarks;
  - EST vs OBS meaning;
  - "not identifiable" with a ground report;
  - a missing product;
  - free-text observer reports;
  - deciding which source to trust, and saying why.

**C2 — Satellite detection of ash fails exactly where it matters, so a Gemini read of Band-13 or Dust-RGB inherits the same blind spots. Grade: SERIOUS (for the image step); NONE for the text/geometry spine.**
- Evidence:
  - Kelut 2014: ash that an airliner flew through, under the main cloud, was not directly visible to satellites [CONFIRMED-X2].
  - AVHRR saw no ash signal on 15 Feb 2014 while IASI did, and ash+ice fits carry about 12× less ash than ash-only fits [CONFIRMED-X2]. That this carries over to a Gemini image read is our inference, not the paper's.
  - VAAs routinely say "NOT IDENTIFIABLE" [CONFIRMED; Ibu 2026/1081 CONFIRMED-X2].
- Grade unchanged after the second check (K2, K3, K13 all HOLD).
- What must change:
  - Treat "no ash visible to Gemini" as no information, never as evidence that ash is absent. The design already says the cone never shrinks below the official polygon; extend the same rule to the HYPOTHESIS cone, so a vision miss can never cancel a ground report.
  - Do not claim Gemini sees ash the VAAC cannot.

**C3 — Most money is lost to closure decisions taken by authorities, which a dispatcher tool cannot avoid. Grade: MINOR.**
- Evidence: the 2010 losses came from closures of 23 countries' airspace [CONFIRMED: CAA]; the APAC figures are airport closures (Agung, Kelud, Rinjani, Ruang) [CONFIRMED].
- What must change: TEPHRA's impact claim should be about per-flight decisions:
  - holds and reroutes while airports stay open;
  - cancellations that may not be needed (Lewotobi March 2025, Puyehue 2011);
  - diversions, and time saved in the first hours.
  It should not claim to recover closure costs.

**C4 — 2010 impact figures conflict across sources (the brief's "EUR 1.3 billion" is not one of the problems). Grade: MINOR (fix the attribution). Revised 2026-10-10.**
- Withdrawn: an earlier draft said the brief's "EUR 1.3 billion" was unsupported. It is IATA's "> US$1.7 billion" in euros, given as "€1.3 billion" by BBC (21 Apr 2010) and the EC JRC case study (Bolić & Sivčev 2011) [verified 2026-10-10: both checks PARTLY on K9].
- Evidence of real conflicts: passengers affected, about 7 million (Oxford Economics) vs about 10 million (Eurocontrol, via UK CAA and EC JRC); airline losses, > US$1.7 bn (IATA), "in the order of €1.4 billion" (airlines, via UK CAA), €1.5–2.5 bn (DLR, snippet); Oxford Economics uses US$2.2 bn for two different scopes; the EC JRC cites Oxford Economics for "EUR 3.75 billion" worldwide [CONFIRMED-X2 / REPORTED above].
- What must change: pick one source per number and name its scope, for example "about €1.3 bn (IATA: more than US$1.7 bn lost revenue to 20 Apr 2010)". Do not say the brief was wrong.

**C5 — No documented case was found of a dispatcher harmed by contradictory VONA/VAA/SIGMET specifically. Grade: MINOR.**
- Evidence: not found after 35 searches (searches 32–35 were aimed at this).
- What must change: frame the hook as "official products are often uncertain, estimated or missing in the first hours, when most damaging encounters happen". DS545 shows most damaging encounters fall within 24 h of onset or < 1,000 km from the volcano [CONFIRMED-X2; data end in 2009]. A team-built count of real disagreements from the VONA and VAA archives would turn this into a measured claim.

**C6 — Europe already has quantitative concentration charts and a mature operator risk-assessment regime. Grade: MINOR (it narrows the market).**
- Evidence: EASA SIB 2010-17R4 refers to "London VAAC NWP Volcanic Ash Concentration Charts" [CONFIRMED].
- What must change: keep the APAC focus (Darwin and Tokyo VAAC areas, Indonesian VONAs), where products are mostly qualitative. Etna-style closures in Europe are short and routine [REPORTED: Wikipedia].
- Open since 2026-10-10: whether EUR Doc 019 was revised after December 2010, or ICAO Annex 3 has since added quantitative VA information that APAC VAACs now issue, was not checked (icao.int blocked). If it has, "APAC products are mostly qualitative" weakens. Grade stays MINOR until checked.

**C7 — Some operator divergence comes from route geometry, not from disagreement. Grade: NONE to MINOR.**
- Evidence: Gulf carriers on westbound routes flew while Australian and Singapore carriers cancelled (June 2025) [CONFIRMED].
- What must change: nothing in the design. In the pitch, cite these cases as evidence that decisions are made per flight, not as evidence that sources contradict each other.

**C8 — Forecast red zones can be false positives, so "never shrink" has a cost. Grade: MINOR. Added 2026-10-10.**
- Evidence: Grímsvötn 2011, BA flew about 45 minutes inside the red zone "at different altitudes" and "found nothing" (Walsh, via Channel 4); no lab result was published [CONFIRMED: Channel 4; verified 2026-10-10]. A later analysis found the model broadly right overall [REPORTED: all-geo.org volcan01010].
- Why it matters: TEPHRA's cone may only widen the official area. A judge may ask how the tool avoids adding needless holds on top of an over-warning product.
- What must change: nothing in the safety rules. In the pitch, frame the value as faster, reasoned per-flight decisions and fewer surprise encounters, not as fewer cancellations from narrowing official areas.

**C9 — The Ibu 2026/1081 "OBS vs estimated" tension could be over-read as a VAAC policy breach. Grade: MINOR. Added 2026-10-10.**
- Evidence: the advisory labels the polygon "OBS VA CLD" while its remark says ash is not identifiable on satellite, the area is estimated, and height and movement are "based on satellite imagery" [CONFIRMED-X2]. The Darwin policy of marking ground-report polygons EST from 21 March 2024 is snippet-only [REPORTED].
- What must change: use the advisory as a parsing demo (OBS vs EST vs RMK text) and say "the label and the remark disagree". Do not call it non-compliance until the ICAO MET SG/29 IP08 wording is read.

**C10 — Several supporting claims rest on sources that are blocked. Grade: MINOR (process risk). Added 2026-10-10.**
- Evidence: as of 2026-10-10 the ICAO meeting papers on icao.int (MET SG/25 IP08 for Semeru 2020, MET SG/29 IP08 for the EST policy, MET SG/27 WP10, the SIGMET test results) and skybrary.aero are behind Cloudflare/JS challenges, and volcano.si.edu (GVP) is "temporarily unavailable". Both second-check verifiers hit the same blocks.
- What must change: nothing that rests only on these may appear in the PDF deck or video as verified until someone opens them in a real browser. That covers the Semeru 25,000 vs 12,000 ft example, the Darwin EST policy, the APAC SIGMET test failures, and the Lewotobi GVP quotes (currently from a blog).

No conflict found at FATAL grade: nothing in the history shows the problem is solved, that the feeds are forbidden, or that a human-gated advisory tool is barred. The second check did not change this.

---

## What this supports

1. **The problem recurs in exactly the target region**, with several disruptive Indonesian events in each year listed: 2014 (Kelud, Sangeang Api), 2015 (Raung, Rinjani), 2017 (Agung), 2024 (Ruang, Lewotobi), 2025 (Lewotobi ×3), plus Anak Krakatau in 2018 and 2026 [CONFIRMED, see notes].
2. **The danger window is the first hours near the volcano**: most damaging encounters happen within 24 h of onset or < 1,000 km away [CONFIRMED-X2: DS545, 1953–2009 data]. That is when VONAs are fresh, VAAs are EST, and satellites may not yet see the cloud. TEPHRA's HYPOTHESIS mode (hold/monitor only) is aimed at that window.
3. **The rules put the decision with the operator**:
   - "Operation through any area where volcanic ash is forecast is at the discretion of the operator" [CONFIRMED-X2: EUR Doc 019, December 2010 edition; later editions not checked].
   - ICAO Doc 9974 (2012) assumes "individual operators are responsible for such operations under the oversight of their respective State regulatory authority" [REPORTED: https://www.icao.int:443/publications/Documents/9974_en.pdf (snippet; page not opened)].
   A dispatcher-facing, human-approved advisory fits this structure.
4. **"Never shrink" and "provenance-stamped" match how the official system treats uncertainty**:
   - EUR Doc 019 (December 2010) counts "areas of contaminated airspace where no ash concentration guidance is available" as High [CONFIRMED-X2].
   - VAACs label estimated areas EST, or say "VA AREA IS AN ESTIMATED AREA" [CONFIRMED; Ibu 2026/1081 CONFIRMED-X2]. Ibu 2026/1081 also shows the label and the remark can disagree within one product (OBS label, estimated area), which is exactly the free text a reasoning layer should read.
5. **Airlines visibly decide differently on the same public data** (Puyehue 2011, Raung 2015, Lewotobi 2025) [CONFIRMED]. A per-flight advisory with stated reasons is the natural product.
6. **A real APAC near-miss gives the deck its strongest hook**: a Perth–Jakarta airliner flew under the main Kelut ash cloud and through ash modelled at up to 9 ± 3 mg/m³ (above the 4 mg/m³ "High" line), which satellites could not directly see [CONFIRMED-X2: Kristiansen et al. 2015 for the encounter; WMO P-22 poster for the route; EASA SIB for the threshold].
7. **Event sizes for the deck**:
   - Agung 2017: ≥ 445 flights and 59,000 travellers as of 27 Nov (a snapshot, not the total).
   - Raung 2015: ≥ 900 flights.
   - Rinjani 2015: 692 flights (R).
   - Anak Krakatau 2026: ≥ 373 flights.
   - Eyjafjallajökull 2010: > 100,000 flights, > US$1.7 bn (about €1.3 bn) airline revenue (IATA), US$4.7–5.0 bn GDP (Oxford Economics).

---

## Corrections and confirmations for the prior-work pack

- "2010 ... cost airlines around EUR 1.3 billion": **supported** (corrected 2026-10-10; an earlier draft said "not supported"). It is IATA's > US$1.7 bn in euros, also given by BBC and the EC JRC case study. Add the attribution: "about €1.3 bn (IATA: more than US$1.7 bn lost revenue to 20 Apr 2010)" (see C4).
- "Ruang closed Sam Ratulangi airport on 30 April 2024": **REPORTED only** (Malay Mail snippet; page 403). The 18 April 2024 closure is CONFIRMED (Reuters via Deccan Herald; Al Jazeera).
- "Lewotobi cancelled Bali flights in November 2024 and March 2025": **CONFIRMED** (Al Jazeera, both dates).
- "Anak Krakatau ... at least 373 flights affected": **CONFIRMED** (CNBC). Qantas was not seen in my extract.
- "Darwin VAAC Ibu advisory numbered 2026/1081 and Dukono 2026/788": **CONFIRMED** (JMA backup list); Ibu text **CONFIRMED-X2**. Note that the Ibu advisory itself is an estimated area under an OBS label, and its remark says both "not identifiable on satellite" and "height and movement based on satellite imagery".
- "Tokyo VAAC 2026/249 Sakurajima 'VA NOT IDENTIFIABLE FM SATELLITE DATA'": **CONFIRMED** text. "While a SIGMET was open" was **not checked**.

---

## Open questions

1. How often do VONA, VAA and SIGMET disagree on height, direction or existence for Indonesian volcanoes? No published rate was found. The team could compute one from the MAGMA VONA archive and the Darwin and Tokyo VAA archives, and it would be the most useful original number for the deck.
2. What do the full ICAO APAC papers say? These are MET SG/25 IP08, MET SG/29 IP08 (the EST policy of 21 March 2024), MET SG/27 WP10 (SIGMET without VA cloud), the 2024–2025 SIGMET test results, and MID MET SG13 WP-07. All were blocked by Cloudflare, so their content here is snippet-level only.
3. Which airline flew Perth–Jakarta through the Kelut ash on 14 Feb 2014, and did ATSB or KNKT investigate? Not found.
4. What were the VAAC heights for Ruang (17 and 30 April 2024)? GVP was down and searches had run out.
5. What do Eurocontrol STATFOR's 2010 figures say exactly? The page returned 403, so only snippet figures are used.
6. What does the USGS/DLR 2010–2016 encounter update contain? It would update the "about two damaging encounters per year" figure.
7. What does Tupper & Wunderman (2009) recommend for reducing ground–satellite height gaps? Only the title was confirmed. This may give TEPHRA a published method for its reconciliation step.
8. Were there documented APAC ash encounters in 2017–2025 (Agung, Lewotobi)? Not searched, because the budget ran out.
9. When did Puyehue-Cordón Caulle erupt in 2011, and when did Hunga Tonga erupt in 2022? Only the impact dates were confirmed.
10. Added 2026-10-10 after the second check: Was EUR Doc 019 revised after December 2010, and has ICAO Annex 3 added quantitative VA information that APAC VAACs now issue? (Affects C6.)
11. What was the final Agung 2017 flight and passenger total for the full closure to 29 Nov? Only the 27 Nov snapshot is confirmed.
13. What do the primary GVP weekly report for Lewotobi (6–12 Nov 2024) and the BA filter lab result for Grímsvötn 2011 say? GVP was down; no lab result was found.

---

## Verification log (2026-10-10)

Two adversarial verifiers (a source-check and a recency check) re-checked 14 key claims. Format: claim id: source-check / recency, then the action taken in this file.

- K1 (USGS DS545 counts and the 24 h / 1,000 km finding): HOLDS / HOLDS. Tag set to CONFIRMED-X2; "about 2 per year" upgraded from REPORTED; noted the data end in 2009 and no newer compilation was checked.
- K2 (Kelut 2014 airliner encounter, 9 ± 3 mg/m³, satellites could not observe): HOLDS / HOLDS. CONFIRMED-X2; added "flew under the main ash cloud"; the Perth–Jakarta route is cited to the WMO P-22 poster, not the GRL abstract.
- K3 (Kylling 2016, IASI vs AVHRR, 12× less ash with ice): HOLDS / HOLDS. CONFIRMED-X2; the Gemini-image inference is marked as ours.
- K4 (Tupper et al. 2007, Manam height gaps and advisory cessation): HOLDS / HOLDS. CONFIRMED-X2; added that gradual cessation "generally worked well".
- K5 (Lewotobi Nov 2024, PVMBG vs Darwin VAAC heights): PARTLY / PARTLY. Corrected: the datum explains only about 1.6 km of a 5–7 km gap, the figures are not matched in time, and the source is a blog quoting GVP. Bottom line 4, Type A and C1 revised.
- K6 (Grímsvötn 2011, red zone vs Ryanair and BA): PARTLY / PARTLY. Corrected: Ryanair was an altitude-band mismatch; BA was a reported in-zone null result; BA cited to Channel 4, not ATC Network. C1 revised; C8 added.
- K7 (EUR Doc 019, operator discretion and High-contamination definition): HOLDS / HOLDS. CONFIRMED-X2; cited as the December 2010 edition; later editions and Annex 3 changes not checked.
- K8 (UK CAA proceedings, 23 countries, 300 airports, 2x10-3 vs 2x10-4 g/m³): HOLDS / HOLDS. CONFIRMED-X2; added the airlines' "€1.4 billion" estimate and Eurocontrol's 10 million passengers.
- K9 (IATA > US$1.7 bn, "theoretical models"; claimed contradiction with EUR 1.3 bn): PARTLY / PARTLY. Quotes CONFIRMED-X2; the contradiction claim is withdrawn (Bottom line 5, C4, Corrections).
- K10 (Oxford Economics: 7 million passengers, US$2.2 bn, US$4.7/5.0 bn GDP): HOLDS / HOLDS. CONFIRMED-X2; added the two-scope US$2.2 bn caution and Eurocontrol's 10 million.
- K11 (Agung 2017, 445 flights and 59,000 travellers): HOLDS / HOLDS. CONFIRMED-X2; relabelled as a 27 Nov snapshot, not the event total.
- K12 (Lewotobi Mar 2025, Jetstar cancelled while airport operated): HOLDS / HOLDS. CONFIRMED-X2; "still operating" marked as Al Jazeera's paraphrase of Reuters; "flight by flight" marked as inference.
- K13 (Darwin VAAC 2026/1081 Ibu, OBS label vs "not identifiable" remark): HOLDS / HOLDS. CONFIRMED-X2; added "HEIGHT AND MOVEMENT BASED ON SATELLITE IMAGERY" and the Tokyo-mirror note; C9 added.
- K14 (Semeru Aug 2020 VONA 25,000 ft vs satellite 12,000 ft, ICAO MET SG/25): COULD_NOT_CHECK / COULD_NOT_CHECK. Tag left REPORTED, marked "(unverified by second check)"; not for the deck until the paper is opened.

Limits of the second check: the shared WebSearch budget ran out after 4 queries, so the per-claim recency sweep, the search for competing entries or commercial VAA/VONA/SIGMET reconciliation tools, and the check for post-2010 EUR Doc 019 or Annex 3 changes were not done. icao.int and skybrary.aero were still behind Cloudflare/JS challenges, and volcano.si.edu was "temporarily unavailable" on 2026-10-10.

Conflict grades after the second check: C1 SERIOUS → MODERATE; C2 SERIOUS (image step) unchanged; C3 MINOR unchanged; C4 MINOR, rewritten (EUR 1.3 bn claim withdrawn; now about attributing conflicting 2010 figures); C5 MINOR unchanged; C6 MINOR unchanged, with an open regulatory check; C7 NONE–MINOR unchanged; C8 MINOR (new); C9 MINOR (new); C10 MINOR (new). Still no FATAL conflict.

---

## Sources

All accessed 2026-10-10. "Opened" means fetched with WebFetch or curl; "snippet" means seen only in a search result.

Opened:
- https://en.wikipedia.org/wiki/British_Airways_Flight_9
- https://pubs.usgs.gov/fs/fs030-97
- https://pubs.usgs.gov/publication/ds545
- https://old.wmo.int/aemp/sites/default/files/WMO-IUGG_VASAG-7_Aircraft-VA-encounter-update.pdf
- https://en.wikipedia.org/wiki/Volcanic_Ash_Advisory_Centre
- https://publicadministration.un.org/unpsa/Portals/0/UNPSA_Submitted_Docs/2018/4E384934-AAB8-4FE4-888A-7CE9231FCDF7/VAAC_Darwin_MAGMA_Letter.pdf?ver=2018-02-26-044107-637
- https://WWW.CAA.CO.UK/media/td4caq0n/teleconferences-log.pdf
- https://www.iaa.ie/news/2015/11/13/new-updated-safety-zones-announced-by-iaa
- https://www.atc-network.com/atc-news/volcanic-dj-vu-how-well-did-we-do-on-the-second-try
- https://ad.easa.europa.eu/blob/SIB_201017R4_Flight_in_Volcanic_Ash.pdf/SIB_2010-17R4_1
- https://www.caa.gov.mk/wp-content/uploads/2019/11/eur-doc-019-nat-006-december-2010.pdf
- https://www.iata.org/en/pressroom/pressroom-archive/2010-press-releases/2010-04-21-01/
- https://controverses.minesparis.psl.eu/public/promo10/promo10_G11/data/documents/Volcanic-Update.pdf
- https://centreforaviation.com/news/grimsvtn-volcanic-ash-crisis-eases-103945
- https://channel4.com/news/factcheck/factcheck-icelandic-roulette-as-airlines-defy-volcanic-ash
- https://voanews.com/a/chilean-volcano-still-causing-widespread-flight-disruptions-123902784/140779.html
- https://www.aljazeera.com/amp/news/2011/6/21/ash-cloud-grounds-flights-across-australia
- https://digitalcommons.mtu.edu/michigantech-p/3343
- https://old.wmo.int/aemp/sites/default/files/P-22_KRISTIANSEN.pdf
- https://amt.copernicus.org/articles/9/2103/2016/
- https://so2.gsfc.nasa.gov/pix/special/2014/kelut/Kelut_summary_Feb14_2014.html
- https://en.republika.co.id/berita/n10yzw/seven-airports-closed-due-to-volcanic-ash-from-mt-kelud
- https://www.thejakartapost.com/news/2014/02/15/mt-kelud-eruption-paralyzes-java
- https://jatim.antaranews.com/berita/127089/flights-halted-due-to-mt-kelud-eruption
- https://www.nbcnews.com/news/world/airports-closed-thousands-forced-flee-indonesia-volcano-erupts-n30196
- https://science.nasa.gov/earth/earth-observatory/sangeang-api-erupts-83799
- https://www.aljazeera.com/news/2015/7/10/five-indonesia-airports-closed-as-volcano-erupts
- https://www.malaymail.com/news/world/2015/07/12/volcanic-ash-closes-bali-airport-again-travel-chaos-back/931937
- https://science.nasa.gov/earth/earth-observatory/eruption-of-raung-volcano-86213
- https://www.nbcnews.com/news/world/eruption-indonesian-volcano-closes-five-airports-sparks-travel-chaos-n389796
- https://www.foxnews.com/world/volcanic-eruption-forces-closure-of-2-airports-in-indonesia-stranding-thousands-in-bali.print
- https://en.wikipedia.org/wiki/Mount_Agung
- https://www.foxnews.com/travel/tourists-trapped-in-bali-for-a-second-day-as-volcano-threatens-to-spill-over-slopes.amp
- https://globalnews.ca/news/3884387/bali-volcano-airport-closed-mount-agung-eruption/
- https://thepointsguy.com/news/bali-airport-tpg-stranded/
- https://fortune.com/2017/11/27/bali-volcano-airport-closure-ash-agung
- https://ds.data.jma.go.jp/svd/vaac/data/vaac_darwin_list.html
- https://ds.data.jma.go.jp/svd/vaac/data/TextData/2018/20181223_99999902_0003_Text.html
- https://ds.data.jma.go.jp/svd/vaac/data/TextData/2018/20181223_26200000_0370_Text.html
- https://ds.data.jma.go.jp/svd/vaac/data/TextData/2026/20260923_26803000_1081_Text.html
- https://ds.data.jma.go.jp/svd/vaac/data/TextData/2026/20260923_99999902_0003_Text.html
- https://ds.data.jma.go.jp/svd/vaac/data/TextData/2026/20260925_28208001_0249_Text.html
- https://www.data.jma.go.jp/vaac/data/TextData/2025/20250814_30026000_0107_Text.html
- https://www.pbs.org/newshour/world/volcano-erupts-near-manila-villagers-flee-airport-shut
- https://www.aljazeera.com/news/2022/1/19/tonga-runway-cleared-for-emergency-aid-flights
- https://www.aljazeera.com/amp/news/2023/4/11/shiveluch-volcano-erupts-in-russia-sending-ash-20km-high
- https://cbsnews.com/news/flights-canceled-alaska-russian-volcano-eruption-ash-cloud-shiveluch
- https://news.yahoo.com/alaska-flights-largely-back-normal-220400582.html
- https://www.newsonair.gov.in/russia-raises-aviation-alert-to-red-as-klyuchevskoy-volcano-eruption-intensifies-in-kamchatka
- https://www.aljazeera.com/amp/news/2024/4/18/11000-evacuated-in-northern-indonesia-as-ruang-volcano-erupts
- https://www.deccanherald.com/amp/story/world%2Findonesia-closes-airport-in-manado-due-to-volcano-eruption-2983445
- https://flighttowonder.com/2024/01/21/guest-videos-indonesias-mount-lewotobi/
- https://www.aljazeera.com/economy/2024/11/13/airlines-cancel-bali-flights-after-volcano-spews-ash-miles-into-the-sky
- https://www.aljazeera.com/news/2025/3/21/indonesian-volcano-sends-ash-cloud-8km-high-some-flights-cancelled
- https://www.aljazeera.com/news/2025/6/18/dozens-of-bali-flights-cancelled-after-indonesia-volcano-erupts
- https://gulfnews.com/business/tourism/volcano-eruption-in-indonesia-emirates-etihad-flights-to-bali-unaffected-1.500168017
- https://www.deccanherald.com/world/australian-airlines-cancel-several-flights-from-australia-to-bali-after-volcanic-eruption-3618900
- https://en.wikipedia.org/wiki/Catania%E2%80%93Fontanarossa_Airport
- https://en.wikipedia.org/wiki/Mount_Etna
- https://www.cnbc.com/2026/09/07/flights-canceled-jakarta-airport-anak-krakatau-eruption-disrupts-regional-travel-volcano.html
- https://un-spider.org/fr/node/4757
- https://cris.huji.ac.il/en/publications/facing-the-challenges-of-the-international-airways-volcano-watch-/
- https://avo.alaska.edu/explore/reference/4548
- https://journal.ugm.ac.id/ijg/article/view/96391

Attempted but blocked or unavailable (content used only from snippets, or not at all):
- https://volcano.si.edu/volcano.cfm?vn=263280 (Smithsonian "temporarily unavailable")
- https://www.eurocontrol.int/archive_download/all/node/10542 (403)
- https://www.sciencedirect.com/science/article/pii/S037702732030113X (403)
- https://repository.si.edu/items/f2273b9b-515d-47de-839c-c64acc1921d0 (403)
- https://link.springer.com/10.1007/11157_2016_49 (login redirect)
- https://www.scipedia.com/public/Lechner_et_al_2017a (connection refused)
- https://wmo.int/node/36537 (404)
- https://newsinfo.inquirer.net/1211954/miaa-puts-all-naia-flights-on-hold-after-taal-eruption/ (Cloudflare)
- https://www.malaymail.com/news/world/2024/04/30/indonesias-ruang-volcano-erupts-again-alert-status-at-highest/131628 (403)
- https://www.icao.int/sites/default/files/APAC/Meetings/2021/2021%20MET%20SG%2025/4-Information%20Papers/IP08_AI.5_AUS_VAAC-Darwin-Management-Report.pdf (Cloudflare)
- https://www.icao.int/sites/default/files/APAC/Meetings/2025/2025%20MET%20SG29/4-Information%20Papers/IP08-AI.5-AUS-VAAC-MANAGEMENT-REPORT.pdf (Cloudflare)
- https://www.icao.int/sites/default/files/APAC/Meetings/2023/2023%20MET%20SG%2027/3-Working%20Papers/WP10_AI.4_AHG_UPDATE-TO-REGIONAL-SIGMET-GUIDE.pdf (Cloudflare)
- https://www.icao.int/sites/default/files/APAC/Meetings/2025/2025%20METIE%20WG23/3-Working%20Papers/WP15_AI3_JPN_RESULTS-OF-SIGMET-TESTS-2024-TC-and-VA-revision-1.pdf (Cloudflare)
- https://www.icao.int/sites/default/files/APAC/Meetings/2026/2026%20MET-IE%20WG-24/3.%20Working%20Papers/WP10_AI3_JPN_RESULTS-OF-SIGMET-TESTS-2025-TC-AND-VA.pdf (Cloudflare)
- https://www.icao.int/sites/default/files/APAC/Meetings/2026/2026%20MET%20SG-30/4.%20Information%20Papers/IP03_AI5_AUS-JPN-NZL-USA_COMBINED-APAC-VAAC-MANAGEMENT-REPORT.pdf (Cloudflare)
- https://www.icao.int/sites/default/files/MID/MeetingDocs/2025/MET%20capabilities%20and%20MIDANPIRG%20MET%20Sub-Group/Documentation%20-%20MET%20SG13/WP-07.pdf (snippet only)
- https://www.icao.int/sites/default/files/Meetings/AMC/MA/2002/cnsmet_sg6/wp16.pdf (403)
- https://www.icao.int:443/publications/Documents/9974_en.pdf (snippet only)
- https://www.volcanodiscovery.com/lewotobi/news/300416/vaac-advisory-2026-53.html and https://www.volcanodiscovery.com/ibu/news/287050/vaac-advisory-2025-1285.html (Cloudflare)

Opened by the second-check verifiers (2026-10-10), not by me:
- https://drmkc.jrc.ec.europa.eu/portals/0/Knowledge/ScienceforDRM2020/Files/supercasestudy_03.pdf
- https://en.wikipedia.org/wiki/Air_travel_disruption_after_the_2010_Eyjafjallaj%C3%B6kull_eruption (citing BBC News, 21 Apr 2010)
- all-geo.org/volcan01010, "Grímsvötn 2011 (Part 2)" (exact URL not recorded)

Snippet-only secondary sources cited:
- https://en.wikipedia.org/wiki/KLM_Flight_867
- https://www.uaf.edu/news/archives/news-archives-2010-2021/redoubts-big-impact-30-years-ago.php
- https://www.preventionweb.net/news/international-airways-volcano-watch-system-effective-ensuring-safety-air-transport
- https://openpolar.no/Record/ftdlr:oai:elib.dlr.de:95545
- https://gulfnews.com/amp/story/world%2Foceania%2Fvolcanic-ash-halts-flights-to-north-australian-city-1.1341288
- https://www.malaymail.com/news/world/2015/08/06/more-travel-misery-from-fourth-bali-airport-closure/947019
- https://newsinfo.inquirer.net/736862/volcanic-eruption-closes-3-indonesian-airports/amp
- https://www.malaymail.com/news/world/2015/11/05/mount-rinjani-volcano-ngurah-rai-airport-shut-for-second-day/999763
- https://newsinfo.inquirer.net/1212301/naia-resumes-partial-operations-on-jan-13-amid-taal-volcano-eruption/amp
- https://earthobservatory.nasa.gov/images/154670/ash-streams-from-klyuchevskaya-sopka

---

## Search log

35 WebSearch queries were run. A 36th was refused because the session-wide search budget was exhausted. Modes: 31 standard, 4 extended.

1. British Airways flight 9 1982 Galunggung volcanic ash four engines failed (standard)
2. USGS KLM 867 Redoubt 1989 volcanic ash 747 all four engines $80 million (standard)
3. Guffanti encounters of aircraft with volcanic ash clouds compilation 1953-2009 USGS Data Series 545 (standard)
4. ICAO International Airways Volcano Watch history established nine Volcanic Ash Advisory Centres designated 1993 1997 (standard)
5. Eurocontrol Eyjafjallajokull 2010 flights cancelled 107,000 passengers 10 million eight days (standard)
6. IATA 2010 volcanic ash crisis airline revenue loss $1.7 billion press release (standard)
7. Oxford Economics Airbus "economic impacts of air travel restrictions due to volcanic ash" GDP $4.7 billion (standard)
8. UK CAA 2010 volcanic ash "Time Limited Zone" 4 mg per cubic metre "Enhanced Procedures Zone" 2 mg (standard)
9. Eyjafjallajokull 2010 test flights no ash found Met Office model criticised KLM Lufthansa British Airways test flight (standard)
10. Grimsvotn May 2011 flights cancelled Eurocontrol 900 Ryanair test flight disputed Met Office ash concentration (standard)
11. ICAO EUR Doc 019 volcanic ash contingency plan "Area of High Contamination" 4 x 10-3 g/m3 "Medium Contamination" (standard)
12. Puyehue Cordon Caulle June 2011 ash Qantas Virgin Australia cancelled flights Melbourne Adelaide New Zealand passengers stranded number (standard)
13. Kelud eruption February 2014 seven airports closed Surabaya Yogyakarta Solo Malang Semarang Bandung flights cancelled (standard)
14. ICAO International Volcanic Ash Task Force IVATF 2010 2012 outcome Doc 9974 Flight Safety and Volcanic Ash safety risk assessment operator (standard)
15. Tupper Wunderman 2009 "Reducing discrepancies in ground and satellite-observed eruption heights" (standard)
16. Tupper "Facing the challenges of the International Airways Volcano Watch" Manam 2004/05 eruption not detected satellite (standard)
17. Kelud 2014 volcanic cloud ice-rich split window brightness temperature difference ash not detected Darwin VAAC Kristiansen (standard)
18. Kristiansen 2015 "Kelut" aircraft encounter "inverse modeling revealed its presence" Geophysical Research Letters (standard)
19. Sangeang Api eruption 30 May 2014 Darwin flights cancelled Jetstar Virgin Australia Bali (standard)
20. Raung eruption July 2015 Bali Ngurah Rai airport closed flights cancelled number passengers stranded (standard)
21. Rinjani eruption November 2015 Bali Lombok airport closed flights cancelled Barujari (standard)
22. Raung July 2015 Virgin Australia Jetstar cancelled Bali while Garuda AirAsia continued flying different decisions ash (standard)
23. Agung November 2017 Ngurah Rai airport closed 445 flights cancelled 59,000 passengers (standard)
24. Taal eruption January 2020 NAIA Manila airport suspended flights cancelled number passengers MIAA (standard)
25. Ruang eruption April 2024 Sam Ratulangi airport Manado closed flights cancelled AirNav (standard)
26. Lewotobi Laki-laki November 2024 Bali flights cancelled Jetstar Virgin Australia Qantas airport remained open (standard)
27. Lewotobi eruption July 2025 18 km ash Bali flights cancelled Air India turned back June 2025 (standard)
28. Lewotobi March 2025 eruption Bali flights cancelled Virgin Australia Jetstar ash 8 km (standard)
29. Shiveluch April 2023 eruption ash cloud Alaska Airlines cancelled flights North Pacific (standard)
30. Klyuchevskoy eruption ash North Pacific air routes rerouted flights KVERT aviation code red 2025 (standard)
31. Hunga Tonga January 2022 eruption Fua'amotu airport ash runway relief flights delayed Wellington VAAC (standard)
32. ICAO Asia Pacific volcanic ash SIGMET test results MWO did not issue SIGMET inconsistent with VAA percentage (extended)
33. "VA NOT IDENTIFIABLE FROM SATELLITE DATA" Darwin VAAC observatory reported ash study frequency advisories (extended)
34. VONA Indonesia PVMBG volcano observatory notice for aviation Darwin VAAC discrepancy plume height paper (extended)
35. VAAC Darwin management report Semeru VONA 25,000 ft not on MAGMA website VAAC estimated 30,000 ft pilot reports diffuse IR temperature (extended)
36. (refused: budget exhausted) APAC regional SIGMET guide volcanic ash SIGMET issuance "cannot be detected by satellite" VONA reliable observation MWO should issue VA SIGMET

Not searched because the budget ran out: a dedicated Etna query (covered from Wikipedia instead), ATSB/KNKT ash-encounter investigations, Ruang VAAC heights, the Puyehue eruption date, Hunga Tonga VAAC performance, and APAC ash encounters 2017–2025.
