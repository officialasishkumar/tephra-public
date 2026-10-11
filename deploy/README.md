# Deploying TEPHRA (run these yourself, from a personal account)

These scripts are written for a person to run by hand; no agent runs them. They refuse to run unless a dedicated gcloud configuration is logged into the account and project you name, so a work login on the same machine can never be used by accident.

## One-time setup

```bash
# A separate gcloud configuration for the personal account (does not touch your default one)
gcloud config configurations create tephra-personal --no-activate
CLOUDSDK_ACTIVE_CONFIG_NAME=tephra-personal gcloud auth login            # personal account
CLOUDSDK_ACTIVE_CONFIG_NAME=tephra-personal gcloud config set project <your-project-id>

export TEPHRA_GCLOUD_ACCOUNT=<your personal Google account>
export TEPHRA_PROJECT=<your-project-id>
export TEPHRA_GCP_REGION=asia-southeast1        # Singapore; any region where the Gemini API is available
export TEPHRA_GCS_BUCKET=<a bucket name>        # create it in a US region to stay inside the free tier

# Firestore (native mode) and the blob bucket, once:
CLOUDSDK_ACTIVE_CONFIG_NAME=tephra-personal gcloud firestore databases create --location="$TEPHRA_GCP_REGION"
CLOUDSDK_ACTIVE_CONFIG_NAME=tephra-personal gcloud storage buckets create "gs://$TEPHRA_GCS_BUCKET" --location=us-central1
```

`deploy/firestore.rules` denies every browser client (the service reaches Firestore through IAM, which rules do not govern). gcloud has no command for security rules: paste the file into the console (Firestore > Rules) or deploy it with the Firebase CLI.

The scripts refuse the `default` gcloud configuration, and refuse to run while an access-token file, a credential-file override or service-account impersonation is set (in the configuration or through a `CLOUDSDK_AUTH_*` variable), because each of those makes gcloud act as someone other than `TEPHRA_GCLOUD_ACCOUNT`.

`cloudrun.sh` runs the service as its own service account, `tephra-run@<project>.iam.gserviceaccount.com`, which it creates if needed and grants exactly `roles/datastore.user` on the project, `roles/storage.objectAdmin` on the bucket and `roles/secretmanager.secretAccessor` on the four secrets. The Compute Engine default account would have far more access and still no right to read the secrets.

## Deploy

```bash
./deploy/secrets.sh      # GEMINI_API_KEY (personal AI Studio key), TEPHRA_DESK_PIN, TEPHRA_TASK_TOKEN, TEPHRA_SESSION_SECRET
./deploy/cloudrun.sh     # Cloud Build -> Artifact Registry -> Cloud Run, gated by scripts/live_smoke.sh
./deploy/scheduler.sh    # one Cloud Scheduler job: POST /tasks/tick every minute
```

`TEPHRA_SESSION_SECRET` and `TEPHRA_TASK_TOKEN` need at least 32 characters (the app refuses to start otherwise), and the token travels in a header, so keep it to letters, digits and `. _ ~ + / = -`. `openssl rand -hex 32` makes a good one for each. `cloudrun.sh` needs all four secrets to exist. After changing the task token, run `cloudrun.sh` (a new revision reads the new value) and then `scheduler.sh` (the job sends it).

Options (environment variables):

| Variable | Default | Meaning |
|---|---|---|
| `TEPHRA_GCLOUD_CONFIG` | `tephra-personal` | gcloud configuration the scripts pin (never `default`) |
| `TEPHRA_SERVICE` | `tephra` | Cloud Run service name |
| `TEPHRA_RUN_SA` | `tephra-run` | name of the runtime service account |
| `TEPHRA_HOSTING` | `always-on` | `always-on`: min 1 instance, CPU always on, Cloud Scheduler ticks. `on-demand`: min 0, CPU only during requests, the instance ticks itself (untested: confirm a cold page shows the replay advancing and the bill stays in the free tier before relying on it) |
| `TEPHRA_LLM` | `gemini` | `stub` deploys without spending Gemini quota |
| `TEPHRA_KEEP_TAG` | unset | also tags the built image, e.g. `keep-submission-20261018`; must start with `keep-` so the cleanup policy keeps it |
| `TEPHRA_SCIENCE` | `false` | `true` builds with satpy and turns on the split-window layer (2 GiB); only `true` or `false` |

