# Onboard your airline

TEPHRA's demo runs on Ring of Fire Air (RFA), a fictional airline. Any real airline can onboard at
`/onboard`: the account first (a work email and a password, on the same page as the list below),
then nine short pages, one topic per page, and a private workspace. Each page is saved to the account on Next, on Back, on a step in the list
and when you leave the page; signing in again
resumes at the first page not finished. Review's **Submit for verification** sends the answers to
this site's dispatchers.

What onboarding is not: running an airline on this site is not switched on yet. Nothing an airline enters
reaches the demo's map or the Desk's picture, no advisory is drafted under its name, and pushes
from airline accounts never enter the shared picture. TEPHRA is decision support only: a person
decides, and nothing is sent to an aircraft.

Onboarding, the accounts and the workspace sit behind `TEPHRA_FEATURES` `onboard`. It is the one
feature whose routes answer 404 (`feature_off`) when it is hidden, so an instance that does not
show it holds no accounts.

## How to onboard: what you provide

1. **Airline**: name, ICAO and IATA codes, callsign prefix, State of the Operator and AOC number, main base and an operations contact.
2. **Ash policy**: start from Policy A, which is ILLUSTRATIVE, and set your own margins, each change with its reason.
3. **Fleet**: each aircraft's registration, type, seats, home base and ICAO 24-bit address.
4. **Network**: the airports you fly to, and the alternates you use.
5. **Schedule and crews**: one day's flights and your crew bases, in TEPHRA's file formats (optional).
6. **Data feeds**: which of positions, flight plans and pilot reports you will send, in the `tephra.airline/1` format.
7. **People**: the dispatchers who approve advisories, and their roles.
8. **Assistant (AI model)**: Gemini or Gemma with your own Google AI Studio key, Gemma on your own computer through Ollama, or no model.
9. **Review**: check every answer and submit it for verification.

Until Review submits them the pages are a **draft** in the account (`PUT /api/airline/draft`): kept
as typed, checked for shape and size only (every key a page writes and nothing else, each value
bounded, a control character kept as a space). A page with a problem says so and offers "Next
anyway"; Submit refuses until every page passes. A save the server does not take (offline, too
many saves, another tab) is said in the bar where Next is, and what was typed stays on the page.

On Submit (`POST /api/airline/submit`) the server checks the answers again
(`tephra/airline/models.py`, format `tephra.onboard/2`): codes
by pattern, every list capped, registrations and aircraft addresses once each, at least one
dispatcher who approves, and every policy change named, within the values an airline may change
and with the policy file's own rules still met (no zero that switches a check off, divert time not
after hold time). A changed value needs the airline's SRA reference. No answer holds a key, a PIN,
a password, an address or a file: the schedule files stay in the browser.

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
  hide it behind, so each such answer counts as one of the address's three sign-ups a day. Sign-in
  and recovery never say whether an email has an account.
- **Saves.** Each save is one store write; an account may make 100 a day (enough for a walk through
  the pages with many edits), and all accounts together 3,000. Every signed-in request reads the
  store twice, so one address may make 60 in five minutes and the site 5,000 a day. Edits fold into
  the record's last history entry, so the history never holds more than 100 entries.
- **Not submitted.** An account whose answers were never submitted is deleted, login first, once
  seven days pass without a save (checked at most hourly, at a sign-up), so its email can sign up
  again and junk drafts cannot fill the cap below.
- **Full.** With 300 accounts still onboarding, 200 airlines pending or 1,000 accounts in all,
  new accounts are paused (`onboarding_full`); with 200 pending, Submit waits too. Counted by the
  store without reading a record.
- **The cookie.** `tephra_airline`: HttpOnly, SameSite=Strict, 12 hours (`TEPHRA_AIRLINE_SESSION_TTL_H`),
  signed with the session secret under its own label, so a Desk cookie never opens a workspace and
  the reverse. Accounts need `TEPHRA_SESSION_SECRET` (`accounts_off` without it).
- **Deleting the account.** Account menu › Delete account…, with the password, at any point (a
  draft too): the record and the login are deleted, and so are the schedule files this browser
  kept. Signing out clears those too.

## Verification

A submitted airline is **Pending verification** until a TEPHRA dispatcher opens it on the Desk
(account menu › Airlines to verify) and verifies or declines it. An account still onboarding
(**Not submitted**) is never listed there and answers 404 on every Desk route: its answers are its
own until it submits. Verifying records that a person checked
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

- **Overview**: still onboarding, "Continue onboarding · step n of 9" and the page to go back to,
  and nothing else (the other sections come once the answers are submitted). Submitted: the
  verification status, the answers, the data feeds, the assistant and the people. Once verified it
  says "Verified." and, while hosting is off, "Running your airline on this site is not switched on
  yet."
