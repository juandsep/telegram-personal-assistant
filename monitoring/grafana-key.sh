#!/usr/bin/env sh
# Creates a key for the read-only assistant-grafana account (roles/
# monitoring.viewer only) and keeps just its private key in monitoring/secrets/,
# which git ignores. Grafana's Cloud Monitoring datasource needs a service
# account key; this one can read metrics and nothing else.
# Revoke: gcloud iam service-accounts keys list --iam-account=<account>, then
# gcloud iam service-accounts keys delete <id> --iam-account=<account>.
set -eu
project="${GCP_PROJECT_ID:-jd-botjonh}"
account="assistant-grafana@${project}.iam.gserviceaccount.com"
dir="$(cd "$(dirname "$0")" && pwd)/secrets"
mkdir -p "$dir"
umask 077
gcloud iam service-accounts keys create "$dir/key.json" \
  --iam-account="$account" --project="$project"
python3 -c 'import json, sys; print(json.load(open(sys.argv[1]))["private_key"], end="")' \
  "$dir/key.json" > "$dir/grafana.pem"
rm "$dir/key.json"
echo "wrote $dir/grafana.pem"
