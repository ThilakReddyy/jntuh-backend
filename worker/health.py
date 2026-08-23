"""Minimal health/metrics surface for the main2.py RabbitMQ consumer process.

Unlike the API process, the worker never had a /metrics or /health endpoint,
so its throughput/liveness was only inferable indirectly via RabbitMQ queue
depth. This starts a tiny stdlib HTTP server (no extra dependency) exposing:

- GET /metrics  -- the standard prometheus_client registry (process CPU/RSS/GC
  metrics come for free; scrape this from prometheus.yml).
- GET /health   -- 200 while the consumer's RabbitMQ connection is open, 503
  otherwise, so this can back a container-level liveness probe if the worker
  is ever split into its own container.
"""

import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

from prometheus_client import CONTENT_TYPE_LATEST, generate_latest


class WorkerState:
    def __init__(self):
        self._ready = False

    def mark_ready(self) -> None:
        self._ready = True

    def mark_not_ready(self) -> None:
        self._ready = False

    @property
    def is_ready(self) -> bool:
        return self._ready


worker_state = WorkerState()


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *args) -> None:  # silence default per-request logging
        pass

    def do_GET(self) -> None:
        if self.path == "/metrics":
            payload = generate_latest()
            self.send_response(200)
            self.send_header("Content-Type", CONTENT_TYPE_LATEST)
            self.end_headers()
            self.wfile.write(payload)
        elif self.path == "/health":
            status = 200 if worker_state.is_ready else 503
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            body = b'{"status": "ok"}' if status == 200 else b'{"status": "not_ready"}'
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()


def start_worker_health_server(port: int) -> None:
    server = HTTPServer(("0.0.0.0", port), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
