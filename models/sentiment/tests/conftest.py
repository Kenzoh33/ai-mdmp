from collections.abc import Callable, Iterator
from pathlib import Path

import joblib
import pytest
from fastapi.testclient import TestClient
from sentiment_service.main import app
from sentiment_service.train import build_pipeline

POSITIVE = [
    "a wonderful and moving film",
    "brilliant acting and a wonderful story",
    "funny, warm and delightful",
    "one of the best movies this year",
    "a beautiful, touching triumph",
    "great fun from start to finish",
]
NEGATIVE = [
    "a boring and tedious mess",
    "terrible acting and a dull plot",
    "the worst movie i have seen",
    "awful, lifeless and far too long",
    "a dull, forgettable disappointment",
    "painfully bad from start to finish",
]


@pytest.fixture(scope="session")
def model_path(tmp_path_factory: pytest.TempPathFactory) -> Path:
    pipeline = build_pipeline(seed=0, min_df=1)
    pipeline.fit(POSITIVE + NEGATIVE, [1] * len(POSITIVE) + [0] * len(NEGATIVE))
    path = tmp_path_factory.mktemp("model") / "model.joblib"
    joblib.dump(pipeline, path)
    return path


@pytest.fixture
def make_client(model_path: Path, monkeypatch: pytest.MonkeyPatch) -> Callable[..., TestClient]:
    """Build a TestClient with the given env overrides. Use it as a context manager so the
    lifespan runs and loads the model."""

    def _make(**env: object) -> TestClient:
        defaults = {
            "MODEL_PATH": str(model_path),
            "MODEL_VERSION": "vtest",
            "EXTRA_LATENCY_MS": "0",
            "ERROR_RATE": "0",
        }
        for key, value in {**defaults, **env}.items():
            monkeypatch.setenv(key, str(value))
        return TestClient(app)

    return _make


@pytest.fixture
def client(make_client: Callable[..., TestClient]) -> Iterator[TestClient]:
    with make_client() as test_client:
        yield test_client
