# Microservices Platform

A containerized, production-patterned microservices platform with a built-in local AI inference service. Four Python services communicate through an API Gateway, backed by PostgreSQL and Redis, with a locally-running LLM (Ollama) for natural language querying — all orchestrated via Docker Compose. **Zero cloud cost. 100% local.**

---

## Architecture

```
                        ┌─────────────────────────────┐
   HTTP Client          │        API Gateway           │  :8000
   ──────────►          │        (FastAPI)              │
                        └──────────────┬──────────────┘
                                       │
               ┌───────────────────────┼───────────────────────┐
               │                       │                        │
               ▼                       ▼                        ▼
   ┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
   │  User Service   │     │  Order Service  │     │   AI Service    │
   │  (Flask) :5001  │     │  (Flask) :5002  │     │ (FastAPI) :5003 │
   └────────┬────────┘     └───────┬─────┬──┘     └────────┬────────┘
            │                      │     │                  │
            ▼                      ▼     ▼                  ▼
   ┌─────────────────┐    ┌──────────┐ ┌──────┐   ┌─────────────────┐
   │   PostgreSQL    │◄───│ Postgres │ │Redis │   │  Ollama Runtime │
   │   :5432         │    └──────────┘ └──────┘   │  llama3.2:1b    │
   └─────────────────┘                             │  :11434 (int.)  │
                                                   └─────────────────┘
```

> **Note:** Ollama is intentionally not exposed to the host. It is reachable only by `ai-service` via internal Docker DNS, preventing unauthenticated LLM access from the host network.

---

## Tech Stack

| Layer | Technology |
|---|---|
| API Gateway | FastAPI + uvicorn |
| User Service | Flask + Gunicorn + psycopg2 |
| Order Service | Flask + Gunicorn + psycopg2 + redis-py |
| AI Service | FastAPI + uvicorn + httpx |
| LLM Runtime | Ollama `0.3.14` (`llama3.2:1b` model) |
| Database | PostgreSQL 15 (Alpine) |
| Cache | Redis 7 (Alpine) |
| Orchestration | Docker Compose v2 |
| Container Base | `python:3.11-slim` (non-root user, minimal footprint) |

---

## Prerequisites

| Requirement | Minimum Version | Check |
|---|---|---|
| Docker Desktop | 24.x | `docker --version` |
| Docker Compose | v2.x | `docker compose version` |
| Python | 3.11+ | `python --version` |
| Free RAM | 8 GB | — |
| Free Disk | 5 GB | — |

> First-run downloads ~1.3 GB of model weights. Subsequent starts are fast — weights are cached in the `ollama_models` Docker volume.

---

## Quick Start

```bash
# 1. Clone the repository
git clone <repo-url>
cd microservices-platform

# 2. Configure environment
cp .env.example .env
#    Edit .env and set strong values for DB_PASSWORD and REDIS_PASSWORD

# 3. One-command setup (recommended)
bash scripts/setup.sh
```

The setup script:
- Validates prerequisites (Docker, Python)
- Bootstraps `.env` from `.env.example` if missing or empty
- Starts PostgreSQL and Redis, waits for readiness
- Pulls the Ollama LLM model (~1.3 GB, one-time)
- Builds and starts all four services
- Runs health checks across all endpoints
- Fires a test AI query to confirm end-to-end connectivity

**Manual alternative:**
```bash
docker compose up --build -d
```

---

## Service Endpoints

| Service | URL | Description |
|---|---|---|
| API Gateway | `http://localhost:8000` | Single entry point for all client traffic |
| AI Service (Swagger) | `http://localhost:5003/docs` | Interactive API docs for AI endpoint |
| User Service | `http://localhost:5001` | Direct access (bypasses gateway) |
| Order Service | `http://localhost:5002` | Direct access (bypasses gateway) |

### Health Checks

```bash
curl http://localhost:8000/health    # Gateway
curl http://localhost:5001/health    # User Service
curl http://localhost:5002/health    # Order Service
curl http://localhost:5003/health    # AI Service (includes Ollama connectivity status)
```

### API Reference

**Get all users**
```bash
curl http://localhost:8000/users
```

