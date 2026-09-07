"""
ai-service/app.py

Natural language query engine. Accepts plain-English queries, uses a local
Ollama LLM to extract structured intent, validates it against an allowlist,
then orchestrates calls to internal microservices to fulfill the request.

Flow: API Gateway → AI Service → Ollama (LLM) → Intent Extraction
                                                → Validator (allowlist gate)
                                                → User/Order Service APIs
                                                → Structured Response

Key design decisions:
  - Intent extraction over RAG: for a small, bounded API surface (2 services,
    ~7 operations) direct intent extraction is simpler and more reliable than
    vector search or RAG. Use RAG when the operation space is large/dynamic.
  - Allowlist validator (validator.py): LLM output is untrusted. Every extracted
    intent is validated against a strict allowlist before execution — prevents
    prompt injection attacks from triggering unauthorized operations.
  - Separation of concerns: prompts.py holds prompt engineering logic,
    validator.py holds security logic, app.py holds orchestration — each
    is independently testable and replaceable.
  - temperature=0.0: zero temperature for deterministic, reproducible output.
    Creativity is not wanted in a structured JSON extraction task.
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from prometheus_fastapi_instrumentator import Instrumentator
from prometheus_client import Counter, Histogram
import httpx, os, json, logging, time
from pythonjsonlogger import jsonlogger
from prompts import INTENT_EXTRACTION_PROMPT
from validator import validate_intent

# ─── Structured JSON Logging ──────────────────────────────────────────────────
logger = logging.getLogger("ai-service")
handler = logging.StreamHandler()
handler.setFormatter(jsonlogger.JsonFormatter(
    fmt="%(asctime)s %(levelname)s %(name)s %(message)s"
))
logger.addHandler(handler)
logger.setLevel(logging.INFO)
logging.getLogger("uvicorn.access").handlers = []

# ─── Custom Prometheus Metrics ────────────────────────────────────────────────
llm_requests_total = Counter("llm_requests_total", "Total LLM inference calls", ["model", "status"])
llm_duration = Histogram(
    "llm_inference_duration_seconds",
    "LLM inference latency distribution",
    buckets=[1, 5, 10, 20, 30, 45, 60],
)

# ─── Configuration ────────────────────────────────────────────────────────────
OLLAMA_URL   = os.environ.get("OLLAMA_BASE_URL", "http://ollama:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL",    "llama3.2:1b")
USER_SVC_URL  = os.environ.get("USER_SERVICE_URL",  "http://user-service:5001")
ORDER_SVC_URL = os.environ.get("ORDER_SERVICE_URL", "http://order-service:5002")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("ai.service.started", extra={
        "ollama_url": OLLAMA_URL, "model": OLLAMA_MODEL
    })
    yield
    logger.info("ai.service.stopped")


app = FastAPI(title="AI Query Service", version="2.0", lifespan=lifespan)
Instrumentator().instrument(app).expose(app)


# ─── Request/Response Models ──────────────────────────────────────────────────

class QueryRequest(BaseModel):
    query: str

    class Config:
        json_schema_extra = {
            "example": {"query": "Show me all pending orders over 50000"}
        }


# ─── Health Check ─────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    """Checks Ollama reachability. Returns degraded if LLM endpoint is unreachable."""
    ollama_status = "healthy"
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(f"{OLLAMA_URL}/api/tags")
            if r.status_code != 200:
                ollama_status = f"unhealthy: HTTP {r.status_code}"
    except Exception as e:
        ollama_status = f"unhealthy: {str(e)}"
        logger.error("health.ollama.failure", extra={"error": str(e)})

    overall = "healthy" if ollama_status == "healthy" else "degraded"
    return JSONResponse(
        status_code=200 if overall == "healthy" else 503,
        content={
            "status": overall,
            "service": "ai-service",
            "version": "2.0",
            "model": OLLAMA_MODEL,
            "dependencies": {"ollama": ollama_status},
        }
    )


# ─── LLM Inference ────────────────────────────────────────────────────────────

async def call_llm(prompt: str, user_query: str) -> dict:
    """
    Calls Ollama's /api/chat endpoint with the structured extraction prompt.
    temperature=0.0 ensures deterministic, reproducible JSON output.
    Strips markdown code fences if the model wraps its response (common with some models).
    """
    payload = {
        "model": OLLAMA_MODEL,
        "messages": [
            {"role": "system", "content": prompt},
            {"role": "user", "content": user_query}
        ],
        "stream": False,
        "options": {"temperature": 0.0},
    }

    start = time.time()
    async with httpx.AsyncClient(timeout=50.0) as client:
        r = await client.post(f"{OLLAMA_URL}/api/chat", json=payload)
        r.raise_for_status()

    duration = time.time() - start
    llm_duration.observe(duration)

    raw = r.json()["message"]["content"].strip()

    # Strip markdown code fences if present (some models add ```json ... ```)
    if raw.startswith("```"):
        raw = raw.split("```")[1].replace("json", "").strip()

    return json.loads(raw)


# ─── Main Endpoint ────────────────────────────────────────────────────────────

@app.post("/ai/query")
async def ai_query(request: QueryRequest):
    """
    Converts a natural language query into structured API calls.

    Security model:
    1. LLM extracts intent as JSON (untrusted output)
    2. Validator checks intent against strict allowlist (trust boundary)
    3. Only validated intents trigger downstream API calls
    This prevents prompt injection: even if a user crafts a query that tricks
    the LLM into generating a malicious intent, the validator blocks execution.
    """
    start = time.time()
    logger.info("ai.query.received", extra={"query": request.query})

    # ── Step 1: Extract Intent via LLM ────────────────────────────────────────
    try:
        intent = await call_llm(INTENT_EXTRACTION_PROMPT, request.query)
        llm_requests_total.labels(model=OLLAMA_MODEL, status="success").inc()
        logger.info("ai.intent.extracted", extra={"intent": intent})
    except json.JSONDecodeError as e:
        llm_requests_total.labels(model=OLLAMA_MODEL, status="parse_error").inc()
        logger.error("ai.intent.parse_error", extra={"error": str(e)})
        raise HTTPException(status_code=500, detail="LLM returned invalid JSON")
    except Exception as e:
        llm_requests_total.labels(model=OLLAMA_MODEL, status="error").inc()
        logger.error("ai.llm.error", extra={"error": str(e)})
        raise HTTPException(status_code=500, detail=f"LLM inference failed: {e}")

    # ── Step 2: Validate Intent (Security Gate) ────────────────────────────────
    is_valid, reason = validate_intent(intent)
    if not is_valid:
        logger.warning("ai.intent.rejected", extra={"reason": reason, "intent": intent})
        raise HTTPException(status_code=400, detail=f"Invalid intent: {reason}")

    # ── Step 3: Execute the Validated Service Call ─────────────────────────────
    filters = intent.get("filters", {})
    results = []

    async with httpx.AsyncClient(timeout=15.0) as client:
        if intent["service"] == "users":
            r = await client.get(f"{USER_SVC_URL}/users", params=filters)
            r.raise_for_status()
            results = r.json()

        elif intent["service"] == "orders":
            # Cross-service lookup: resolve user_name → user_id before querying orders
            if "user_name" in filters:
                u = await client.get(f"{USER_SVC_URL}/users", params={"name": filters.pop("user_name")})
                u.raise_for_status()
                users = u.json()
                if not users:
                    return {"intent": intent, "results": [], "note": "User not found"}
                filters["user_id"] = users[0]["id"]

            r = await client.get(f"{ORDER_SVC_URL}/orders", params=filters)
            r.raise_for_status()
            results = r.json()

    duration_ms = round((time.time() - start) * 1000, 2)
    logger.info("ai.query.complete", extra={
        "service": intent["service"],
        "operation": intent["operation"],
        "result_count": len(results),
        "duration_ms": duration_ms,
    })

    return {
        "intent": intent,
        "results": results,
        "meta": {"duration_ms": duration_ms, "model": OLLAMA_MODEL},
    }