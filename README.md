# API Gateway

A thin, synchronous HTTP entry point for the realtime order processing system. It sits in front of the three Django services (**Order** :8001, **Inventory** :8000, **Payment** :8002) and forwards public `/api/*` requests to them, propagating the correlation ID so the existing distributed tracing (root README, Phase 6) extends seamlessly to the outside world.

```
 Client
   │  POST /api/orders/  (X-Correlation-ID: optional)
   ▼
┌─────────────────────────────────────────┐
│           API Gateway (:8081)           │
│  FastAPI + uvicorn, stateless           │
│                                         │
│  CorrelationMiddleware                  │
│    │  generate/trust X-Correlation-ID   │
│    │  store on request.state            │
│    │  echo on response                  │
│    ▼                                    │
│  Router (proxy)                         │
│    │  method + path + query + body      │
│    │  + X-Correlation-ID forwarded      │
│    ▼                                    │
│  GatewayClient (httpx, 10s timeout)     │
│    │  strips hop-by-hop headers         │
│    │  normalizes timeouts → 504         │
│    │  normalizes unreachable → 503      │
│    ▼                                    │
│  JSONResponse / Response                │
└──────────────┬──────────────────────────┘
               │
   ┌───────────┼───────────────┐
   ▼           ▼               ▼
Order svc   Inventory svc   Payment svc
 :8001         :8000           :8002
```

---

## Running the Server

### 1. Start the upstream services

The gateway only forwards requests — it needs the three Django services up and migrated first (see the root README "Running the System"):

```bash
cd infra && docker compose up -d                       # Kafka, Kafka UI, Loki, Alloy, Grafana
cd ../order_service && docker compose up -d            # Postgres :5433
cd ../inventory_service && docker compose up -d        # Postgres :5434
cd ../payment_service && docker compose up -d          # Postgres :5435
```

Then migrate and start each service (one terminal per service, or VS Code launch configs):

```bash
cd order_service && source venv/bin/activate && python manage.py migrate && honcho start
cd inventory_service && source venv/bin/activate && python manage.py migrate && honcho start
cd payment_service && source .venv/bin/activate && python manage.py migrate && honcho start
```

### 2. Start the gateway

```bash
cd api-gateway
python -m venv venv && source venv/bin/activate   # first time only
pip install -r requirements.txt                   # first time only
honcho start                                      # or: uvicorn app.main:app --host 0.0.0.0 --port 8081
```

The gateway listens on `http://localhost:8081`. Health check: `http://localhost:8081/health` → `{"status": "ok"}`. Interactive API docs: `http://localhost:8081/docs`.

## Testing the Endpoints

Seed data and run requests **through the gateway** (port 8081), not the services directly.

```bash
# 1. Create a product (inventory service via gateway)
curl -X POST http://127.0.0.1:8081/api/products/ \
  -H "Content-Type: application/json" \
  -d '{"name": "Laptop", "description": "A laptop", "price": "999.99"}'

# 2. Create inventory for it (grab the product uuid from the response)
curl -X POST http://127.0.0.1:8081/api/inventory/ \
  -H "Content-Type: application/json" \
  -d '{"product": "<product-uuid>", "available_quantity": 10}'

# 3. List payments (payment service, read-only)
curl http://127.0.0.1:8081/api/payments/

# 4. Create an order through the gateway, with your own correlation ID
curl -X POST http://127.0.0.1:8081/api/orders/ \
  -H "Content-Type: application/json" \
  -H "X-Correlation-ID: aaaa1111-bbbb-2222-cccc-3333dddd4444" \
  -d '{"customer": "<customer-uuid>", "items": [{"product_id": "<product-uuid>", "quantity": 2, "price": "999.99"}]}'
```

### What to expect

- **`GET /health`** → `{"status": "ok"}` — gateway is up.
- **Happy path** → the gateway echoes the upstream's response, and the response carries the `X-Correlation-ID` header you sent (or a generated one). Follow that ID in Grafana to watch the full saga.
- **Upstream down** → `503 {"error": "SERVICE_UNAVAILABLE", ..., "correlation_id": "..."}` — the gateway never hangs or leaks internal details.
- **Upstream timeout** → `504 {"error": "UPSTREAM_TIMEOUT", ...}` after the 10s `GATEWAY_TIMEOUT_SECONDS` budget.

Every request is logged by the gateway (`Request received` / `Request completed` with `correlation_id`, `method`, `path`, `duration_ms`).

---

## What it is (and deliberately isn't)

The gateway is **stateless by design** — no database, no Kafka, no outbox, no business logic. It only knows:

1. where each upstream service lives (`app/config.py`, from env vars),
2. how long to wait for them (`GATEWAY_TIMEOUT_SECONDS`, default 10s),
3. how to propagate the correlation ID.

Asynchronous workflows (Kafka, the transactional outbox, the saga) are untouched by the gateway. It is the *synchronous* entry point only: it exposes the `POST /api/orders/` create-order call and the read/write inventory and payment APIs, and the response the client gets is the response the upstream returned.

**Why a gateway exists at all:** without it, clients would need to know three internal addresses, would receive raw upstream failures, and would have no single place to start the correlation trace. The gateway gives one public surface, one timeout policy, one place where internal errors are normalized into clean `503/504` JSON, and it hides which service actually handles what.

---

## Request lifecycle

### 1. Correlation ID (birth of the trace)

`app/middleware/correlation.py` — the external entry point of the whole system, so it is the **first** place a correlation ID is minted for an external request. Same rules as the Django services' `CorrelationMiddleware`:

