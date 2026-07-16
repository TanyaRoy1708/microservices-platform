# Microservices Platform

A containerized, production-grade microservices platform with a built-in local AI inference service. Four Python services communicate through an API Gateway, backed by PostgreSQL and Redis, with a locally-running LLM (Ollama) for natural language querying — all orchestrated via Docker Compose for local development and deployable to AWS EKS via Terraform + Helm with a fully automated CI/CD pipeline.

---

## What's in this repo

| Phase | Scope |
|---|---|
| **Phase 1 — Local Platform** | Docker Compose, four Python services, PostgreSQL, Redis, Ollama LLM |
| **Phase 2 — Cloud & CI/CD** | Terraform (VPC + EKS + RDS + ECR), Helm chart, GitHub Actions pipeline, Trivy scanning, K8sGPT post-deploy analysis, HPA |

---

## Architecture

### Local (Docker Compose)

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

### Cloud (AWS EKS)

```
GitHub Actions (push → main)
         │
         ├─ CI matrix (4 services in parallel)
         │    ├─ pytest
         │    ├─ docker build → ECR push (tagged by commit SHA)
         │    └─ Trivy scan (CRITICAL/HIGH → fail)
         │
         └─ CD (after all CI jobs pass)
              ├─ helm upgrade --install ai-platform ./helm/ai-platform/
              ├─ kubectl rollout status (all 4 deployments)
              └─ K8sGPT cluster analysis → Slack sink

Internet ──► AWS ALB (Ingress) ──► api-gateway:8000 (EKS, production ns)
                                        │
               ┌────────────────────────┼────────────────────────┐
               ▼                        ▼                         ▼
        user-service:5001       order-service:5002        ai-service:5003
               │                                                  │
        AWS RDS (PostgreSQL 15)                        Ollama on EC2 sidecar
        (private subnet, VPC-only)                     http://<EC2-IP>:11434
```

---

## Tech Stack

| Layer | Local (Phase 1) | Cloud (Phase 2) |
|---|---|---|
| API Gateway | FastAPI + uvicorn | Same image → ECR → EKS |
| User Service | Flask + Gunicorn + psycopg2 | Same image → ECR → EKS |
| Order Service | Flask + Gunicorn + psycopg2 + redis-py | Same image → ECR → EKS |
| AI Service | FastAPI + uvicorn + httpx | Same image → ECR → EKS |
| LLM Runtime | Ollama `0.3.14` (`llama3.2:1b`) in Docker | Ollama on EC2 sidecar (not in cluster) |
| Database | PostgreSQL 15 (Alpine container) | AWS RDS PostgreSQL 15 (`db.t3.micro`) |
| Cache | Redis 7 (Alpine container) | — |
| Orchestration | Docker Compose v2 | Helm `ai-platform` chart on EKS 1.30 |
| Infrastructure | — | Terraform ≥ 1.6 (AWS provider ~5.0) |
| CI/CD | — | GitHub Actions (OIDC → AWS, Trivy, K8sGPT) |
| Autoscaling | — | HPA (CPU ≥ 70% → scale up, max 10 pods) |
| Container Base | `python:3.11-slim` (non-root) | Same |

---

## Prerequisites

### Local development

| Requirement | Minimum Version | Check |
|---|---|---|
| Docker Desktop | 24.x | `docker --version` |
| Docker Compose | v2.x | `docker compose version` |
| Python | 3.11+ | `python --version` |
| Free RAM | 8 GB | — |
| Free Disk | 5 GB | — |

> First-run downloads ~1.3 GB of model weights. Subsequent starts are fast — weights are cached in the `ollama_models` Docker volume.

### Cloud deployment (Phase 2)

| Requirement | Notes |
|---|---|
| Terraform ≥ 1.6 | `terraform --version` |
| AWS CLI v2 | Configured with IAM permissions for EKS/ECR/RDS/VPC |
| kubectl | `kubectl version --client` |
| Helm 3 | `helm version` |
| AWS Account | Region `ap-south-1` (Mumbai) |
| S3 bucket + DynamoDB table | For Terraform remote state (`tanya-tfstate-2026` / `tanya-tfstate-lock`) |

---

## Quick Start — Local

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

## Cloud Deployment — AWS EKS (Phase 2)

### 1. Provision infrastructure with Terraform

```bash
cd terraform/

# Initialise (downloads providers, connects to remote state)
terraform init

# Preview changes
terraform plan

# Apply — creates VPC, EKS cluster, RDS, ECR repos (~15 min)
terraform apply
```

Resources created:

| Resource | Details |
|---|---|
| VPC | `10.0.0.0/16`, 2 AZs (`ap-south-1a/b`), public + private subnets |
| NAT Gateway | Single, on public subnet (cost-optimised) |
| EKS Cluster | `ai-microservices-platform`, Kubernetes 1.30 |
| Node Group | `spot_workers` — `t3.medium/large` SPOT, 2–5 nodes |
| ECR Repos | One per service: `api-gateway`, `user-service`, `order-service`, `ai-service` |
| RDS | PostgreSQL 15, `db.t3.micro`, private subnet, VPC-only access |
| IRSA | OIDC provider enabled — pods get AWS IAM roles, no static keys |

