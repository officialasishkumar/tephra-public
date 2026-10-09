#!/usr/bin/env bash
# One Cloud Scheduler job (inside the 3 free jobs) that POSTs /tasks/tick every minute.
source "$(dirname "$0")/_common.sh"

JOB="${TEPHRA_SCHEDULER_JOB:-tephra-tick}"
url="$(gcloud run services describe "$SERVICE" --region "$REGION" --format='value(status.url)')"
[ -n "$url" ] || { echo "Deploy the service first (deploy/cloudrun.sh)." >&2; exit 1; }
token="$(gcloud secrets versions access latest --secret=TEPHRA_TASK_TOKEN)"

confirm "Create/update Scheduler job $JOB -> POST $url/tasks/tick every minute?"
gcloud services enable cloudscheduler.googleapis.com

common=(--location "$REGION" --schedule "* * * * *" --time-zone "Etc/UTC"
        --uri "$url/tasks/tick" --http-method POST
        --headers "X-Tephra-Task-Token=$token,Content-Type=application/json"
        --message-body '{}' --attempt-deadline 120s)
if gcloud scheduler jobs describe "$JOB" --location "$REGION" >/dev/null 2>&1; then
  gcloud scheduler jobs update http "$JOB" "${common[@]}"
else
  gcloud scheduler jobs create http "$JOB" "${common[@]}"
fi
unset token
echo "Scheduler job $JOB ready."
