#!/usr/bin/env bash
# Sends N requests through the ingress and counts which model version answered.
# Usage: bash k8s/models/verify-canary.sh [N] [URL]
# At canary-weight 20 and N=200, expect roughly 160 v1 and 40 v2.
set -euo pipefail

N="${1:-200}"
URL="${2:-http://localhost/models/sentiment/health}"

for _ in $(seq "$N"); do
  body="$(curl -s --max-time 5 "$URL" || true)"
  version="$(printf '%s' "$body" | grep -o '"version":"[^"]*"' | cut -d'"' -f4 || true)"
  echo "${version:-no_answer}"
done | sort | uniq -c
