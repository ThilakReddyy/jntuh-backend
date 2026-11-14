import asyncio
import json
import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from fastapi import FastAPI
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from prometheus_client import REGISTRY

from utils.observability import RequestTelemetryMiddleware, operation, request_id_context
from utils.logger import JsonFormatter


@pytest.fixture(scope="module")
def spans():
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    with patch("utils.observability.tracer", provider.get_tracer("test")):
        yield exporter
    provider.shutdown()


def test_request_trace_metrics_and_error_handling(spans):
    app = FastAPI()
    app.add_middleware(RequestTelemetryMiddleware)

    @app.get("/student/{roll}")
    async def student(roll: str):
        return {"ok": True}

    @app.get("/fail")
    async def fail():
        raise RuntimeError("private payload")

    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app, raise_app_exceptions=False), base_url="http://test") as client:
            for roll in ("198R1A05C4", "21HA1R0002", "24011P0164", "18E51A0473", "18E51A0479"):
                response = await client.get(f"/student/{roll}?secret=hidden", headers={"x-request-id": "test-request"})
                assert response.headers["x-request-id"] == "test-request"
                assert len(response.headers["x-trace-id"]) == 32
            response = await client.get("/fail")
            assert response.status_code == 500
        assert request_id_context.get() == ""

    asyncio.run(run())
    assert REGISTRY.get_sample_value("jntuh_http_requests_total", {"method": "GET", "route": "/student/{roll}", "status": "200"}) == 5
    assert REGISTRY.get_sample_value("jntuh_http_requests_total", {"method": "GET", "route": "/fail", "status": "500"}) == 1
    assert REGISTRY.get_sample_value("jntuh_http_requests_in_progress") == 0
    recorded = spans.get_finished_spans()
    assert recorded[-1].status.status_code.name == "ERROR"
    assert "198R1A05C4" not in str([dict(span.attributes) for span in recorded])
    assert "hidden" not in str([dict(span.attributes) for span in recorded])


def test_operation_exception_records_error_and_releases_gauge(spans):
    with pytest.raises(ValueError):
        with operation("test", "failure"):
            raise ValueError("private payload")
    assert REGISTRY.get_sample_value("jntuh_operations_in_progress", {"component": "test", "operation": "failure"}) == 0
    assert REGISTRY.get_sample_value("jntuh_operations_total", {"component": "test", "operation": "failure", "outcome": "error"}) == 1
    assert not spans.get_finished_spans()[-1].events


def test_queue_producer_and_consumer_share_trace(spans):
    from messaging.publisher import _publish
    from opentelemetry import propagate
    from opentelemetry.trace import SpanKind
    exchange = SimpleNamespace(publish=AsyncMock())

    async def run():
        with operation("test", "request"):
            await _publish(exchange, "198R1A05C4", "default_queue")
        message = exchange.publish.await_args.args[0]
        assert "traceparent" in message.headers
        assert message.delivery_mode == 2
        with operation("test", "consume", context=propagate.extract(message.headers), kind=SpanKind.CONSUMER):
            pass

    asyncio.run(run())
    producer, parent, consumer = spans.get_finished_spans()[-3:]
    assert producer.context.trace_id == parent.context.trace_id == consumer.context.trace_id
    assert consumer.parent.span_id == producer.context.span_id


def test_json_logs_redact_identifiers_credentials_and_query():
    record = logging.LogRecord("test", logging.INFO, "", 1,
        "198R1A05C4 21HA1R0002 24011P0164 18E51A0473 18E51A0479 https://user:password@example.com/path?key=secret", (), None)
    data = json.loads(JsonFormatter().format(record))
    assert data["message"].count("[roll-redacted]") == 5
    assert "password" not in data["message"]
    assert "key=secret" not in data["message"]


def test_readiness_checks_dependencies_without_leaking_errors():
    from utils.health import readiness
    connection = SimpleNamespace(is_closed=True)
    app = SimpleNamespace(state=SimpleNamespace(rabbitmq_connection=connection))
    with patch("utils.health.prismaConnection.prisma", SimpleNamespace(query_raw=AsyncMock(side_effect=RuntimeError("secret")))), patch("utils.health.redisConnection.client", None):
        response = asyncio.run(readiness(app))
    assert response.status_code == 503
    assert json.loads(response.body)["checks"] == {"postgres": "down", "redis": "down", "rabbitmq": "down"}
    assert b"secret" not in response.body


def test_metrics_exact_route_exposes_openmetrics_without_redirect():
    from starlette.routing import Route
    from utils.observability import MetricsEndpoint
    app = FastAPI()
    app.router.routes.append(Route("/metrics", endpoint=MetricsEndpoint()))

    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/metrics", headers={"Accept": "application/openmetrics-text"})
            assert response.status_code == 200
            assert "application/openmetrics-text" in response.headers["content-type"]
            assert "jntuh_http_requests_in_progress" in response.text
            assert response.text.endswith("# EOF\n")
    asyncio.run(run())


def test_handled_errors_are_not_counted_as_empty_results(spans):
    from utils.observability import observed, set_operation_outcome

    @observed("test", "handled", empty_result=True)
    async def handled():
        set_operation_outcome("error")
        return None

    asyncio.run(handled())
    assert REGISTRY.get_sample_value("jntuh_operations_total", {"component": "test", "operation": "handled", "outcome": "error"}) == 1
    assert REGISTRY.get_sample_value("jntuh_operations_total", {"component": "test", "operation": "handled", "outcome": "empty"}) is None


def test_mcp_unknown_tool_names_have_bounded_metric_labels():
    from utils.mcpMetrics import _extract_tool_name
    assert _extract_tool_name(SimpleNamespace(params=SimpleNamespace(name="attacker-generated-id"))) == "unknown"
    assert _extract_tool_name(SimpleNamespace(params=SimpleNamespace(name="get_all_result"))) == "get_all_result"
