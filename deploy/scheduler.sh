#!/usr/bin/env bash
# One Cloud Scheduler job (inside the 3 free jobs) that POSTs /tasks/tick every minute.
# shellcheck source=deploy/_common.sh
source "$(dirname "$0")/_common.sh"

JOB="${TEPHRA_SCHEDULER_JOB:-tephra-tick}"
url="$(gcloud run services describe "$SERVICE" --region "$REGION" --format='value(status.url)')"
[ -n "$url" ] || { echo "Deploy the service first (deploy/cloudrun.sh)." >&2; exit 1; }
token="$(gcloud secrets versions access latest --secret=TEPHRA_TASK_TOKEN)"
# gcloud splits a header list on commas, so a token with one would be cut short and every
# tick refused with 403. Hex (openssl rand -hex 32) or base64 tokens are safe.
if ! [[ "$token" =~ ^[A-Za-z0-9._~+/=-]+$ ]]; then
  echo "Refusing: TEPHRA_TASK_TOKEN must be letters, digits and . _ ~ + / = - only." >&2
  echo "  Set a new one with deploy/secrets.sh (for example: openssl rand -hex 32)." >&2
  exit 1
fi

confirm "Create/update Scheduler job $JOB -> POST $url/tasks/tick every minute?"
gcloud services enable cloudscheduler.googleapis.com

common=(--location "$REGION" --schedule "* * * * *" --time-zone "Etc/UTC"
        --uri "$url/tasks/tick" --http-method POST
        --message-body '{}' --attempt-deadline 120s)
# --- B06 (own commit; the owner checks these flags against `gcloud scheduler jobs create http --help`)
# A tick that fails (the instance restarting) is tried again twice within the same minute's
# window: 10 s, then 20 s later, so a lost minute is rare and a slow tick is never doubled
# up for long. The next minute's job is a fresh attempt either way.
common+=(--max-retry-attempts 2 --min-backoff 10s --max-backoff 30s --max-doublings 1)
# --- end B06 ------------------------------------------------------------------------------
headers="X-Tephra-Task-Token=$token,Content-Type=application/json"
if gcloud scheduler jobs describe "$JOB" --location "$REGION" >/dev/null 2>&1; then
  # "jobs update http" has no --headers flag; --update-headers replaces these two keys.
  gcloud scheduler jobs update http "$JOB" "${common[@]}" --update-headers "$headers"
else
  gcloud scheduler jobs create http "$JOB" "${common[@]}" --headers "$headers"
fi
unset token headers
echo "Scheduler job $JOB ready."
