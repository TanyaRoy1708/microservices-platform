"""
order-service/app.py

Handles order retrieval with a Redis caching layer to reduce PostgreSQL load.
On cache miss: queries DB, caches result for 60 seconds. On cache hit: serves
directly from Redis — eliminates DB round-trip entirely.

Flow: API Gateway → Order Service → Redis (HIT) → Return
                                 → Redis (MISS) → PostgreSQL → Cache → Return

Key design decisions:
  - Redis TTL=60s: short enough to reflect near-real-time data, long enough
    to absorb traffic spikes. In production, use cache invalidation on write
    instead of TTL for stronger consistency guarantees.
  - Per-query cache keys: each unique filter combination gets its own key.
    Avoids serving stale filtered results when only some orders change.
  - Custom Prometheus counters: tracks cache hit/miss ratio — the primary
    metric for evaluating whether Redis is actually helping. Target: >70% hit rate.
  - lifespan + asynccontextmanager: modern FastAPI lifecycle management.
"""
from contextlib import asynccontextmanager, closing
from fastapi import FastAPI, HTTPException, Request, Query
from fastapi.responses import JSONResponse
from prometheus_fastapi_instrumentator import Instrumentator
from prometheus_client import Counter
import redis, psycopg2, os, json, time, uuid, logging
from psycopg2 import pool
from pythonjsonlogger import jsonlogger
from typing import Optional

# ─── Structured JSON Logging ──────────────────────────────────────────────────
logger = logging.getLogger("order-service")
handler = logging.StreamHandler()
handler.setFormatter(jsonlogger.JsonFormatter(
    fmt="%(asctime)s %(levelname)s %(name)s %(message)s"
))
logger.addHandler(handler)
logger.setLevel(logging.INFO)
logging.getLogger("uvicorn.access").handlers = []

# ─── Custom Prometheus Metrics ────────────────────────────────────────────────
# These counters measure cache effectiveness — the primary KPI for the Redis layer.
# In Grafana: rate(cache_hits_total[5m]) / rate(cache_requests_total[5m]) = hit ratio
cache_hits = Counter("order_cache_hits_total", "Redis cache hits for order queries")
cache_misses = Counter("order_cache_misses_total", "Redis cache misses for order queries")

# ─── Redis Client ─────────────────────────────────────────────────────────────
# redis-py maintains its own internal connection pool (default: 50 connections).
# Module-level instantiation is correct and safe for shared use across requests.
redis_client = redis.from_url(
    os.environ.get("REDIS_URL", "redis://redis:6379"),
    decode_responses=False,
    socket_connect_timeout=2,
    socket_timeout=2,
)

# ─── Application Lifecycle ────────────────────────────────────────────────────
db_pool = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global db_pool
    db_pool = pool.SimpleConnectionPool(
        minconn=1,
        maxconn=20,
        host=os.environ["DB_HOST"],
        port=os.environ.get("DB_PORT", "5432"),
        database=os.environ["DB_NAME"],
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
        connect_timeout=5,
    )
    logger.info("db.pool.initialized", extra={"min": 1, "max": 20})
    yield
    if db_pool:
        db_pool.closeall()
        logger.info("db.pool.closed")


app = FastAPI(title="Order Service", version="2.0", lifespan=lifespan)
Instrumentator().instrument(app).expose(app)


@asynccontextmanager
async def get_db_conn():
    conn = db_pool.getconn()
    try:
        yield conn
    finally:
        db_pool.putconn(conn)


# ─── Request ID Middleware ────────────────────────────────────────────────────
@app.middleware("http")
async def add_request_id(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    start = time.time()
    response = await call_next(request)
    duration_ms = round((time.time() - start) * 1000, 2)
    response.headers["X-Request-ID"] = request_id
    logger.info("http.request", extra={
        "request_id": request_id,
        "method": request.method,
        "path": request.url.path,
        "status_code": response.status_code,
        "duration_ms": duration_ms,
    })
    return response


# ─── Health Check ─────────────────────────────────────────────────────────────
@app.get("/health")
async def health():
    """
    Checks both PostgreSQL and Redis connectivity.
    Returns 'degraded' (HTTP 503) if either dependency is unreachable.
    This tells Kubernetes to stop routing traffic without restarting the pod.
    """
    db_status, redis_status = "healthy", "healthy"

    try:
        async with get_db_conn() as conn:
            with closing(conn.cursor()) as cur:
                cur.execute("SELECT 1")
    except Exception as e:
        db_status = f"unhealthy: {str(e)}"
        logger.error("health.db.failure", extra={"error": str(e)})

    try:
        redis_client.ping()
    except Exception as e:
        redis_status = f"unhealthy: {str(e)}"
        logger.error("health.redis.failure", extra={"error": str(e)})

    overall = "healthy" if db_status == "healthy" and redis_status == "healthy" else "degraded"
    return JSONResponse(
        status_code=200 if overall == "healthy" else 503,
        content={
            "status": overall,
            "service": "order-service",
            "version": "2.0",
            "dependencies": {"postgres": db_status, "redis": redis_status},
        }
    )


# ─── Endpoints ────────────────────────────────────────────────────────────────

@app.get("/orders")
async def get_orders(
    request: Request,
    status: Optional[str] = Query(None, description="Filter by order status (pending/shipped/delivered/cancelled)"),
    user_id: Optional[int] = Query(None, description="Filter by user ID"),
    min_amount: Optional[float] = Query(None, description="Minimum order amount (inclusive)"),
    max_amount: Optional[float] = Query(None, description="Maximum order amount (inclusive)"),
):
    """
    List orders with optional filters. Results are cached in Redis for 60s.

    Cache key is deterministic: built from sorted query params so
    /orders?status=pending&user_id=1 and /orders?user_id=1&status=pending
    hit the same cache entry.
    """
    start = time.time()

    # Build deterministic cache key from sorted query params
    params_str = "_".join([f"{k}={v}" for k, v in sorted(request.query_params.items())])
    cache_key = f"orders_{params_str}" if params_str else "orders_all"

    cached = redis_client.get(cache_key)
    if cached:
        cache_hits.inc()
        logger.info("orders.cache.hit", extra={"cache_key": cache_key})
        return json.loads(cached)

    cache_misses.inc()

    try:
        async with get_db_conn() as conn:
            with closing(conn.cursor()) as cur:
                query = "SELECT id, user_id, product, amount, status FROM orders WHERE 1=1"
                params = []
                if status:
                    query += " AND status = %s"
                    params.append(status)
                if user_id:
                    query += " AND user_id = %s"
                    params.append(user_id)
                if min_amount is not None:
                    query += " AND amount >= %s"
                    params.append(min_amount)
                if max_amount is not None:
                    query += " AND amount <= %s"
                    params.append(max_amount)

                cur.execute(query, params)
                orders = [
                    {"id": r[0], "user_id": r[1], "product": r[2],
                     "amount": float(r[3]), "status": r[4]}
                    for r in cur.fetchall()
                ]

        # Cache for 60 seconds — short TTL balances freshness vs. DB load reduction
        redis_client.setex(cache_key, 60, json.dumps(orders))

        duration_ms = round((time.time() - start) * 1000, 2)
        logger.info("orders.list.complete", extra={
            "count": len(orders),
            "cache_hit": False,
            "cache_key": cache_key,
            "duration_ms": duration_ms,
        })
        return orders

    except Exception as e:
        logger.error("orders.list.error", extra={"error": str(e)})
        raise HTTPException(status_code=500, detail="database error")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5002)