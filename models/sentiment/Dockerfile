# Build from the repo root:
#   docker build -f models/sentiment/Dockerfile --build-arg VARIANT=v1 -t ai-mdmp-sentiment:v1 .
# VARIANT picks the model trained during the build: v1 (healthy), v2 (broken), v3 (healthy retrain).
# EXTRA_LATENCY_MS and ERROR_RATE are runtime env vars, set by docker run -e or the k8s manifest.

FROM python:3.11-slim AS base
WORKDIR /app
COPY models/sentiment/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

FROM base AS train
ARG VARIANT=v1
COPY models/sentiment/requirements-train.txt .
RUN pip install --no-cache-dir -r requirements-train.txt
COPY models/sentiment/sentiment_service/__init__.py models/sentiment/sentiment_service/train.py ./sentiment_service/
RUN python -m sentiment_service.train --variant "$VARIANT" --out /app/model

FROM base AS runtime
ARG VARIANT=v1
ENV MODEL_VERSION=$VARIANT \
    MODEL_PATH=/app/model/model.joblib \
    PYTHONUNBUFFERED=1
COPY --from=train /app/model /app/model
COPY models/sentiment/sentiment_service ./sentiment_service
EXPOSE 8080
CMD ["uvicorn", "sentiment_service.main:app", "--host", "0.0.0.0", "--port", "8080"]
