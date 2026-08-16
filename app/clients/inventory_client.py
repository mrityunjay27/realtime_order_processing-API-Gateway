"""HTTP client for the inventory service.

One origin serves two public prefixes:
    - /api/inventory/*  -> {INVENTORY_SERVICE_URL}/api/inventory/*
    - /api/products/*   -> {INVENTORY_SERVICE_URL}/api/products/*
"""

from app.clients.base import GatewayClient
from app.config import INVENTORY_SERVICE_URL


class InventoryClient(GatewayClient):
    """Proxies to the inventory service under a configurable path prefix."""

    def __init__(self, prefix: str = "/api/inventory"):
        super().__init__(base_url=INVENTORY_SERVICE_URL, prefix=prefix)


class ProductsClient(InventoryClient):
    """Proxies to the inventory service under the `/api/products` prefix."""

    def __init__(self):
        super().__init__(prefix="/api/products")
