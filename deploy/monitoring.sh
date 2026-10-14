#!/usr/bin/env bash
# Optional Cloud Monitoring for TEPHRA: three log-based metrics read from the service's JSON
# log lines, one dashboard, and (only with TEPHRA_MONITORING_ALERTS=true) one email channel
# and two alert policies. The app runs the same without any of it.
#
# Check current pricing for log-based metrics, alert policies and uptime checks before you run
# this: Google changes these prices, and TEPHRA is meant to stay on free services.
#
# Metrics (labels are only tier and outcome; never a volcano, flight, prompt or name):
#   gemini_calls       counter of jsonPayload.event="gemini_call" lines, by tier and outcome
#   gemini_latency_ms  distribution of jsonPayload.latency_ms for calls that reached Gemini
#   tephra_ticks       counter of the scheduler's "tick <reason>: ..." line
# Every gcloud command is printed before it runs.
# shellcheck source=deploy/_common.sh
source "$(dirname "$0")/_common.sh"

ALERTS="${TEPHRA_MONITORING_ALERTS:-false}"
DASHBOARD_FILE="$(dirname "$0")/monitoring-dashboard.json"
DASHBOARD_NAME="TEPHRA"
case "$ALERTS" in
  true) EMAIL="${TEPHRA_ALERT_EMAIL:?set TEPHRA_ALERT_EMAIL to the address that gets alerts}" ;;
  false) ;;
  *) echo "TEPHRA_MONITORING_ALERTS must be 'true' or 'false', not '$ALERTS'." >&2; exit 1 ;;
esac

run() {
  printf '+'
  printf ' %q' "$@"
  printf '\n'
  "$@"
}

workdir="$(mktemp -d)"
trap 'rm -rf "$workdir"' EXIT

SOURCE_FILTER="resource.type=\"cloud_run_revision\" AND resource.labels.service_name=\"$SERVICE\""
GEMINI_FILTER="$SOURCE_FILTER AND jsonPayload.event=\"gemini_call\""
# A cache hit and a call refused by the budget never reach Gemini (latency_ms is 0).
LATENCY_FILTER="$GEMINI_FILTER AND NOT jsonPayload.outcome=(\"cache_hit\" OR \"budget_exhausted\")"
TICK_FILTER="$SOURCE_FILTER AND jsonPayload.logger=\"tephra.scheduler\" AND jsonPayload.message=~\"^tick [^ ]+: [0-9]+ feeds\""

# A YAML double-quoted scalar: escape backslashes and double quotes.
yaml_quote() {
  local value="${1//\\/\\\\}"
  printf '"%s"' "${value//\"/\\\"}"
}

cat >"$workdir/gemini_calls.yaml" <<EOF
name: gemini_calls
description: Gemini calls made by TEPHRA, by tier and outcome
filter: $(yaml_quote "$GEMINI_FILTER")
metricDescriptor:
  metricKind: DELTA
  valueType: INT64
  unit: "1"
  labels:
  - key: tier
    valueType: STRING
  - key: outcome
    valueType: STRING
labelExtractors:
  tier: EXTRACT(jsonPayload.tier)
  outcome: EXTRACT(jsonPayload.outcome)
EOF

cat >"$workdir/gemini_latency_ms.yaml" <<EOF
name: gemini_latency_ms
description: Latency of TEPHRA's Gemini calls that reached the model, in milliseconds
filter: $(yaml_quote "$LATENCY_FILTER")
metricDescriptor:
  metricKind: DELTA
  valueType: DISTRIBUTION
  unit: ms
  labels:
  - key: tier
    valueType: STRING
labelExtractors:
  tier: EXTRACT(jsonPayload.tier)
valueExtractor: EXTRACT(jsonPayload.latency_ms)
bucketOptions:
  exponentialBuckets:
    numFiniteBuckets: 20
    growthFactor: 1.5
    scale: 100
EOF

cat >"$workdir/tephra_ticks.yaml" <<EOF
name: tephra_ticks
description: Scheduler ticks TEPHRA finished
filter: $(yaml_quote "$TICK_FILTER")
metricDescriptor:
  metricKind: DELTA
  valueType: INT64
  unit: "1"
EOF

summary="log-based metrics gemini_calls, gemini_latency_ms, tephra_ticks and the $DASHBOARD_NAME dashboard"
if [ "$ALERTS" = "true" ]; then
  summary="$summary, plus an email channel and two alert policies"
fi
# --- B20 (optional; the owner reads the uptime-check pricing page first) -------------------
# One uptime check on GET /health every 5 minutes, from Google's checkers, so an instance
# that stops answering is seen without anyone opening the Wall. Idempotent by display name.
UPTIME_NAME="TEPHRA /health"
service_host="$(gcloud run services describe "$SERVICE" --region "$REGION" \
  --format='value(status.url)' | sed -e 's#^https://##')"