- A **valid** `X-Correlation-ID` request header is trusted and reused (a client or an upstream gateway can start the trace).
- A **missing or invalid** header gets a fresh `uuid4()`.
- The value is stored on `request.state.correlation_id` and echoed back on the **response** as `X-Correlation-ID`.

It also logs `Request received` / `Request completed` (with `duration_ms`) per request.

### 2. Routing

`app/main.py` registers four routers, all built by the shared `make_proxy_router` helper (`app/routes/proxy.py`):

| Public prefix | Upstream client | Backing service |
|---------------|-----------------|-----------------|
| `/api/orders` | `OrderClient` | order service |
| `/api/inventory` | `InventoryClient` | inventory service |
| `/api/products` | `ProductsClient` | inventory service |
| `/api/payments` | `PaymentClient` | payment service |

`make_proxy_router` registers **two** routes per prefix (`{prefix}` and `{prefix}/{path:path}`) so both `POST /api/orders` and `POST /api/orders/` are served directly — no trailing-slash redirects. Every method (`GET/POST/PUT/PATCH/DELETE/HEAD/OPTIONS`) is forwarded.

The proxy handler:
1. reads the correlation ID off `request.state`,
2. forwards method, path, query string, headers and body as-is, overriding `X-Correlation-ID` with the gateway's value,
3. returns the upstream's response byte-for-byte (status, headers minus hop-by-hop, body).

### 3. Forwarding

`app/clients/base.py` — a `GatewayClient` knows the origin of one service, the internal path prefix it proxies, and the timeout budget. `proxy()` builds `{origin}{prefix}/{path}` and calls `httpx.AsyncClient.request(...)`.

**Hop-by-hop headers** (`connection`, `content-length`, `host`, `transfer-encoding`, `upgrade`, …) are stripped in both directions — `httpx` recomputes `content-length` from the body it sends.

### 4. Failure normalization

| Upstream condition | Client response |
|--------------------|-----------------|
| Timeout (`httpx.TimeoutException`) | `504 UPSTREAM_TIMEOUT` |
| Unreachable / HTTP error (`httpx.HTTPError`) | `503 SERVICE_UNAVAILABLE` |

Both raise `UpstreamError`, which the route handler converts to a `JSONResponse` — internal service names and stack traces never leak to the client. The `correlation_id` is always included in the error body so failures can be traced.

---

## Directory structure

```
api-gateway/
├── Procfile                          # web: uvicorn app.main:app --port $GATEWAY_PORT
├── requirements.txt                  # fastapi, uvicorn[standard], httpx
├── .env                              # GATEWAY_HOST/PORT, *_SERVICE_URL, timeout
└── app/
    ├── main.py                       # FastAPI app, middleware + router wiring, /health
    ├── config.py                     # env-driven config, no secrets, stateless
    ├── middleware/
    │   └── correlation.py            # external correlation ID entry point
    ├── routes/
    │   ├── proxy.py                  # make_proxy_router (shared pass-through helper)
    │   ├── orders.py                 # /api/orders → OrderClient
    │   ├── inventory.py              # /api/inventory + /api/products → inventory svc
    │   └── payment.py                # /api/payments → PaymentClient
    └── clients/
        ├── base.py                   # GatewayClient, UpstreamError, hop-by-hop filter
        ├── order_client.py
        ├── inventory_client.py       # InventoryClient + ProductsClient (one origin, two prefixes)
        └── payment_client.py
```

## Configuration (`.env`)

| Variable | Default | Purpose |
|----------|---------|---------|
| `GATEWAY_HOST` | `0.0.0.0` | Bind address |
| `GATEWAY_PORT` | `8081` | Listen port |
| `ORDER_SERVICE_URL` | `http://localhost:8001` | Order upstream |
| `INVENTORY_SERVICE_URL` | `http://localhost:8000` | Inventory upstream |
| `PAYMENT_SERVICE_URL` | `http://localhost:8002` | Payment upstream |
| `GATEWAY_TIMEOUT_SECONDS` | `10` | Upstream timeout — the gateway never waits forever |
| `CORRELATION_HEADER` | `X-Correlation-ID` | Header carrying the trace ID |

When services are dockerized, swap the URLs for service DNS (e.g. `http://order-service:8000`) — the gateway needs no code change.

## Running

```bash
cd api-gateway && source venv/bin/activate
honcho start
# or directly:
uvicorn app.main:app --host 0.0.0.0 --port 8081
```

Health check at `http://localhost:8081/health`; OpenAPI docs at `/docs`.

### Example

```bash
# Via the gateway — the order service's create-order API, with a client-chosen trace ID
curl -X POST http://127.0.0.1:8081/api/orders/ \
  -H "Content-Type: application/json" \
  -H "X-Correlation-ID: aaaa1111-bbbb-2222-cccc-3333dddd4444" \
  -d '{"customer": "<customer-uuid>", "items": [{"product_id": "<product-uuid>", "quantity": 2, "price": "999.99"}]}'

# The same ID is echoed back on the response and forwarded to the order service,
# so the whole saga (inventory.reserved → payments.requested → ...) stays one trace.
```

## Relationship to the rest of the system

- **Kafka is untouched.** The gateway never produces or consumes events. After the synchronous `POST /api/orders/` returns, the asynchronous flow (`orders.created` → inventory reservation → payment → saga compensation) runs exactly as documented in the root README.
- **The gateway is the new birth place of the correlation ID.** Previously the Order service's `CorrelationMiddleware` was the first hop; now the gateway owns that role for external requests and passes the ID down, so downstream tracing still works with no changes to the services.
- **Stateless = horizontally scalable.** Because the gateway holds no data, any number of gateway instances can be run in front of the services.
