"""
user-service/app.py

Manages user CRUD operations. Connects to PostgreSQL via a connection pool
to avoid connection exhaustion under concurrent load.

Flow: API Gateway → User Service (FastAPI) → psycopg2 Pool → PostgreSQL → Response

Key design decisions:
  - SimpleConnectionPool (min=1, max=20): pre-warms connections at startup,
    avoids the TCP + TLS handshake cost on every request. Under 20 concurrent
    requests, this eliminates connection exhaustion entirely.
  - Structured JSON logging: every log line is machine-parseable by CloudWatch
    Logs Insights, Datadog, or any log aggregator — enabling log-based alerting.
  - Deep health check: actually verifies DB connectivity, not just "I started".
    Kubernetes liveness/readiness probes call this — a shallow check masks outages.
  - lifespan pattern (FastAPI 0.95+): replaces the deprecated @on_event decorator.
    Proper async context manager for startup/shutdown lifecycle management.
"""
from contextlib import asynccontextmanager, closing
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse
import psycopg2, os, time, uuid, logging
from psycopg2 import pool
from pythonjsonlogger import jsonlogger

# ─── Structured JSON Logging ──────────────────────────────────────────────────
# Each log line is a JSON object — parseable by CloudWatch Logs Insights.
# Query example: fields @timestamp, service, event, count | filter service="user-service"
logger = logging.getLogger("user-service")
handler = logging.StreamHandler()
handler.setFormatter(jsonlogger.JsonFormatter(
    fmt="%(asctime)s %(levelname)s %(name)s %(message)s"
))
logger.addHandler(handler)
logger.setLevel(logging.INFO)
logging.getLogger("uvicorn.access").handlers = []  # Avoid duplicate access logs


# ─── Prometheus Metrics ───────────────────────────────────────────────────────
from prometheus_fastapi_instrumentator import Instrumentator


# ─── Application Lifecycle ────────────────────────────────────────────────────
db_pool = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Replaces the deprecated @on_event("startup"/"shutdown") pattern.
    Everything before `yield` runs at startup; everything after at shutdown.
    Using asynccontextmanager ensures proper cleanup even on unexpected exits.
    """
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
    logger.info("db.pool.initialized", extra={"min": 1, "max": 20, "host": os.environ["DB_HOST"]})
    yield
    # Shutdown: return all connections cleanly
    if db_pool:
        db_pool.closeall()
        logger.info("db.pool.closed")


app = FastAPI(title="User Service", version="2.0", lifespan=lifespan)

# Mount Prometheus metrics endpoint at /metrics
# Scraped by Prometheus / kube-prometheus-stack in production
Instrumentator().instrument(app).expose(app)


# ─── DB Connection Context Manager ───────────────────────────────────────────
@asynccontextmanager
async def get_db_conn():
    """
    Checks out a connection from the pool, yields it, then returns it.
    Using a context manager guarantees the connection is returned even on exceptions —
    prevents pool exhaustion from leaked connections under error conditions.
    """
    conn = db_pool.getconn()
    try:
        yield conn
    finally:
        db_pool.putconn(conn)


# ─── Request ID Middleware ────────────────────────────────────────────────────
@app.middleware("http")
async def add_request_id(request: Request, call_next):
    """
    Injects a unique X-Request-ID into every request for distributed tracing.
    Allows correlating a single user action across logs from multiple services.
    """
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


# ─── Health Check ────────────────────────────────────────────────────────────
@app.get("/health")
async def health():
    """
    Deep health check — verifies actual DB connectivity, not just 'I started'.

    Kubernetes readiness probe calls this before routing traffic to the pod.
    If this returns 'degraded', the pod is temporarily removed from load balancing
    without being killed — allowing DB recovery without pod restarts.

    Interview Q: "What's the difference between a liveness and readiness probe?"
    A: Liveness → kill & restart if unhealthy. Readiness → stop traffic but keep pod.
    """
    db_status = "healthy"
    pool_info = {}

    try:
        async with get_db_conn() as conn:
            with closing(conn.cursor()) as cur:
                cur.execute("SELECT 1")  # Lightweight connectivity check
        pool_info = {"min": db_pool.minconn, "max": db_pool.maxconn}
    except Exception as e:
        db_status = f"unhealthy: {str(e)}"
        logger.error("health.db.failure", extra={"error": str(e)})

    overall = "healthy" if db_status == "healthy" else "degraded"
    status_code = 200 if overall == "healthy" else 503

    return JSONResponse(
        status_code=status_code,
        content={
            "status": overall,
            "service": "user-service",
            "version": "2.0",
            "dependencies": {"postgres": db_status},
            "pool": pool_info,
        }
    )


# ─── Endpoints ───────────────────────────────────────────────────────────────

@app.get("/users")
async def get_users(
    name: str | None = Query(None, description="Filter by exact name (case-insensitive)"),
    city: str | None = Query(None, description="Filter by city (case-insensitive)"),
    email: str | None = Query(None, description="Filter by exact email address"),
):
    """List users with optional filters. Uses parameterized queries to prevent SQL injection."""
    start = time.time()
    try:
        async with get_db_conn() as conn:
            with closing(conn.cursor()) as cur:
                query = "SELECT id, name, email, city FROM users WHERE 1=1"
                params = []
                if name:
                    query += " AND LOWER(name) = LOWER(%s)"
                    params.append(name)
                if city:
                    query += " AND LOWER(city) = LOWER(%s)"
                    params.append(city)
                if email:
                    query += " AND email = %s"
                    params.append(email)
                cur.execute(query, params)
                users = [
                    {"id": r[0], "name": r[1], "email": r[2], "city": r[3]}
                    for r in cur.fetchall()
                ]

        logger.info("users.list.complete", extra={
            "count": len(users),
            "duration_ms": round((time.time() - start) * 1000, 2),
            "filters": {"name": name, "city": city, "email": email},
        })
        return users

    except Exception as e:
        logger.error("users.list.error", extra={"error": str(e)})
        raise HTTPException(status_code=500, detail="database error")


@app.get("/users/{user_id}")
async def get_user(user_id: int):
    """Fetch a single user by ID. Returns 404 if not found."""
    try:
        async with get_db_conn() as conn:
            with closing(conn.cursor()) as cur:
                cur.execute(
                    "SELECT id, name, email, city FROM users WHERE id = %s;",
                    (user_id,)
                )
                row = cur.fetchone()

        if not row:
            raise HTTPException(status_code=404, detail="user not found")

        return {"id": row[0], "name": row[1], "email": row[2], "city": row[3]}

    except HTTPException:
        raise
    except Exception as e:
        logger.error("users.get.error", extra={"user_id": user_id, "error": str(e)})
        raise HTTPException(status_code=500, detail="database error")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5001)
