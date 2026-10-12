# shellcheck shell=bash
# Sourced by the deploy scripts. Pins a dedicated gcloud configuration and refuses to run
# unless it is logged into the account and project you named. These scripts are for you to
# run by hand; no agent runs them.
#
# CI mode (deploy/cloudrun.sh only, from .github/workflows/deploy.yml): when
# TEPHRA_DEPLOY_CI=true AND GITHUB_ACTIONS=true, there is no tephra-personal configuration and
# nobody to answer a prompt. The guard then requires instead that gcloud is the deployer
# service account named in TEPHRA_DEPLOY_SA (through the workload identity federation
# credential that google-github-actions/auth wrote, and nothing else), in TEPHRA_PROJECT, for
# the repository and branch in TEPHRA_GITHUB_REPO and refs/heads/main.
set -euo pipefail

: "${TEPHRA_PROJECT:?set TEPHRA_PROJECT to your personal Google Cloud project id}"
REGION="${TEPHRA_GCP_REGION:-asia-southeast1}"
SERVICE="${TEPHRA_SERVICE:-tephra}"

CI_MODE=false
if [ "${TEPHRA_DEPLOY_CI:-}" = true ]; then
  if [ "${GITHUB_ACTIONS:-}" != true ]; then
    echo "Refusing: TEPHRA_DEPLOY_CI=true is only for .github/workflows/deploy.yml in GitHub" >&2
    echo "Actions. Unset it to deploy by hand from the tephra-personal configuration." >&2
    exit 1
  fi
  # Only cloudrun.sh sets TEPHRA_CI_CAPABLE before sourcing this file; secrets, the Scheduler
  # job, monitoring and the federation setup stay with a person.
  if [ "${TEPHRA_CI_CAPABLE:-}" != 1 ]; then
    echo "Refusing: $(basename "$0") never runs in CI; only deploy/cloudrun.sh does." >&2
    exit 1
  fi
  CI_MODE=true
fi

