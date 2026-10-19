
# AI-MDMP - Monitoring & Logging Setup

## Overview

This directory contains the monitoring configuration for the AI-Powered Model Deployment & Monitoring Platform (AI-MDMP).

The monitoring implementation uses:

- **FastAPI:** Exposes monitoring endpoints and Prometheus metrics.
- **Prometheus:** Collects application metrics and evaluates alert rules.
- **Grafana:** Visualizes monitoring data through dashboards.
- **Python logging:** Produces structured JSON logs for HTTP requests and application errors.

Elasticsearch and Logstash are planned integrations and are not configured in this setup.

## 1. Prerequisites

Install the following software:

- Python 3.14 or a compatible Python version
- Docker Desktop
- Git
- Python dependencies required by the monitoring service, including FastAPI, Uvicorn, and prometheus-client

Run commands from the root directory of the `ai-mdmp` repository.

Ensure Docker Desktop is running before starting the monitoring containers.

## 2. Start the FastAPI Monitoring Service

In a terminal at the project root, run:

```powershell
py -m uvicorn services.monitor.mdmp_monitor.main:app --host 0.0.0.0 --port 8001
```

Verify the service using:

- Health check: http://localhost:8001/health
- Application homepage: http://localhost:8001/
- Prometheus metrics: http://localhost:8001/metrics

The `/health` endpoint should return a JSON response indicating the service is healthy.

## 3. Start Prometheus

Create the Docker network if it does not already exist:

```powershell
docker network create ai-mdmp-network
```

Start the Prometheus container:

```powershell
docker run -d --name ai-mdmp-prometheus --network ai-mdmp-network -p 9090:9090 -v "${PWD}/k8s/monitoring/prometheus.yml:/etc/prometheus/prometheus.yml:ro" -v "${PWD}/k8s/monitoring/alerts.yml:/etc/prometheus/alerts.yml:ro" prom/prometheus
```

These commands are intended for Windows PowerShell.

If the network or container already exists, reuse or start the existing resource instead of creating a duplicate.

Open Prometheus:

http://localhost:9090

Navigate to **Status → Targets** and verify that the `ai-mdmp-monitor` target is UP.

The monitoring configuration collects metrics every 15 seconds from:

`host.docker.internal:8001/metrics`

To check service availability, execute this PromQL query:

```promql
up{job="ai-mdmp-monitor"}
```

A value of `1` indicates that Prometheus can successfully scrape the monitoring service. A value of `0` indicates a failed scrape.

## 4. Start Grafana

Start a Grafana container connected to the same Docker network:

```powershell
docker run -d --name ai-mdmp-grafana --network ai-mdmp-network -p 3000:3000 grafana/grafana
```

Open Grafana:

http://localhost:3000

Log in using your configured Grafana credentials.

### Configure Prometheus as a Data Source

1. Navigate to **Connections → Data sources**.
2. Add a Prometheus data source.
3. Set the Prometheus server URL to:

   `http://ai-mdmp-prometheus:9090`

4. Select **Save & test**.

### Import the Monitoring Dashboard

1. Navigate to **Dashboards**.
2. Select the dashboard import option.
3. Upload `k8s/monitoring/grafana-dashboard.json`.
4. Select the Prometheus data source.
5. Import the dashboard.

The dashboard provides monitoring visualizations for request activity, latency, and error rates.

## 5. Prometheus Metrics

The monitoring service exposes metrics through `/metrics`.

Important application metrics include:

| Metric | Purpose |
|---|---|
| `monitor_requests_total` | Counts requests to the application homepage |
| `monitor_request_latency_seconds` | Measures HTTP request processing duration |
| `monitor_request_errors_total` | Counts server errors and failed requests |

Prometheus also collects standard runtime metrics exposed by the Python Prometheus client.

## 6. Alert Rules

Alert rules are defined in:

`k8s/monitoring/alerts.yml`

Configured alerts include:

### MonitoringServiceDown

- Condition: Prometheus cannot scrape the monitoring service.
- Expression: `up{job="ai-mdmp-monitor"} == 0`
- Duration: 1 minute
- Severity: Critical

### HighRequestLatency

- Condition: Average request latency exceeds 1 second.
- Evaluation window: 5 minutes
- Duration: 2 minutes
- Severity: Warning

### HighErrorRate

- Condition: The error counter increases faster than 0.1 errors per second.
- Evaluation window: 5 minutes
- Duration: 2 minutes
- Severity: Critical

View alert status in the Prometheus web interface.

These rules evaluate monitoring conditions but do not independently configure email, Slack, or other external alert notifications.

## 7. Structured JSON Logging

The monitoring service automatically logs HTTP requests as JSON.

Example successful request:

```json
{
  "timestamp": "2026-10-19T00:22:29+00:00",
  "service": "ai-mdmp-monitor",
  "event": "request_completed",
  "method": "GET",
  "path": "/health",
  "status_code": 200,
  "duration_seconds": 0.0043
}
```

