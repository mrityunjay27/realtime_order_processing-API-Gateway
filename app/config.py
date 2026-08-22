"""Gateway configuration, loaded from environment variables.

The gateway is deliberately stateless: no database, no Kafka, no outbox.
All it needs to know is where the upstream services live and how long to
wait for them.
"""

import os


def _service_url(name: str, default: str) -> str:
    return os.getenv(name, default).rstrip("/")


GATEWAY_HOST = os.getenv("GATEWAY_HOST", "0.0.0.0")
GATEWAY_PORT = int(os.getenv("GATEWAY_PORT", "8081"))

# Upstream service origins. Defaults match the natively-running services:
#   order_service     -> 8001
#   inventory_service -> 8000
#   payment_service   -> 8002
ORDER_SERVICE_URL = _service_url("ORDER_SERVICE_URL", "http://localhost:8001")
INVENTORY_SERVICE_URL = _service_url("INVENTORY_SERVICE_URL", "http://localhost:8000")
PAYMENT_SERVICE_URL = _service_url("PAYMENT_SERVICE_URL", "http://localhost:8002")
AUTH_SERVICE_URL = _service_url("AUTH_SERVICE_URL", "http://localhost:8003")

# Never let the gateway wait on an upstream forever.
GATEWAY_TIMEOUT_SECONDS = float(os.getenv("GATEWAY_TIMEOUT_SECONDS", "10"))

# Header used to carry the correlation ID in and out of the gateway.
CORRELATION_HEADER = os.getenv("CORRELATION_HEADER", "X-Correlation-ID")

# ---------------------------------------------------------------------------
# JWT verification (Phase 3)
#
# The gateway verifies access tokens issued by the auth service (RS256).
# It only ever holds the PUBLIC key — the private key never leaves the
# auth service.
# ---------------------------------------------------------------------------
JWT_PUBLIC_KEY_PATH = os.getenv(
    "JWT_PUBLIC_KEY_PATH", str(os.path.join(os.path.dirname(os.path.dirname(__file__)), "keys", "public.pem"))
)
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "RS256")
JWT_ISSUER = os.getenv("JWT_ISSUER", "auth-service")
JWT_AUDIENCE = os.getenv("JWT_AUDIENCE", "api-gateway")

# ---------------------------------------------------------------------------
# Development authentication bypass
#
# The bypass activates ONLY when ALL of the following hold:
#   1. ENVIRONMENT is exactly "development"
#   2. DEV_AUTH_BYPASS_ENABLED is explicitly "true"
#   3. The request carries X-Dev-Auth equal to DEV_AUTH_BYPASS_TOKEN
#
# In any other environment the header is ignored as if it did not exist.
# ---------------------------------------------------------------------------
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")


def _env_flag(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).strip().lower() == "true"


DEV_AUTH_BYPASS_ENABLED = _env_flag("DEV_AUTH_BYPASS_ENABLED")
DEV_AUTH_BYPASS_TOKEN = os.getenv("DEV_AUTH_BYPASS_TOKEN", "")
DEV_AUTH_HEADER = os.getenv("DEV_AUTH_HEADER", "X-Dev-Auth")

# Identity headers the gateway sets on proxied requests. Client-supplied
# values are stripped so they can never be spoofed downstream.
USER_ID_HEADER = os.getenv("USER_ID_HEADER", "X-User-ID")
USER_ROLE_HEADER = os.getenv("USER_ROLE_HEADER", "X-User-Role")
AUTH_TYPE_HEADER = os.getenv("AUTH_TYPE_HEADER", "X-Auth-Type")
