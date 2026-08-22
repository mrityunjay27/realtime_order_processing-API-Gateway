"""
JWT verification for access tokens issued by the auth service.

The gateway is a *verifier*, never an issuer: it holds only the auth
service's RSA public key. Every token is checked for

    - RS256 signature (algorithm pinned — `alg` from the token itself is
      never trusted),
    - expiry (`exp`, verified by PyJWT),
    - issuer (`iss == JWT_ISSUER`),
    - audience (`aud == JWT_AUDIENCE`),
    - token type (`token_type == "access"`).

On success the verified claims dict is returned; on any failure an
`AuthenticationError` is raised, which the dependency layer maps to 401.
"""

import logging
from functools import lru_cache

import jwt

from app.config import (
    JWT_ALGORITHM,
    JWT_AUDIENCE,
    JWT_ISSUER,
    JWT_PUBLIC_KEY_PATH,
)

logger = logging.getLogger("gateway.auth")


class AuthenticationError(Exception):
    """Raised when a bearer token cannot be verified."""


@lru_cache(maxsize=1)
def _public_key() -> bytes:
    try:
        with open(JWT_PUBLIC_KEY_PATH, "rb") as f:
            return f.read()
    except OSError as exc:
        logger.error("JWT public key not readable at %s", JWT_PUBLIC_KEY_PATH)
        raise RuntimeError(
            f"Gateway misconfigured: cannot read JWT public key at {JWT_PUBLIC_KEY_PATH}"
        ) from exc


def verify_access_token(token: str) -> dict:
    """Verify signature + claims of a bearer token and return its claims.

    Raises `AuthenticationError` with a safe message on any failure.
    """
    try:
        claims = jwt.decode(
            token,
            _public_key(),
            algorithms=[JWT_ALGORITHM],
            issuer=JWT_ISSUER,
            audience=JWT_AUDIENCE,
            options={"require": ["exp", "sub"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise AuthenticationError("Token has expired") from exc
    except jwt.InvalidIssuerError as exc:
        raise AuthenticationError("Invalid token issuer") from exc
    except jwt.InvalidAudienceError as exc:
        raise AuthenticationError("Invalid token audience") from exc
    except jwt.MissingRequiredClaimError as exc:
        raise AuthenticationError("Token missing required claim") from exc
    except jwt.ImmatureSignatureError as exc:
        raise AuthenticationError("Token not yet valid") from exc
    except jwt.InvalidAlgorithmError as exc:
        raise AuthenticationError("Invalid token algorithm") from exc
    except jwt.PyJWTError as exc:
        raise AuthenticationError("Invalid token") from exc

    if claims.get("token_type") != "access":
        raise AuthenticationError("Wrong token type")

    return claims