`cloudrun.sh` also forwards each of these app settings to the service when it is set in your shell, and prints the full list before it asks to go ahead: `TEPHRA_MODE`, `TEPHRA_REPLAY_CASE`, `TEPHRA_REPLAY_START`, `TEPHRA_REPLAY_END`, `TEPHRA_REPLAY_SPEED`, `TEPHRA_AUTO_REPLAY`, `TEPHRA_REGION`, `TEPHRA_MODEL`, `TEPHRA_MODEL_LITE`, `TEPHRA_MODEL_DAILY_BUDGET`, `TEPHRA_MODEL_LITE_DAILY_BUDGET`. Anything else keeps the default in `tephra/config.py`. There is no automatic switch to another model.

What `cloudrun.sh` does, in order:

1. Refuses unless the working tree is clean and `HEAD` is on `origin/main` (after `git fetch origin`). The image is tagged `<12-character commit>-<UTC time>` and built with that commit, which `GET /api/state` shows as `build_sha`.
2. Uploads only what the Dockerfile copies (`.gcloudignore`), builds with Cloud Build and applies the cleanup policy in `deploy/ar-cleanup.json` (see Kept images).
3. On the first deploy, creates the service (it takes all traffic) and runs `scripts/live_smoke.sh --read-only` against it.
4. Afterwards, notes the revision serving now, deploys the new one with `--no-traffic --tag candidate`, and runs `scripts/live_smoke.sh --read-only` against the candidate's own URL. Nothing is ever POSTed to a candidate, and it gets no Scheduler ticks. If the test fails, traffic stays where it was.
5. When it passes, moves all traffic to the candidate and runs the full smoke test against the main URL (this waits up to 3 minutes for the new instance's first tick). If that fails, it prints the rollback command and leaves traffic alone for you to decide.
6. Prints the revision name, the image digest and the rollback command.

## First deploy and smoke test

1. Deploy with the stub model first, so a broken deploy spends no Gemini quota:
   ```bash
   ./deploy/secrets.sh
   TEPHRA_LLM=stub ./deploy/cloudrun.sh
   ./deploy/scheduler.sh
   scripts/live_smoke.sh https://<service-url>
   ```
2. Then deploy again with `TEPHRA_LLM=gemini` (the default). This goes through the gate: the candidate is tested before it takes traffic.
3. Force one more revision (run `./deploy/cloudrun.sh` again with nothing changed) and run `scripts/live_smoke.sh https://<service-url>` once more. This proves a restart restores from Firestore and the scheduler reaches the new revision.
4. Open the Wall and the Desk in a browser and sign in to the Desk with the PIN.

`scripts/live_smoke.sh <url> [--read-only] [--watch MINUTES]` uses only public endpoints and needs no secret. It checks `/healthz`; `/api/state` (the last tick finished under 3 ticks ago, the policy hash matches `/api/policy` and the newest pin in `tests/test_policy.py`, `build_sha` when `EXPECT_SHA` is set, the mode and case when `EXPECT_MODE` and `EXPECT_CASE` are set, and the store health when the build exposes it); `/` and `/desk` with a Content-Security-Policy header and every `/static/` file they load; a first `/api/events` event within 30 s; and that `POST /tasks/tick` without the token is refused. It prints one line per check and exits non-zero on any failure. `--read-only` skips the two tick checks.

## Rollback

`cloudrun.sh` prints the exact command after every deploy. It is:

```bash
CLOUDSDK_ACTIVE_CONFIG_NAME=tephra-personal gcloud run services update-traffic <service> \
  --region <region> --to-revisions <previous revision>=100
```

Then run `scripts/live_smoke.sh` against the main URL and reload any open Wall and Desk. Rolling back moves traffic only: no image is built. Old revisions stay deployable as long as their image is in Artifact Registry (see Kept images).

## Judging window, 19 Oct to 6 Nov, and the 4 Dec final

Judges look at the live link on their own schedule from the submission (18 Oct) to 6 Nov, and again for the final on 4 Dec (re-check that date). For all of that time:

- **Freeze what was submitted.** Tag the submitted commit with `git tag -a submission-2026-10-18`, deploy it with `TEPHRA_KEEP_TAG=keep-submission-20261018`, and write down the revision name and the image digest that `cloudrun.sh` prints. Keep the GitHub repository public.
- **Merge nothing to main** until judging ends. Deploy only fixes for an outage, through the same gate, and log each one (what broke, the commit, the revision) in `docs/DECISION-MEMO.md`.
- **Never pause the service or scale it to a frozen picture.** A replay and the auto-replay switch move only on ticks, so a paused or tickless service shows a stale screen.
- **Recommended demo configuration:** `TEPHRA_MODE=REPLAY`, `TEPHRA_REPLAY_CASE=anak-krakatau-20260905`, `TEPHRA_REPLAY_START=2026-09-05T10:30:00Z` and `TEPHRA_REPLAY_END=2026-09-05T19:30:00Z` (the window whose ADS-B was reconstructed, 10:00Z-19:30Z, played as a loop; the Wall opens on the case's volcano, Anak Krakatau, with its flights and advisories: docs/UI-REDESIGN.md R2.2), and `TEPHRA_AUTO_REPLAY=false`. Before deploying, a person re-probes that window with `uv run python scripts/record_replay.py probe --case anak-krakatau-20260905 ...` and scrubs it to confirm that flights in or heading in stay above 0 through the loop.
- **Change settings without a new image** where you can: `gcloud run services update <service> --region <region> --update-env-vars KEY=VALUE` (with the tephra-personal configuration). This makes a new revision from the same image; run `scripts/live_smoke.sh` afterwards.
- **Reload the Wall and the Desk** after any deploy.
- **Every day:** run `scripts/live_smoke.sh https://<service-url> --watch 60` (or once a day from cron or launchd), click through the Wall, and sign in to the Desk with the PIN once.

## If the model is retired

A retired or renamed model makes each model step report `AI UNAVAILABLE` with an error that names the model. Read the Gemini API deprecations page, pick the next stable model id, and redeploy with `TEPHRA_MODEL` and/or `TEPHRA_MODEL_LITE` set to it (or change only the env vars as above). The judged deployment stays on the free tier. Turning on prepaid billing for the Gemini key needs the user's approval first.

## Kept images

`deploy/ar-cleanup.json` is the Artifact Registry cleanup policy `cloudrun.sh` applies on every deploy:

- `keep-tagged`: keep every image with a tag starting `keep-` (the submitted build);
- `keep-recent`: keep the 5 newest images (rollback targets);
- `delete-old`: delete anything else older than 30 days.

Keep rules win over the delete rule. Storage over the free 0.5 GB is billed, which is why old images go at all. Check what is applied with `gcloud artifacts repositories list-cleanup-policies <repo> --location <region>`.

## Monitoring (optional, check pricing first)

The app does not need this to run. Before running it, check Google's current pricing for log-based metrics, alert policies and uptime checks, since TEPHRA is meant to stay on free services.

```bash
./deploy/monitoring.sh                                   # metrics and dashboard only
TEPHRA_MONITORING_ALERTS=true TEPHRA_ALERT_EMAIL=<address> ./deploy/monitoring.sh   # plus alerts
```

It prints every gcloud command before running it and creates:

- three log-based metrics read from the service's JSON log lines: `gemini_calls` (one per Gemini call, labelled only by `tier` and `outcome`), `gemini_latency_ms` (a distribution of the latency of calls that reached Gemini) and `tephra_ticks` (one per finished scheduler tick);
- a dashboard named `TEPHRA` from `deploy/monitoring-dashboard.json` with those three charts;
- with `TEPHRA_MONITORING_ALERTS=true` only: one email notification channel and two alert policies, "no tick for 10 min" and "Gemini errors >= 2 in 30 min". These use the `beta` and `alpha` gcloud command groups.

It creates no uptime check and no Cloud Trace setup. Rerunning it updates the metrics and leaves an existing dashboard, channel or policy as it is. If you pause the scheduler job or the service, disable the no-tick policy first, or it will email you.

## Cost notes

- Cloud Run needs a billing account even inside the free tier.
- With `TEPHRA_HOSTING=always-on` (min 1 instance, `--no-cpu-throttling`) the instance is billed all the time it is up; that keeps the Wall's live stream and the background ADS-B passes working. Check the Cloud Run free tier and the billing page before relying on it, and check that the previous revision does not keep an instance up after traffic moves. Cloud Build and Artifact Registry storage have free allowances too; check them.
- One Scheduler job is inside the three free jobs. Firestore's free tier is 20K writes/day; TEPHRA writes only on change.
- The Gemini free tier is reported at about 20 requests/day for `gemini-3.8-flash`; TEPHRA's daily budgets (`TEPHRA_MODEL_DAILY_BUDGET`, `TEPHRA_MODEL_LITE_DAILY_BUDGET`) stop calls before the quota does, and the step then reports `AI UNAVAILABLE`; nothing is substituted.

## Terms to respect

TEPHRA is decision support for a fictional airline and sends nothing to any real system. Google Cloud's terms bar High Risk Activities (they name air traffic control); keep the deployed app labelled as a prototype, not for operational use (see `research/06-rules-terms-and-limits.md`).
