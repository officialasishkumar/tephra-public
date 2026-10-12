#!/usr/bin/env bash
# Build the image with Cloud Build and deploy the single TEPHRA Cloud Run service, gated:
# the new revision gets no traffic until scripts/live_smoke.sh passes against it, and the
# previous revision is named so a rollback is one command. One instance holds the live state
# the Wall streams from, so max = 1.
#
# TEPHRA_HOSTING picks how the instance runs:
#   always-on (default)  --min-instances 1, --no-cpu-throttling, Cloud Scheduler ticks.
#                        The background ADS-B passes need CPU outside requests. Billed all
#                        the time the instance is up: check the Cloud Run free tier first.
#   on-demand            --min-instances 0, --cpu-throttling, TEPHRA_LOCAL_SCHEDULER=true.
#                        UNTESTED: confirm a cold page shows the replay advancing and the bill
#                        stays in the free tier before relying on it. A candidate revision
#                        also ticks itself while its smoke test keeps it up.
#
# By hand it runs from the tephra-personal configuration and asks before deploying. From
# .github/workflows/deploy.yml it runs in CI mode (TEPHRA_DEPLOY_CI=true in GitHub Actions; see
# deploy/_common.sh): no prompt, as the deployer service account, and it only builds and
# rolls out. The one-time setup (APIs, the runtime service account and its grants, the
# Artifact Registry repository and its cleanup policy, the first deploy) stays with a person.
# shellcheck disable=SC2034  # read by deploy/_common.sh
TEPHRA_CI_CAPABLE=1
# shellcheck source=deploy/_common.sh
source "$(dirname "$0")/_common.sh"

if [ -n "${TEPHRA_MIN_INSTANCES:-}" ]; then
  echo "TEPHRA_MIN_INSTANCES is gone: set TEPHRA_HOSTING=always-on or on-demand instead." >&2
  exit 1
fi
HOSTING="${TEPHRA_HOSTING:-always-on}"
MEMORY="${TEPHRA_MEMORY:-1Gi}"
SCIENCE="${TEPHRA_SCIENCE:-false}"
BUCKET="${TEPHRA_GCS_BUCKET:?set TEPHRA_GCS_BUCKET (a US-region bucket keeps blobs in the free tier)}"
LLM="${TEPHRA_LLM:-gemini}"
RUN_SA_NAME="${TEPHRA_RUN_SA:-tephra-run}"
RUN_SA="$RUN_SA_NAME@$TEPHRA_PROJECT.iam.gserviceaccount.com"
SECRETS=(GEMINI_API_KEY TEPHRA_DESK_PIN TEPHRA_TASK_TOKEN TEPHRA_SESSION_SECRET)
# Settings forwarded to the service when they are set in this shell; nothing else is.
FORWARDED=(TEPHRA_MODE TEPHRA_REPLAY_CASE TEPHRA_REPLAY_START TEPHRA_REPLAY_END TEPHRA_REPLAY_SPEED
  TEPHRA_AUTO_REPLAY TEPHRA_REGION TEPHRA_MODEL TEPHRA_MODEL_LITE
  TEPHRA_MODEL_DAILY_BUDGET TEPHRA_MODEL_LITE_DAILY_BUDGET)
KEEP_TAG="${TEPHRA_KEEP_TAG:-}"
# The same value builds the image and switches the app's layer on, so both must agree.
case "$SCIENCE" in
  true) MEMORY="${TEPHRA_MEMORY:-2Gi}"; science_arg=1 ;;
  false) science_arg=0 ;;
  *) echo "TEPHRA_SCIENCE must be 'true' or 'false', not '$SCIENCE'." >&2; exit 1 ;;
esac
case "$HOSTING" in
  always-on) scaling=(--min-instances 1 --no-cpu-throttling); local_scheduler=false ;;
  on-demand) scaling=(--min-instances 0 --cpu-throttling); local_scheduler=true ;;
  *) echo "TEPHRA_HOSTING must be 'always-on' or 'on-demand', not '$HOSTING'." >&2; exit 1 ;;
esac
if [ -n "$KEEP_TAG" ] && ! [[ "$KEEP_TAG" =~ ^keep-[a-z0-9][a-z0-9._-]*$ ]]; then
  echo "TEPHRA_KEEP_TAG must start with 'keep-' (the cleanup policy keeps only those)." >&2
  exit 1
fi

# --- the commit being deployed ----------------------------------------------------------
# Only a clean tree that main already contains is deployed, so the image's commit is the
# whole story of what runs.
cd "$(dirname "$0")/.." || exit 1
if [ -n "$(git status --porcelain)" ]; then
  echo "Refusing: the working tree has changes. Commit them to main first:" >&2
  git status --short >&2
  exit 1
