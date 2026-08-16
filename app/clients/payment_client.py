"""HTTP client for the payment service."""

from app.clients.base import GatewayClient
from app.config import PAYMENT_SERVICE_URL


class PaymentClient(GatewayClient):
    """Proxies to `{PAYMENT_SERVICE_URL}/api/payments/` and friends."""

    def __init__(self):
        super().__init__(base_url=PAYMENT_SERVICE_URL, prefix="/api/payments")
