#!/usr/bin/env bash
# Create or update the Secret Manager secrets TEPHRA reads. Values are read from stdin
# without echo and never written to disk.
# shellcheck source=deploy/_common.sh
source "$(dirname "$0")/_common.sh"

SECRETS=(GEMINI_API_KEY TEPHRA_DESK_PIN TEPHRA_TASK_TOKEN TEPHRA_SESSION_SECRET)
confirm "Create/update secrets ${SECRETS[*]}?"

# tephra/config.py refuses to start with a session secret or task token under 32 characters
# (MIN_SECRET_CHARS), and the token travels in an HTTP header that gcloud splits on commas.
check() {
  case "$1" in
    TEPHRA_SESSION_SECRET) [ "${#2}" -ge 32 ] ;;
    TEPHRA_TASK_TOKEN) [ "${#2}" -ge 32 ] && [[ "$2" =~ ^[A-Za-z0-9._~+/=-]+$ ]] ;;
    *) true ;;
  esac
}

gcloud services enable secretmanager.googleapis.com
for name in "${SECRETS[@]}"; do
  read -r -s -p "Value for $name (empty = skip): " value; echo
  [ -z "$value" ] && { echo "  skipped $name"; continue; }
  if ! check "$name" "$value"; then
    unset value
    echo "Refusing $name: use 32+ characters of letters, digits and . _ ~ + / = -" >&2
    echo "  (for example: openssl rand -hex 32). Nothing was stored for it." >&2
    exit 1
  fi
  if ! gcloud secrets describe "$name" >/dev/null 2>&1; then
    gcloud secrets create "$name" --replication-policy=automatic >/dev/null
  fi
  printf '%s' "$value" | gcloud secrets versions add "$name" --data-file=- >/dev/null
  unset value
  echo "  updated $name"
done
