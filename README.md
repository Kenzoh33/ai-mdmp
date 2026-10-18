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
    pytest                             # all tests should pass

Run one service locally (example: api on port 8000):

    PYTHONPATH=.:services/api uvicorn mdmp_api.main:app --reload --port 8000

## Workflow

1. `git checkout -b feat/<topic>` from an up-to-date `main`.
2. Before pushing: `ruff check . && ruff format . && pytest`.
3. Open a pull request; one teammate reviews; CI must pass.
4. Contracts live in `docs/CONTRACTS.md` and `common/schemas.py`. Tell the team before changing them.
