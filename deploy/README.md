# Deploying TEPHRA (run these yourself, from a personal account)

These scripts are written for a person to run by hand; no agent runs them on a machine. They refuse to run unless a dedicated gcloud configuration is logged into the account and project you name, so a work login on the same machine can never be used by accident.

After the one-time setup below, every push to `main` deploys by itself from GitHub Actions through the same gate (see [Automatic deploys](#automatic-deploys)). The scripts stay the way to do the first deploy, change secrets or the Scheduler job, and roll back.

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
| `TEPHRA_SECRET_VERSIONS` | unset | pins secret versions, e.g. `GEMINI_API_KEY=3,TEPHRA_DESK_PIN=2`; the rest stay `latest`. A rollback target then reads the values it was tested with |

`cloudrun.sh` also forwards each of these app settings to the service when it is set in your shell, and prints the full list before it asks to go ahead: `TEPHRA_MODE`, `TEPHRA_REPLAY_CASE`, `TEPHRA_REPLAY_START`, `TEPHRA_REPLAY_END`, `TEPHRA_REPLAY_SPEED`, `TEPHRA_AUTO_REPLAY`, `TEPHRA_REGION`, `TEPHRA_MODEL`, `TEPHRA_MODEL_LITE`, `TEPHRA_MODEL_DAILY_BUDGET`, `TEPHRA_MODEL_LITE_DAILY_BUDGET`, `TEPHRA_FEATURES`, `TEPHRA_VISITOR_ACCESS`, `TEPHRA_REPLAY_QUANTUM_S`, `TEPHRA_RECOVERY_AUTO`, `TEPHRA_CLOUD_REGION`, `TEPHRA_AI_INTERACTIVE_SHARE`, `TEPHRA_AI_ANSWER_REPLAY_KEEP_H`. Anything else keeps the default in `tephra/config.py`. There is no automatic switch to another model. It always sets `TEPHRA_SECRETS_SOURCE=secret-manager` beside `--set-secrets`, so the service reports where its secrets come from rather than guessing.

The service is deployed with `--concurrency 300` (one instance carries the Wall's event streams), a start-up probe on `/health` that gives the restore from Firestore up to two minutes, and a liveness probe on `/health` every 30 s that replaces a stuck instance.

What `cloudrun.sh` does, in order:

1. Refuses unless the working tree is clean and `HEAD` is on `origin/main` (after `git fetch origin`). The image is tagged `<12-character commit>-<UTC time>` and built with that commit, which `GET /api/state` shows as `build_sha`.
2. Uploads only what the Dockerfile copies (`.gcloudignore`), builds with Cloud Build and applies the cleanup policy in `deploy/ar-cleanup.json` (see Kept images).
3. On the first deploy, creates the service (it takes all traffic) and runs `scripts/live_smoke.sh --read-only` against it.
4. Afterwards, notes the revision serving now, deploys the new one with `--no-traffic --tag candidate`, and runs `scripts/live_smoke.sh --read-only` against the candidate's own URL. Nothing is ever POSTed to a candidate, and it gets no Scheduler ticks. If the test fails, traffic stays where it was.
5. When it passes, moves all traffic to the candidate and runs the full smoke test against the main URL (this waits up to 3 minutes for the new instance's first tick). If that fails, it prints the rollback command and leaves traffic alone for you to decide.
6. Prints the revision name, the image digest and the rollback command.

## Automatic deploys

`.github/workflows/deploy.yml` runs `deploy/cloudrun.sh` in CI mode on every push to `main` (and on demand: Actions tab > deploy > Run workflow, from `main`).

**What triggers it.** A push to `main` that changes something that can alter what runs or how it is deployed: what the image is built from (`Dockerfile`, `.dockerignore`, `.gcloudignore`, `pyproject.toml`, `uv.lock`, `tephra/`, `data/`, `docs/backtest/`, `docs/evals/`), `deploy/`, `scripts/live_smoke.sh` and the policy pins it reads (`tests/test_policy.py`), and the workflow itself. That list is the workflow's `paths:` filter; `tests/test_scripts.py` checks it covers every `COPY` in the Dockerfile. Everything else does not deploy: other docs and Markdown (the root `README.md` is copied into the image for the package metadata only), `research/`, `evals/`, other tests and scripts, `ci.yml`, `.claude/`. A push whose last commit message says `[skip ci]` (or `[skip actions]`) starts no run either; its changes go out with the next deploy. It never runs on a fork or for another branch.

**What it does.** Exactly the gate above, at the pushed commit: build it, deploy it with no traffic as tag `candidate`, `scripts/live_smoke.sh --read-only` against the candidate, move traffic only if that passes, then the full smoke test against the main URL. The settings are the `env:` block at the top of the workflow (the demo configuration: `TEPHRA_MODE=REPLAY`, `TEPHRA_REPLAY_CASE=anak-krakatau-20260905`, the 10:30Z-19:30Z window, `TEPHRA_AUTO_REPLAY=false`, `TEPHRA_FEATURES=connect` (the hero path plus Connect), `TEPHRA_VISITOR_ACCESS=replay`, `TEPHRA_REPLAY_QUANTUM_S=60`, `TEPHRA_RECOVERY_AUTO=false`, `TEPHRA_CLOUD_REGION=asia-southeast1`, `TEPHRA_LLM=gemini`, `always-on`). To change a setting for good, change it there; the push deploys it. A hand change with `gcloud run services update <service> --region <region> --update-env-vars KEY=VALUE` (tephra-personal configuration) makes a new revision from the same image, but the next automatic deploy sets the environment from the workflow again, so put the same value there too.

`.github/workflows/ci.yml` runs the static checks and the offline test suite (`TEPHRA_LLM=stub`) on every push to `main` and every pull request, and keeps the JUnit report as a run artifact. The deploy does not wait for it: a push deploys through the gate above whether or not that run is green, until `needs: test` is added to the deploy job (planned after 17 Oct 2026; the `skip_tests` input on the deploy workflow is for that day).

**Order.** One deploy runs at a time, in push order (a concurrency group). A running deploy is never cancelled; a newer push replaces a run that is still waiting. When a run starts and `main` has moved on past its commit (it was overtaken, or it is a re-run of an old run), it looks at what changed since: if a later push changed deployable files, that push has a run of its own, so this one stops without deploying ("Not deployed" on its summary) and a re-run can never roll the site back; if only non-deploying files changed (a docs push, which starts no run), it deploys its own commit, which runs the same code as the tip. A run whose commit is no longer on `main` at all (history rewritten) refuses.

**Watching it.** Repository > Actions > deploy. Each run's summary page says what happened: "Deployed <commit>" with the revision, the previous revision and the rollback command, or "Not deployed" (the candidate failed; traffic was not moved), or "Live smoke test FAILED" (traffic is on the new revision; roll back if the site is broken). If the deploy step was stopped part-way (its 55-minute limit, a cancelled run), the step after it says how far it got from what the script recorded: before any deploy, while the candidate had no traffic, or after traffic moved, with the rollback command. The log shows every smoke-test line and a link to the Cloud Build log. GitHub emails the pusher when a run fails.

**Rolling back.** The run prints the command; run it yourself from the tephra-personal configuration:

```bash
CLOUDSDK_ACTIVE_CONFIG_NAME=tephra-personal gcloud run services update-traffic tephra \
  --region asia-southeast1 --to-revisions <previous revision>=100
```

Then `scripts/live_smoke.sh https://<service-url>`. The next push to `main` deploys again, so revert or fix the commit on `main` as well, or pause the workflow first.

**Pausing.** Actions > deploy > `...` > Disable workflow (anyone with write access can). Pushes then deploy nothing; enable it again the same way. Deploying by hand with `./deploy/cloudrun.sh` still works while it is disabled.

**What CI mode changes.** With `TEPHRA_DEPLOY_CI=true` and `GITHUB_ACTIONS=true` (both, or it refuses), `deploy/_common.sh` skips the prompt and the tephra-personal configuration, and instead refuses unless gcloud is the deployer service account in `TEPHRA_DEPLOY_SA`, the project is `TEPHRA_PROJECT`, the repository is `officialasishkumar/tephra` and the ref is `refs/heads/main`. The one credential file it lets through is the federation file the auth step wrote for this job (outside the checkout, impersonating exactly that account through exactly `TEPHRA_WIF_PROVIDER`); an access-token file or impersonation is still refused, and the hand path still refuses any credential file. `cloudrun.sh` then requires `HEAD` to be the pushed commit and on `origin/main` (see Order for when `main` has moved on), only checks that the runtime account, the repository and the secrets exist (no API enabling, no IAM changes, no cleanup-policy change, no first deploy), polls Cloud Build instead of streaming its log, and leaves the service's public-access binding as it is. `secrets.sh`, `scheduler.sh`, `monitoring.sh` and `github_deploy_setup.sh` refuse to run in CI.

### One-time setup for automatic deploys

No key is stored anywhere: GitHub's OIDC token for this repository's `main` is exchanged through workload identity federation for a short-lived token of a deployer service account. Nothing goes in GitHub secrets, and no GitHub App is installed.

1. The service must already be deployed by hand once (the scripts above).
2. Run `./deploy/github_deploy_setup.sh` with the same `TEPHRA_GCLOUD_ACCOUNT` and `TEPHRA_PROJECT` as the other scripts. It prints each gcloud command and asks before each change. It creates:
   - workload identity pool `github-actions` and OIDC provider `tephra-main` for `https://token.actions.githubusercontent.com`, whose condition accepts only tokens from `officialasishkumar/tephra` (by name and numeric id), owner `officialasishkumar` (by name and id), `refs/heads/main` and the workflow file `.github/workflows/deploy.yml`;
   - service account `tephra-deployer` with `roles/run.developer` on the `tephra` service only (not the project, so it cannot touch any other Cloud Run service or job), `roles/cloudbuild.builds.editor` and `roles/serviceusage.serviceUsageConsumer` on the project (neither has a narrower scope), `roles/iam.serviceAccountUser` on `tephra-run` only, `roles/artifactregistry.writer` on the `tephra` repository only, `roles/storage.objectCreator` and `roles/storage.legacyBucketReader` on the Cloud Build staging bucket `<project>_cloudbuild` only, and `roles/secretmanager.viewer` (metadata, never values) on the four secrets only;
   - `roles/iam.workloadIdentityUser` on `tephra-deployer` for the principal set of that repository.
3. It prints `TEPHRA_WIF_PROVIDER` and `TEPHRA_DEPLOY_SA` and offers to write them over the `REPLACE_WITH_...` placeholders in `.github/workflows/deploy.yml`. Until they are filled in, the workflow fails at its first step without touching Google Cloud.
4. Commit and push that change to `main`. That push is the first automatic deploy: watch it in the Actions tab.

If the first build fails with a permission error naming `iam.serviceAccounts.actAs` on the Cloud Build service account, the script printed the one grant that fixes it (projects whose builds run as the Compute Engine default account need it). If the deploy itself is refused for a `run.services.*` or `run.revisions.*` permission, the service-level grant was not enough for that call: add `roles/run.viewer` on the project (read-only) and re-run, rather than giving `run.developer` back to the whole project. Undo everything by deleting the provider, the pool and `tephra-deployer`.

**Who can deploy, and what that reaches.** The provider's condition pins the repository, `main` and the workflow file's path, not what the file or the code says. So anyone who can push to `main` (every collaborator with write access) can make a run do what the deployer can: deploy any image as `tephra-run`, which reads the four secrets, Firestore and the bucket, and submit any Cloud Build config, whose steps run as the project's Cloud Build service account. That is inherent to "every push to `main` deploys". Keep write access to people you would hand the project to. The setup script prints the build account's roles and warns if it holds Editor or Owner (the Compute Engine default account often does), which would make a push to `main` worth Editor on the whole project; TEPHRA's build needs only `roles/cloudbuild.builds.builder` on it, and the warning prints the commands to narrow it.

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

`scripts/live_smoke.sh <url> [--read-only] [--watch MINUTES]` uses only public endpoints and needs no secret. Cloud Run answers 429 or 503 while the single instance starts, so a request that gets one is retried with backoff for up to 90 s (`SMOKE_RETRY_S`; at most 240 s of waiting per run, `SMOKE_RETRY_BUDGET_S`) and the line says so, for example `PASS healthz: 200, mode=REPLAY (429 for 20 s, then 200)`; the last line adds how long it waited in all. A 429 or 503 after the service has already answered in the same run is not a start-up (the instance went away or filled up, and visitors got it too), so that check fails even if a retry then succeeds (`FAIL state: ... (429 for 80 s, then 200, after the service had answered)`): look at the revision's logs for a restart or a memory limit. `--watch` never retries (a visitor's browser does not), so the daily monitor shows what visitors get. It checks `/health` (Cloud Run answers `/healthz` itself with a 404, since Google reserves URL paths ending in z); `/api/state` (the last tick finished under 3 ticks ago, the policy hash matches `/api/policy` and the newest pin in `tests/test_policy.py`, `build_sha` when `EXPECT_SHA` is set, the mode and case when `EXPECT_MODE` and `EXPECT_CASE` are set, and the store health when the build exposes it); when the build reports where it runs (`cloud` in `/api/state`): that it is Cloud Run on Firestore with a revision name, `GET /api/audit/verify` answers 200 and `GET /api/evals` answers 200 (404 is reported, not failed, until the scorecard JSON is committed); `/` and `/desk` with a Content-Security-Policy header and every `/static/` file they load; a first `/api/events` event within 30 s; and that `POST /tasks/tick` without the token is refused. It prints one line per check and exits non-zero on any failure. `--read-only` skips the two tick checks.

## Rollback

`cloudrun.sh` prints the exact command after every deploy. It is:

```bash
CLOUDSDK_ACTIVE_CONFIG_NAME=tephra-personal gcloud run services update-traffic <service> \
  --region <region> --to-revisions <previous revision>=100
```

Then run `scripts/live_smoke.sh` against the main URL and reload any open Wall and Desk. Rolling back moves traffic only: no image is built. With automatic deploys on, the next push to `main` deploys again: revert or fix the bad commit on `main`, or disable the workflow first (see Automatic deploys). Old revisions stay deployable as long as their image is in Artifact Registry (see Kept images).

## Keeping a submitted build

- **Keep what was submitted as a rollback target.** Tag the submitted commit with `git tag -a submission-2026-10-18`, deploy it by hand with `TEPHRA_KEEP_TAG=keep-submission-20261018` (or tag its image afterwards with `gcloud artifacts docker tags add <image> <image base>:keep-submission-20261018`), and write down the revision name and the image digest. Keep the GitHub repository public.
- **The site is not frozen:** every push to `main` deploys through the gate (see Automatic deploys), so `main` must stay deployable. Run the tests before pushing, watch the run in the Actions tab, and log each change that went out (what changed, the commit, the revision) in `docs/DECISION-MEMO.md`. To freeze the site for a while, disable the deploy workflow.
- **Never pause the service or scale it to a frozen picture.** A replay and the auto-replay switch move only on ticks, so a paused or tickless service shows a stale screen.
- **Reload the Wall and the Desk** after any deploy.
- **Every day:** run `scripts/live_smoke.sh https://<service-url> --watch 60` (or once a day from cron or launchd), click through the Wall, and sign in to the Desk with the PIN once.

## If the model is retired

A retired or renamed model makes each model step report `AI UNAVAILABLE` with an error that names the model. Read the Gemini API deprecations page, pick the next stable model id, and add `TEPHRA_MODEL` and/or `TEPHRA_MODEL_LITE` with it to the `env:` block of `.github/workflows/deploy.yml` (the push deploys it), or redeploy by hand with them set. The demo deployment stays on the free tier. Turning on prepaid billing for the Gemini key needs the user's approval first.

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

It also creates one uptime check, `TEPHRA /health`, from Google's checkers every 5 minutes (left as it is when it exists). It creates no Cloud Trace setup. Rerunning it updates the metrics and leaves an existing dashboard, channel or policy as it is. If you pause the scheduler job or the service, disable the no-tick policy first, or it will email you.

## Cost notes

- Cloud Run needs a billing account even inside the free tier.
- With `TEPHRA_HOSTING=always-on` (min 1 instance, `--no-cpu-throttling`) the instance is billed all the time it is up; that keeps the Wall's live stream and the background ADS-B passes working. Check the Cloud Run free tier and the billing page before relying on it, and check that the previous revision does not keep an instance up after traffic moves. Cloud Build and Artifact Registry storage have free allowances too; check them.
- One Scheduler job is inside the three free jobs. Firestore's free tier is 20K writes/day; TEPHRA writes only on change.
- Firestore TTL on the kept model answers (`./deploy/firestore.sh`, once) deletes each `ai_answers` document when its `expires_at` passes; TTL deletes count as deletes.
- The Gemini free tier is reported at about 20 requests/day for `gemini-3.8-flash`; TEPHRA's daily budgets (`TEPHRA_MODEL_DAILY_BUDGET`, `TEPHRA_MODEL_LITE_DAILY_BUDGET`) stop calls before the quota does, and the step then reports `AI UNAVAILABLE`; nothing is substituted.

## Terms to respect

TEPHRA is decision support for a fictional airline and sends nothing to any real system. Google Cloud's terms bar High Risk Activities (they name air traffic control); keep the deployed app labelled as a prototype, not for operational use (see `research/06-rules-terms-and-limits.md`).
