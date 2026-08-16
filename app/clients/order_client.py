"""HTTP client for the order service."""

from app.clients.base import GatewayClient
from app.config import ORDER_SERVICE_URL


class OrderClient(GatewayClient):
    """Proxies to `POST {ORDER_SERVICE_URL}/api/orders/` and friends."""

    def __init__(self):
        super().__init__(base_url=ORDER_SERVICE_URL, prefix="/api/orders")
