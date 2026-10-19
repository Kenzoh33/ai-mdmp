#!/usr/bin/env bash
# End-to-end check on a live cluster: v1 stable -> v2 canary -> fake critical event -> rollback.
# Used by .github/workflows/cd.yml and runnable locally once kind is up.
# Needs: the deployer at DEPLOYER_URL (e.g. via kubectl port-forward), the ingress at INGRESS_URL,
# kubectl, and python3 with httpx (for send_fake_event.py).
#   bash k8s/smoke-test.sh
set -euo pipefail

DEPLOYER_URL="${DEPLOYER_URL:-http://localhost:8001}"
INGRESS_URL="${INGRESS_URL:-http://localhost/models/sentiment}"
NS="${MODELS_NAMESPACE:-mdmp-models}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

pass() { echo "PASS: $*"; }
fail() { echo "FAIL: $*" >&2; exit 1; }

# json FIELD: read JSON on stdin and print one top-level field.
json() { python3 -c "import json,sys; print(json.load(sys.stdin)['$1'])"; }

# wait_for DESCRIPTION SECONDS COMMAND...: retry COMMAND every 2 s until it succeeds.
wait_for() {
  local desc="$1" timeout="$2"
  shift 2
  for ((waited = 0; waited < timeout; waited += 2)); do
    if "$@" >/dev/null 2>&1; then return 0; fi
    sleep 2
  done
  fail "$desc (not true after ${timeout}s)"
}

# create_deployment JSON_BODY: POST it and print the new deployment id.
create_deployment() {
  local response
  response="$(curl -sS -X POST "$DEPLOYER_URL/api/v1/deployments" \
    -H 'content-type: application/json' -d "$1")"
  printf '%s' "$response" | json id 2>/dev/null || fail "create deployment: $response"
}

status_is() {
  [ "$(curl -sS "$DEPLOYER_URL/api/v1/deployments/$1" | json status)" = "$2" ]
}

health_version_is() {
  [ "$(curl -s --max-time 5 "$INGRESS_URL/health" | json version)" = "$1" ]
}

versions_seen() { bash "$ROOT/k8s/models/verify-canary.sh" "$1" "$INGRESS_URL/health"; }
canary_seen() { versions_seen 40 | grep -q ' v2$'; }
only_v1_seen() { [ "$(versions_seen 20 | awk '{print $2}' | sort -u)" = "v1" ]; }
canary_gone() { ! kubectl -n "$NS" get deployment sentiment-canary; }

echo "== 1. full deploy of v1"
v1="$(create_deployment '{"model": "sentiment", "version": "v1", "strategy": "full"}')"
wait_for "v1 deployment promoted" 240 status_is "$v1" promoted
wait_for "ingress answers with v1" 120 health_version_is v1
pass "v1 is stable and serving ($v1)"

echo "== 2. v2 canary at weight 50"
v2="$(create_deployment \
  '{"model": "sentiment", "version": "v2", "strategy": "canary", "initial_weight": 50}')"
kubectl -n "$NS" rollout status deployment/sentiment-canary --timeout=180s
wait_for "canary receives traffic" 90 canary_seen
pass "v2 canary is receiving traffic ($v2): $(versions_seen 40 | tr -s ' \n' ' ')"

echo "== 3. fake critical event -> automatic rollback"
result="$(python3 "$ROOT/services/deployer/scripts/send_fake_event.py" --url "$DEPLOYER_URL" \
  --deployment-id "$v2" --severity critical --metric error_rate --value 0.2 --threshold 0.05)"
echo "$result"
grep -q '"action": "rollback"' <<<"$result" || fail "deployer did not roll back"
status_is "$v2" rolled_back || fail "v2 status is not rolled_back"
wait_for "canary Deployment deleted" 60 canary_gone
wait_for "all traffic back on v1" 60 only_v1_seen
pass "v2 rolled back automatically; all traffic on v1"

echo "== 4. feedback risk for v2"
risk="$(curl -sS "$DEPLOYER_URL/api/v1/feedback/risk?model=sentiment&version=v2" | json risk_level)"
[ "$risk" = "high" ] || fail "risk for v2 is '$risk', expected high"
pass "feedback rates v2 as high risk"

echo "ALL SMOKE TESTS PASSED"
