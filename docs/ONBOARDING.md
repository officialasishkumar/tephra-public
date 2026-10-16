# Onboard your airline

TEPHRA's demo runs on Ring of Fire Air (RFA), a fictional airline. Any real airline can onboard at
`/onboard`: nine short pages, one topic per page, then an account and a private workspace with a
setup kit to run its own TEPHRA on its own fleet. The answers stay in the browser while the airline
types them and leave it only when the account is created on the last page.

What onboarding is not: there is no live operation on the shared site. Nothing an airline enters
reaches the demo's map or the Desk's picture, no advisory is drafted under its name, and pushes
from airline accounts never enter the shared picture. TEPHRA is decision support only: a person
decides, and nothing is sent to an aircraft.

Onboarding, the accounts and the workspace sit behind `TEPHRA_FEATURES` `onboard`. It is the one
feature whose routes answer 404 (`feature_off`) when it is hidden, so an instance that does not
show it (an airline's own TEPHRA, for one) holds no accounts.

## How to onboard: what you provide

1. **Airline**: name, ICAO and IATA codes, callsign prefix, State of the Operator and AOC number, main base and an operations contact.
2. **Ash policy**: start from Policy A, which is ILLUSTRATIVE, and set your own margins, each change with its reason.
3. **Fleet**: each aircraft's registration, type, seats, home base and ICAO 24-bit address.
4. **Network**: the airports you fly to, and the alternates you use.
5. **Schedule and crews**: one day's flights and your crew bases, in TEPHRA's file formats (optional).
6. **Data feeds**: which of positions, flight plans and pilot reports you will send, in the `tephra.airline/1` format.
7. **People**: the dispatchers who approve advisories, and their roles.
8. **Assistant (AI model)**: Gemini or Gemma with your own Google AI Studio key, Gemma on your own computer through Ollama, or no model.
9. **Review**: check every answer and create your account.

The server checks the answers again (`tephra/airline/models.py`, format `tephra.onboard/2`): codes
by pattern, every list capped, registrations and aircraft addresses once each, at least one
dispatcher who approves, and every policy change named, within the values an airline may change
and with the policy file's own rules still met (no zero that switches a check off, divert time not
after hold time). A changed value needs the airline's SRA reference. No answer holds a key, a PIN,
a password, an address or a file: the schedule files stay in the browser and go only into the kit.

## Your account

- **Email and password.** The password is 12 characters or more. TEPHRA keeps a salted scrypt hash
  (N = 2^14, r = 8, p = 5, standard library), never the password itself, and compares in constant
  time. A password typed with composed or decomposed accents is the same password (NFC).
- **The recovery code, shown once.** Sixteen characters in four groups (`XXXX-XXXX-XXXX-XXXX`,
  about 78 bits). Only its SHA-256 is kept. With it, Sign in › Use your recovery code sets a new
  password and gives a new code; the old code stops working and every other browser is signed out.
  Password reset by email is not built, so the code is the way back in.
- **Sign-in limits.** Five wrong tries from one address in 15 minutes, and ten for one email from
  any address, then sign-in waits; recovery codes have their own limit (five an hour per email), so
  someone guessing passwords cannot lock the owner out of recovery. An unknown email is answered
  and counted exactly like a wrong password. New accounts: ten tries an hour and three accepted a
  day from one address, thirty accepted a day on the whole site; an IPv6 address counts by its /64.
  The limits live in the server's memory and start again after a deploy or restart.
- **Known and accepted.** Signing up with an email that already has an account says so ("An account
  with this email exists. Sign in instead."): with no email check (not built) there is nothing to
  hide it behind. Sign-in and recovery never say whether an email has an account.
- **Full.** With 200 airlines pending or 1,000 stored, new airlines are paused (`onboarding_full`).
- **The cookie.** `tephra_airline`: HttpOnly, SameSite=Strict, 12 hours (`TEPHRA_AIRLINE_SESSION_TTL_H`),
  signed with the session secret under its own label, so a Desk cookie never opens a workspace and
  the reverse. Accounts need `TEPHRA_SESSION_SECRET` (`accounts_off` without it).
- **Deleting the account.** Account menu › Delete account…, with the password: the record and the
  login are deleted, and so are the onboarding answers and schedule files this browser kept.
  Signing out clears those too.

## Verification

A new airline is **Pending verification** until a TEPHRA dispatcher opens it on the Desk (account
menu › Airlines to verify) and verifies or declines it. Verifying records that a person checked
who the operator is (for example its designator, its AOC and the email domain). It does not approve
its policy or its use of TEPHRA, publishes nothing and changes no picture. Declining needs a
reason, which the airline sees.

- While pending the airline can change its answers; verified or declined, they are kept as they are
  ("Ask a TEPHRA dispatcher to change them"). The assistant's model can change in every status.
- Each change and each decision is an entry in the airline record's own hash-linked history, which
  only the airline and this site's dispatchers read. It is never written to the public audit trail,
  which would list airlines publicly. A history its writer can rewrite shows accidents, not
  tampering, so the Desk says only where a link does not check out.
- The Desk sees hints that code works out, never shown to the airline and never blocking: a
  designator TEPHRA's route table holds (a real operator may hold it), a public mail provider, an
  account email whose domain differs from the operations email's, airports outside TEPHRA's list,
  no AOC number.
- A dispatcher can delete a declined airline's record and login, so spam does not fill the cap.

## The workspace

Sign in at `/signin`. The workspace (`/workspace`) is private: only the airline and this site's
TEPHRA dispatchers, who verify it, read its answers; it is never listed publicly, never on the
demo's map or the Desk's picture.

- **Overview**: the verification status, the setup kit, the answers, the data feeds, the assistant
  and the people, then once: running your live operation on this shared TEPHRA is not built.
- **Your answers**: each page's answers, editable while pending.
- **Data feeds**: the `tephra.airline/1` format and its schema (`/api/connect/schema.json`), and a
  **dry run** (DRY RUN · NOTHING TAKEN IN): a file is checked record by record exactly as a push
  would be, with the push's own reasons, and nothing is taken in. Freshness (`observed_at` within
  5 minutes) is checked against the current UTC time, as the airline's own TEPHRA does. Pilot
  reports are checked for shape only. A position without an airline-style callsign (designator and
  flight number, e.g. RFA1654) is taken by a push but never checked against the ash; the dry run
  says so for each one. Thirty dry runs an hour, 512 KiB a file.
