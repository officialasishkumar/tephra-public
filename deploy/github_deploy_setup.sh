#!/usr/bin/env bash
# One-time setup so .github/workflows/deploy.yml can deploy on every push to main, with no key
# stored anywhere: GitHub's OIDC token for this repository's main branch is exchanged through
# workload identity federation for a short-lived token of a deployer service account that can
# only build and roll out TEPHRA. You run this by hand, once; it prints every gcloud command
# and asks before each one that changes anything. Rerunning it is safe.
#
# It creates:
#   - workload identity pool $POOL and OIDC provider $PROVIDER_ID for
#     https://token.actions.githubusercontent.com, accepting only tokens from the deploy
#     workflow of $GITHUB_REPO on refs/heads/main (checked by name and by numeric id);
#   - service account $DEPLOY_SA_NAME with:
#       roles/run.developer                    project  deploy revisions, move traffic (no IAM)
#       roles/cloudbuild.builds.editor         project  submit the image build, read its status
#       roles/serviceusage.serviceUsageConsumer project  call the APIs on the project's quota
#       roles/iam.serviceAccountUser           on the runtime account only (deploy as it)
#       roles/artifactregistry.writer          on the $REPO repository only (push, tag)
#       roles/storage.objectCreator +
#       roles/storage.legacyBucketReader       on the Cloud Build staging bucket only
#       roles/secretmanager.viewer             on the four secrets only (metadata, not values)
#   - roles/iam.workloadIdentityUser on that account for the repository's principal set.
#
# Then it prints the two values for .github/workflows/deploy.yml and offers to write them in.
# shellcheck source=deploy/_common.sh
source "$(dirname "$0")/_common.sh"

POOL="${TEPHRA_WIF_POOL:-github-actions}"
PROVIDER_ID="${TEPHRA_WIF_PROVIDER_ID:-tephra-main}"
DEPLOY_SA_NAME="${TEPHRA_DEPLOY_SA_NAME:-tephra-deployer}"
DEPLOY_SA="$DEPLOY_SA_NAME@$TEPHRA_PROJECT.iam.gserviceaccount.com"
GITHUB_REPO="${TEPHRA_GITHUB_REPO:-officialasishkumar/tephra}"
GITHUB_OWNER="${GITHUB_REPO%%/*}"
# Numeric ids survive a rename: a new repository later given the same name gets a new id, so
# it could not use this trust. From `gh api repos/$GITHUB_REPO --jq '.id, .owner.id'`.
GITHUB_REPO_ID="${TEPHRA_GITHUB_REPO_ID:-1412347651}"
GITHUB_OWNER_ID="${TEPHRA_GITHUB_OWNER_ID:-87874775}"
WORKFLOW_REF="$GITHUB_REPO/.github/workflows/deploy.yml@refs/heads/main"
RUN_SA="${TEPHRA_RUN_SA:-tephra-run}@$TEPHRA_PROJECT.iam.gserviceaccount.com"
REPO="${TEPHRA_AR_REPO:-tephra}"
STAGING_BUCKET="${TEPHRA_PROJECT}_cloudbuild"
SECRETS=(GEMINI_API_KEY TEPHRA_DESK_PIN TEPHRA_TASK_TOKEN TEPHRA_SESSION_SECRET)
WORKFLOW_FILE="$(cd "$(dirname "$0")/.." && pwd)/.github/workflows/deploy.yml"

for value in "$GITHUB_REPO_ID" "$GITHUB_OWNER_ID"; do
  [[ "$value" =~ ^[0-9]+$ ]] || { echo "GitHub ids must be numbers, not '$value'." >&2; exit 1; }
done

# Print a command, ask, then run it. "n" skips just that one.
step() {
  echo
  printf '$'; printf ' %q' "$@"; echo
  read -r -p "Run it? [y/N] " answer
  if [ "$answer" = "y" ] || [ "$answer" = "Y" ]; then
    "$@"
  else
    echo "  skipped"
  fi
}
# Read-only lookups are printed but not asked about.
# The command line goes to stderr so that a lookup's answer can be captured from stdout.
look() {
  { printf '(read-only) $'; printf ' %q' "$@"; echo; } >&2
  "$@"
}