if [ "$CI_MODE" = true ]; then
  : "${TEPHRA_DEPLOY_SA:?set TEPHRA_DEPLOY_SA to the deployer service account (deploy/github_deploy_setup.sh prints it)}"
  : "${TEPHRA_WIF_PROVIDER:?set TEPHRA_WIF_PROVIDER to the workload identity provider (deploy/github_deploy_setup.sh prints it)}"
  GITHUB_REPO="${TEPHRA_GITHUB_REPO:-officialasishkumar/tephra}"
  if [[ "$TEPHRA_DEPLOY_SA" != *.iam.gserviceaccount.com ]] || [[ "$TEPHRA_WIF_PROVIDER" != projects/*/providers/* ]]; then
    echo "Refusing: TEPHRA_DEPLOY_SA or TEPHRA_WIF_PROVIDER is still a placeholder in" >&2
    echo "  .github/workflows/deploy.yml. Run deploy/github_deploy_setup.sh and fill them in." >&2
    exit 1
  fi
  if [ "${GITHUB_REPOSITORY:-}" != "$GITHUB_REPO" ] || [ "${GITHUB_REF:-}" != refs/heads/main ] \
     || [ -z "${GITHUB_SHA:-}" ]; then
    echo "Refusing: CI deploys run only for $GITHUB_REPO on refs/heads/main" >&2
    echo "  (this is ${GITHUB_REPOSITORY:-?} on ${GITHUB_REF:-?})." >&2
    exit 1
  fi
  TEPHRA_GCLOUD_ACCOUNT="$TEPHRA_DEPLOY_SA"
else
  : "${TEPHRA_GCLOUD_ACCOUNT:?set TEPHRA_GCLOUD_ACCOUNT to your personal Google account}"
  export CLOUDSDK_ACTIVE_CONFIG_NAME="${TEPHRA_GCLOUD_CONFIG:-tephra-personal}"

  if [ "$CLOUDSDK_ACTIVE_CONFIG_NAME" = "default" ]; then
    echo "Refusing: use a named gcloud configuration for the personal account, never 'default'." >&2
    exit 1
  fi

  if ! gcloud config configurations describe "$CLOUDSDK_ACTIVE_CONFIG_NAME" >/dev/null 2>&1; then
    echo "gcloud configuration '$CLOUDSDK_ACTIVE_CONFIG_NAME' does not exist. Create it with:" >&2
    echo "  gcloud config configurations create $CLOUDSDK_ACTIVE_CONFIG_NAME --no-activate" >&2
    echo "  CLOUDSDK_ACTIVE_CONFIG_NAME=$CLOUDSDK_ACTIVE_CONFIG_NAME gcloud auth login" >&2
    exit 1
  fi
fi

active_account="$(gcloud config get-value account 2>/dev/null)"
active_project="$(gcloud config get-value project 2>/dev/null)"
where="configuration '${CLOUDSDK_ACTIVE_CONFIG_NAME:-}'"
[ "$CI_MODE" = false ] || where="the CI gcloud"
if [ "$active_account" != "$TEPHRA_GCLOUD_ACCOUNT" ]; then
  echo "Refusing: $where is logged in as '$active_account'," >&2
  echo "not '$TEPHRA_GCLOUD_ACCOUNT'." >&2
  exit 1
fi
if [ "$active_project" != "$TEPHRA_PROJECT" ]; then
  echo "Refusing: $where has project '$active_project', not '$TEPHRA_PROJECT'." >&2
  [ "$CI_MODE" = true ] || \
    echo "  gcloud config set project $TEPHRA_PROJECT   (with CLOUDSDK_ACTIVE_CONFIG_NAME=$CLOUDSDK_ACTIVE_CONFIG_NAME)" >&2
  exit 1
fi

# The one credential file CI mode accepts: the external-account (federation) file that
# google-github-actions/auth wrote for this job, outside the checkout, which impersonates
# exactly TEPHRA_DEPLOY_SA through exactly TEPHRA_WIF_PROVIDER. It holds no key.
federation_file_ok() {
  local path="$1" checkout
  checkout="$(cd "$(dirname "$0")/.." && pwd -P)"
  [ "$CI_MODE" = true ] && [ -n "${GOOGLE_GHA_CREDS_PATH:-}" ] && [ "$path" = "$GOOGLE_GHA_CREDS_PATH" ] \
    && [ -f "$path" ] && [[ "$(cd "$(dirname "$path")" && pwd -P)/" != "$checkout/"* ]] \
    && python3 -I - "$path" "$TEPHRA_DEPLOY_SA" "$TEPHRA_WIF_PROVIDER" <<'PY'
import json
import sys

path, account, provider = sys.argv[1:4]
with open(path, encoding="utf-8") as handle:
    cred = json.load(handle)
impersonate = cred.get("service_account_impersonation_url", "")
ok = (
    cred.get("type") == "external_account"
    and cred.get("audience") == f"//iam.googleapis.com/{provider}"
    and impersonate.endswith(f"/serviceAccounts/{account}:generateAccessToken")
)
sys.exit(0 if ok else 1)
PY
}

# Each of these makes gcloud act as someone other than the account checked above, whether it
# is set in the configuration or through a CLOUDSDK_AUTH_* environment variable. CI mode lets
# through only the federation file described above.
for property in auth/access_token_file auth/credential_file_override auth/impersonate_service_account; do
  value="$(gcloud config get-value "$property" 2>/dev/null)"
  [ -n "$value" ] || continue
  if [ "$property" = auth/credential_file_override ] && federation_file_ok "$value"; then
    continue
  fi
  echo "Refusing: gcloud property $property is set, so commands would not run as" >&2
  echo "'$TEPHRA_GCLOUD_ACCOUNT'. Unset it (or its CLOUDSDK_AUTH_* variable) first." >&2
  exit 1
done
unset value

confirm() {
  echo
  echo "Account: $active_account   Project: $active_project   Region: $REGION   Service: $SERVICE"
  if [ "$CI_MODE" = true ]; then
    # The push to main is the go-ahead; the gate below (candidate smoke test) still applies.
    echo "$1 -> yes (CI: push to main by ${GITHUB_ACTOR:-?}, run ${GITHUB_RUN_ID:-?})"
    return 0
  fi
  read -r -p "$1 [y/N] " answer
  [ "$answer" = "y" ] || [ "$answer" = "Y" ] || { echo "Aborted."; exit 1; }
}
