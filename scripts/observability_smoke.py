#!/usr/bin/env python3
"""Exercise a running Compose stack and verify telemetry reaches its stores.

Run from the repository root. Honors COMPOSE_FILE / COMPOSE_PROJECT_NAME.
Use --skip-results in deployment to avoid initiating student scrapes.
"""
import argparse
import subprocess
import sys

CHECK = r'''
import json, os, time, urllib.request, urllib.error, urllib.parse, uuid

def get(url, headers=None):
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers or {}), timeout=15) as response:
        return json.load(response)

def eventually(fn, description, seconds=120):
    deadline = time.monotonic() + seconds
    while True:
        try:
            result = fn()
            assert result, description
            print("PASS", description, flush=True)
            return result
        except Exception as error:
            if time.monotonic() >= deadline:
                raise RuntimeError(description + ": " + str(error)) from error
            time.sleep(5)

def query(expression):
    return get("http://prometheus:9090/api/v1/query?" + urllib.parse.urlencode({"query":expression}))["data"]["result"]

get("http://app:8000/health/ready")
get("http://grafana:3000/api/health")
required = {"api", "worker", "rabbitmq", "redis", "postgres", "host", "containers", "prometheus", "loki", "tempo", "alloy", "grafana", "readiness"}
def targets_ready():
    targets = get("http://prometheus:9090/api/v1/targets")["data"]["activeTargets"]
    healthy = {t["labels"]["job"] for t in targets if t["health"] == "up"}
    missing = required - healthy
    assert not missing, "Unhealthy/missing targets: " + str(sorted(missing))
    return True
eventually(targets_ready, "all 13 Prometheus scrape jobs healthy")
for expression in ["node_cpu_seconds_total", "node_memory_MemAvailable_bytes", "node_network_receive_bytes_total", 'container_memory_working_set_bytes{container_label_com_docker_compose_service="app"}', 'jntuh_worker_connected{job="worker"} == 1', 'probe_success{job="readiness"} == 1']:
    eventually(lambda: query(expression), expression)

request_id = "smoke-" + uuid.uuid4().hex
with urllib.request.urlopen(urllib.request.Request("http://app:8000/", headers={"X-Request-ID":request_id}), timeout=15) as response:
    trace_id = response.headers.get("X-Trace-ID")
assert trace_id, "Response has no trace ID"

def logs():
    params = urllib.parse.urlencode({"query":'{service="app"} |= "' + request_id + '"', "limit":10})
    return get("http://loki:3100/loki/api/v1/query_range?" + params)["data"]["result"]
eventually(logs, "request log collected by Alloy into Loki")
eventually(lambda: get("http://tempo:3200/api/traces/" + trace_id), "matching trace stored in Tempo")
eventually(lambda: query('jntuh_http_requests_total{route="/"}'), "request metrics stored in Prometheus")

if "--skip-results" not in sys.argv:
    for roll in ["198R1A05C4", "21HA1R0002", "24011P0164", "18E51A0473", "18E51A0479"]:
        request = urllib.request.Request("http://app:8000/api/getAllResult?" + urllib.parse.urlencode({"rollNumber":roll}), headers={"X-Api-Key":os.getenv("API_ACCESS_KEY") or "observability-smoke"})
        try:
            response = urllib.request.urlopen(request, timeout=30)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            print("RESULT", roll, response.status, "trace=" + str(response.headers.get("X-Trace-ID")), flush=True)
            assert response.status in (200, 202, 424), "Unexpected result status"
    print("202 means queued; 424 means the upstream university servers are unavailable. Neither proves a completed scrape.", flush=True)
print("Observability smoke checks passed.", flush=True)
'''

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-results", action="store_true")
    args = parser.parse_args()
    # Execute inside the API network; telemetry backends have no public ports.
    command = ["docker", "compose", "exec", "-T", "app", "python", "-"]
    if args.skip_results:
        command.append("--skip-results")
    result = subprocess.run(command, input="import sys\n" + CHECK, text=True)
    sys.exit(result.returncode)
