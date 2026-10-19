"""Send a fake AnomalyEvent to the deployer, standing in for the monitor.

Example (roll back the live canary):
    python services/deployer/scripts/send_fake_event.py --deployment-id dep_abc123 \
        --severity critical --metric error_rate --value 0.21 --threshold 0.05
"""

import argparse
import json
import sys
from datetime import UTC, datetime

import httpx


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--url", default="http://localhost:8001", help="deployer base URL")
    parser.add_argument("--deployment-id", required=True)
    parser.add_argument("--model", default="sentiment")
    parser.add_argument("--version", default="v2")
    parser.add_argument("--track", choices=["stable", "canary"], default="canary")
    parser.add_argument(
        "--metric", choices=["error_rate", "p95_latency", "confidence"], default="error_rate"
    )
    parser.add_argument("--value", type=float, default=0.2)
    parser.add_argument("--threshold", type=float, default=0.05)
    parser.add_argument("--severity", choices=["info", "warning", "critical"], default="critical")
    parser.add_argument("--summary", default=None, help="optional ai_summary text")
    args = parser.parse_args()

    event = {
        "model": args.model,
        "version": args.version,
        "track": args.track,
        "deployment_id": args.deployment_id,
        "metric": args.metric,
        "value": args.value,
        "threshold": args.threshold,
        "severity": args.severity,
        "ai_summary": args.summary,
        "timestamp": datetime.now(UTC).isoformat(),
    }
    response = httpx.post(f"{args.url}/internal/anomalies", json=event, timeout=30)
    print(response.status_code, json.dumps(response.json(), indent=2))
    return 0 if response.is_success else 1


if __name__ == "__main__":
    sys.exit(main())
