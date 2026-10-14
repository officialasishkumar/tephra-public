#!/usr/bin/env bash
# Firestore time-to-live on the kept model answers: documents in ai_answers go when their
# expires_at passes, so the store never has to sweep them itself. A person runs this once;
# the TTL policy outlives deploys. Check the Firestore pricing page first: TTL deletes are
# billed as deletes (the free tier covers 20K a day; the sweep is a few hundred).
# shellcheck source=deploy/_common.sh
source "$(dirname "$0")/_common.sh"

COLLECTION="${TEPHRA_ANSWERS_COLLECTION:-ai_answers}"
FIELD="expires_at"

confirm "Enable Firestore TTL on $COLLECTION.$FIELD in project $TEPHRA_PROJECT?"
gcloud firestore fields ttls update "$FIELD" --collection-group="$COLLECTION" --enable-ttl
echo "TTL policy on $COLLECTION.$FIELD requested; Firestore applies it in the background."
echo "Check with: gcloud firestore fields ttls list --collection-group=$COLLECTION"
