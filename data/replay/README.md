# Replay cases

A case is a directory `data/replay/<case_id>/` with a `manifest.json` (`tephra.models.ReplayCase`: case id, label, window, region, volcano ids, notes, and for every response its exact URL, time, sha256, status and content type) and the responses under `raw/<feed>/`. Backfilled responses are named by the start of their sha256 and stored once, however many records point at them. In REPLAY mode the Wall and the Desk show a permanent banner, "REPLAY: recorded real feeds from <date>". The Docker image carries every case with its `raw/` files, so REPLAY works on Cloud Run too.

`ReplaySource` serves, for each exact URL, the latest response at or before the replay clock, or the earliest one when the clock is before all of them, and it checks each file's sha256. Two rules follow from that:

- Every URL in a case needs a response at or before the window start. Otherwise the replay would show a later one early.
- A feed with no responses in a case shows as "not in this replay case". It is absent, not failing.

## Cases

| Case | Window (UTC) | Story | Feeds | Responses, size |
|---|---|---|---|---|
| `anak-krakatau-20260905` | 2026-09-05 06:00 to 09-07 06:00 | Ash to FL500 closes Soekarno-Hatta; the only Krakatau VONA says "not observed" | SIGMET (rebuilt), Darwin VAA, VONA, METAR (rebuilt), winds, ADS-B (rebuilt, two spans) | 5,176, 19 MB |
| `semeru-20260923` | 2026-09-23 12:00 to 09-27 06:00 | Every SIGMET moves the ash SE while 20 VONAs say N/NE | SIGMET, Darwin VAA, VONA, TAF, METAR, winds | 2,833, 17 MB |
| `java-live-20261010` | 2026-10-10 05:59 to 07:29 | Live feeds over Java and Bali by day: Semeru and Anak Krakatau SIGMETs with daytime traffic | as recorded, without NICT frames | 583, 11 MB |

Not recorded yet: Taal 2026-10-08 12:00-20:00 (Tokyo VAAC with frames), which leaves AWC's 30-day history around 7 Nov.

## How cases are built

`scripts/record_replay.py` builds every case. Its docstring and `--help` list every option.

- `live` runs the real pollers (stub LLM, throwaway store) for N minutes and keeps every fresh response.
- `noaaport` streams IEM NOAAPort day files (about 300 MB each, read as a stream and never written to disk). It keeps the VA SIGMET and VAA bulletins, and the South-East Asian METAR and TAF collectives, as JSON lines in a scratch directory. The days given to one `backfill` must be consecutive and complete (only the last may stop early), because a Darwin slot's state at the window start is its last bulletin in them.
- `backfill` rebuilds a window from archives, with every response stored under the URL the live poller requests, at the time it describes:
  - product legs: VA SIGMETs, Darwin VAAs and MAGMA VONA list pages;
  - context legs (`--context`): replay ticks over the window, through a source that logs every URL the pollers ask for, find the exact TAF, METAR, winds and ADS-B URLs (they depend on the active volcanoes, the region and the flights near the cone). Each URL is then filled across the whole window, and probing repeats until nothing is missing. ADS-B is probed every minute inside its spans.
- `probe` runs replay ticks at chosen times and prints the picture: active volcanoes, discrepancies, cones, exposed flights, drafts, and any URL the case lacks.

Pass `--cache-dir` to keep every archive answer (and the decoded heatmap positions) on disk, so a rebuild fetches nothing twice and still works after an archive drops the dates.

### Licence rule

Nothing from `ftp.bom.gov.au` goes into a case. BoM's anonymous FTP terms allow personal or in-organisation use and say "you may not supply that material to any other person". Darwin VAAs therefore come from the IEM NOAAPort archive, the public-domain relay of the same bulletins that NWS serves on tgftp. The recorder refuses any content carrying BoM's copyright footer.

MAGMA is never fetched here, because its robots.txt disallows crawling (research/05). The VONA legs import the list pages the research census saved on 9 Oct 2026, and the poller reads them from their list cards. It asks for each notice's detail page too; those are not in any case, so it falls back to the cards.

### What is real and what is reconstructed