confirm "Set up GitHub Actions deploys for $GITHUB_REPO (main) through pool $POOL, provider $PROVIDER_ID, deployer $DEPLOY_SA?"

# What the deploys build on must already exist: a hand deploy (deploy/cloudrun.sh) makes it.
missing=0
look gcloud run services describe "$SERVICE" --region "$REGION" --format='value(status.url)' \
  || { echo "  Service $SERVICE is missing." >&2; missing=1; }
look gcloud iam service-accounts describe "$RUN_SA" --format='value(email)' \
  || { echo "  Runtime account $RUN_SA is missing." >&2; missing=1; }
look gcloud artifacts repositories describe "$REPO" --location "$REGION" --format='value(name)' \
  || { echo "  Artifact Registry repository $REPO is missing." >&2; missing=1; }
look gcloud storage buckets describe "gs://$STAGING_BUCKET" --format='value(name)' \
  || { echo "  Cloud Build staging bucket gs://$STAGING_BUCKET is missing." >&2; missing=1; }
for secret in "${SECRETS[@]}"; do
  look gcloud secrets describe "$secret" --format='value(name)' \
    || { echo "  Secret $secret is missing." >&2; missing=1; }
done
if [ "$missing" -ne 0 ]; then
  echo "Deploy once by hand (deploy/secrets.sh, deploy/cloudrun.sh) first, then rerun this." >&2
  exit 1
fi
PROJECT_NUMBER="$(look gcloud projects describe "$TEPHRA_PROJECT" --format='value(projectNumber)')"
[[ "$PROJECT_NUMBER" =~ ^[0-9]+$ ]] || { echo "Could not read the project number." >&2; exit 1; }
POOL_NAME="projects/$PROJECT_NUMBER/locations/global/workloadIdentityPools/$POOL"
PROVIDER_NAME="$POOL_NAME/providers/$PROVIDER_ID"

# --- federation ---------------------------------------------------------------------------
step gcloud services enable iamcredentials.googleapis.com sts.googleapis.com iam.googleapis.com

if ! look gcloud iam workload-identity-pools describe "$POOL" --location global --format='value(name)'; then
  step gcloud iam workload-identity-pools create "$POOL" --location global \
    --display-name "GitHub Actions" --description "OIDC tokens from GitHub Actions for TEPHRA deploys"
fi

# google.subject is "repo:<owner>/<repo>:ref:refs/heads/main" for these tokens. The condition
# is the real gate: only this repository (by name and id), its owner, the main branch and the
# deploy workflow file. A fork, another branch, a pull request or another workflow gets nothing.
mapping="google.subject=assertion.sub,attribute.repository=assertion.repository"
mapping+=",attribute.repository_owner=assertion.repository_owner,attribute.ref=assertion.ref"
condition="assertion.repository=='$GITHUB_REPO'"
condition+=" && assertion.repository_id=='$GITHUB_REPO_ID'"
condition+=" && assertion.repository_owner=='$GITHUB_OWNER'"
condition+=" && assertion.repository_owner_id=='$GITHUB_OWNER_ID'"
condition+=" && assertion.ref=='refs/heads/main'"
condition+=" && assertion.workflow_ref=='$WORKFLOW_REF'"
provider_flags=(--location global --workload-identity-pool "$POOL"
  --attribute-mapping "$mapping" --attribute-condition "$condition")
if look gcloud iam workload-identity-pools providers describe "$PROVIDER_ID" \
     --location global --workload-identity-pool "$POOL" --format='value(name)'; then
  step gcloud iam workload-identity-pools providers update-oidc "$PROVIDER_ID" "${provider_flags[@]}"
else
  step gcloud iam workload-identity-pools providers create-oidc "$PROVIDER_ID" "${provider_flags[@]}" \
    --display-name "TEPHRA main" --issuer-uri "https://token.actions.githubusercontent.com"