- **Assistant**: where the airline's own TEPHRA runs its model: Gemini or Gemma with its own Google
  AI Studio key, Gemma on its own computer through Ollama, or no model (NO MODEL). Only the provider
  and the model names are stored.
- **Setup kit**: the zip below, made in the browser. The page's Gemini key field is the only place
  on the site that takes a secret: the key goes only into the zip made in that tab and TEPHRA never
  receives or stores it.

## The setup kit, file by file

`tephra-kit-<icao>.zip`, everything under `tephra-kit-<icao>/`:

| File | What |
|---|---|
| `airline.env` | the settings for the airline's own TEPHRA; copy it to `.env`. It holds secrets (the Desk PIN, the session secret and the task token, made in the browser at download): never commit it. The shape is [`.env.airline.example`](../.env.airline.example) |
| `policy.json` | Policy A with the airline's changes, each value's `source` saying who set it and why, `label` still "ILLUSTRATIVE, not an airline SRA"; copy it to `data/policy/airline.json` |
| `fleet.json` | the aircraft in `data/rfa`'s fleet shape: registration as the tail, type, seats, and the home base and address when given |
| `flights.json`, `crews.json` | the schedule files read on page 5, or empty ones to fill (no invented rows) |
| `network.json` | the airports and the alternates the airline uses |
| `answers.json` | the stored answers, the airline id and its status |
| `push.py` | the push tool (`tephra/web/kit/push.py`, standard library only) |
| `CHECKLIST.md` | the eight steps below |

`airline.env` sets, in order: `TEPHRA_MODE=LIVE`, `TEPHRA_AUTO_REPLAY=false`, `TEPHRA_REGION` (the
area that holds the main base; outside TEPHRA's three areas the line is commented out, since the
live ash feeds cover only those), `TEPHRA_FEATURES=connect` (`,crew` when pilot reports are pushed),
`TEPHRA_VISITOR_ACCESS=off`, `TEPHRA_RECOVERY_AUTO=false` (recovery re-planning for the airline's
network is not built), `TEPHRA_VONA_LIVE=false`, `TEPHRA_STORE=sqlite`, `TEPHRA_LOCAL_SCHEDULER=true`,
the three secrets, the own-fleet and own-airport lists, `TEPHRA_POLICY_FILE=policy/airline.json`,
then the model lines of the provider chosen (`TEPHRA_LLM=stub` is labelled NO MODEL).

`push.py`:

```
python3 push.py --url URL --key tph_... [--dry-run] plans --schedule flights.json --fleet fleet.json --date YYYY-MM-DD [--callsign-rule ICAO] [--tails-are-today]
python3 push.py --url URL --key tph_... [--dry-run] positions FILE.csv|FILE.json [--stamp-now]
```

Nothing is guessed. A flight plan gets a callsign from its row, or with `--callsign-rule` from the
designator and the flight number's digits (`RF0401` → `RFA401`); it gets an aircraft address only
with `--tails-are-today`, since a schedule's tail is often not the aircraft flying that day. A plan
with neither is skipped and said. A position keeps its `observed_at`; one without is refused unless
`--stamp-now` stamps it with the send time, which is for positions measured in the last minute and
refuses a file written more than a minute before. Batches are at most 1,000 records, a little over a
second apart. `--dry-run` prints the batches and sends nothing.

## Run your own TEPHRA

1. **What this is**: a private TEPHRA for the airline, which checks only its fleet and the
   aircraft it pushes. Not built: one shared service for many airlines; advisories under the
   airline's own flight numbers (drafts name each flight by an RFA number of the fictional Ring of
   Fire Air, and the airline's flight numbers and callsigns never appear in a draft's text);
   Policy B; recovery re-planning for its network; a sign-in for the map page.
