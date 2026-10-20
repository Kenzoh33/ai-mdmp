# AI-MDMP: AI-Powered Model Deployment & Monitoring Platform

| Area | Owner |
| --- | --- |
| Steps 1, 4: `services/api`, `common/`, `frontend/` | Shane Marks |
| Steps 3, 5: `services/monitor`, `k8s/monitoring`, `tests/` | Member B |
| Steps 2, 6: `services/deployer`, `models/`, `k8s/`, CI/CD | Rochak Ghimire |

## Getting started

    git clone https://github.com/Kenzoh33/ai-mdmp.git
    cd ai-mdmp
    python3 -m venv .venv
    source .venv/bin/activate          # Windows Git Bash: source .venv/Scripts/activate
    pip install -r requirements-dev.txt
    cp .env.example .env               # add the team OpenAI key
    LLM_MOCK=true python -m pytest     # all tests should pass; no OpenAI calls

Run one service locally (example: api on port 8000):

    PYTHONPATH=.:services/api uvicorn mdmp_api.main:app --reload --port 8000

## Architecture

- **Dashboard** (`frontend/`) is served by the **api** service, which forwards `/api/v1/*` to the deployer.
- **Deployer** (`services/deployer/`) is the only service that changes Kubernetes: stable and canary
  Deployments, the ingress-nginx canary weight, promote, rollback, and deployment history with AI risk advice.
- **Monitor** (`services/monitor/`) analyses error rate and latency, explains anomalies with the LLM, and
  reports them to the deployer at `/internal/anomalies`, which rolls the canary back automatically.
- **Models** (`models/sentiment/`, v1 healthy, v2 broken, v3 retrain) expose `/metrics` for Prometheus
  (`k8s/monitoring/`). `loadgen/` sends steady demo traffic.

## Run the demo locally

From the repo root with the venv active (the deployer needs a kubeconfig, e.g. the kind cluster from
`k8s/kind-config.yaml`; see `k8s/models/README.md`):

    # 1. Deployer
    LLM_MOCK=true PYTHONPATH=.:services/deployer uvicorn mdmp_deployer.main:app --port 8001
    # 2. Api + dashboard at http://localhost:8000
    PYTHONPATH=.:services/api uvicorn mdmp_api.main:app --port 8000
    # 3. Monitor
    LLM_MOCK=true DEPLOYER_URL=http://localhost:8001 PYTHONPATH=.:services/monitor \
        uvicorn mdmp_monitor.main:app --port 8002

Deploy v1, then a v2 canary (`POST /api/v1/deployments`, see `services/deployer/README.md`), and
report bad metrics for the canary:

    curl -X POST localhost:8002/anomalies/analyze -H 'content-type: application/json' -d \
      '{"error_rate": 0.2, "latency_ms": 900, "baseline_error_rate": 0.01,
        "baseline_latency_ms": 100, "deployment_id": "<canary id>"}'

The deployer rolls the canary back, and the dashboard shows `rolled_back` within a few seconds.

## CI/CD

- **CI** (`.github/workflows/ci.yml`, every PR): ruff, pytest, and Docker builds of every service.
- **CD** (`.github/workflows/cd.yml`, every push to `main`): builds images tagged with the commit SHA,
  pushes them to GHCR, starts a kind cluster, deploys the deployer, and runs `k8s/smoke-test.sh`:
  v1 stable, then v2 canary, then a critical anomaly, then an automatic rollback.

## Workflow

1. `git checkout -b feat/<topic>` from an up-to-date `main`.
2. Before pushing: `ruff check . && ruff format . && LLM_MOCK=true python -m pytest`.
3. Open a pull request; one teammate reviews; CI must pass.
4. Contracts live in `docs/CONTRACTS.md` and `common/schemas.py`. Tell the team before changing them.
