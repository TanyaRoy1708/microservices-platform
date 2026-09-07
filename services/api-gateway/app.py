"""
api-gateway/app.py

Single entry point for all external traffic. Routes requests to the correct
downstream microservice based on URL prefix.

Flow: Client → API Gateway → [user-service | order-service | ai-service] → Client

Key design decisions:
  - Transparent proxy: forwards headers, body, and method verbatim.
    Avoids re-serializing payloads (preserves streaming potential).
  - Differentiated timeouts: connect (5s) vs. read (60s).
    AI queries need a long read timeout; connection failures should fail fast.
  - Explicit error mapping: ConnectError→503, TimeoutException→504, other→502.
    Each HTTP status code tells the client exactly what went wrong and where.
  - X-Request-ID propagation: request IDs generated here flow through all
    downstream services, enabling end-to-end log correlation.
  - Structured JSON logging: all proxy calls logged with upstream URL,
    status, and duration for observability.
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import Response
from prometheus_fastapi_instrumentator import Instrumentator
import httpx, os, logging, time, uuid
from pythonjsonlogger import jsonlogger

# ─── Structured JSON Logging ──────────────────────────────────────────────────
logger = logging.getLogger("api-gateway")
handler = logging.StreamHandler()
handler.setFormatter(jsonlogger.JsonFormatter(
    fmt="%(asctime)s %(levelname)s %(name)s %(message)s"
))
logger.addHandler(handler)
logger.setLevel(logging.INFO)
logging.getLogger("uvicorn.access").handlers = []

# ─── Upstream Service URLs ────────────────────────────────────────────────────
USER_SVC  = os.environ.get("USER_SERVICE_URL",  "http://user-service:5001")
ORDER_SVC = os.environ.get("ORDER_SERVICE_URL", "http://order-service:5002")
AI_SVC    = os.environ.get("AI_SERVICE_URL",    "http://ai-service:5003")

# ─── HTTP Client Timeouts ─────────────────────────────────────────────────────
# connect=5s: fail fast if service is unreachable (avoids hanging threads)
# read=60s: AI service may take up to 45s for LLM inference — needs a longer read timeout
STANDARD_TIMEOUT = httpx.Timeout(connect=5.0, read=30.0, write=10.0, pool=5.0)
AI_TIMEOUT       = httpx.Timeout(connect=5.0, read=65.0, write=10.0, pool=5.0)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("api.gateway.started", extra={"upstream_services": {
        "users": USER_SVC, "orders": ORDER_SVC, "ai": AI_SVC
    }})
    yield
    logger.info("api.gateway.stopped")


app = FastAPI(title="API Gateway", version="2.0", lifespan=lifespan)
Instrumentator().instrument(app).expose(app)


# ─── Request ID Middleware ────────────────────────────────────────────────────
@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    """
    Generates or forwards a unique request ID for distributed tracing.
    By injecting X-Request-ID at the gateway, all downstream services
    can log the same ID — making it trivial to trace a user's request
    across multiple services in CloudWatch or any log aggregator.
    """
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    start = time.time()
    response = await call_next(request)
    duration_ms = round((time.time() - start) * 1000, 2)
    response.headers["X-Request-ID"] = request_id
    logger.info("gateway.request", extra={
        "request_id": request_id,
        "method": request.method,
        "path": str(request.url.path),
        "status_code": response.status_code,
        "duration_ms": duration_ms,
    })
    return response


# ─── Health Check ─────────────────────────────────────────────────────────────
@app.get("/health")
async def health():
    return {"status": "healthy", "service": "api-gateway", "version": "2.0"}


# ─── Proxy Routes ─────────────────────────────────────────────────────────────

@app.api_route("/users{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def proxy_users(path: str, request: Request):
    return await _proxy(f"{USER_SVC}/users{path}", request, timeout=STANDARD_TIMEOUT)


@app.api_route("/orders{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def proxy_orders(path: str, request: Request):
    return await _proxy(f"{ORDER_SVC}/orders{path}", request, timeout=STANDARD_TIMEOUT)


@app.post("/ai/query")
async def proxy_ai(request: Request):
    # AI queries involve LLM inference — use extended timeout
    return await _proxy(f"{AI_SVC}/ai/query", request, timeout=AI_TIMEOUT)


# ─── Core Proxy Function ──────────────────────────────────────────────────────

async def _proxy(url: str, request: Request, timeout: httpx.Timeout = STANDARD_TIMEOUT) -> Response:
    """
    Transparently forwards the request to the upstream service.

    Error mapping rationale:
      - 503 Service Unavailable: upstream is down (ConnectError) — client should retry later
      - 504 Gateway Timeout: upstream is up but too slow — may indicate load or LLM delay
      - 502 Bad Gateway: upstream returned unexpected response — may indicate upstream bug
    """
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))

    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            body = await request.body()
            # Forward all headers including auth tokens, content-type, etc.
            # Filter out 'host' header to avoid confusing the upstream service
            headers = {k: v for k, v in request.headers.items() if k.lower() != "host"}
            headers["X-Request-ID"] = request_id  # Propagate for distributed tracing

            r = await client.request(
                method=request.method,
                url=url,
                content=body,
                headers=headers,
            )
            logger.info("proxy.upstream.response", extra={
                "request_id": request_id,
                "upstream_url": url,
                "upstream_status": r.status_code,
            })
            return Response(
                content=r.content,
                status_code=r.status_code,
                media_type=r.headers.get("content-type"),
            )

        except httpx.ConnectError as e:
            logger.error("proxy.upstream.unavailable", extra={
                "request_id": request_id, "upstream_url": url, "error": str(e)
            })
            raise HTTPException(status_code=503, detail=f"Service unavailable: {url}")

        except httpx.TimeoutException as e:
            logger.error("proxy.upstream.timeout", extra={
                "request_id": request_id, "upstream_url": url, "error": str(e)
            })
            raise HTTPException(status_code=504, detail=f"Gateway timeout: {url}")

        except httpx.RequestError as e:
            logger.error("proxy.upstream.error", extra={
                "request_id": request_id, "upstream_url": url, "error": str(e)
            })
            raise HTTPException(status_code=502, detail=f"Bad gateway: {url}")