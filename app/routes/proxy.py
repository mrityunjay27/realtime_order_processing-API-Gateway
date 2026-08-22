"""
Shared helper for building pass-through proxy routers.

A proxy router maps a public prefix (e.g. `/api/orders`) onto one upstream
service via a `GatewayClient`. It forwards the method, path, query string,
headers and body as-is, adds the gateway's correlation ID and — for
authenticated routers — the verified user identity as trusted headers,
and normalizes upstream failures so internal errors never leak to clients.

Two routes are registered per prefix so both `POST /api/payments` and
`POST /api/payments/` are served directly (no trailing-slash redirects).
"""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from app.auth.dependencies import AuthenticatedUser, get_authenticated_user
from app.clients.base import GatewayClient, UpstreamError, build_response
from app.config import (
    AUTH_TYPE_HEADER,
    CORRELATION_HEADER,
    USER_ID_HEADER,
    USER_ROLE_HEADER,
)

ALL_METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"]


def _identity_headers(user: AuthenticatedUser) -> dict[str, str]:
    """Trusted identity headers added after gateway authentication.

    The downstream service never sees the JWT again; it trusts these
    headers because only the gateway can set them (client-supplied values
    are stripped in GatewayClient.proxy).
    """
    headers = {
        USER_ID_HEADER: user.user_id,
        USER_ROLE_HEADER: user.role,
    }
    if user.auth_type != "jwt":
        headers[AUTH_TYPE_HEADER] = user.auth_type
    return headers


def make_proxy_router(
    client: GatewayClient, prefix: str, tag: str, *, authenticated: bool = False
) -> APIRouter:
    router = APIRouter(tags=[tag])

    summary = f"Proxy to {tag} service"
    description = (
        f"Forwards the request to the {tag} service. The correlation ID "
        "from the gateway is added as X-Correlation-ID before forwarding."
    )

    if authenticated:

        async def proxy(
            request: Request,
            path: str = "",
            user: AuthenticatedUser = Depends(get_authenticated_user),
        ):
            return await _handle(request, path, client, user)
    else:

        async def proxy(request: Request, path: str = ""):
            return await _handle(request, path, client)

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


async def _handle(
    request: Request,
    path: str,
    client: GatewayClient,
    user: AuthenticatedUser | None = None,
):
    correlation_id = request.state.correlation_id

    headers = {
        **dict(request.headers),
        CORRELATION_HEADER: correlation_id,
    }
    if user is not None:
        for key, value in _identity_headers(user).items():
            headers[key] = value

    try:
        upstream = await client.proxy(
            method=request.method,
            path=path,
            headers=headers,
            body=await request.body(),
            query=request.query_params,
            trusted_identity=_identity_headers(user) if user is not None else None,
        )
    except UpstreamError as exc:
        return JSONResponse(
            status_code=exc.status_code,
            content={**exc.payload, "correlation_id": correlation_id},
        )

    return build_response(upstream)
