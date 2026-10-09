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
CLOUDSDK_ACTIVE_CONFIG_NAME=tephra-personal gcloud firestore rules deploy deploy/firestore.rules 2>/dev/null \
  || echo "Upload deploy/firestore.rules in the console (Firestore > Rules) if your gcloud lacks the command."
```

The Cloud Run runtime service account (by default the Compute Engine default service account) needs `roles/datastore.user`, `roles/storage.objectAdmin` on the bucket, and `roles/secretmanager.secretAccessor`.

## Deploy

```bash
./deploy/secrets.sh      # GEMINI_API_KEY (personal AI Studio key), TEPHRA_DESK_PIN, TEPHRA_TASK_TOKEN, TEPHRA_SESSION_SECRET
./deploy/cloudrun.sh     # Cloud Build -> Artifact Registry -> Cloud Run (prints the URL and checks /healthz)
./deploy/scheduler.sh    # one Cloud Scheduler job: POST /tasks/tick every minute
```

Options (environment variables):

| Variable | Default | Meaning |
|---|---|---|
| `TEPHRA_GCLOUD_CONFIG` | `tephra-personal` | gcloud configuration the scripts pin |
| `TEPHRA_SERVICE` | `tephra` | Cloud Run service name |
| `TEPHRA_MIN_INSTANCES` | `1` | `0` scales to zero between ticks (cheaper, slower first page) |
| `TEPHRA_LLM` | `gemini` | `stub` deploys without spending Gemini quota |
| `TEPHRA_SCIENCE` | `false` | `true` builds with satpy and turns on the split-window layer (2 GiB) |

## Cost notes

- Cloud Run needs a billing account even inside the free tier.
- With `min-instances=1` and `--no-cpu-throttling` the instance is billed all the time it is up; that keeps the Wall's live stream and the background ADS-B passes working. Use `TEPHRA_MIN_INSTANCES=0` outside demo days.
- One Scheduler job is inside the three free jobs. Firestore's free tier is 20K writes/day; TEPHRA writes only on change.
- The Gemini free tier is reported at about 20 requests/day for `gemini-3.8-flash`; TEPHRA's daily budgets (`TEPHRA_MODEL_DAILY_BUDGET`, `TEPHRA_MODEL_LITE_DAILY_BUDGET`) stop calls before the quota does and fall back to code.

## Terms to respect

TEPHRA is decision support for a fictional airline and sends nothing to any real system. Google Cloud's terms bar High Risk Activities (they name air traffic control); keep the deployed app labelled as a prototype, not for operational use (see `research/06-rules-terms-and-limits.md`).