### 2. Set up the EKS cluster

```bash
bash scripts/eks-setup.sh
```

This script:
- Updates your local kubeconfig (`aws eks update-kubeconfig`)
- Installs the AWS Load Balancer Controller via Helm (required for ALB Ingress)
- Verifies the controller is running

### 3. Configure GitHub Actions secrets

Add the following secrets to your repository (`Settings → Secrets → Actions`):

| Secret | Value |
|---|---|
| `AWS_ACCOUNT_ID` | Your 12-digit AWS account ID |
| `ECR_REGISTRY` | `<account-id>.dkr.ecr.ap-south-1.amazonaws.com` |
| `DB_HOST` | RDS endpoint from `terraform output rds_endpoint` |
| `DB_NAME` | `platformdb` |
| `DB_USER` | `postgres` |
| `DB_PASSWORD` | Your RDS password |
| `OLLAMA_EC2_IP` | Private IP of the EC2 running Ollama |

> The pipeline authenticates to AWS using OIDC — no static IAM keys are stored in GitHub.

### 4. Deploy

Push to `main`. The pipeline runs automatically:

```
push → main
  └─ ci (parallel matrix: 4 services)
       ├─ pytest
       ├─ docker build → push to ECR (tag: commit SHA)
       └─ trivy scan (CRITICAL/HIGH CVEs → fail)
  └─ deploy (sequential, after all ci jobs pass)
       ├─ helm upgrade --install ai-platform ./helm/ai-platform/ --namespace production
       ├─ kubectl rollout status (all 4 deployments)
       └─ k8sgpt analyze → uploads JSON report as artifact
```

### 5. Manual Helm deploy

```bash
helm upgrade --install ai-platform ./helm/ai-platform/ \
  --namespace production \
  --create-namespace \
  --set global.imageTag=<commit-sha> \
  --set global.ecrRegistry=<ecr-registry> \
  --set aiService.ollamaUrl=http://<ollama-ec2-ip>:11434 \
  --wait --timeout 8m --atomic
```

---

## Service Endpoints

### Local

| Service | URL | Description |
|---|---|---|
| API Gateway | `http://localhost:8000` | Single entry point for all client traffic |
| AI Service (Swagger) | `http://localhost:5003/docs` | Interactive API docs for AI endpoint |
| User Service | `http://localhost:5001` | Direct access (bypasses gateway) |
| Order Service | `http://localhost:5002` | Direct access (bypasses gateway) |

### Cloud (EKS)

All traffic enters through the AWS ALB created by the Ingress resource. Get the ALB hostname after deploying:

```bash
kubectl get ingress -n production
```

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

> **Note:** `.env` is listed in `.gitignore` and must **never** be committed. Only `.env.example` (containing no real secrets) is tracked.

---

## Project Structure

```
microservices-platform/
│
│  ── Root config ──────────────────────────────────────────────────────
├── docker-compose.yml          # Local orchestration (all services)
├── init.sql                    # PostgreSQL seed — users + orders tables
├── .env.example                # Secrets template (committed, no real values)
├── .env                        # Local secrets (gitignored)
├── k8sgpt-config.yaml          # K8sGPT operator CRD (Slack sink, 5-min scan)
│
│  ── Application services ─────────────────────────────────────────────
├── api-gateway/
│   ├── app.py                  # FastAPI reverse proxy → routes to all services
│   ├── Dockerfile
│   └── requirements.txt
├── user-service/
│   ├── app.py                  # Flask + psycopg2 (contextlib.closing pattern)
│   ├── Dockerfile
│   └── requirements.txt
├── order-service/
│   ├── app.py                  # Flask + Redis 60s cache + psycopg2
│   ├── Dockerfile
│   └── requirements.txt
├── ai-service/
│   ├── app.py                  # FastAPI + Ollama httpx client (llama3.2:1b)
│   ├── Dockerfile
│   └── requirements.txt
│
│  ── Infrastructure & CI/CD ───────────────────────────────────────────
├── terraform/                  # AWS infrastructure as code
│   ├── main.tf                 # Provider + S3/DynamoDB remote state backend
│   ├── variables.tf            # aws_region, db_name, db_user, db_password
│   ├── outputs.tf              # rds_endpoint
│   ├── vpc.tf                  # VPC 10.0.0.0/16, 2 AZs, public + private subnets
│   ├── eks.tf                  # EKS 1.30, SPOT node group (t3.medium/large), IRSA
│   ├── ecr.tf                  # ECR repos × 4 services, scan_on_push
│   └── rds.tf                  # RDS PostgreSQL 15, db.t3.micro, private subnet
│
├── helm/
│   └── ai-platform/            # Helm chart — deploys all services to EKS
│       ├── Chart.yaml
│       ├── values.yaml         # Replica counts, resource limits, Ollama URL
│       └── templates/
│           ├── namespace.yaml
│           ├── configmap.yaml  # Service URLs + OLLAMA_BASE_URL injected at deploy
│           ├── ingress.yaml    # AWS ALB Ingress → api-gateway:8000
│           ├── api-gateway/    # deployment, service, hpa
│           ├── user-service/   # deployment, service, hpa
│           ├── order-service/  # deployment, service, hpa
│           └── ai-service/     # deployment, service, hpa
│
├── .github/
│   └── workflows/
│       └── deploy.yaml         # CI: pytest → ECR push → Trivy scan
│                               # CD: Helm deploy → rollout check → K8sGPT
│
│  ── Utilities ────────────────────────────────────────────────────────
├── scripts/
│   ├── setup.sh                # One-command local bootstrap
│   ├── eks-setup.sh            # Post-Terraform: kubeconfig + ALB controller
│   ├── setup-oidc.md           # One-time: OIDC provider + IAM role commands (run manually)
│   └── setup-k8sgpt.md         # K8sGPT operator install + monitoring config (run manually)
└── tests/                      # pytest integration / smoke tests
```