[ -n "$service_host" ] || { echo "Deploy the service first (deploy/cloudrun.sh)." >&2; exit 1; }
summary="$summary, plus an uptime check on https://$service_host/health every 5 min"
# --- end B20 ------------------------------------------------------------------------------
confirm "Create $summary for service $SERVICE (check pricing first)?"
run gcloud services enable logging.googleapis.com monitoring.googleapis.com

# --- B20 (continued) ----------------------------------------------------------------------
existing_uptime="$(gcloud monitoring uptime list-configs \
  --filter="displayName=\"$UPTIME_NAME\"" --format='value(name)' | head -n 1)"
if [ -n "$existing_uptime" ]; then
  echo "Uptime check '$UPTIME_NAME' already exists ($existing_uptime); left as it is."
else
  run gcloud monitoring uptime create "$UPTIME_NAME" \
    --resource-type=uptime-url --resource-labels="host=$service_host,project_id=$TEPHRA_PROJECT" \
    --protocol=https --port=443 --path=/health --period=5 --timeout=10
fi
# --- end B20 ------------------------------------------------------------------------------

for metric in gemini_calls gemini_latency_ms tephra_ticks; do
  if gcloud logging metrics describe "$metric" >/dev/null 2>&1; then
    run gcloud logging metrics update "$metric" --config-from-file="$workdir/$metric.yaml"
  else
    run gcloud logging metrics create "$metric" --config-from-file="$workdir/$metric.yaml"
  fi
done

existing_dashboard="$(gcloud monitoring dashboards list \
  --filter="displayName=\"$DASHBOARD_NAME\"" --format='value(name)')"
if [ -n "$existing_dashboard" ]; then
  echo "Dashboard $DASHBOARD_NAME already exists ($existing_dashboard); left as it is."
  echo "  Delete it in the console (Monitoring > Dashboards) and rerun to apply $DASHBOARD_FILE."
else
  run gcloud monitoring dashboards create --config-from-file="$DASHBOARD_FILE"
fi

if [ "$ALERTS" != "true" ]; then
  echo "Monitoring ready (no alerts; set TEPHRA_MONITORING_ALERTS=true to add them)."
  exit 0
fi

# Notification channels and alert policies are in the beta and alpha gcloud command groups.
CHANNEL_NAME="TEPHRA alerts"
channel="$(gcloud beta monitoring channels list \
  --filter="displayName=\"$CHANNEL_NAME\"" --format='value(name)' | head -n 1)"
if [ -z "$channel" ]; then
  run gcloud beta monitoring channels create --display-name="$CHANNEL_NAME" --type=email \
    --channel-labels="email_address=$EMAIL"
  channel="$(gcloud beta monitoring channels list \
    --filter="displayName=\"$CHANNEL_NAME\"" --format='value(name)' | head -n 1)"
fi
[ -n "$channel" ] || { echo "The notification channel was not created." >&2; exit 1; }

cat >"$workdir/no_tick.json" <<EOF
{
  "displayName": "TEPHRA: no tick for 10 min",
  "combiner": "OR",
  "notificationChannels": ["$channel"],
  "conditions": [{
    "displayName": "tephra_ticks absent for 10 min",
    "conditionAbsent": {
      "filter": "metric.type=\"logging.googleapis.com/user/tephra_ticks\" AND resource.type=\"cloud_run_revision\"",
      "duration": "600s",
      "aggregations": [{
        "alignmentPeriod": "60s",
        "perSeriesAligner": "ALIGN_SUM",
        "crossSeriesReducer": "REDUCE_SUM"
      }]
    }
  }]
}
EOF

cat >"$workdir/gemini_errors.json" <<EOF
{
  "displayName": "TEPHRA: Gemini errors >= 2 in 30 min",
  "combiner": "OR",
  "notificationChannels": ["$channel"],
  "conditions": [{
    "displayName": "gemini_calls with outcome error, 2 or more in 30 min",
    "conditionThreshold": {
      "filter": "metric.type=\"logging.googleapis.com/user/gemini_calls\" AND resource.type=\"cloud_run_revision\" AND metric.label.outcome=\"error\"",
      "comparison": "COMPARISON_GT",
      "thresholdValue": 1,
      "duration": "0s",
      "aggregations": [{
        "alignmentPeriod": "1800s",
        "perSeriesAligner": "ALIGN_SUM",
        "crossSeriesReducer": "REDUCE_SUM"
      }]
    }
  }]
}
EOF

for policy in no_tick gemini_errors; do
  display="$(sed -n 's/^  "displayName": "\(.*\)",$/\1/p' "$workdir/$policy.json")"
  existing="$(gcloud alpha monitoring policies list \
    --filter="displayName=\"$display\"" --format='value(name)')"
  if [ -n "$existing" ]; then
    echo "Alert policy '$display' already exists ($existing); left as it is."
  else
    run gcloud alpha monitoring policies create --policy-from-file="$workdir/$policy.json"
  fi
done
echo "Monitoring ready. Pausing the scheduler or the service makes the no-tick policy fire;"
echo "disable that policy in the console (Monitoring > Alerting) first."
