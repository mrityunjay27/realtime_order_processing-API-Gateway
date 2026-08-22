"""Payment endpoints — JWT-protected at the gateway.

Forwarded to the payment service. The gateway authenticates the caller
(Bearer JWT or dev bypass), then forwards the verified identity as
X-User-ID / X-User-Role headers. The payment service never sees the JWT.
"""

from app.clients.payment_client import PaymentClient
from app.routes.proxy import make_proxy_router

router = make_proxy_router(
    PaymentClient(), prefix="/api/payments", tag="payments", authenticated=True
)
