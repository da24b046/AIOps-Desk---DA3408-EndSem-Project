"""Prometheus instrumentation with bounded, non-sensitive labels."""

from functools import wraps
from time import perf_counter

from fastapi import HTTPException
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Histogram,
    Info,
    generate_latest,
)
from starlette.responses import Response

HTTP_REQUESTS = Counter(
    "aiopsdesk_http_requests_total",
    "API HTTP requests.",
    ["method", "route", "status_class"],
)
HTTP_DURATION = Histogram(
    "aiopsdesk_http_request_duration_seconds",
    "API HTTP request duration.",
    ["method", "route"],
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10),
)
MODEL_CALLS = Counter(
    "aiopsdesk_model_calls_total",
    "Calls from the API to the model service, including readiness probes.",
    ["outcome"],
)
MODEL_DURATION = Histogram(
    "aiopsdesk_model_call_duration_seconds",
    "API-to-model call duration.",
    ["outcome"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 3),
)
PREDICTIONS = Counter(
    "aiopsdesk_predictions_total",
    "Successfully saved predictions.",
    ["category", "priority", "needs_review"],
)
CATEGORY_SCORE = Histogram(
    "aiopsdesk_category_score",
    "Category model scores for successfully saved predictions.",
    buckets=(0, 0.2, 0.4, 0.6, 0.8, 1),
)
PRIORITY_SCORE = Histogram(
    "aiopsdesk_priority_score",
    "Priority model scores for successfully saved predictions.",
    buckets=(0, 0.2, 0.4, 0.6, 0.8, 1),
)
DB_WRITE_FAILURES = Counter(
    "aiopsdesk_db_write_failures_total",
    "Failed prediction database writes.",
)
EXPECTED_RELEASE = Info(
    "aiopsdesk_expected_release",
    "Model and policy versions configured in the API.",
)


def instrument_model_call(function):
    @wraps(function)
    def wrapped(*args, **kwargs):
        started = perf_counter()
        outcome = "error"
        try:
            result = function(*args, **kwargs)
            outcome = "success"
            return result
        except HTTPException as error:
            outcome = {
                504: "timeout",
                503: "unavailable",
                502: "upstream_error",
            }.get(error.status_code, "error")
            raise
        finally:
            MODEL_CALLS.labels(outcome=outcome).inc()
            MODEL_DURATION.labels(outcome=outcome).observe(
                perf_counter() - started
            )
    return wrapped


def install_metrics(app, model_version, policy_version):
    EXPECTED_RELEASE.info({
        "model_version": model_version,
        "policy_version": policy_version,
    })

    @app.middleware("http")
    async def measure_request(request, call_next):
        if request.url.path == "/metrics":
            return await call_next(request)

        started = perf_counter()
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
            return response
        finally:
            route = getattr(request.scope.get("route"), "path", "unmatched")
            method = request.method
            if method not in {"GET", "POST", "DELETE", "PUT", "PATCH", "OPTIONS", "HEAD"}:
                method = "OTHER"

            HTTP_REQUESTS.labels(
                method=method,
                route=route,
                status_class=f"{status // 100}xx",
            ).inc()
            HTTP_DURATION.labels(method=method, route=route).observe(
                perf_counter() - started
            )

    @app.get("/metrics", include_in_schema=False)
    def metrics():
        return Response(
            content=generate_latest(),
            headers={"Content-Type": CONTENT_TYPE_LATEST},
        )