**Get a single user**
```bash
curl http://localhost:8000/users/1
```

**Get all orders** *(Redis-cached, 60s TTL)*
```bash
curl http://localhost:8000/orders
```

**Natural language AI query**
```bash
curl -s -X POST http://localhost:8000/ai/query \
  -H 'Content-Type: application/json' \
  -d '{"query": "Show me all orders placed by users from Mumbai", "context_limit": 5}' \
  | python3 -m json.tool
```

**Example queries to try:**
```bash
# Filter by order status
-d '{"query": "Which orders are still pending?"}'

# Filter by amount
-d '{"query": "List all orders over 50000"}'

# Cross-service reasoning
-d '{"query": "Who placed the most expensive order and where are they from?"}'
```

---

## Environment Variables

Copy `.env.example` to `.env` and populate before starting services.

```bash
# .env.example
DB_HOST=postgres
DB_NAME=appdb
DB_USER=appuser
DB_PASSWORD=change_me_in_env   # ← set a strong value

REDIS_PASSWORD=change_me_in_env  # ← set a strong value

OLLAMA_MODEL=llama3.2:1b         # swap for a larger model if RAM allows
```

> ⚠️ `.env` is listed in `.gitignore` and must **never** be committed. Only `.env.example` (containing no real secrets) is tracked.

---

## Project Structure

```
microservices-platform/
├── docker-compose.yml          # Full platform orchestration
├── .env.example                # Committed secrets template (no real values)
├── .env                        # Local secrets (gitignored)
├── init.sql                    # PostgreSQL seed — users + orders tables
├── scripts/
│   └── setup.sh                # One-command platform bootstrap
├── api-gateway/
│   ├── app.py                  # FastAPI reverse proxy
│   ├── Dockerfile
│   └── requirements.txt
├── user-service/
│   ├── app.py                  # Flask + psycopg2, connection-safe
│   ├── Dockerfile
│   └── requirements.txt
├── order-service/
│   ├── app.py                  # Flask + Redis cache + psycopg2
│   ├── Dockerfile
│   └── requirements.txt
└── ai-service/
    ├── app.py                  # FastAPI + Ollama LLM integration
    ├── Dockerfile
    └── requirements.txt
```

---

## Key Design Decisions

### 1. Non-root containers
All service images create a dedicated `appuser` (UID 1000) and drop privileges before running. Running as root in a container exposes the host if a container escape vulnerability is exploited.

### 2. Pinned image versions
All images use explicit version tags (`postgres:15-alpine`, `redis:7-alpine`, `ollama/ollama:0.3.14`). `latest` is never used — it creates non-reproducible builds and can silently introduce breaking changes.

### 3. `service_healthy` dependency chain
Services wait for their dependencies to pass healthchecks before starting, not just for the container to exist. This eliminates cold-start race conditions where a service starts before its database is accepting connections.

### 4. Ollama not exposed to host
The LLM engine has no authentication layer. Exposing port `11434` to the host would allow any process — or any person on the local network — to run arbitrary prompts against the model. The `ai-service` reaches Ollama exclusively via Docker's internal DNS.

### 5. Database connections via `contextlib.closing`
Each request opens and **guarantees closure** of its PostgreSQL connection using `contextlib.closing`. This prevents connection exhaustion against PostgreSQL's default `max_connections=100`, even under concurrent Gunicorn workers, without adding the complexity of a connection pool to the application layer.

### 6. Redis cache on orders
Order data changes infrequently but is fetched on every AI query. A 60-second TTL cache absorbs repeated reads without stale-data risk. The `redis-py` client is instantiated at module level because it manages its own internal connection pool.

---

## Useful Commands

```bash
# View live logs from all services
docker compose logs -f

# View logs from a specific service
docker compose logs -f ai-service

# Rebuild a single service after code change
docker compose up --build -d user-service

# Stop everything (preserves volumes)
docker compose down

# Stop and wipe all data (volumes included)
docker compose down -v

# Check container health status
docker compose ps

# Open a shell in a running container
docker compose exec user-service bash

# Inspect the PostgreSQL database
docker compose exec postgres psql -U appuser -d appdb
```