fi

# --- the deployer and its grants ----------------------------------------------------------
if ! look gcloud iam service-accounts describe "$DEPLOY_SA" --format='value(email)'; then
  step gcloud iam service-accounts create "$DEPLOY_SA_NAME" \
    --display-name "TEPHRA deployer (GitHub Actions, main only)"
fi
member="serviceAccount:$DEPLOY_SA"

for role in roles/run.developer roles/cloudbuild.builds.editor roles/serviceusage.serviceUsageConsumer; do
  step gcloud projects add-iam-policy-binding "$TEPHRA_PROJECT" --member "$member" \
    --role "$role" --condition=None --format=none
done
step gcloud iam service-accounts add-iam-policy-binding "$RUN_SA" --member "$member" \
  --role roles/iam.serviceAccountUser --format=none
step gcloud artifacts repositories add-iam-policy-binding "$REPO" --location "$REGION" \
  --member "$member" --role roles/artifactregistry.writer --format=none
for role in roles/storage.objectCreator roles/storage.legacyBucketReader; do
  step gcloud storage buckets add-iam-policy-binding "gs://$STAGING_BUCKET" --member "$member" \
    --role "$role" --format=none
done
for secret in "${SECRETS[@]}"; do
  step gcloud secrets add-iam-policy-binding "$secret" --member "$member" \
    --role roles/secretmanager.viewer --format=none
done

# Only tokens that passed the provider's condition belong to this principal set.
step gcloud iam service-accounts add-iam-policy-binding "$DEPLOY_SA" \
  --role roles/iam.workloadIdentityUser \
  --member "principalSet://iam.googleapis.com/$POOL_NAME/attribute.repository/$GITHUB_REPO" \
  --format=none

# --- the build's own service account ------------------------------------------------------
build_sa="$(look gcloud builds get-default-service-account --format='value(serviceAccountEmail)' || true)"
build_sa="${build_sa##*/}"
echo
echo "Cloud Build runs builds as: ${build_sa:-unknown}"
if [ -n "$build_sa" ] && [[ "$build_sa" != *@cloudbuild.gserviceaccount.com ]]; then
  echo "  That is not the legacy Cloud Build account. If the first Actions build fails with a"
  echo "  permission error naming iam.serviceAccounts.actAs on it, grant only that, then re-run"
  echo "  the workflow:"
  echo "    gcloud iam service-accounts add-iam-policy-binding $build_sa \\"
  echo "      --member $member --role roles/iam.serviceAccountUser"
fi

# --- the two values for the workflow ------------------------------------------------------
echo
echo "Put these two values in .github/workflows/deploy.yml (env: at the top):"
echo "  TEPHRA_WIF_PROVIDER: $PROVIDER_NAME"
echo "    (replaces REPLACE_WITH_WIF_PROVIDER)"
echo "  TEPHRA_DEPLOY_SA: $DEPLOY_SA"
echo "    (replaces REPLACE_WITH_DEPLOY_SA)"
if [ -f "$WORKFLOW_FILE" ] && grep -q 'REPLACE_WITH_' "$WORKFLOW_FILE"; then
  read -r -p "Write them into $WORKFLOW_FILE now? [y/N] " answer
  if [ "$answer" = "y" ] || [ "$answer" = "Y" ]; then
    python3 -I - "$WORKFLOW_FILE" "$PROVIDER_NAME" "$DEPLOY_SA" <<'PY'
import sys

path, provider, account = sys.argv[1:4]
with open(path, encoding="utf-8") as handle:
    text = handle.read()
text = text.replace("REPLACE_WITH_WIF_PROVIDER", provider)
text = text.replace("REPLACE_WITH_DEPLOY_SA", account)
with open(path, "w", encoding="utf-8") as handle:
    handle.write(text)
PY
    echo "  Written. Review with git diff, then commit and push it to main: that push deploys."
  fi
fi
echo
echo "Watch the run in the repository's Actions tab (workflow 'deploy')."
