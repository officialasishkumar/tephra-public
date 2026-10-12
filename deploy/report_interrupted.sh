#!/usr/bin/env bash
# Run by .github/workflows/deploy.yml after deploy/cloudrun.sh did not succeed. When cloudrun.sh
# ended on its own it has already written the run's summary (stage "reported") and this says
# nothing more. When it was stopped part-way (the step's time limit, a cancelled run, a crash),
# this reads how far it got from $STAGE_FILE and puts on the summary where traffic was left
# and the rollback command. It runs no gcloud and changes nothing.
set -euo pipefail

stage="" sha="" prev="" candidate="" url="" rollback=""
if [ -n "${STAGE_FILE:-}" ] && [ -f "$STAGE_FILE" ]; then
  while IFS='=' read -r key value; do
    case "$key" in
      stage) stage="$value" ;;
      sha) sha="$value" ;;
      prev) prev="$value" ;;
      candidate) candidate="$value" ;;
      url) url="$value" ;;
      rollback) rollback="$value" ;;
    esac
  done <"$STAGE_FILE"
fi

case "$stage" in
  reported) exit 0 ;;
  "" | checks | building)
    title="Not deployed${sha:+: $sha}"
    lines=("The deploy step ended ${OUTCOME:-unexpectedly} before any new revision was deployed." \
      "Traffic was not touched.") ;;
  candidate)
    title="Stopped while deploying the candidate: $sha"
    lines=("The deploy step ended ${OUTCOME:-unexpectedly} while deploying or testing the candidate${candidate:+ \`$candidate\`}, which has no traffic." \
      "Traffic was not moved: \`$prev\` still serves $url.") ;;
  moving-traffic | traffic-moved)
    title="Stopped after moving traffic: $sha"
    lines=("The deploy step ended ${OUTCOME:-unexpectedly} after (or while) moving traffic to \`$candidate\` (was \`$prev\`), before the live smoke test finished." \
      "Run \`scripts/live_smoke.sh $url\` and, if the site is broken, roll back with (\`CLOUDSDK_ACTIVE_CONFIG_NAME=tephra-personal\`):" \
      "" '```' "$rollback" '```') ;;
  *)
    title="Stopped at an unknown stage ($stage)"
    lines=("Check the service's traffic in the Cloud Run console before anything else.") ;;
esac

echo "::error::$title. ${lines[0]}"
printf '%s\n' "${lines[@]}" >&2
if [ -n "${GITHUB_STEP_SUMMARY:-}" ]; then
  printf '%s\n' "### $title" "" "${lines[@]}" >>"$GITHUB_STEP_SUMMARY"
fi
