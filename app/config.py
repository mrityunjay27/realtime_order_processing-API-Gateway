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
