"""Public payment endpoints.

Forwarded to the payment service. The gateway never triggers or stores
payments; it only routes the synchronous HTTP calls.
"""

from app.clients.payment_client import PaymentClient
from app.routes.proxy import make_proxy_router

router = make_proxy_router(PaymentClient(), prefix="/api/payments", tag="payments")
