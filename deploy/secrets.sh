#!/usr/bin/env bash
# Create or update the Secret Manager secrets TEPHRA reads. Values are read from stdin
# without echo and never written to disk.
source "$(dirname "$0")/_common.sh"

SECRETS=(GEMINI_API_KEY TEPHRA_DESK_PIN TEPHRA_TASK_TOKEN TEPHRA_SESSION_SECRET)
confirm "Create/update secrets ${SECRETS[*]}?"

gcloud services enable secretmanager.googleapis.com
for name in "${SECRETS[@]}"; do
  read -r -s -p "Value for $name (empty = skip): " value; echo
  [ -z "$value" ] && { echo "  skipped $name"; continue; }
  if ! gcloud secrets describe "$name" >/dev/null 2>&1; then
    gcloud secrets create "$name" --replication-policy=automatic >/dev/null
  fi
  printf '%s' "$value" | gcloud secrets versions add "$name" --data-file=- >/dev/null
  unset value
  echo "  updated $name"
done
