# Deployer service

The only service that changes Kubernetes objects. It creates the stable and canary Deployments
for a model, moves canary traffic through the ingress-nginx `canary-weight` annotation, scales,
promotes, rolls back, and rolls back automatically when the monitor reports an anomaly. Every
deployment and its outcome is stored in a database and used by `GET /api/v1/feedback/risk`.

## API

Under `/api/v1` (see `docs/CONTRACTS.md` for request and response bodies):

| Method | Path | What it does |
| --- | --- | --- |
| POST | `/deployments` | Deploy `model`/`version` with `strategy` `full` or `canary` (`replicas`, `initial_weight`) |
| GET | `/deployments`, `/deployments/{id}` | List or read deployments |
| POST | `/deployments/{id}/weight` | Set the canary traffic `percent` |
| POST | `/deployments/{id}/scale` | Set `replicas` |
| POST | `/deployments/{id}/promote` | Make the canary the new stable |
| POST | `/deployments/{id}/rollback` | Manual rollback with a `reason` |
| GET | `/feedback/risk?model=&version=` | Risk level, recommended canary start weight and reasoning, based on deployment history |

`POST /internal/anomalies` accepts an `AnomalyEvent` (`common/schemas.py`) from the monitor.
Errors use the `{"error": {"code", "message"}}` format. Status values: deploying, canary,
promoted, rolled_back, failed.

## Automatic rollback policy (`mdmp_deployer/policy.py`)

1. Events for a deployment that is already rolled back or no longer serving are ignored.
2. Two warnings for the same deployment within 5 minutes count as critical.
3. Anything below critical is only recorded.
4. A critical event within 2 minutes after a rollback of the same model is ignored (cooldown).
5. Critical on a canary: weight goes to 0 and the canary objects are deleted.
6. Critical on stable after a full deploy: the previous stable version is redeployed.

Every rollback is stored together with the event that triggered it.

## Configuration

All settings come from environment variables (`mdmp_deployer/config.py`):

| Variable | Default | Purpose |
| --- | --- | --- |
| `DATABASE_URL` | `sqlite:///./deployer.db` | SQLite locally and in tests, Postgres in the cluster |
| `MODELS_NAMESPACE` | `mdmp-models` | Namespace the model Deployments live in |
| `MODEL_IMAGE_TEMPLATE` | `ai-mdmp-{model}:{version}` | Image name for a model version |
| `IN_CLUSTER` | `false` | `true` uses the pod's ServiceAccount, otherwise kubeconfig |
| `K8S_SIMULATE` | `false` | `true` logs Kubernetes actions instead of calling a cluster (demo without kind) |
| `WARNING_WINDOW_SECONDS` / `ROLLBACK_COOLDOWN_SECONDS` | `300` / `120` | Policy timings |
| `PROMETHEUS_URL` | unset | When set, canary metrics are snapshotted into history |
| `LLM_MOCK` | | `true` returns a canned risk answer instead of calling OpenAI |

## Running

```bash
# Tests (Kubernetes client is mocked, no cluster or OpenAI needed)
LLM_MOCK=true python -m pytest services/deployer

# Locally against the kind cluster (uses your kubeconfig)
PYTHONPATH=.:services/deployer uvicorn mdmp_deployer.main:app --port 8001

# Without a cluster (simulated Kubernetes)
K8S_SIMULATE=true LLM_MOCK=true PYTHONPATH=.:services/deployer uvicorn mdmp_deployer.main:app --port 8001
```

In the cluster it runs from `k8s/platform/deployer.yaml` with a ServiceAccount and an RBAC Role
scoped to `mdmp-models`.

## Demo: trigger an automatic rollback

```bash
# Create a canary of v2, then report a critical error rate for it
python services/deployer/scripts/send_fake_event.py --deployment-id <canary id> \
    --severity critical --metric error_rate --value 0.21 --threshold 0.05
```

The deployment moves to `rolled_back` and all traffic returns to stable. `k8s/smoke-test.sh` runs
the full v1 stable -> v2 canary -> critical event -> rollback path, and the CD workflow runs it on
every push to `main`.

## Known gap

The monitor does not yet send `AnomalyEvent`s to `/internal/anomalies`, and the api service does
not yet call the deployer, so the fake-event script stands in for the monitor.
