"""Public inventory and product endpoints.

Both `/api/inventory/*` and `/api/products/*` live in the inventory
service, so the client hides that both prefixes hit the same origin.
"""

from app.clients.inventory_client import InventoryClient, ProductsClient
from app.routes.proxy import make_proxy_router

inventory_router = make_proxy_router(
    InventoryClient(), prefix="/api/inventory", tag="inventory"
)

products_router = make_proxy_router(
    ProductsClient(), prefix="/api/products", tag="products"
)
