# Build from the repo root: docker build -f services/deployer/Dockerfile -t ai-mdmp-deployer .
FROM python:3.11-slim
WORKDIR /app
COPY services/deployer/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY common ./common
COPY services/deployer/mdmp_deployer ./mdmp_deployer
EXPOSE 8000
CMD ["uvicorn", "mdmp_deployer.main:app", "--host", "0.0.0.0", "--port", "8000"]