Application exceptions generate an error log with the event name `request_failed`.

JSON logs include timestamps, service names, request methods, request paths, and processing durations.

Logs are currently written to the monitoring service's terminal output. Centralized collection using Elasticsearch and Logstash has not yet been configured.

## 8. Verification

After starting the monitoring components:

1. Open `http://localhost:8001/health` and confirm a successful response.
2. Open `http://localhost:8001/metrics` and confirm Prometheus metrics are displayed.
3. Open `http://localhost:9090/targets` and verify the monitoring target is UP.
4. Query `up{job="ai-mdmp-monitor"}` in Prometheus and confirm the value is `1`.
5. Open Grafana at `http://localhost:3000` and inspect the monitoring dashboard.
6. Access the health endpoint again and verify that a JSON `request_completed` log appears in the FastAPI terminal.
7. Review alert status in Prometheus.

A downtime alert was tested during development by temporarily changing the scrape target to an unavailable port. The target was restored to port `8001` after testing.

## 9. Troubleshooting

**FastAPI does not start:** Check that the required Python packages are installed and port `8001` is available.

**Prometheus target is DOWN:** Confirm FastAPI is running on port `8001` and Docker can reach `host.docker.internal`.

**Grafana shows no data:** Confirm the Prometheus data source URL, target status, metric queries, and dashboard time range.

**Prometheus container fails to start:** Check Docker Desktop, the configuration file mounts, and whether a container with the same name already exists.

**No JSON logs appear:** Make a request to `/health` and check the terminal running the monitoring service.

## 10. Project Files

| File | Purpose |
|---|---|
| `prometheus.yml` | Prometheus scrape configuration |
| `alerts.yml` | Prometheus alert definitions |
| `grafana-dashboard.json` | Exported Grafana dashboard |
| `README.md` | Monitoring setup and usage documentation |
| `../../services/monitor/mdmp_monitor/main.py` | FastAPI monitoring service and JSON logging |

## Current Implementation Status

Completed and tested:

- FastAPI monitoring endpoints
- Prometheus metrics collection
- Grafana dashboard visualization
- Prometheus downtime alert testing
- Structured JSON request and error logging

Not yet configured:

- Elasticsearch and Logstash centralized logging
- External alert notification delivery
- Automated production deployment of the monitoring stack

## Centralized Logging with Elasticsearch and Logstash

The AI-MDMP monitoring service uses Elasticsearch and Logstash for centralized application logging.

### Components

- **FastAPI:** Generates structured JSON logs for application requests and errors.
- **Logstash:** Receives HTTP logs on port 8080, parses JSON, and forwards events to Elasticsearch.
- **Elasticsearch:** Stores searchable application logs in the `ai-mdmp-logs` index.

### Prerequisites

Docker Desktop must be running. The Docker network `ai-mdmp-network` must exist.

### Start Elasticsearch

```powershell
docker run -d --name ai-mdmp-elasticsearch --network ai-mdmp-network -p 127.0.0.1:9200:9200 --memory=1500m -e "discovery.type=single-node" -e "xpack.security.enabled=false" -e "xpack.ml.enabled=false" -e "ES_JAVA_OPTS=-Xms512m -Xmx512m" docker.elastic.co/elasticsearch/elasticsearch:8.17.10
```

### Start Logstash

Run this command from the project root:

```powershell
docker run -d --name ai-mdmp-logstash --network ai-mdmp-network -p 127.0.0.1:8080:8080 --memory=1000m -e "LS_JAVA_OPTS=-Xms256m -Xmx256m" -e "XPACK_MONITORING_ENABLED=false" -v "${PWD}/k8s/monitoring/logstash/pipeline.conf:/usr/share/logstash/pipeline/logstash.conf:ro" docker.elastic.co/logstash/logstash:8.17.10
```

Wait for the Logstash pipeline to start.

### Run FastAPI with Logging Enabled

```powershell
$env:LOGSTASH_URL = "http://127.0.0.1:8080"
python -m uvicorn services.monitor.mdmp_monitor.main:app --host 127.0.0.1 --port 8001
```

### Test Logging

In another PowerShell terminal:

```powershell
curl.exe http://127.0.0.1:8001/health
curl.exe "http://localhost:9200/ai-mdmp-logs/_search?sort=@timestamp:desc&size=1&pretty"
```

The Elasticsearch response should contain an event named `request_completed` with path `/health` and status code `200`.

### Notes

- Logging to Elasticsearch is optional. Without `LOGSTASH_URL`, logs still appear in the FastAPI terminal.
- Elasticsearch security is disabled for local development only. Do not expose this configuration to the public internet.
- Log forwarding is synchronous and intended for development/testing rather than production use.
- Elasticsearch and Logstash require substantial memory. Ensure Docker Desktop has sufficient resources.