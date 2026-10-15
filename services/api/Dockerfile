# Build from the repo root: docker build -f services/api/Dockerfile -t ai-mdmp-api .
FROM python:3.11-slim
WORKDIR /app
COPY services/api/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY common ./common
COPY services/api/mdmp_api ./mdmp_api
EXPOSE 8000
CMD ["uvicorn", "mdmp_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
