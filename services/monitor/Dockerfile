# Build from the repo root: docker build -f services/monitor/Dockerfile -t ai-mdmp-monitor .
FROM python:3.11-slim
WORKDIR /app
COPY services/monitor/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY common ./common
COPY services/monitor/mdmp_monitor ./mdmp_monitor
EXPOSE 8000
CMD ["uvicorn", "mdmp_monitor.main:app", "--host", "0.0.0.0", "--port", "8000"]
