"""
Correlation ID middleware for the API Gateway.

This is the external entry point of the whole system, so it is the FIRST
place a correlation ID is seen for an external request. Same rules as the
Django services (core/logging/middleware.py):

    - A valid `X-Correlation-ID` request header is trusted and reused.
    - A missing or invalid header gets a freshly generated UUID.
    - The value is stored on the request state for the duration of the
      request and echoed back on the response as `X-Correlation-ID`.

The route handlers read `request.state.correlation_id` and forward it to
the downstream service on every proxied HTTP call, so the trace the
Django services already maintain continues seamlessly through the gateway.
"""

import logging
import time
import uuid

from starlette.datastructures import MutableHeaders

from app.config import CORRELATION_HEADER

logger = logging.getLogger("gateway.correlation")


class CorrelationMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        correlation_id = self._extract_or_generate(scope)
        scope.setdefault("state", {})["correlation_id"] = correlation_id

        start = time.perf_counter()

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers[CORRELATION_HEADER] = correlation_id
            await send(message)

        method = scope.get("method", "")
        path = scope.get("path", "")

        logger.info(
            "Request received",
            extra={
                "correlation_id": correlation_id,
                "method": method,
                "path": path,
            },
        )

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception:
            logger.exception(
                "Unhandled exception during request",
                extra={
                    "correlation_id": correlation_id,
                    "method": method,
                    "path": path,
                },
            )
            raise
        finally:
            duration_ms = round((time.perf_counter() - start) * 1000, 2)
            logger.info(
                "Request completed",
                extra={
                    "correlation_id": correlation_id,
                    "method": method,
                    "path": path,
                    "duration_ms": duration_ms,
                },
            )

    @staticmethod
    def _extract_or_generate(scope) -> str:
        for raw_key, raw_value in scope.get("headers", []):
            if raw_key.lower() == CORRELATION_HEADER.encode().lower():
                incoming = raw_value.decode()
                if CorrelationMiddleware._is_valid_uuid(incoming):
                    return incoming
                break
        return str(uuid.uuid4())

    @staticmethod
    def _is_valid_uuid(value: str) -> bool:
        try:
            uuid.UUID(value)
            return True
        except (ValueError, TypeError, AttributeError):
            return False
