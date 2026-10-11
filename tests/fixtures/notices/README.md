# Synthetic notice fixtures

Every file here is written by hand for TEPHRA's tests. The volcano names are real catalogue
names; the dates, times, heights, counts and alert levels are invented, and no observer or
station name appears. The wording follows the layout of the public notices (MAGMA
Indonesia, PHIVOLCS 24-hour card, a JMA-style sentence) without copying any of their text.
Real MAGMA and PHIVOLCS text must never be added to the repository (research/18c, section
2.8).

| File | Language | What it exercises |
|---|---|---|
| `synthetic_id_ash_seen.txt` | Bahasa Indonesia | WIT zone, column above summit and above sea level, direction |
| `synthetic_id_not_observed.txt` | Bahasa Indonesia | eruption "not observed" (never "no ash") |
| `synthetic_fil_kanlaon_card.txt` | Filipino | AM/PM time with PHT, height with no datum |
| `synthetic_ja_sakurajima.txt` | Japanese | full-width digits, 日本時間, height above the crater |