| Leg | Real bytes or rebuilt | Source and licence |
|---|---|---|
| VA SIGMETs, Semeru | real AWC JSON (`date=` snapshots saved hourly by the census) | aviationweather.gov, NWS, public domain |
| VA SIGMETs, Krakatau | **rebuilt**: raw bulletins wrapped in the isigmet JSON fields the parser reads | IEM NOAAPort archive, public domain (bulletins by BMKG and BoM, relayed by NWS) |
| Darwin VAAs | real bulletin text, stored under the tgftp slot of its heading | IEM NOAAPort archive, public domain (bulletins by Darwin VAAC) |
| VONAs | real MAGMA list pages, read from their list cards | MAGMA Indonesia (PVMBG), via the census |
| TAF, METAR, Semeru | real AWC JSON (`date=` history, 30 days) | aviationweather.gov, NWS, public domain |
| METAR, Krakatau | **rebuilt**: IEM ASOS text decoded into AWC's METAR JSON | IEM ASOS archive, public domain |
| Winds | real Open-Meteo answers from its Historical Forecast API, under the live URL | Open-Meteo, CC BY 4.0 ("Weather data by Open-Meteo.com") |
| ADS-B, Krakatau | **rebuilt**: adsb.lol `/v2/point` answers derived from its heatmaps | adsb.lol globe_history, ODbL 1.0 ("Aircraft: adsb.lol"); the derived answers stay ODbL |

How each rebuilt leg is made:

- **isigmet JSON around raw bulletins.** AWC's JSON for early September no longer exists. Each WIIF, WAAF and YMMM VA SIGMET bulletin keeps its exact text in `rawSigmet`, and gets `icaoId`, `firId`, `firName`, `seriesId`, `hazard` (`VA`), `validTimeFrom`/`validTimeTo` (from its VALID group) and `receiptTime` (from its heading or the archive hour). Geometry, levels and movement stay in `rawSigmet` for the parser to read. A SIGMET with a forecast polygon also gets an `F` record, as AWC makes. A `CNL SIGMET` bulletin is listed as a record of its own and ends the SIGMET it cancels at its start, as AWC shortens `validTimeTo`. A list is stored at the window start and after each later arrival.
- **Relayed twice.** NOAAPort carries many bulletins twice, wrapped differently and sometimes with `*` turned into `?`. Copies are merged by their content key (FIR, series, validity and correction for SIGMETs; heading, advisory number and DTG for VAAs). The copy kept has the fewest `?`, then the most text, and counts from the first copy's arrival.
- **Darwin slots.** Each VAA is stored under `tgftp.nws.noaa.gov/data/raw/fv/fvauNN.adrm..txt` for its `FVAUNN ADRM` heading, at the later of its DTG and its arrival. Each slot also keeps its last bulletin before the window, so the replay never shows a slot's first bulletin of the window early. A slot never goes back to an older advisory: NOAAPort sometimes replays a backlog (on 23 Sep 10:00-15:00Z it re-sent Darwin's bulletins of 13-15 Sep), and a bulletin whose DTG is older than one its slot already received is skipped. A slot with a bulletin in the window but none in the streamed days before it gets an empty 204 record at the window start (read as unavailable).
- **METARs from IEM ASOS.** One IEM request covers every catalogue airport. Every 30 min each requested station list gets an AWC-shaped answer holding each station's latest METAR: `icaoId`, `obsTime`, `reportTime`, `rawOb` (IEM's text, without AWC's `METAR`/`SPECI` prefix), `visib` (statute miles as AWC renders them, `6+` for 9999), `wxString`, `clouds`, `vertVis` and `fltCat`, all decoded from the text.
- **Winds.** The live call asks Open-Meteo for `past_hours=1&forecast_hours=24`; the archive is asked for the same fields over the same hours as `start_hour`/`end_hour`, hourly. The answer has the live shape and `parse_winds` reads it unchanged (`tests/test_record_replay.py`). These are short-range model runs stitched together, not the forecast that was current then.
- **ADS-B from heatmaps.** adsb.lol's half-hour heatmaps (`globe_history/YYYY/MM/DD/heatmap/NN.bin.ttf`, about 18-30 MB each) hold every aircraft's position every 10-20 s. Every 60 s inside a span, each query point the replay requests gets a `/v2/point` answer listing each aircraft whose latest position in the last 60 s is inside the radius. `hex`, `flight`, `lat`, `lon`, `alt_baro` (25 ft steps; the heatmap falls back to geometric altitude when baro is missing) and `gs` come from the heatmap. `track` is derived from successive positions (the bearing from a position 20-180 s earlier), and `seen_pos`/`seen` from the position's age. `type`, registration and selected altitude are absent. Outside the spans each point holds an empty 204 record, so ADS-B shows as failing rather than freezing or leaking positions. Receiver coverage over the Java Sea has gaps of one to seven minutes, so some flights drop out and come back, as they would have live.

