<div align="center">

# ☁️ Cloud-Native AI Microservices Platform

### *End-to-End DevOps — From Local Docker to Production AWS EKS*

[![Python](https://img.shields.io/badge/Python-3.11-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.111-009688?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![AWS EKS](https://img.shields.io/badge/AWS_EKS-v1.36-FF9900?style=for-the-badge&logo=amazonaws&logoColor=white)](https://aws.amazon.com/eks/)
[![Terraform](https://img.shields.io/badge/Terraform-IaC-7B42BC?style=for-the-badge&logo=terraform&logoColor=white)](https://www.terraform.io/)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?style=for-the-badge&logo=docker&logoColor=white)](https://www.docker.com/)
[![GitHub Actions](https://img.shields.io/badge/CI%2FCD-GitHub_Actions-2088FF?style=for-the-badge&logo=github-actions&logoColor=white)](https://github.com/features/actions)
[![Helm](https://img.shields.io/badge/Helm-v3-0F1689?style=for-the-badge&logo=helm&logoColor=white)](https://helm.sh/)
[![Trivy](https://img.shields.io/badge/Security-Trivy-1904DA?style=for-the-badge&logo=aquasecurity&logoColor=white)](https://trivy.dev/)

> 4 Python microservices containerized with Docker, orchestrated on AWS EKS with Terraform IaC, deployed via a fully automated GitHub Actions CI/CD pipeline — with container security scanning, HPA autoscaling, and an AI-powered natural language query engine.

</div>

---

## 🎯 What This Project Demonstrates

| Skill Area | Implementation |
|:---|:---|
| **Infrastructure as Code** | Complete AWS environment (VPC, EKS, RDS, ECR) provisioned with Terraform; `default_tags` for cost allocation; remote state in S3 with native locking; variable validation enforcing password strength |
| **CI/CD Automation** | Parallel matrix pipeline: code push → pytest → Docker BuildKit cache → ECR push → Trivy CVE gate → `helm upgrade` on EKS |
| **Security Engineering** | Keyless AWS auth via OIDC federation; Trivy scan **gates** deploys on critical CVEs (exit-code 1); non-root containers; no static IAM keys anywhere |
| **Kubernetes Orchestration** | HPA (CPU+memory, with scale behavior policies), PodDisruptionBudgets, Helm packaging, AWS ALB Ingress, automated DB migrations via Helm `post-install` hooks |
| **Resilience** | PostgreSQL connection pooling (`psycopg2.pool`); Redis caching with 60s TTL; PDB prevents Spot eviction outages; `--atomic` Helm deploys auto-rollback on failure |
| **Cloud Cost Optimization** | EKS Spot Instance node group (~70% cheaper); `single_nat_gateway` for dev; HPA scales down during off-peak; explicit cost tags on all AWS resources |
| **AI Integration** | Natural language → structured intent → microservice orchestration, powered by Llama 3.2 (1B) via Ollama; prompt injection protection via allowlist validator |

> 📋 **[Technical Deep Dive — screenshots, pipeline breakdown, engineering challenges & trade-offs →](./docs/TECHNICAL_DEEP_DIVE.md)**

---

## 🏗️ Architecture

```
Internet ──HTTPS──▶ AWS ALB Ingress
                          │
                    ┌─────┴──────────────────────────────────────────────┐
                    │           AWS EKS Cluster (production ns)          │
                    │                                                     │
                    │   API Gateway (:8000)                               │
                    │     ├──▶ User Service  (:5001) ──▶ RDS Postgres    │
                    │     ├──▶ Order Service (:5002) ──▶ RDS + Redis     │
                    │     └──▶ AI Service    (:5003) ──────────────────┐ │
                    └─────────────────────────────────────────────────│─┘
                                                                      │
                    EC2 (t3.large, VPC-internal)                      │
                    └──▶ Ollama / Llama 3.2 ◀────────────────────────┘

Local Dev: All services + PostgreSQL + Redis + Llama 3.2 run via
           a single `bash scripts/setup.sh` using Docker Compose.
```

---

## 🛠️ Technology Stack

| Layer | Technology | Decision Rationale |
|:---|:---|:---|
| **Cloud** | AWS (`ap-south-1`) | — |
| **IaC** | Terraform `~> 5.0` · S3 native locking | No DynamoDB table needed; `default_tags` auto-tags all resources |
| **Containers** | Docker · Docker Compose | Multi-stage builds; non-root user; BuildKit layer caching in CI |
| **Orchestration** | AWS EKS `v1.36` · Helm `v3` · ALB Ingress | HPA + PDB for resilience; `--atomic` for safe deploys |
| **CI/CD** | GitHub Actions — parallel matrix + Trivy gate | OIDC keyless auth; build cache; CVE gate on critical/high |
| **Backend** | Python `3.11` · FastAPI `0.111` | `lifespan` pattern (modern); async throughout |
| **Databases** | AWS RDS PostgreSQL `15` · Redis `7` | Connection pooling prevents exhaustion; 60s Redis TTL for orders |
| **AI Engine** | Ollama · `llama3.2:1b` · Intent extraction | Bounded operation set → direct extraction beats RAG for this scope |
| **Registry** | Amazon ECR (4 private repositories) | Integrated with OIDC auth; image tag = commit SHA for traceability |

---

## 🏛️ Architecture Decision Records

> *Why were these choices made? This section answers the "why X over Y?"*

**OIDC over static IAM keys** — GitHub Actions federates with AWS using short-lived OIDC tokens. Static `AWS_SECRET_ACCESS_KEY` secrets can be leaked via log output, forked PRs, or secret scanning misses. OIDC tokens expire in minutes; static keys persist until rotated.

**EKS Spot instances** — ~70% cost reduction vs. On-Demand for the same t3.medium/large. Trade-off: 2-minute eviction notice. Mitigated by: multiple instance types (better availability), PodDisruptionBudgets (minimum pods guaranteed during drains), and HPA (fast rescheduling on new nodes).

**Redis TTL=60s (not cache invalidation)** — For a read-mostly dataset (orders list), 60s staleness is acceptable and dramatically simpler than maintaining a cache invalidation bus. At higher write frequency or stricter consistency requirements, switch to explicit invalidation on order status changes.

**`psycopg2.SimpleConnectionPool` (not `ThreadedConnectionPool`)** — FastAPI's thread pool uses synchronous DB calls here, not async. `SimpleConnectionPool` is correct and slightly faster; `ThreadedConnectionPool` adds locking overhead only needed for true multi-threaded access patterns.

**Flat Terraform files (not nested modules)** — Each `.tf` file has a single responsibility (vpc.tf, eks.tf, rds.tf). For this scale (1 environment, ~5 resources), flat structure is more readable and faster to iterate on than module indirection. Module extraction becomes worthwhile when managing 3+ environments or sharing infra patterns across projects.

**Intent extraction over RAG for AI** — The API surface is bounded: 2 services, 7 operations. Direct LLM extraction is simpler, faster (<2s vs. embedding lookups), and more reliable for a fixed schema than vector search. RAG becomes the right choice when the operation space is large or dynamic.

---

## ⚡ Quick Start (Local)

> *Requires Docker Desktop v24+ and ~8GB RAM (for Llama 3.2)*

```bash
# 1. Clone
git clone https://github.com/TanyaRoy1708/microservices-platform.git
cd microservices-platform

# 2. Bootstrap — builds images, seeds DB, starts all services, pulls AI model
bash scripts/setup.sh

# 3. Verify all services are healthy
docker compose ps

# 4. Test the AI natural language query engine
curl -s -X POST http://localhost:8000/ai/query \
  -H 'Content-Type: application/json' \
  -d '{"query": "Show me all orders over 50000"}'

# 5. Open interactive API docs: http://localhost:8000/docs
```

---

## ☁️ Cloud Deployment (AWS EKS)

**Prerequisites:** AWS CLI, Terraform `1.7+`, `kubectl`, `helm`

```bash
# 1. Provision infrastructure
cd terraform/
export TF_VAR_db_password="your-secure-password-min-16-chars"
terraform init && terraform apply

# 2. Set up EKS + ALB controller
bash scripts/eks-setup.sh

# 3. CI/CD deploys automatically on push to main
git push origin main
```

### 🛑 Teardown (Prevents AWS Charges)

**Important:** Uninstall Helm before destroying Terraform — otherwise the ALB Ingress Controller leaves orphaned AWS Load Balancers that block VPC deletion.

```bash
# 1. Remove Helm release (deletes ALB, pods, services)
helm uninstall ai-platform -n production

# 2. Destroy all AWS infrastructure
cd terraform/
terraform destroy
```

---

## 📂 Repository Structure

```
microservices-platform/
├── .github/workflows/deploy.yaml   # CI/CD: parallel matrix build + Trivy gate + Helm deploy
├── services/                       # Application source code
│   ├── api-gateway/                # FastAPI entry point — routes + request ID propagation
│   ├── ai-service/                 # NL → intent extraction → service orchestration
│   │   ├── prompts.py              # LLM prompt engineering (separated for testability)
│   │   └── validator.py            # Intent allowlist (security gate against prompt injection)
│   ├── user-service/               # User CRUD — PostgreSQL + connection pooling
│   └── order-service/              # Order queries — PostgreSQL + Redis cache
├── infra/                          # Infrastructure definitions
│   ├── terraform/                  # Flat IaC: vpc.tf, eks.tf, rds.tf, ecr.tf
│   └── helm/ai-platform/           # Unified Helm chart
│       └── templates/
│           ├── */deployment.yaml   # Deployment manifests (liveness + readiness probes)
│           ├── */hpa.yaml          # HPA per service (CPU+memory, scale behavior policies)
│           ├── */pdb.yaml          # PodDisruptionBudget per service (Spot eviction protection)
│           ├── redis/              # In-cluster Redis deployment
│           ├── ingress.yaml        # AWS ALB Ingress
│           └── db-init-job.yaml    # Helm post-install hook: idempotent DB migration
├── local-dev/                      # Local development assets (docker-compose, etc)
├── scripts/                        # Automation scripts
├── tests/                          # Unit & integration tests
└── docs/                           # Documentation
    └── TECHNICAL_DEEP_DIVE.md      # Live screenshots, pipeline walk-through, trade-offs
```

---

## 📊 Project Metrics

| Metric | Value |
|:---|:---|
| AWS Infrastructure | VPC · 2 AZs · EKS Spot Cluster · RDS PostgreSQL · Redis · ECR · ALB · IAM/OIDC |
| Microservices | 4 (api-gateway, user-service, order-service, ai-service) |
| CI/CD Pipeline Duration | ~3 minutes (parallel matrix) |
| Kubernetes Resources | Deployments · Services · HPA · PDB · Ingress · ConfigMap · Secrets · Helm Hooks |
| Test Coverage | 20+ test cases across all 4 services |
| Estimated AWS Cost | ~$120/month (optimized via Spot instances + single NAT gateway) |
