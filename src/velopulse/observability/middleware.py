"""FastAPI middlewares for distributed correlation IDs and Prometheus metrics."""

import logging
import time
from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.routing import Match
from starlette.types import ASGIApp

from velopulse.observability.context import (
    get_correlation_id,
    reset_correlation_id,
    set_correlation_id,
)
from velopulse.observability.metrics import (
    HTTP_REQUEST_DURATION_SECONDS,
    HTTP_REQUESTS_TOTAL,
)

logger = logging.getLogger("velopulse.observability.middleware")


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """Extracts or generates an X-Correlation-ID header, attaching it to contextvars."""

    def __init__(self, app: ASGIApp, header_name: str = "X-Correlation-ID") -> None:
        super().__init__(app)
        self.header_name = header_name

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        incoming_cid = request.headers.get(self.header_name) or request.headers.get("X-Request-ID")
        token = set_correlation_id(incoming_cid)
        active_cid = get_correlation_id()

        start_time = time.perf_counter()
        try:
            response: Response = await call_next(request)
            response.headers[self.header_name] = active_cid
            return response
        finally:
            elapsed = time.perf_counter() - start_time
            logger.debug(
                "Request handled [%s]: %s %s (took %.3f ms)",
                active_cid,
                request.method,
                request.url.path,
                elapsed * 1000.0,
            )
            reset_correlation_id(token)


class PrometheusMetricsMiddleware(BaseHTTPMiddleware):
    """Instruments incoming HTTP requests with Prometheus metrics counters and histograms."""

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        # Don't record internal scraping requests to prevent recursion/distortion
        if request.url.path == "/metrics":
            return await call_next(request)

        method = request.method
        endpoint = self._get_matched_endpoint(request)
        start_time = time.perf_counter()
        status_code = 500

        try:
            response: Response = await call_next(request)
            status_code = response.status_code
            return response
        finally:
            duration = max(0.0, time.perf_counter() - start_time)
            HTTP_REQUESTS_TOTAL.labels(
                method=method,
                endpoint=endpoint,
                status_code=str(status_code),
            ).inc()
            HTTP_REQUEST_DURATION_SECONDS.labels(
                method=method,
                endpoint=endpoint,
            ).observe(duration)

    @staticmethod
    def _get_matched_endpoint(request: Request) -> str:
        """Resolve matched route pattern or fallback to path."""
        for route in request.app.routes:
            match, _ = route.matches(request.scope)
            if match == Match.FULL and hasattr(route, "path"):
                return str(route.path)
        return request.url.path