## `anak-krakatau-20260905`

The eruption began on 4 Sep at 16:50Z. Soekarno-Hatta (CGK) closed by NOTAM A3341/26 at 18:30Z on 5 Sep, and METARs at WIII show VA from then. In the window: 81 WIIF/WAAF/YMMM VA SIGMET bulletins (8 of them CNL), 51 Darwin bulletins (Krakatau 2026/174-194), 23 VONA list pages, and METARs, winds and ADS-B under the URLs the pollers request.

Gaps, also in the manifest notes:

- IEM's NOAAPort archive holds nothing between 18:00Z and 20:00Z on 5 Sep, so SIGMETs and VAAs issued then are missing. Of Darwin's Krakatau run 2026/171-203, only 2026/180 (about 18:30Z) is missing, and Dukono 2026/715.
- ADS-B covers two spans: 5 Sep 10:00Z-19:30Z, while traffic was still flying into the ash, and 6 Sep 00:30Z-01:30Z (21 heatmaps, 452 MB downloaded once). Outside them the case has no aircraft.
- MAGMA's only Krakatau notice in the window (#22575, RED) says ash was not observed.
- TAF and Tokyo VAAC are not in the case.

What the replay shows (stub LLM, probed with `probe --from 2026-09-05T06:00Z --every 1`):

- Active: Anak Krakatau, Semeru, Ili Lewotolok, Dukono and Ibu, each with a SIGMET and a Darwin VAA.
- Anak Krakatau: Darwin VAA 2026/176 and WIIF SIGMET 16 both carry two areas from the same 10:10Z observation, SFC/FL200 moving south-east and SFC/FL500 moving west, and the YMMM SIGMETs carry SFC/FL500 areas to the south-west. So the 30,000 ft difference in tops (ENVELOPE) is between the two layers, not between the products. The RED VONA is hours older than both and could not observe the ash (LAG, never a conflict). The official cone merges the layers and runs FL000-FL500 (`docs/ARCHITECTURE.md`, section 3).
- 5 Sep 10:30Z-10:50Z is the strongest moment: 27 flights are exposed at 10:40Z, and HOLD drafts appear for flights at cruise level minutes from the cloud. GIA315 (FL360) is 11 min from entry at 10:34Z, GIA419 (FL360) 23 min at 10:35Z, HVN791 (FL390) 6 min at 10:39Z, and BTK6401 (FL360) 4 min at 10:46Z.
- After the CGK closure, CTV217 (FL340, 15 min out) at 18:03Z and QFA77 (FL360, 13 min out) at 18:49Z get HOLD drafts.

Rebuild (IEM days 4-8 Sep; days after the window only add later bulletins):

```bash
uv run python scripts/record_replay.py noaaport --out /tmp/np-krakatau \
    --day 2026-09-04 --day 2026-09-05 --day 2026-09-06 --day 2026-09-07 --day 2026-09-08
uv run python scripts/record_replay.py backfill --case anak-krakatau-20260905 --force \
    --label "Anak Krakatau: ash to FL500 closes Jakarta, 5-7 Sep 2026 (reconstructed)" \
    --start 2026-09-05T06:00Z --end 2026-09-07T06:00Z --volcano 262000 \
    --sigmet-source noaaport --noaaport-dir /tmp/np-krakatau \
    --census-dir research/data/census --with-vona \
    --context metar,winds,adsb --metar-source iem \
    --adsb-span 2026-09-05T10:00Z/2026-09-05T19:30Z \
    --adsb-span 2026-09-06T00:30Z/2026-09-06T01:30Z \
    --cache-dir /tmp/rr-cache
uv run python scripts/record_replay.py probe --case anak-krakatau-20260905 \
    --from 2026-09-05T06:00Z --at 2026-09-05T17:30Z --at 2026-09-06T01:00Z
```

