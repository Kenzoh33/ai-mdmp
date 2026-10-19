import asyncio
from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
from mdmp_deployer.history import DeploymentOutcome, HistorySummary
from mdmp_deployer.risk import HeuristicAdvisor, LLMAdvisor, parse_reply


def history(outcomes: list[tuple[str, str]], version: str = "v4") -> HistorySummary:
    deployments = [
        DeploymentOutcome(f"dep_{i}", v, "canary", status, None)
        for i, (v, status) in enumerate(outcomes)
    ]
    return HistorySummary(model="sentiment", version=version, deployments=deployments)


@pytest.mark.parametrize(
    ("outcomes", "version", "level", "weight"),
    [
        ([], "v1", "medium", 10),
        ([("v1", "promoted"), ("v2", "rolled_back")], "v2", "high", 5),
        ([("v1", "promoted"), ("v2", "failed")], "v3", "high", 5),
        ([("v1", "promoted")] * 3 + [("v2", "rolled_back")], "v3", "medium", 10),
        ([("v1", "promoted")] * 5, "v3", "low", 25),
    ],
)
def test_heuristic_levels(outcomes: list, version: str, level: str, weight: int) -> None:
    result = HeuristicAdvisor().decide(history(outcomes, version))
    assert (result.risk_level, result.recommended_initial_weight) == (level, weight)
    assert result.source == "heuristic"


def test_parse_reply_accepts_fenced_json_and_clamps_weight() -> None:
    reply = (
        'Sure:\n```json\n{"risk_level": "HIGH", "recommended_initial_weight": 300, '
        '"reasoning": "v2 failed before."}\n```'
    )
    parsed = parse_reply(reply)
    assert parsed is not None
    assert (parsed.risk_level, parsed.recommended_initial_weight, parsed.source) == (
        "high",
        100,
        "llm",
    )


@pytest.mark.parametrize(
    "reply",
    [
        "[MOCK MODE] Mock AI response for prompt: You review ML...",
        '{"risk_level": "extreme", "recommended_initial_weight": 5, "reasoning": "x"}',
        '{"risk_level": "low", "recommended_initial_weight": "lots", "reasoning": "x"}',
        '{"risk_level": "low", "recommended_initial_weight": 5}',
        "{not json}",
    ],
)
def test_parse_reply_rejects_unusable_replies(reply: str) -> None:
    assert parse_reply(reply) is None


def run_llm(get_response: Callable, timeout_s: float = 1.0):
    advisor = LLMAdvisor(get_response=get_response, timeout_s=timeout_s)
    return asyncio.run(advisor.assess(history([("v1", "promoted")], "v2")))


def test_llm_advisor_uses_valid_reply_and_sends_history() -> None:
    prompts: list[str] = []

    async def fake(prompt: str) -> str:
        prompts.append(prompt)
        return '{"risk_level": "low", "recommended_initial_weight": 20, "reasoning": "ok"}'

    result = run_llm(fake)
    assert (result.source, result.risk_level, result.recommended_initial_weight) == (
        "llm",
        "low",
        20,
    )
    assert '"candidate_version": "v2"' in prompts[0]


def test_llm_advisor_falls_back_on_plain_text_errors_and_timeouts() -> None:
    async def mock_text(prompt: str) -> str:
        return "[MOCK MODE] Mock AI response"

    async def broken(prompt: str) -> str:
        raise RuntimeError("no network")

    async def slow(prompt: str) -> str:
        await asyncio.sleep(5)
        return "{}"

    for fake in (mock_text, broken):
        assert run_llm(fake).source == "heuristic"
    assert run_llm(slow, timeout_s=0.05).source == "heuristic"


def send_critical(client: TestClient, dep: dict) -> None:
    body = {
        "model": "sentiment",
        "version": dep["version"],
        "track": "canary",
        "deployment_id": dep["id"],
        "metric": "error_rate",
        "value": 0.21,
        "threshold": 0.05,
        "severity": "critical",
        "timestamp": "2026-10-19T12:00:00Z",
    }
    assert client.post("/internal/anomalies", json=body).json()["action"] == "rollback"


def test_risk_endpoint_with_seeded_history(client: TestClient, canary_v2: dict) -> None:
    send_critical(client, canary_v2)

    response = client.get("/api/v1/feedback/risk", params={"model": "sentiment", "version": "v2"})

    body = response.json()
    assert response.status_code == 200
    assert body["risk_level"] == "high" and body["recommended_initial_weight"] == 5
    assert body["source"] == "heuristic"
    assert body["history"] == {
        "deployments": 2,
        "promoted": 1,
        "rolled_back": 1,
        "failed": 0,
        "version_rolled_back_before": True,
    }


def test_risk_endpoint_passes_anomaly_metrics_to_llm(
    make_client: Callable[..., TestClient],
) -> None:
    prompts: list[str] = []

    async def fake(prompt: str) -> str:
        prompts.append(prompt)
        return '{"risk_level": "medium", "recommended_initial_weight": 10, "reasoning": "r"}'

    with make_client(risk_advisor=LLMAdvisor(get_response=fake)) as client:
        for version, strategy in (("v1", "full"), ("v2", "canary")):
            body = {"model": "sentiment", "version": version, "strategy": strategy}
            dep = client.post("/api/v1/deployments", json=body).json()
        send_critical(client, dep)
        response = client.get(
            "/api/v1/feedback/risk", params={"model": "sentiment", "version": "v3"}
        )

    assert response.json()["source"] == "llm"
    assert '"error_rate": 0.21' in prompts[0]
    assert '"metrics_source": "anomaly_events"' in prompts[0]


def test_risk_endpoint_requires_model_and_version(client: TestClient) -> None:
    response = client.get("/api/v1/feedback/risk", params={"model": "sentiment"})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_request"
