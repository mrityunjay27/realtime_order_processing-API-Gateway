"""
API Gateway — the synchronous HTTP entry point for the system.

Responsibilities (v1):
    - route public /api/* prefixes to the microservices
    - own the correlation ID for external requests
    - log requests/responses
    - normalize upstream failures (timeout, unavailable)
    - hide internal service addresses

Deliberately NOT here: business logic, databases, Kafka, the outbox.
Kafka remains the transport for asynchronous workflows; the gateway only
touches HTTP.
"""

import logging

from fastapi import FastAPI

from app.config import CORRELATION_HEADER
from app.middleware.correlation import CorrelationMiddleware
from app.routes.inventory import inventory_router, products_router
from app.routes.orders import router as orders_router
from app.routes.payment import router as payment_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

app = FastAPI(
    title="API Gateway",
    description=(
        "Synchronous HTTP entry point. Forwards /api/* to the order, "
        "inventory, and payment services and propagates the correlation ID."
    ),
    version="0.1.0",
    redirect_slashes=False,
)

app.add_middleware(CorrelationMiddleware)

app.include_router(orders_router)
app.include_router(inventory_router)
app.include_router(products_router)
app.include_router(payment_router)


@app.get("/health", tags=["health"])
async def health():
    return {"status": "ok"}


@app.get("/", tags=["health"], include_in_schema=False)
async def root():
    return {"service": "api-gateway", "docs": "/docs", "health": "/health"}
