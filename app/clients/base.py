"""
Shared HTTP client for talking to upstream microservices.

A `GatewayClient` knows three things:
    - the origin of one service (from config),
    - the internal path prefix it proxies (e.g. `/api/orders`),
    - the timeout budget for that service.

Routes stay free of HTTP details: they call `proxy()` and either get an
`httpx.Response` or an `UpstreamError` with a normalized payload.
"""

import logging

import httpx
from starlette.responses import Response

from app.config import GATEWAY_TIMEOUT_SECONDS

logger = logging.getLogger("gateway.client")

# Headers that must not be forwarded hop-to-hop. httpx recomputes
# content-length itself from the body we pass.
HOP_BY_HOP_HEADERS = {
    "connection",
    "content-length",
    "host",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
}


class UpstreamError(Exception):
    """A normalized error representing an unhealthy/unreachable upstream."""

    def __init__(self, status_code: int, payload: dict):
        self.status_code = status_code
        self.payload = payload
        super().__init__(payload.get("message"))


class GatewayClient:
    def __init__(self, base_url: str, prefix: str, timeout: float = GATEWAY_TIMEOUT_SECONDS):
        self.base_url = base_url.rstrip("/")
        self.prefix = prefix.rstrip("/")
        self.timeout = timeout

    def _target(self, path: str) -> str:
        if path:
            return f"{self.base_url}{self.prefix}/{path.lstrip('/')}"
        return f"{self.base_url}{self.prefix}/"

    async def proxy(self, method, path, *, headers=None, body=None, query=None) -> httpx.Response:
        target = self._target(path)
        forwarded_headers = {
            key: value
            for key, value in (headers or {}).items()
            if key.lower() not in HOP_BY_HOP_HEADERS
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                return await client.request(
                    method=method,
                    url=target,
                    params=query,
                    headers=forwarded_headers,
                    content=body,
                )
        except httpx.TimeoutException:
            logger.exception("Upstream timed out: %s", target)
            raise UpstreamError(
                status_code=504,
                payload={
                    "error": "UPSTREAM_TIMEOUT",
                    "message": "Upstream service timed out",
                },
            )
        except httpx.HTTPError:
            logger.exception("Upstream unreachable: %s", target)
            raise UpstreamError(
                status_code=503,
                payload={
                    "error": "SERVICE_UNAVAILABLE",
                    "message": "Upstream service is temporarily unavailable",
                },
            )


def build_response(upstream: httpx.Response) -> Response:
    """Copy the upstream response to the gateway, dropping hop-by-hop headers."""
    headers = {
        key: value
        for key, value in upstream.headers.items()
        if key.lower() not in HOP_BY_HOP_HEADERS
    }
    return Response(content=upstream.content, status_code=upstream.status_code, headers=headers)