fi
if [ "$CI_MODE" = true ]; then
  # CI: HEAD must be the commit that was pushed, and still the newest on origin/main. A run
  # that a newer push overtook (or a re-run of an old one) stands down instead of rolling
  # the site back; the newer push's own run deploys it.
  git fetch --quiet origin main
  head="$(git rev-parse HEAD)"
  tip="$(git rev-parse FETCH_HEAD)"
  if [ "$head" != "$GITHUB_SHA" ]; then
    echo "Refusing: HEAD ($head) is not the pushed commit ($GITHUB_SHA)." >&2
    exit 1
  fi
  if [ "$head" != "$tip" ]; then
    echo "::notice::Not deploying ${head:0:12}: origin/main is already at ${tip:0:12}, whose own run deploys it."
    echo "Not deploying ${head:0:12}: origin/main has moved on to ${tip:0:12}."
    exit 0
  fi
else
  git fetch origin
  if ! git merge-base --is-ancestor HEAD origin/main; then
    echo "Refusing: HEAD ($(git rev-parse --short=12 HEAD)) is not on origin/main." >&2
    exit 1
  fi
fi
SHA="$(git rev-parse --short=12 HEAD)"

env_vars=(
  "TEPHRA_STORE=firestore"
  "TEPHRA_GCP_PROJECT=$TEPHRA_PROJECT"
  "TEPHRA_GCS_BUCKET=$BUCKET"
  "TEPHRA_LLM=$LLM"
  "TEPHRA_SCIENCE=$SCIENCE"
  "TEPHRA_LOCAL_SCHEDULER=$local_scheduler"
)
for name in "${FORWARDED[@]}"; do
  if [ -n "${!name:-}" ]; then
    env_vars+=("$name=${!name}")
  fi
done
for pair in "${env_vars[@]}"; do
  # gcloud splits --set-env-vars on commas.
  if [[ "$pair" == *,* ]]; then
    echo "Refusing: '$pair' contains a comma, which --set-env-vars would split." >&2
    exit 1
  fi
done
env_list="$(IFS=,; echo "${env_vars[*]}")"

echo "Commit $SHA, hosting $HOSTING, max 1 instance, $MEMORY, as $RUN_SA"
echo "Environment:"
printf '  %s\n' "${env_vars[@]}"
[ -z "$KEEP_TAG" ] || echo "Image also tagged $KEEP_TAG (kept by deploy/ar-cleanup.json)"
confirm "Deploy $SERVICE at $SHA with these settings?"

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

REPO="${TEPHRA_AR_REPO:-tephra}"
# Secret metadata only (does it exist?); the deployer never reads a secret's value.
for secret in "${SECRETS[@]}"; do
  if ! gcloud secrets describe "$secret" >/dev/null 2>&1; then
    echo "Secret $secret does not exist (or this account may not see it); run deploy/secrets.sh first." >&2
    exit 1
  fi
done

if [ "$CI_MODE" = true ]; then
  # The deployer service account holds no rights to enable APIs, create service accounts,
  # change IAM or repository settings; a person did all of that with the first deploy. Check
  # that it is there and go on.
  if ! gcloud iam service-accounts describe "$RUN_SA" >/dev/null 2>&1; then
    echo "Runtime service account $RUN_SA is missing: deploy once by hand first." >&2
    exit 1
  fi
  if ! gcloud artifacts repositories describe "$REPO" --location "$REGION" >/dev/null 2>&1; then
    echo "Artifact Registry repository $REPO is missing: deploy once by hand first." >&2
    exit 1
  fi
else
  gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com \
    firestore.googleapis.com storage.googleapis.com secretmanager.googleapis.com iam.googleapis.com

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

  if ! gcloud artifacts repositories describe "$REPO" --location "$REGION" >/dev/null 2>&1; then
    gcloud artifacts repositories create "$REPO" --repository-format=docker --location "$REGION"
  fi
  # Keep every keep-* tag and the 5 newest images; delete the rest after 30 days, so the
  # repository stays small (storage over the free 0.5 GB is billed) without losing a rollback
  # target or the submitted build. Flags from
  # https://cloud.google.com/artifact-registry/docs/repositories/cleanup-policy
  # (check them there; preview with --dry-run and list with `list-cleanup-policies`).
  gcloud artifacts repositories set-cleanup-policies "$REPO" --location "$REGION" \
    --policy deploy/ar-cleanup.json --no-dry-run
fi

# --- image --------------------------------------------------------------------------------
IMAGE_BASE="$REGION-docker.pkg.dev/$TEPHRA_PROJECT/$REPO/$SERVICE"
IMAGE="$IMAGE_BASE:$SHA-$(date -u +%Y%m%d-%H%M%S)"

