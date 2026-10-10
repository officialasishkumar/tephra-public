#!/usr/bin/env bash
# Build the image with Cloud Build and deploy the single TEPHRA Cloud Run service.
# One instance holds the live state the Wall streams from, so max = 1. Background ADS-B
# passes need CPU outside requests, hence --no-cpu-throttling. Both cost money while the
# instance is up; set TEPHRA_MIN_INSTANCES=0 to scale to zero between ticks (state is
# restored from Firestore on a cold start, at the price of a slower first page).
# shellcheck source=deploy/_common.sh
source "$(dirname "$0")/_common.sh"

MIN_INSTANCES="${TEPHRA_MIN_INSTANCES:-1}"
MEMORY="${TEPHRA_MEMORY:-1Gi}"
SCIENCE="${TEPHRA_SCIENCE:-false}"
BUCKET="${TEPHRA_GCS_BUCKET:?set TEPHRA_GCS_BUCKET (a US-region bucket keeps blobs in the free tier)}"
LLM="${TEPHRA_LLM:-gemini}"
RUN_SA_NAME="${TEPHRA_RUN_SA:-tephra-run}"
RUN_SA="$RUN_SA_NAME@$TEPHRA_PROJECT.iam.gserviceaccount.com"
SECRETS=(GEMINI_API_KEY TEPHRA_DESK_PIN TEPHRA_TASK_TOKEN TEPHRA_SESSION_SECRET)
# The same value builds the image and switches the app's layer on, so both must agree.
case "$SCIENCE" in
  true) MEMORY="${TEPHRA_MEMORY:-2Gi}"; science_arg=1 ;;
  false) science_arg=0 ;;
  *) echo "TEPHRA_SCIENCE must be 'true' or 'false', not '$SCIENCE'." >&2; exit 1 ;;
esac

# A service account that IAM has only just created can take a little while to be usable.
retry() {
  local attempt
  for attempt in 1 2 3 4 5 6; do
    "$@" && return 0
    echo "  retrying in 10 s ($attempt/6)" >&2
    sleep 10
  done
  return 1
}

confirm "Deploy $SERVICE (min $MIN_INSTANCES, max 1, $MEMORY, LLM=$LLM, science=$SCIENCE) as $RUN_SA?"

gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com \
  firestore.googleapis.com storage.googleapis.com secretmanager.googleapis.com iam.googleapis.com

for secret in "${SECRETS[@]}"; do
  if ! gcloud secrets describe "$secret" >/dev/null 2>&1; then
    echo "Secret $secret does not exist; run deploy/secrets.sh first." >&2
    exit 1
  fi
done

# The runtime identity gets only what TEPHRA uses (docs/ARCHITECTURE.md section 4). Without
# one the service runs as the Compute Engine default account, which holds far more than
# this yet cannot read secret values without a grant, so --set-secrets would be refused.
if ! gcloud iam service-accounts describe "$RUN_SA" >/dev/null 2>&1; then
  gcloud iam service-accounts create "$RUN_SA_NAME" --display-name "TEPHRA Cloud Run runtime"
fi
retry gcloud projects add-iam-policy-binding "$TEPHRA_PROJECT" --member "serviceAccount:$RUN_SA" \
  --role roles/datastore.user --condition=None >/dev/null
retry gcloud storage buckets add-iam-policy-binding "gs://$BUCKET" --member "serviceAccount:$RUN_SA" \
  --role roles/storage.objectAdmin >/dev/null
for secret in "${SECRETS[@]}"; do
  retry gcloud secrets add-iam-policy-binding "$secret" --member "serviceAccount:$RUN_SA" \
    --role roles/secretmanager.secretAccessor >/dev/null
done

REPO="${TEPHRA_AR_REPO:-tephra}"
IMAGE="$REGION-docker.pkg.dev/$TEPHRA_PROJECT/$REPO/$SERVICE:$(date -u +%Y%m%d-%H%M%S)"
if ! gcloud artifacts repositories describe "$REPO" --location "$REGION" >/dev/null 2>&1; then
  gcloud artifacts repositories create "$REPO" --repository-format=docker --location "$REGION"
fi

cd "$(dirname "$0")/.." || exit 1
gcloud builds submit . --config deploy/cloudbuild.yaml \
  --substitutions "_IMAGE=$IMAGE,_SCIENCE=$science_arg"

gcloud run deploy "$SERVICE" \
  --image "$IMAGE" \
  --region "$REGION" \
  --service-account "$RUN_SA" \
  --allow-unauthenticated \
  --min-instances "$MIN_INSTANCES" \
  --max-instances 1 \
  --no-cpu-throttling \
  --memory "$MEMORY" \
  --cpu 1 \
  --timeout 3600 \
  --set-env-vars "TEPHRA_STORE=firestore,TEPHRA_GCP_PROJECT=$TEPHRA_PROJECT,TEPHRA_GCS_BUCKET=$BUCKET,TEPHRA_LLM=$LLM,TEPHRA_SCIENCE=$SCIENCE,TEPHRA_LOCAL_SCHEDULER=false" \
  --set-secrets "GEMINI_API_KEY=GEMINI_API_KEY:latest,TEPHRA_DESK_PIN=TEPHRA_DESK_PIN:latest,TEPHRA_TASK_TOKEN=TEPHRA_TASK_TOKEN:latest,TEPHRA_SESSION_SECRET=TEPHRA_SESSION_SECRET:latest"

url="$(gcloud run services describe "$SERVICE" --region "$REGION" --format='value(status.url)')"
echo "Deployed: $url"
code="$(curl -s -o /dev/null -w '%{http_code}' "$url/healthz")"
echo "$url/healthz -> $code (expect 200)"
