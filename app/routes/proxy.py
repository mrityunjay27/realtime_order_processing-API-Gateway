"""
Shared helper for building pass-through proxy routers.

A proxy router maps a public prefix (e.g. `/api/orders`) onto one upstream
service via a `GatewayClient`. It forwards the method, path, query string,
headers and body as-is, adds the gateway's correlation ID, and normalizes
upstream failures so internal errors never leak to clients.

Two routes are registered per prefix so both `POST /api/orders` and
`POST /api/orders/` are served directly (no trailing-slash redirects).
"""

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.clients.base import GatewayClient, UpstreamError, build_response

ALL_METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"]


def make_proxy_router(client: GatewayClient, prefix: str, tag: str) -> APIRouter:
    router = APIRouter(tags=[tag])

    summary = f"Proxy to {tag} service"
    description = (
        f"Forwards the request to the {tag} service. The correlation ID "
        "from the gateway is added as X-Correlation-ID before forwarding."
    )

    async def proxy(request: Request, path: str = ""):
        correlation_id = request.state.correlation_id

        try:
            upstream = await client.proxy(
                method=request.method,
                path=path,
                headers={
                    **dict(request.headers),
                    "X-Correlation-ID": correlation_id,
                },
                body=await request.body(),
                query=request.query_params,
            )
        except UpstreamError as exc:
            return JSONResponse(
                status_code=exc.status_code,
                content={**exc.payload, "correlation_id": correlation_id},
            )

        return build_response(upstream)

    router.add_api_route(
        prefix,
        proxy,
        methods=ALL_METHODS,
        summary=summary,
        description=description,
    )
    router.add_api_route(
        f"{prefix}/{{path:path}}",
        proxy,
        methods=ALL_METHODS,
        summary=summary,
        description=description,
    )

    return router
