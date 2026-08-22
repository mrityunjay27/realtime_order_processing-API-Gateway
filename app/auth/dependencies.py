"""
Authentication dependency for protected gateway routes.

Resolution order per request:

    1. Development bypass — only when ALL of these hold:
         ENVIRONMENT == "development"
         DEV_AUTH_BYPASS_ENABLED is true
         the X-Dev-Auth header equals DEV_AUTH_BYPASS_TOKEN
       In any other environment, or with a wrong/missing header, the
       bypass is invisible and normal JWT verification runs.
    2. `Authorization: Bearer <jwt>` verified against the auth service's
       public key.

The result is an `AuthenticatedUser` value object that routes forward
downstream as trusted identity headers.
"""

import logging
import secrets
from dataclasses import dataclass, field
from typing import Any

from fastapi import Request
from fastapi.security.utils import get_authorization_scheme_param

from app.auth.jwt import verify_access_token, AuthenticationError
from app.config import (
    DEV_AUTH_BYPASS_ENABLED,
    DEV_AUTH_BYPASS_TOKEN,
    DEV_AUTH_HEADER,
    ENVIRONMENT,
)

logger = logging.getLogger("gateway.auth")

BEARER_SCHEME = "bearer"


@dataclass(frozen=True)
class AuthenticatedUser:
    user_id: str
    role: str
    auth_type: str  # "jwt" | "dev_bypass"
    claims: dict[str, Any] = field(default_factory=dict)


def _dev_bypass_user() -> AuthenticatedUser:
    return AuthenticatedUser(
        user_id="dev-superuser",
        role="ADMIN",
        auth_type="dev_bypass",
        claims={"sub": "dev-superuser", "role": "ADMIN", "auth_type": "dev_bypass"},
    )


def _dev_bypass_active(request: Request) -> bool:
    if ENVIRONMENT != "development" or not DEV_AUTH_BYPASS_ENABLED:
        return False
    presented = request.headers.get(DEV_AUTH_HEADER, "")
    return bool(
        DEV_AUTH_BYPASS_TOKEN
        and secrets.compare_digest(presented, DEV_AUTH_BYPASS_TOKEN)
    )


async def get_authenticated_user(request: Request) -> AuthenticatedUser:
    """FastAPI dependency: resolve the caller's identity or raise 401."""
    from fastapi import HTTPException

    def unauthorized(detail: str) -> HTTPException:
        return HTTPException(
            status_code=401,
            detail=detail,
            headers={"WWW-Authenticate": "Bearer"},
        )

    if _dev_bypass_active(request):
        logger.info("Dev authentication bypass used")
        return _dev_bypass_user()

    authorization = request.headers.get("Authorization", "")
    scheme, token = get_authorization_scheme_param(authorization)
    if scheme.lower() != BEARER_SCHEME or not token:
        raise unauthorized("Authentication required")

    try:
        claims = verify_access_token(token)
    except AuthenticationError as exc:
        raise unauthorized(str(exc)) from exc

    return AuthenticatedUser(
        user_id=str(claims["sub"]),
        role=str(claims.get("role", "")),
        auth_type="jwt",
        claims=claims,
    )
