<div align="center">

# ☁️ Cloud-Native AI Microservices Platform

### *End-to-End DevOps — From Local Docker to Production AWS EKS*

[![Python](https://img.shields.io/badge/Python-3.11-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.103-009688?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![AWS EKS](https://img.shields.io/badge/AWS_EKS-Prod-FF9900?style=for-the-badge&logo=amazonaws&logoColor=white)](https://aws.amazon.com/eks/)
[![Terraform](https://img.shields.io/badge/Terraform-IaC-7B42BC?style=for-the-badge&logo=terraform&logoColor=white)](https://www.terraform.io/)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?style=for-the-badge&logo=docker&logoColor=white)](https://www.docker.com/)
[![GitHub Actions](https://img.shields.io/badge/CI%2FCD-GitHub_Actions-2088FF?style=for-the-badge&logo=github-actions&logoColor=white)](https://github.com/features/actions)
[![Helm](https://img.shields.io/badge/Helm-v3-0F1689?style=for-the-badge&logo=helm&logoColor=white)](https://helm.sh/)
[![Trivy](https://img.shields.io/badge/Security-Trivy-1904DA?style=for-the-badge&logo=aquasecurity&logoColor=white)](https://trivy.dev/)

> 4 Python microservices containerized with Docker, orchestrated on AWS EKS with Terraform, deployed via a fully automated GitHub Actions CI/CD pipeline with security scanning — backed by an AI-powered natural language query engine.

</div>

---

## 🎯 What This Project Demonstrates

| Skill Area | What I Built |
|:---|:---|
| **Infrastructure as Code** | Complete AWS infrastructure (VPC, EKS, RDS, ECR) provisioned from scratch with Terraform modules; remote state in S3 (native locking) |
| **CI/CD Automation** | Fully automated pipeline: code push → parallel tests → Trivy CVE scan → ECR push → `helm upgrade` on EKS |
| **Security Engineering** | Keyless AWS auth via OIDC federation; automated container scanning that blocks deploys on critical CVEs |
| **Kubernetes Orchestration** | HPA, Helm packaging, AWS ALB Ingress, ClusterIP internal routing, automated DB migrations via Helm `post-install` hooks |
| **Cloud Cost Optimization** | EKS Spot Instance node group to reduce compute costs without sacrificing availability |
| **Resilience & Performance** | PostgreSQL connection pooling (`psycopg2.pool`) + ephemeral Redis caching to eliminate connection exhaustion |
| **AI Integration** | Natural language → SQL query engine powered by Llama 3.2 (1B) via Ollama on a VPC-internal EC2 instance |

> 📋 **[Technical Deep Dive — screenshots, pipeline breakdown, engineering challenges & metrics →](./TECHNICAL_DEEP_DIVE.md)**

---

## 🏗️ Architecture

```
Internet ──HTTPS──▶ AWS ALB Ingress
                          │
                    ┌─────┴──────────────────────────────────────┐
                    │         AWS EKS Cluster (Production NS)     │
                    │                                             │
                    │    API Gateway (:8000)                      │
                    │      ├──▶ User Service    ──▶ RDS Postgres  │
                    │      ├──▶ Order Service   ──▶ RDS Postgres  │
                    │      │         └────────────▶ Redis Cache   │
                    │      └──▶ AI Service ─────────────────────┐ │
                    └───────────────────────────────────────────│─┘
                                                                │
                    EC2 (t3.large, VPC-internal)                │
                    └──▶ Ollama / Llama 3.2 ◀───────────────────┘
```

**Local dev:** The full stack (microservices, PostgreSQL, Redis, Llama 3.2) runs with a single `bash scripts/setup.sh` command via Docker Compose, mirroring production.

---

## 🛠️ Technology Stack

| Layer | Technology |
|:---|:---|
| **Cloud** | AWS (`ap-south-1`) |
| **IaC** | Terraform `~> 5.0` · S3 remote state (native locking) |
| **Containers** | Docker · Docker Compose |
| **Orchestration** | AWS EKS `v1.36` · Helm `v3` · AWS ALB Ingress Controller |
| **CI/CD** | GitHub Actions — parallel matrix build + Helm deploy |
| **Security** | AWS OIDC Federation · Trivy (SARIF upload to GitHub Security tab) |
| **Backend** | Python `3.11` · FastAPI `0.111` |
| **Databases** | AWS RDS PostgreSQL `15` · Redis `7` (in-cluster) |
| **AI Engine** | Ollama · `llama3.2:1b` · Natural language → SQL |
| **Registry** | Amazon ECR (4 private repositories) |

---

## ⚡ Quick Start (Local)

> *Requires Docker Desktop v24+ and ~8GB RAM*

```bash
# 1. Clone
git clone https://github.com/TanyaRoy1708/microservices-platform.git
cd microservices-platform

# 2. Bootstrap (pulls images, seeds DB, starts all services)
bash scripts/setup.sh

# 3. Test the AI query engine
curl -s -X POST http://localhost:8000/ai/query \
  -H 'Content-Type: application/json' \
  -d '{"query": "Show me all orders over 5000"}'

# 4. Open Swagger UI: http://localhost:8000/docs
```

---

## ☁️ Cloud Deployment (AWS EKS)

**Prerequisites:** AWS CLI, Terraform `1.6+`, `kubectl`, `helm`

```bash
cd terraform/
terraform init && terraform apply

# Pipeline deploys automatically on push to main
git push origin main
```

### 🛑 Cloud Teardown (Important!)

To prevent ongoing AWS charges, tear down the infrastructure when finished. **You must uninstall the Helm release before destroying Terraform**, otherwise VPC deletion will hang due to the ALB provisioned by the Ingress Controller.

```bash
# 1. Uninstall Helm release
helm uninstall ai-platform -n production

# 2. Destroy AWS infrastructure
cd terraform/
terraform destroy
```

---

## 📂 Repository Structure

```
microservices-platform/
├── .github/workflows/deploy.yaml   # CI/CD pipeline (matrix + deploy)
├── api-gateway/                    # FastAPI entrypoint — routes all traffic
├── ai-service/                     # NL query engine — Llama 3.2 via Ollama
├── user-service/                   # User CRUD — PostgreSQL + connection pooling
├── order-service/                  # Order logic — PostgreSQL + Redis cache
├── terraform/
│   ├── modules/vpc/                # VPC, subnets, IGW
│   ├── modules/eks/                # EKS cluster + Spot node group
│   ├── modules/rds/                # RDS PostgreSQL
│   └── modules/ecr/                # ECR repositories
├── helm/ai-platform/               # Unified Helm chart
│   └── templates/
│       ├── redis/                  # In-cluster Redis
│       └── db-init-job.yaml        # Helm pre-install hook (DB migration)
├── scripts/
│   ├── setup.sh                    # Local bootstrap
│   └── eks-setup.sh                # ALB controller IAM setup
└── TECHNICAL_DEEP_DIVE.md          # Live proof — pipeline, pods, infra, challenges
```
