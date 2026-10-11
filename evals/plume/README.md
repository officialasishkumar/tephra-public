# Plume Reader evaluation

The test that decides whether satellite pictures may enter TEPHRA's decision path, and whether Gemini reconciles the official texts correctly. The protocol, cases and pass criteria come from `research/10-gemini-capability-and-architecture-check.md` (section 5).

| Arm | Input | Label | Pass |
|---|---|---|---|
| I (images) | 3 Ash RGB frames + 1 IR frame from Tokyo VAAC's labelled archive, the vent pixel, the FL180 wind. The advisory text is withheld. | 5 ash and 5 "VA not identifiable" advisories | ≥ 8/10 existence correct with no high-confidence ash on a quiet case; direction within 45° on ≥ 3 detected cases; ≥ 8/10 stable across 3 runs; all responses pass the schema checks |
| T (texts) | Semeru VA SIGMETs (AWC 30-day history) + the VONA text for the same hour | research/13 | Names the direction disagreement between a SIGMET and the VONA and keeps `top_fl` ≥ the official FL150 |

The FL180 wind is the advisory's own `WIND FL180 ddd/ffKT` group. Only "VA not identifiable" advisories carry one, so for the ash cases it is Open-Meteo's 500 hPa wind at the vent for the hour nearest OBS VA DTG, as research/10 allows; giving the wind to the quiet cases alone would hand the model the label. `case.json` records `wind_source`.

Scoring takes the majority of the 3 runs. Existence is "ash" (`ash_seen`) against "not ash" (anything else, an unparseable response included). Until every run of every case has a response, each verdict reads INCOMPLETE instead of PASS or FAIL.

```bash
uv run python scripts/make_plume_cases.py --arm-t-date 2026-09-26T23:00:00Z   # downloads cases; check needs_human_check in each case.json
# paste the MAGMA VONA text for that hour into evals/plume/arm_t/vona.txt (MAGMA disallows crawling)
read -rs GEMINI_API_KEY && export GEMINI_API_KEY                            # paste the key; it is not echoed
uv run python scripts/plume_eval.py --max-calls 18        # day 1 (free tier ~20/day)
uv run python scripts/plume_eval.py --max-calls 18        # day 2 finishes the 33 calls from cache
uv run python scripts/plume_eval.py --score-only                              # re-score without calling
```

The eval key is a team member's own default AI Studio project, used only by the eval harness. It is never a project created to double the free quota; if the quota runs out, publish the results as they stand, with each unfinished verdict reading INCOMPLETE.

Responses are cached in `results/raw/`; scorecards go to `results/scorecard-*.md`. A call that fails (a 429 or 503, say) is reported and left for the next run. Arm T will not call the model until `vona.txt` holds the VONA text. AWC keeps SIGMET history for 30 days only, so fetch the Arm T snapshot before about 25 Oct 2026; `make_plume_cases.py` refuses a snapshot with no Semeru SIGMET.

**If Arm I fails**, try the four variants in research/10 once each, then take the image out of the decision path and say so in the video: "We tested Gemini 3.8 Flash on ten Tokyo VAAC cases; it told ash from cloud in X of 10, so TEPHRA shows the satellite picture but does not decide from it."

Caveats: "VA not identifiable" is the forecaster's call, not ground truth. The ten test cases must never be used as few-shot examples.
