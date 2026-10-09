#!/usr/bin/env bash
# Build the image with Cloud Build and deploy the single TEPHRA Cloud Run service.
# One instance holds the live state the Wall streams from, so max = 1. Background ADS-B
# passes need CPU outside requests, hence --no-cpu-throttling. Both cost money while the
# instance is up; set TEPHRA_MIN_INSTANCES=0 to scale to zero between ticks (state is
# restored from Firestore on a cold start, at the price of a slower first page).
source "$(dirname "$0")/_common.sh"

MIN_INSTANCES="${TEPHRA_MIN_INSTANCES:-1}"
MEMORY="${TEPHRA_MEMORY:-1Gi}"
SCIENCE="${TEPHRA_SCIENCE:-false}"
BUCKET="${TEPHRA_GCS_BUCKET:?set TEPHRA_GCS_BUCKET (a US-region bucket keeps blobs in the free tier)}"
LLM="${TEPHRA_LLM:-gemini}"
[ "$SCIENCE" = "true" ] && MEMORY="${TEPHRA_MEMORY:-2Gi}"

confirm "Deploy $SERVICE (min $MIN_INSTANCES, max 1, $MEMORY, LLM=$LLM, science=$SCIENCE)?"

gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com \
  firestore.googleapis.com storage.googleapis.com secretmanager.googleapis.com

REPO="${TEPHRA_AR_REPO:-tephra}"
IMAGE="$REGION-docker.pkg.dev/$TEPHRA_PROJECT/$REPO/$SERVICE:$(date -u +%Y%m%d-%H%M%S)"
if ! gcloud artifacts repositories describe "$REPO" --location "$REGION" >/dev/null 2>&1; then
  gcloud artifacts repositories create "$REPO" --repository-format=docker --location "$REGION"
fi

cd "$(dirname "$0")/.."
science_arg=0
[ "$SCIENCE" = "true" ] && science_arg=1
gcloud builds submit . --config deploy/cloudbuild.yaml \
  --substitutions "_IMAGE=$IMAGE,_SCIENCE=$science_arg"

gcloud run deploy "$SERVICE" \
  --image "$IMAGE" \
  --region "$REGION" \
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
