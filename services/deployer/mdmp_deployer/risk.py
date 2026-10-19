"""Risk assessment for the next deployment, from the deployment history.

LLMAdvisor asks the shared client in common/llm.py for JSON and validates it. When the reply is
not usable (mock mode returns plain text, the call fails or times out), HeuristicAdvisor answers
instead, and the response's `source` says which one did.
"""

import asyncio
import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Literal, Protocol

from mdmp_deployer.history import HistorySummary
from mdmp_deployer.logs import logger

RiskLevel = Literal["low", "medium", "high"]
RISK_LEVELS = ("low", "medium", "high")

PROMPT = """You review ML model deployments. Assess the risk of releasing the candidate version
below as a canary, using the deployment history of the same model (newest first). Metrics are
error_rate (fraction of failed requests), p95_latency (seconds) and confidence (mean prediction
confidence, 0-1). Rollback thresholds: error rate above 0.05, p95 latency above 2x stable,
confidence 0.20 below stable.

History (JSON):
{history}

Reply with a single JSON object and nothing else:
{{"risk_level": "low" | "medium" | "high", "recommended_initial_weight": <integer 1-50>,
"reasoning": "<at most three sentences>"}}"""


@dataclass(frozen=True)
class RiskAssessment:
    risk_level: RiskLevel
    recommended_initial_weight: int
    reasoning: str
    source: Literal["llm", "heuristic"]


class RiskAdvisor(Protocol):
    async def assess(self, history: HistorySummary) -> RiskAssessment: ...


class HeuristicAdvisor:
    """Deterministic rules, used on its own in tests and as the LLM fallback."""

    async def assess(self, history: HistorySummary) -> RiskAssessment:
        return self.decide(history)

    def decide(self, history: HistorySummary) -> RiskAssessment:
        counts = history.counts()
        total = counts["deployments"]
        bad = counts["rolled_back"] + counts["failed"]

        if history.version_rolled_back_before:
            level, weight = "high", 5
            why = f"{history.version} was rolled back before."
        elif total == 0:
            level, weight = "medium", 10
            why = f"No finished deployments of {history.model} yet."
        elif bad / total >= 0.5:
            level, weight = "high", 5
            why = f"{bad} of the last {total} deployments were rolled back or failed."
        elif bad / total >= 0.2:
            level, weight = "medium", 10
            why = f"{bad} of the last {total} deployments were rolled back or failed."
        else:
            level, weight = "low", 25
            why = f"{counts['promoted']} of the last {total} deployments were promoted cleanly."
        return RiskAssessment(level, weight, f"{why} Start the canary at {weight}%.", "heuristic")


def parse_reply(text: str) -> RiskAssessment | None:
    """Pull the JSON object out of an LLM reply (tolerating ```json fences) and validate it."""
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        data = json.loads(text[start : end + 1])
        level = str(data["risk_level"]).lower()
        weight = int(data["recommended_initial_weight"])
        reasoning = str(data["reasoning"]).strip()
    except (ValueError, KeyError, TypeError):
        return None
    if level not in RISK_LEVELS or not reasoning:
        return None
    return RiskAssessment(level, max(0, min(100, weight)), reasoning, "llm")  # type: ignore[arg-type]


def _shared_llm() -> Callable[[str], Awaitable[str]]:
    # Imported here: common.llm builds its OpenAI client at import time, which raises without a
    # key, and that must not stop the deployer from starting.
    from common.llm import llm_client

    return llm_client.get_response


class LLMAdvisor:
    def __init__(
        self,
        get_response: Callable[[str], Awaitable[str]] | None = None,
        timeout_s: float = 15.0,
        fallback: HeuristicAdvisor | None = None,
    ) -> None:
        self._get_response = get_response
        self.timeout_s = timeout_s
        self.fallback = fallback or HeuristicAdvisor()

    async def assess(self, history: HistorySummary) -> RiskAssessment:
        prompt = PROMPT.format(history=json.dumps(history.as_dict(), indent=2))
        try:
            get_response = self._get_response or _shared_llm()
            reply = await asyncio.wait_for(get_response(prompt), self.timeout_s)
        except Exception as exc:
            logger.warning("risk LLM call failed, using heuristic: %s", exc)
            return self.fallback.decide(history)
        parsed = parse_reply(reply or "")
        if parsed is None:
            logger.info("risk LLM reply was not valid JSON, using heuristic")
            return self.fallback.decide(history)
        return parsed