2. **Get TEPHRA**: clone the repository, then `uv sync` (or Docker).
3. **Put the kit in place**: `cp tephra-kit-<icao>/airline.env .env` and
   `cp tephra-kit-<icao>/policy.json data/policy/airline.json`.
4. **The model**: Gemini or Gemma on AI Studio: paste the airline's own key after `GEMINI_API_KEY=`.
   When its free daily limit is spent the assistant says AI UNAVAILABLE and plans nothing in its
   place; a model with no row in TEPHRA's free-tier table is never called until one is added with
   `TEPHRA_MODEL_LIMITS` (`.env.example` shows the shape). Ollama: `ollama pull <model>` and
   `ollama serve` at the address given. No model: nothing to do (NO MODEL).
5. **Start it**: `uv run tephra`, then `http://localhost:8080/demo` for the map and `/desk` for the
   Desk with the PIN in `.env`. The map page and its read API have no sign-in: keep TEPHRA on the
   airline's own network or put its own access control in front of it.
6. **Make a push key**: Desk › account menu › Data connections › New connection (shown once).
7. **Push the data**: `python3 push.py --url http://localhost:8080 --key tph_... plans --schedule
   flights.json --fleet fleet.json --date <YYYY-MM-DD>` when the schedule is there, then
   `positions <export.csv>` (each with `observed_at`), or `--stamp-now` for a file written in the
   last minute.
8. **Check it**: `GET /api/fleet` shows the prefixes and the number of aircraft addresses; only the
   fleet's flights become drafts. For Cloud Run instead, read `deploy/README.md` first: a billing
   account is needed even inside the free tier, and an always-on instance is billed while it runs.

## Own-fleet filter, own airports, policy file

Four settings, all empty or default, so the demo is exactly as it was:

| Setting | What |
|---|---|
| `TEPHRA_FLEET_PREFIXES` | callsign prefixes (ICAO, 3 letters, comma list). With `TEPHRA_FLEET_HEXES`, only flights whose airline-style callsign starts with one, the listed aircraft and every pushed aircraft are checked against the ash; everyone else's flights stay on the map. Empty: every aircraft, as the demo does |
| `TEPHRA_FLEET_HEXES` | ICAO 24-bit addresses (6 hex digits, comma list). `GET /api/fleet` gives the prefixes and how many addresses, never the addresses |
| `TEPHRA_NETWORK_AIRPORTS` | the airline's airports in TEPHRA's list (ICAO, 4 letters), checked every tick by code for a closure by the ash, now or within the horizon; a pushed flight plan to or from one is flagged. No model is asked |
| `TEPHRA_POLICY_FILE` | the operator policy file under `TEPHRA_DATA_DIR`, `policy/<name>.json` (default `policy/policy_a.json`) |

The filter narrows only which aircraft enter the exposure check: no validator changes, the
official area stays binding, and other aircraft stay on the map.

## Privacy

What is stored: the account email; the password as a salted scrypt hash, never the password; a
hash of the recovery code; the onboarding answers, including the operations email, the contact
name and the dispatchers' names or initials. Where: Firestore on the live site (`airlines`,
`airline_logins`), SQLite locally. Who reads it: the airline when signed in, and this site's
signed-in dispatchers, to verify it. It is never public, never in the audit trail and never sent
to Gemini. The browser keeps the onboarding draft and the schedule files in its own storage until
"Clear my answers", sign-out or deleting the account. A Gemini key typed on the Setup kit page
stays in that tab and goes only into the zip. Records are kept until the airline deletes its
account, or a dispatcher deletes a declined airline's record; nothing expires them. The site's
privacy page says the same (`/privacy#accounts`).

## Not built

- Running a verified airline's live operation on this shared TEPHRA: pushes from airline accounts
  and advisories under an airline's name never appear on the demo or the Desk.
- Advisories under the airline's own flight numbers: its own TEPHRA still drafts under Ring of
  Fire Air numbers.
- One shared service with a desk per airline over the same public picture.
- Policy B (through, under or over the ash): no code applies a Policy B preset.
- Recovery re-planning for the airline's network.
- Password reset by email, and email address checks.
- A sign-in for the map page of an airline's own TEPHRA.

## FAQ

**Why do drafts still say Ring of Fire Air?** TEPHRA names every flight in a draft by an RFA
number of the fictional airline, and its checks refuse a draft that names the aircraft's own
callsign. That holds in an airline's own TEPHRA too; drafts under the airline's own numbers are
not built.

**Where does my Gemini key go?** Only into the zip made on the Setup kit page, in that browser tab.
The field has no name and sits outside any form, so no request carries it; TEPHRA never receives or
stores it. The workspace keeps the provider and the model names only.

**Why is my policy still ILLUSTRATIVE?** TEPHRA cannot check a safety risk assessment. The policy
file records the airline's numbers, its reasons and its SRA reference, and keeps the label
"ILLUSTRATIVE, not an airline SRA", the only label the policy schema allows.

**Why can't I push to the demo?** The demo is a replay of a fictional airline's day, and the shared
picture is the same for every visitor. Pushes from airline accounts never enter it. Try a file in
the workspace's dry run, then push to your own TEPHRA from the setup kit.