# .gcloudignore limits the upload to what the Dockerfile copies.
build_args=(. --config deploy/cloudbuild.yaml
  --substitutions "_IMAGE=$IMAGE,_SCIENCE=$science_arg,_BUILD_SHA=$SHA")
if [ "$CI_MODE" = false ]; then
  gcloud builds submit "${build_args[@]}"
else
  # Streaming the log needs Viewer on the whole project (it is read from Cloud Build's own
  # bucket), and an unnamed staging bucket needs project-wide bucket listing. So: name the
  # staging bucket the hand deploys already use, submit without waiting, and poll the
  # build's status. The log is in the console at the printed link.
  build_id="$(gcloud builds submit "${build_args[@]}" --async \
    --gcs-source-staging-dir "gs://${TEPHRA_PROJECT}_cloudbuild/source" --format='value(id)')"
  echo "Cloud Build $build_id: $(gcloud builds describe "$build_id" --format='value(logUrl)')"
  build_deadline=$((SECONDS + 3600))
  while :; do
    status="$(gcloud builds describe "$build_id" --format='value(status)')"
    case "$status" in
      SUCCESS) echo "Build $build_id: SUCCESS"; break ;;
      QUEUED|PENDING|WORKING) ;;
      *) echo "::error::Cloud Build $build_id ended $status; nothing was deployed."
         echo "Build $build_id ended $status; nothing was deployed." >&2
         exit 1 ;;
    esac
    if [ "$SECONDS" -ge "$build_deadline" ]; then
      echo "Build $build_id still $status after an hour; nothing was deployed." >&2
      exit 1
    fi
    sleep 15
  done
fi
if [ -n "$KEEP_TAG" ]; then
  gcloud artifacts docker tags add "$IMAGE" "$IMAGE_BASE:$KEEP_TAG"
fi

# --- gated rollout ------------------------------------------------------------------------
deploy_args=(
  --image "$IMAGE"
  --region "$REGION"
  --service-account "$RUN_SA"
  "${scaling[@]}"
  --max-instances 1
  --memory "$MEMORY"
  --cpu 1
  --timeout 3600
  --set-env-vars "$env_list"
  --set-secrets "GEMINI_API_KEY=GEMINI_API_KEY:latest,TEPHRA_DESK_PIN=TEPHRA_DESK_PIN:latest,TEPHRA_TASK_TOKEN=TEPHRA_TASK_TOKEN:latest,TEPHRA_SESSION_SECRET=TEPHRA_SESSION_SECRET:latest"
)
# Public access is an IAM binding on the service, which outlives revisions. A person sets it;
# the deployer (roles/run.developer) cannot change IAM, and a revision keeps the binding.
[ "$CI_MODE" = true ] || deploy_args+=(--allow-unauthenticated)
smoke_env=("EXPECT_SHA=$SHA")
[ -z "${TEPHRA_MODE:-}" ] || smoke_env+=("EXPECT_MODE=$TEPHRA_MODE")
[ -z "${TEPHRA_REPLAY_CASE:-}" ] || smoke_env+=("EXPECT_CASE=$TEPHRA_REPLAY_CASE")

describe() {
  gcloud run services describe "$SERVICE" --region "$REGION" --format=json
}
# The one revision serving all traffic; refuses a split, which a person settles first.
serving_revision() {
  python3 -I -c '
import json, sys
svc = json.load(sys.stdin)
full = [t for t in svc["status"].get("traffic", []) if t.get("percent") == 100]
if len(full) != 1:
    sys.exit("traffic is not on one revision; settle it before deploying")
entry = full[0]
print(entry.get("revisionName") or svc["status"]["latestReadyRevisionName"])
'
}
tag_url() {
  python3 -I -c '
import json, sys
svc = json.load(sys.stdin)
urls = [t["url"] for t in svc["status"].get("traffic", []) if t.get("tag") == sys.argv[1]]
if not urls:
    sys.exit("no traffic tag " + sys.argv[1])
print(urls[0])
' "$1"
}
report_revision() {
  local digest
  digest="$(gcloud run revisions describe "$1" --region "$REGION" --format='value(status.imageDigest)')"
  echo "Revision: $1"
  echo "Image:    $digest"
}

# In CI, and in the step summary on the run's page, so the outcome is visible without the log.
summary() {
  [ "$CI_MODE" = true ] && [ -n "${GITHUB_STEP_SUMMARY:-}" ] || return 0
  printf '%s\n' "$@" >>"$GITHUB_STEP_SUMMARY"
}
# How a person rolls back: from the tephra-personal configuration (CI never rolls back).
person_config="${TEPHRA_GCLOUD_CONFIG:-tephra-personal}"

