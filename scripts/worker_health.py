"""Health check fails if the consumer is disconnected or its loop is stalled."""
import time
import urllib.request

text = urllib.request.urlopen("http://localhost:8001/metrics", timeout=3).read().decode()
values = dict(line.split() for line in text.splitlines() if line.startswith("jntuh_worker_"))
assert float(values["jntuh_worker_connected"]) == 1
assert time.time() - float(values["jntuh_worker_heartbeat_timestamp_seconds"]) < 30
