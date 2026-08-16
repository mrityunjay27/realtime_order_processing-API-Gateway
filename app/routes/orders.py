"""Public order endpoints.

`POST /api/orders` (create order) and any future `/api/orders/*` are
forwarded to the order service. Order business logic, the outbox, and the
`orders.created` Kafka publish all stay in the order service.
"""

from app.clients.order_client import OrderClient
from app.routes.proxy import make_proxy_router

router = make_proxy_router(OrderClient(), prefix="/api/orders", tag="orders")
