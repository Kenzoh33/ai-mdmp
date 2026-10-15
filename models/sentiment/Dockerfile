# Build from the repo root: docker build -f models/sentiment/Dockerfile -t ai-mdmp-sentiment .
FROM python:3.11-slim
WORKDIR /app
COPY models/sentiment/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY models/sentiment/sentiment_service ./sentiment_service
EXPOSE 8080
CMD ["uvicorn", "sentiment_service.main:app", "--host", "0.0.0.0", "--port", "8080"]