---

## Key Design Decisions

### 1. Non-root containers
All service images create a dedicated `appuser` (UID 1000) and drop privileges before running. Running as root in a container exposes the host if a container escape vulnerability is exploited.

### 2. Pinned image versions
All images use explicit version tags (`postgres:15-alpine`, `redis:7-alpine`, `ollama/ollama:0.3.14`). `latest` is never used — it creates non-reproducible builds and can silently introduce breaking changes.

### 3. `service_healthy` dependency chain
Services wait for their dependencies to pass healthchecks before starting, not just for the container to exist. This eliminates cold-start race conditions where a service starts before its database is accepting connections.

### 4. Ollama not exposed to host / cluster network
The LLM engine has no authentication layer. In local mode, port `11434` is not published to the host — `ai-service` reaches it via Docker's internal DNS. In EKS mode, Ollama runs as a sidecar process on an EC2 node (not as a pod) and is accessed by its private IP; it is never reachable from the internet.

### 5. Database connections via `contextlib.closing`
Each request opens and **guarantees closure** of its PostgreSQL connection using `contextlib.closing`. This prevents connection exhaustion against PostgreSQL's default `max_connections=100`, even under concurrent Gunicorn workers, without adding the complexity of a connection pool to the application layer.

### 6. Redis cache on orders
Order data changes infrequently but is fetched on every AI query. A 60-second TTL cache absorbs repeated reads without stale-data risk. The `redis-py` client is instantiated at module level because it manages its own internal connection pool.

### 7. SPOT node group for EKS
Worker nodes use EC2 SPOT instances (`t3.medium/large`), reducing compute cost by ~70% versus On-Demand. The HPA (min 2, max 10 pods) and `--atomic` Helm flag ensure automatic rollback if a deployment fails after a SPOT interruption.

### 8. OIDC authentication — no static IAM keys
GitHub Actions assumes an IAM role via OIDC (`gh-actions-oidc-role`). Temporary, scoped credentials are issued per-run. No long-lived access keys are stored in GitHub Secrets.

### 9. Trivy CVE gating
Every CI run scans the built Docker image. CRITICAL or HIGH severity vulnerabilities block the pipeline (`exit-code: 1`) before the image is ever deployed. SARIF reports are uploaded as pipeline artifacts for audit.

### 10. K8sGPT post-deploy health analysis
After every Helm deployment, K8sGPT CLI analyses the `production` namespace using the same `llama3.2:1b` model, scanning Pods, Deployments, ReplicaSets, Services, Ingress objects, and HPAs. Results are uploaded as a JSON artifact and can be routed to a Slack webhook via the K8sGPT operator CRD (`k8sgpt-config.yaml`).

### 11. Terraform remote state with DynamoDB locking
State is stored in S3 (`tanya-tfstate-2026`) with a DynamoDB lock table (`tanya-tfstate-lock`). This prevents concurrent `terraform apply` runs from corrupting state in a team environment.

### 12. ECR image scanning on push
Each ECR repository has `scan_on_push = true`, giving a second layer of vulnerability detection independent of the Trivy step in CI.

---

## Useful Commands

### Local

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

### Cloud (EKS)

```bash
# Check all pods in the production namespace
kubectl get pods -n production

# Check rollout status for a specific deployment
kubectl rollout status deployment/api-gateway -n production

# View logs from a running pod
kubectl logs -l app=ai-service -n production --tail=100

# Scale a deployment manually
kubectl scale deployment/order-service --replicas=3 -n production

# View HPA status (autoscaler metrics)
kubectl get hpa -n production

# View the ALB endpoint
kubectl get ingress -n production

# Roll back the last Helm release
helm rollback ai-platform -n production

# View Helm release history
helm history ai-platform -n production
```

### Terraform

```bash
# Preview infrastructure changes
terraform plan

# Apply changes
terraform apply

# Destroy all provisioned resources
terraform destroy

# Show the RDS connection endpoint
terraform output rds_endpoint
```
