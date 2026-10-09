# Replay cases

Each case is a directory `data/replay/<case_id>/` holding real recorded feed responses under `raw/<feed>/` and a `manifest.json` (`tephra.models.ReplayCase`): case id, human label, recording window, region, volcano ids, notes, and for every response its exact URL, fetch time, sha256, status and content type. `ReplaySource` serves the latest response at or before the replay clock for each URL and checks every file's sha256. In REPLAY mode the Wall and the Desk show a permanent banner: "REPLAY: recorded real feeds from <date>".

Record cases with `scripts/record_replay.py`:

- `live`: run the real pollers for N minutes and keep every fresh response.
- `backfill`: rebuild a past window. VA SIGMETs come from aviationweather.gov's `date=` snapshots (30 days of history only); Darwin VAA bulletins come from archive files. Each response is stored under the live poller's URL at the time it describes; the manifest's notes say it was reconstructed.

Cases worth recording now (research/09, research/13):

| Case | Window (UTC) | Why | Deadline |
|---|---|---|---|
| Semeru direction mismatch | 2026-09-23 12:00 – 09-27 06:00 | Every SIGMET MOV SE while 20 VONAs said N/NE at the same times | SIGMET history expires ~2026-10-23 |
| Semeru today | live, daytime WIB | A live SIGMET/VAA vs a "not observed" VONA, with daytime traffic | — |
| Taal 2026-10-08 | 2026-10-08 12:00 – 20:00 | Fully scriptable fallback; Tokyo VAAC with frames | ~2026-11-07 |

The 5–7 Sep 2026 Anak Krakatau closure would be the strongest story, but its SIGMETs have already dropped out of the 30-day history. Use it as the hook in the video, not as a replay.

VONA pages are not recorded by default because MAGMA's robots.txt disallows crawling. Add them only with PVMBG's permission (`--with-vona`).