- **Your answers**: each page's answers, editable while pending.
- **Data feeds**: the `tephra.airline/1` format and its schema (`/api/connect/schema.json`), and a
  **dry run** (DRY RUN · NOTHING TAKEN IN): a file is checked record by record exactly as a push
  would be, with the push's own reasons, and nothing is taken in. Freshness (`observed_at` within
  5 minutes) is checked against the current UTC time, as a push is. Pilot
  reports are checked for shape only. A position without an airline-style callsign (designator and
  flight number, e.g. RFA1654) is taken by a push but never checked against the ash; the dry run
  says so for each one. Thirty dry runs an hour, 512 KiB a file.
- **Assistant**: the model the airline chooses: Gemini or Gemma with its own Google AI Studio key,
  Gemma on its own computer through Ollama, or no model (NO MODEL). Only the provider and the model
  names are stored; TEPHRA never asks for the key.

## From verification to hosting

When this site hosts airlines (the opt-in feature `hosted`, off on the deployed demo; see
`docs/HOSTED.md`), a verified airline can run TEPHRA here, in its own private space at
`/a/<ICAO>/`:

1. **Verification.** An operator verifies the airline on `/admin`, which also approves hosting. An
   airline a dispatcher verified on the Desk sees "TEPHRA's operators approve hosting after
   verification" until an operator approves it.
2. **Set up.** The workspace's Overview shows **Go live on TEPHRA**. The account holder names
   themself once ("Your name on TEPHRA") and becomes the airline's first ops manager. Nothing runs
   yet and the airline takes none of the site's places.
3. **The checklist.** Feeds connected (pushes on a key made on the airline's Feeds page), model and
   key set (Settings › Assistant), policy confirmed (Settings › Policy), dispatchers invited
   (Settings › People; each invite is a link the ops manager sends). The region is derived from the
   network's airports, or chosen when they fall in several regions or in none.
4. **SHADOW.** An ops manager starts shadow runs when a place is free. TEPHRA runs on the airline's
   real flights and every draft says "Shadow · not for use".
5. **LIVE.** An ops manager switches to LIVE, ticking "I am <name>'s ops manager…" and typing the
   airline's code; the switch goes into the airline's record. Back to SHADOW and Stop each need a
   reason; Stop frees the place and returns the space to setup.

Until the airline has its space, the workspace's Not built line reads: "TEPHRA runs at most 3
airlines at once on this site."; from then the places line beside Start says it.
Invited members sign in at `/signin` (or on the invite page, `/join`); a login that belongs only to
hosted airlines has "Your airlines" as its workspace.

## The push tool

`tephra/web/kit/push.py` (standard library only) sends an airline's flight plans and positions to a
TEPHRA's push endpoint, with a key made on the Desk (account menu › Data connections):

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
hash of the recovery code; from sign-up on, the onboarding answers with the account, including the
operations email, the contact name and the dispatchers' names or initials. Where: Firestore on the
live site (`airlines`, `airline_logins`), SQLite locally. Who reads it: the airline when signed in,
and this site's signed-in dispatchers once the airline submits, to verify it. It is never public,
never in the audit trail and never sent to Gemini. The browser keeps only the schedule files (their
counts go with the answers), until sign-out or deleting the account. TEPHRA never asks for a Gemini
key.
Records are kept until the airline deletes its
account, or a dispatcher deletes a declined airline's record; nothing expires them. The site's
privacy page says the same (`/privacy#accounts`).

## Not built

- Running an airline on this site: not switched on yet while hosting is off (the deployed demo);
  where the site hosts airlines, each runs in its own space (above). Pushes from airline accounts
  and advisories under an airline's name never appear on the demo or the Desk.
- One shared service with a desk per airline over the same public picture.
- Policy B (through, under or over the ash): no code applies a Policy B preset.
- Recovery re-planning for the airline's network.
- Password reset by email, and email address checks.

## FAQ

**Where does my Gemini key go?** Nowhere: TEPHRA never asks for it. The workspace keeps the
provider and the model names only.

**Why is my policy still ILLUSTRATIVE?** TEPHRA cannot check a safety risk assessment. The policy
file records the airline's numbers, its reasons and its SRA reference, and keeps the label
"ILLUSTRATIVE, not an airline SRA", the only label the policy schema allows.

**Why can't I push to the demo?** The demo is a replay of a fictional airline's day, and the shared
picture is the same for every visitor. Pushes from airline accounts never enter it. Try a file in
the workspace's dry run.
