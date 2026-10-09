# Sourced by the deploy scripts. Pins a dedicated gcloud configuration and refuses to run
# unless it is logged into the account and project you named. These scripts are for you to
# run by hand; no agent runs them.
set -euo pipefail

: "${TEPHRA_GCLOUD_ACCOUNT:?set TEPHRA_GCLOUD_ACCOUNT to your personal Google account}"
: "${TEPHRA_PROJECT:?set TEPHRA_PROJECT to your personal Google Cloud project id}"
export CLOUDSDK_ACTIVE_CONFIG_NAME="${TEPHRA_GCLOUD_CONFIG:-tephra-personal}"
REGION="${TEPHRA_GCP_REGION:-asia-southeast1}"
SERVICE="${TEPHRA_SERVICE:-tephra}"

if ! gcloud config configurations describe "$CLOUDSDK_ACTIVE_CONFIG_NAME" >/dev/null 2>&1; then
  echo "gcloud configuration '$CLOUDSDK_ACTIVE_CONFIG_NAME' does not exist. Create it with:" >&2
  echo "  gcloud config configurations create $CLOUDSDK_ACTIVE_CONFIG_NAME --no-activate" >&2
  echo "  CLOUDSDK_ACTIVE_CONFIG_NAME=$CLOUDSDK_ACTIVE_CONFIG_NAME gcloud auth login" >&2
  exit 1
fi

active_account="$(gcloud config get-value account 2>/dev/null)"
active_project="$(gcloud config get-value project 2>/dev/null)"
if [ "$active_account" != "$TEPHRA_GCLOUD_ACCOUNT" ]; then
  echo "Refusing: configuration '$CLOUDSDK_ACTIVE_CONFIG_NAME' is logged in as '$active_account'," >&2
  echo "not '$TEPHRA_GCLOUD_ACCOUNT'." >&2
  exit 1
fi
if [ "$active_project" != "$TEPHRA_PROJECT" ]; then
  echo "Refusing: configuration project is '$active_project', not '$TEPHRA_PROJECT'." >&2
  echo "  gcloud config set project $TEPHRA_PROJECT   (with CLOUDSDK_ACTIVE_CONFIG_NAME=$CLOUDSDK_ACTIVE_CONFIG_NAME)" >&2
  exit 1
fi

confirm() {
  echo
  echo "Account: $active_account   Project: $active_project   Region: $REGION   Service: $SERVICE"
  read -r -p "$1 [y/N] " answer
  [ "$answer" = "y" ] || [ "$answer" = "Y" ] || { echo "Aborted."; exit 1; }
}
