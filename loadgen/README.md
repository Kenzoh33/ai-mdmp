# Load generator for demo traffic (Rochak)

Sends a steady stream of movie reviews to the sentiment model through the ingress, so
`model_requests_total` keeps climbing on both the stable and the canary pods.

    python -m pip install -r loadgen/requirements.txt
    python loadgen/traffic.py --rate 5                 # until Ctrl-C
    python loadgen/traffic.py --rate 10 --duration 60  # one minute

| Option | Env var | Default |
| --- | --- | --- |
| `--url` | `LOADGEN_URL` | `http://localhost/models/sentiment/predict` |
| `--rate` (requests/s) | `LOADGEN_RATE` | `5` |
| `--duration` (s, 0 = forever) | | `0` |
| `--concurrency` (max in flight) | | `20` |
| `--timeout` (s per request) | | `5` |

It prints one JSON line every 10 seconds and one at exit: `sent`, `ok`, `errors` (by HTTP status,
`timeout` or `connection_error`), `dropped`, and mean and p95 latency.

Traffic is open loop: a request starts every `1/rate` seconds even if earlier ones are still
waiting, so the slow v2 canary cannot lower the offered rate. If `--concurrency` requests are
already in flight, that tick is counted as `dropped` instead of piling up.

## Check that both tracks get traffic

    kubectl -n mdmp-models port-forward deploy/sentiment-stable 9001:8080 &
    kubectl -n mdmp-models port-forward deploy/sentiment-canary 9002:8080 &
    curl -s localhost:9001/metrics | grep '^model_requests_total{'
    curl -s localhost:9002/metrics | grep '^model_requests_total{'

Run the curls twice a few seconds apart: both counters should grow, and the canary (v2) should
also show `status="error"`.
