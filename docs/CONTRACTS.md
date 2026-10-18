# Contracts

Full version: the AI-MDMP Team Plan doc (Contracts section). Change anything here only after telling the team.

- API: everything under /api/v1, JSON, UTC ISO 8601 timestamps, errors as {"error": {"code", "message"}}.
- Model metrics on /metrics, labelled model + version: model_requests_total (+ status),
  model_request_latency_seconds, model_prediction_confidence.
- Anomaly event: common/schemas.py -> AnomalyEvent. Monitor sends it to deployer at POST /internal/anomalies.
- Rollback thresholds: error rate > 5%, p95 latency > 2x stable, mean confidence 0.20 below stable.
- Logs: one JSON object per line with timestamp, level, service, message (+ model, version, deployment_id).