## `semeru-20260923`

Rebuilt on 10 Oct 2026. Its Darwin leg used to be BoM FTP copies; those files and records are gone, and the same bulletins now come from IEM's NOAAPort archive (19-27 Sep). In the window: 91 hourly AWC SIGMET snapshots, 72 Darwin bulletins (Semeru 2026/1090-1106, Dukono 788-802, Ibu 1081-1097, Lewotolok 270-284, no gaps), 23 VONA list pages, and TAF, METAR and winds every hour under the URLs the pollers request.

- On 23 Sep 10:00-15:00Z NOAAPort replayed a backlog of Darwin's 13-15 Sep bulletins (36 of them). They are left out of the slots, so each slot keeps Darwin's current advisory; the manifest notes say so.
- FVAU09 and FVAU10 have bulletins in the window but none in the streamed days before it, so each starts with an empty 204 record.
- The data hunt found no aircraft near Semeru on 25 Sep in adsb.lol's archive, so ADS-B is not in this case and shows as "not in this replay case". Tokyo VAAC and satellite frames are absent too.
- The station lists include Philippine and Kyushu airports, because the global isigmet list also names Mayon and Sakurajima.

What the replay shows at 25 Sep 16:00Z (stub LLM): Semeru, Ili Lewotolok, Dukono, Ibu and Sakurajima are active. For Semeru, VONA #22717 (ORANGE, ash to 4,076 m) moves the ash N while SIGMET WAAF 12 and Darwin VAA 2026/1098 say MOV SE 10KT: a DIRECTION_MISMATCH of 135 degrees, a point 15 km N of the vent outside the official polygon, and a LAG of 4 h 54 min. The official cone runs FL000-FL150.

Rebuild (IEM days 20-27 Sep; AWC keeps TAF and METAR history for 30 days, so after about 23 Oct only a `--cache-dir` from an earlier build can rebuild those legs):

```bash
uv run python scripts/record_replay.py noaaport --out /tmp/np-semeru --day 2026-09-20 \
    --day 2026-09-21 --day 2026-09-22 --day 2026-09-23 --day 2026-09-24 \
    --day 2026-09-25 --day 2026-09-26
uv run python scripts/record_replay.py noaaport --out /tmp/np-semeru --day 2026-09-27 --last-hour 6
uv run python scripts/record_replay.py backfill --case semeru-20260923 --force \
    --label "Semeru: SIGMETs move the ash SE while VONAs say N/NE, 23-27 Sep 2026 (reconstructed)" \
    --start 2026-09-23T12:00Z --end 2026-09-27T06:00Z --volcano 263300 \
    --census-dir research/data/census --sigmet-source census --with-vona \
    --noaaport-dir /tmp/np-semeru --context taf,metar,winds --cache-dir /tmp/rr-cache
```

## `java-live-20261010`

Recorded live for 90 min from 05:59Z (13:00 WIB) on 10 Oct 2026 with `live --minutes 90`: every feed's real answers, including Darwin VAAs from tgftp and ADS-B from adsb.lol's API (ODbL 1.0). NICT true-colour frames were removed after recording because NICT's terms allow non-commercial use only; JMA frames (Public Data License 1.0) remain.

The ADS-B answers still carry each aircraft's registration (`r`) and database flags, and include business jets, military, police and light aircraft. `scripts/scrub_adsb.py` removes them: it drops every target whose callsign is not an airline callsign by the app's own rule, or that is flagged military (`dbFlags & 1`), and deletes `r` and `dbFlags` from the targets it keeps (`t` stays, because the type drives fuel and exposure). It rewrites each changed file's sha256 in `manifest.json` and adds a line to the manifest notes. Its default is a dry run; a person runs it with `--write` and commits the result. The original files stay in git history, so publishing this case also needs the FEED-05 history filter (a user step).
