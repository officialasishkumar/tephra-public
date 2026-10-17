# Hosted airlines: TEPHRA on this site for a verified airline

A verified airline can run TEPHRA on this site, in its own private space at `/a/<ICAO>/`. It is
the same TEPHRA: the airline's own flights, its own policy, its own assistant on its own model key, and only the people it invites.
It starts in SHADOW, where every draft says "Shadow · not for use", and its ops manager switches it
to LIVE when the airline is ready. It is decision support only: TEPHRA sends nothing to an aircraft
or to any system; an approved advisory goes to the airline's own outbound list, and a person passes
it on.

Hosting is the opt-in feature `hosted`. It is **off** on the deployed demo: `TEPHRA_FEATURES` in
`.github/workflows/deploy.yml` does not name it, and `all` never includes it. With it off, nothing
on this page exists and every demo answer is as before, except that TEPHRA staff still verify
airlines on `/admin` (onboarding's console, with its hosting parts not drawn). Turning it on is the owner's change
(`deploy/README.md`, "Hosted airlines").

## 1. What an airline gets

| Page | Address | What it is |
|---|---|---|
| Map | `/a/<ICAO>/` | The demo's map, in LIVE, filtered to the airline's own fleet and flight numbers, with its own Inside TEPHRA panel. No replay, no case switcher. |
| Desk | `/a/<ICAO>/desk` | Today's Desk on the airline's own drafts, for its signed-in members. Drafts made in SHADOW carry the "Shadow · not for use" stamp. |
| Feeds | `/a/<ICAO>/feeds` | What the airline's systems push, as it arrives (positions, flight plans, pilot reports), its push keys, the uploader (`push.py`, "Download uploader": members only, from `/a/<ICAO>/api/tenant/feeds/uploader`; `/static/kit/` answers 404 with hosting on) and the dry run. |
| Settings | `/a/<ICAO>/settings/{policy,assistant,people,record}` | Policy versions and the SRA acceptance; model, key, daily limits and the Desk reserve; members and invites; the airline's own hash-chained record. |
| Documents | `/a/<ICAO>/docs/<id>` | The airline's regulator drafts and handovers. |

Every page sits behind sign-in and answers `X-Robots-Tag: noindex`. A header on every page names
the airline (a switcher for people in several), the four pages, the state chip (SHADOW, LIVE,
SUSPENDED, or "Not started" in setup; in SHADOW and LIVE its (i) says what a draft is) and the
account. The footer says "Private to <name> and
TEPHRA staff". The decision-support sentence is not page chrome (owner, 17 Oct 2026: "don't
put this everywhere"): it is said in the Switch to LIVE dialog and the sign-up and invite ticks, and
documents and outbound text keep their labels; every SHADOW draft keeps its stamp.

## 2. States

| State | What runs | Who moves it on |
|---|---|---|
| Verified, waiting | Nothing. An airline verified without hosting (at the Desk before 17 Oct 2026, or by staff while hosting was off) shows "TEPHRA staff approve hosting after verification." | TEPHRA staff approve hosting on `/admin`. With hosting on, a staff Verify approves hosting too. |
| Can set up | Nothing. The workspace offers "Set up TEPHRA for <name>". | The airline's account holder names themself once and becomes the first ops manager. |
| Setup | No runtime and no airline place. Feeds, keys and Settings work; a push is checked and counted, never taken in (202, `taken_in: false`). | An ops manager starts shadow runs once the checklist is 4 of 4, a region is set and a place is free. |
| SHADOW | TEPHRA runs on the airline's real flights; every draft carries "Shadow · not for use", written by code outside any editable text. | An ops manager switches to LIVE (ticks "I am <name>'s ops manager…" and types the code), or stops. |
| LIVE | The stamp goes; approved drafts are for the airline's dispatchers to use. The switch is recorded with a name and a time. | An ops manager goes back to SHADOW (with a reason) or stops TEPHRA (with a reason). |
| Suspended | Runs stop and pushes are refused; every page stays readable, every change is refused. | TEPHRA staff resume it (always in SHADOW) or, from 7 days after suspension, delete its data. |
| Data deleted | A tombstone with the code, the airline's name and the times it was set up and deleted; nothing about its people (names, member ids, the SRA signatory), no suspension reason, key or region. Members and invites are removed. | — |

The go-live checklist (workspace): **Feeds connected** (positions and, if declared, flight plans
received on an active key in the last 10 minutes; pilot reports are optional; an airline with no
declared feed is found by its callsign on public ADS-B); **Model and key set** (both models in the
free-tier table, the key set and readable); **Policy confirmed** (the current version confirmed by
an ops manager); **Dispatchers invited** (at least one dispatcher has joined). After a restart the
feed counts begin again and the checklist says since when.

The workspace says the site's limit ("TEPHRA runs at most 3 airlines at once on this site.") until
the airline has its space; from then the places line beside Start says it ("1 of 3 airline places
in use"). Once the space exists, the workspace's nav drops Data feeds and Assistant, and their
addresses open the space's Feeds and Settings › Assistant. Each card says one short line; the
rest of what it means sits behind its (i).

## 3. Roles

| | Viewer | Dispatcher | Ops manager | TEPHRA staff |
|---|---|---|---|---|
| Map, Desk queues, documents, Feeds, Policy, Assistant (no key), People (no emails), Record | ✓ | ✓ | ✓ | console only |
| Approve, edit, reject; crew reports; notices; Ask; dry run | | ✓ | ✓ | |
| Push keys, policy, model and key, invites and roles, Start, LIVE, back to SHADOW, Stop, Record check and export | | | ✓ | |
| Verify, approve hosting, suspend, resume, delete data, ops-manager link, staff accounts | | | | ✓ |

Members are airline accounts. An ops manager invites by email and role; the invite is a one-time
link, valid 72 hours, that the ops manager copies and sends. The token travels in the link's
fragment (`/join#<token>`) and in JSON bodies, never in a path. TEPHRA sends no email and does not
check emails: the link is the proof. An airline always keeps at least one ops manager; when none is
left, TEPHRA staff make an ops-manager link for the airline's account email.

TEPHRA staff ("operators" in code) are TEPHRA's own people, with their own accounts and cookie
(`tephra_operator`, 8 hours), on `/admin`. They verify every airline that onboards, with hosting on
or off (the demo Desk is RFA's dispatcher only and verifies nothing); with hosting on they also see
each hosted airline as one row (status, counts, contacts), never its advisory drafts, member
accounts or key. The
first staff account comes from a one-time link that works only while no account is active
(`deploy/README.md`, "The first TEPHRA staff account"); every later one is invited from `/admin`.

## 4. Keys

- **The airline's model key** (Google AI Studio) is entered once in Settings › Assistant, sealed with
  AES-256-GCM under a key derived from `TEPHRA_KEY_SECRET` (else `TEPHRA_SESSION_SECRET`), and kept
  only sealed in the airline's record. It is shown only as its last four (`••••x9Qa`), never
  returned, logged or sent anywhere but Google's API from that airline's own backend. TEPHRA's own
  key is never used for an airline. Rotating the secret makes every sealed key unreadable: the
  Assistant tab says so and asks for the key again.
- **Push keys** are shown once; TEPHRA keeps only their SHA-256. Rotate stops the old key at once.
- An airline with no readable key gets `AI UNAVAILABLE: <reason>` on every model step. Nothing is
  substituted. The pages say it once per screen ("AI unavailable" and its (i), which gives the
  reason and where it is set); the raw reason is one tap in. `GET /api/budget` carries it as
  `unavailable`, so the map and the Desk read the airline's state, never "on".

## 5. Limits, allowances and pauses (free tier only)

- At most **3 airlines** in SHADOW or LIVE at once on this site (`TEPHRA_HOSTED_MAX_TENANTS`, 0-3).
  Setup takes no place. A full site says "All airline places on this site are in use" where Start
  is, and "Airline limit reached" on the console.
- Firestore's free tier is shared. The site caps are 40,000 reads, 16,000 writes and 16,000 deletes
  a Pacific day (20 % under the free tier, kept for TTL deletes and the console). Each running
  airline has its own allowance, `cap × 0.6 / 3` (8,000 reads, 3,200 writes, 3,200 deletes), which
  counts what its people's requests read and write in the site's own documents too. An airline
  over its allowance **pauses alone** until 00:00 Pacific. Its people's reads go on up to its
  ceiling, `cap / 3` (13,333 reads), and are then refused (503 `airline_paused`) except the
  header that says why, so the airlines together never pass a cap. At a site cap, reached by the
  airlines together, every airline pauses; the demo's own use (its visitors' reads included) is
  shown on the console and never pauses an airline. While paused, ticks and pushes stop, Desk
  decisions still work, and nothing stands in for the paused work. The airline's pages say so in
  red; the console shows the meter.
- Event streams: each airline has its own 10 places (4 per person), held apart from the demo's
  (`TEPHRA_MAX_EVENT_STREAMS` less every airline's), so no number of demo visitors cuts an
  airline's live updates off.
- Signed-in requests count per address and per login, never per site: one self-made account
  cannot lock the airlines' people out.
- Satellite frame uploads by airlines are capped at 4,000 a month; past it the frames feed says
  "Satellite frames paused: the site's free storage operations for this month are used".
- Pushes: 10 s between pushes per key, 30 a minute per airline, 60 pilot reports an hour.
- Memory: a new airline does not start while the process is above `TEPHRA_HOSTED_RSS_LIMIT_MB`
  (700 MB).
- An airline that is active during an eruption in its region can use its daily share and pause.
  Only paying for Firestore or hosting fewer airlines changes that; the owner's rule is free tier
  only.

## 6. Not built

- Email: invites and staff links are links you copy; no email is sent and emails are not
  checked.
- Password reset by email.
- Two-factor sign-in, single sign-on, custom domains, a choice of data residency.
- Ollama on hosted TEPHRA.
- Regions other than Java / Bali, Halmahera and Kyushu.
- Recovery re-planning for an airline's own network.
- Uploading an own schedule (`flights.json`): flights are named by pushed flight plans, callsigns and
  registrations.
- Policy B.
- More than 3 airlines at once.
- Re-sealing keys after a secret rotation: the Assistant tab asks for the key again.
- Persisted feed statistics: the Feeds cards count since the process started.
- A grace window when a push key is rotated.
- Sending anything to an aircraft or an outside system is never built: TEPHRA is decision support
  only.

## 7. Measured cost

Measured offline on the stub replay (laptop, SQLite): runtime creation 0.06-0.09 s CPU; +24-31 MB
RSS per extra runtime at creation; 0.05-0.14 s CPU per tick of code steps; about 43 writes and 101
document reads per active tick before the write-on-change and read-cache work.

`scripts/hosted_measure.py` ran two LIVE airlines (RFB and RFC, each flying about half of the
recorded traffic) for 120 steps of the Anak Krakatau recording, each step a tick, an ADS-B pass and
the AI worker's work, both fetching through one shared source (stub model, SQLite counted as
Firestore bills):

| | RFB | RFC |
|---|---|---|
| Exposed flights (most at once) | 12 | 21 |
| CPU per step, mean / max | 0.094 / 0.25 s | 0.098 / 0.25 s |
| Store reads per step (a minute) | 19.8 | 47.4 |
| Store writes per step | 9.3 | 14.6 |
| Store deletes per step | 0.8 | 1.3 |

Memory: about 22 MB more peak RSS per airline, with no growth over the 120 steps (131-138 MB
before the runtimes, 178-181 MB with two). Three airlines and the demo stay near 200 MB, well
under the 700 MB guard, so the limit of 3 airlines stands.

At eruption activity, reads, not writes, pause a busy airline first: at 47 reads a minute its
8,000 reads a day last about 2.8 hours (its 3,200 writes about 3.6 hours). A quiet airline reads
far less. The in-memory read cache saved no reads in this run, because the repeated reads happen
across passes and every pass empties it.
