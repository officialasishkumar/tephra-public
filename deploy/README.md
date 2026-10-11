# Deploying TEPHRA (run these yourself, from a personal account)

These scripts are written for a person to run by hand. They refuse to run unless a dedicated gcloud configuration is logged into the account and project you name, so a work login on the same machine can never be used by accident.

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
./deploy/cloudrun.sh     # Cloud Build -> Artifact Registry -> Cloud Run (prints the URL and checks /healthz)
./deploy/scheduler.sh    # one Cloud Scheduler job: POST /tasks/tick every minute
```

`TEPHRA_SESSION_SECRET` and `TEPHRA_TASK_TOKEN` need at least 32 characters (the app refuses to start otherwise), and the token travels in a header, so keep it to letters, digits and `. _ ~ + / = -`. `openssl rand -hex 32` makes a good one for each. `cloudrun.sh` needs all four secrets to exist. After changing the task token, run `cloudrun.sh` (a new revision reads the new value) and then `scheduler.sh` (the job sends it).

Options (environment variables):

| Variable | Default | Meaning |
|---|---|---|
| `TEPHRA_GCLOUD_CONFIG` | `tephra-personal` | gcloud configuration the scripts pin (never `default`) |
| `TEPHRA_SERVICE` | `tephra` | Cloud Run service name |
| `TEPHRA_RUN_SA` | `tephra-run` | name of the runtime service account |
| `TEPHRA_MIN_INSTANCES` | `1` | `0` scales to zero between ticks (cheaper, slower first page) |
| `TEPHRA_LLM` | `gemini` | `stub` deploys without spending Gemini quota |
| `TEPHRA_SCIENCE` | `false` | `true` builds with satpy and turns on the split-window layer (2 GiB); only `true` or `false` |

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
- With `min-instances=1` and `--no-cpu-throttling` the instance is billed all the time it is up; that keeps the Wall's live stream and the background ADS-B passes working. Use `TEPHRA_MIN_INSTANCES=0` outside demo days.
- One Scheduler job is inside the three free jobs. Firestore's free tier is 20K writes/day; TEPHRA writes only on change.
- The Gemini free tier is reported at about 20 requests/day for `gemini-3.8-flash`; TEPHRA's daily budgets (`TEPHRA_MODEL_DAILY_BUDGET`, `TEPHRA_MODEL_LITE_DAILY_BUDGET`) stop calls before the quota does, and each step then reports AI UNAVAILABLE; nothing falls back to code.

## Terms to respect

TEPHRA is decision support for a fictional airline and sends nothing to any real system. Google Cloud's terms bar High Risk Activities (they name air traffic control); keep the deployed app labelled as a prototype, not for operational use (see `research/06-rules-terms-and-limits.md`).