if ! gcloud run services describe "$SERVICE" --region "$REGION" >/dev/null 2>&1; then
  if [ "$CI_MODE" = true ]; then
    echo "Service $SERVICE does not exist in $REGION: the first deploy is done by hand." >&2
    exit 1
  fi
  # First create: --no-traffic is refused, so the first revision takes all traffic.
  gcloud run deploy "$SERVICE" "${deploy_args[@]}"
  svc="$(describe)"
  url="$(python3 -I -c 'import json,sys; print(json.load(sys.stdin)["status"]["url"])' <<<"$svc")"
  rev="$(python3 -I -c 'import json,sys; print(json.load(sys.stdin)["status"]["latestReadyRevisionName"])' <<<"$svc")"
  report_revision "$rev"
  echo "First deploy: $url"
  # No Scheduler job yet, so no ticks: read-only until deploy/scheduler.sh has run.
  if ! env "${smoke_env[@]}" scripts/live_smoke.sh "$url" --read-only; then
    echo "Smoke test FAILED on the first revision. Fix it and deploy again." >&2
    exit 1
  fi
  echo "Next: deploy/scheduler.sh, then scripts/live_smoke.sh $url (full check)."
  [ "$HOSTING" = always-on ] || echo "on-demand: skip scheduler.sh; the instance ticks itself."
  exit 0
fi

PREV="$(describe | serving_revision)"
echo "Serving now: $PREV"
gcloud run deploy "$SERVICE" "${deploy_args[@]}" --no-traffic --tag candidate
svc="$(describe)"
CANDIDATE="$(python3 -I -c 'import json,sys; print(json.load(sys.stdin)["status"]["latestCreatedRevisionName"])' <<<"$svc")"
candidate_url="$(tag_url candidate <<<"$svc")"
url="$(python3 -I -c 'import json,sys; print(json.load(sys.stdin)["status"]["url"])' <<<"$svc")"
report_revision "$CANDIDATE"
rollback="gcloud run services update-traffic $SERVICE --region $REGION --to-revisions $PREV=100"

# Read-only: the candidate gets no Scheduler ticks, and nothing is POSTed to it.
echo "Smoke test of the candidate at $candidate_url"
if ! env "${smoke_env[@]}" scripts/live_smoke.sh "$candidate_url" --read-only; then
  echo "Candidate $CANDIDATE FAILED its smoke test. Traffic was not moved: $PREV still serves." >&2
  [ "$CI_MODE" = false ] || echo "::error::Candidate $CANDIDATE failed its smoke test; traffic stays on $PREV."
  summary "### Not deployed: $SHA" "" "Candidate \`$CANDIDATE\` failed its read-only smoke test." \
    "Traffic was not moved: \`$PREV\` still serves $url."
  exit 1
fi

gcloud run services update-traffic "$SERVICE" --region "$REGION" --to-revisions "$CANDIDATE=100"
echo "Smoke test of $url after moving traffic to $CANDIDATE"
if ! env "${smoke_env[@]}" scripts/live_smoke.sh "$url"; then
  echo "The live URL FAILED its smoke test on $CANDIDATE. Traffic was left as it is." >&2
  echo "Roll back with (CLOUDSDK_ACTIVE_CONFIG_NAME=$person_config):" >&2
  echo "  $rollback" >&2
  [ "$CI_MODE" = false ] || echo "::error::$url failed its smoke test on $CANDIDATE (traffic left on it). Roll back: $rollback"
  summary "### Live smoke test FAILED: $SHA" "" "Traffic is on \`$CANDIDATE\` (was \`$PREV\`); it was left as it is." \
    "" "Roll back with (\`CLOUDSDK_ACTIVE_CONFIG_NAME=$person_config\`):" "" '```' "$rollback" '```'
  exit 1
fi
if [ "$HOSTING" = on-demand ]; then
  echo "on-demand: the instance ticks itself, so pause the Scheduler job if it exists:"
  echo "  CLOUDSDK_ACTIVE_CONFIG_NAME=$person_config gcloud scheduler jobs pause ${TEPHRA_SCHEDULER_JOB:-tephra-tick} --location $REGION"
fi
echo "Deployed $SHA as $CANDIDATE at $url (previous: $PREV)."
echo "Roll back with: $rollback"
summary "### Deployed $SHA" "" "Revision \`$CANDIDATE\` serves $url (previous: \`$PREV\`)." \
  "" "Roll back with (\`CLOUDSDK_ACTIVE_CONFIG_NAME=$person_config\`):" "" '```' "$rollback" '```'
echo "Reload any open Wall and Desk so they load the new code."
