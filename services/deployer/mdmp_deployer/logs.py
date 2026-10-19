"""One JSON object per log line, per docs/CONTRACTS.md."""

import json
import logging
from datetime import UTC, datetime

SERVICE = "deployer"


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "service": SERVICE,
            "message": record.getMessage(),
        }
        for key in ("model", "version", "deployment_id"):
            if hasattr(record, key):
                entry[key] = getattr(record, key)
        return json.dumps(entry)


logger = logging.getLogger(SERVICE)
if not logger.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(JsonFormatter())
    logger.addHandler(_handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
