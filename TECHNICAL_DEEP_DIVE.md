# 📋 Technical Deep Dive

> This document contains live proof screenshots, pipeline architecture, engineering challenges, and project metrics for the [Cloud-Native AI Microservices Platform](./README.md).

---

## ✅ CI/CD Pipeline — All Checks Passing

*5 parallel jobs (4 microservice CI + 1 deploy) — all green. Pipeline runs in under 3 minutes.*

![GitHub Actions Full Pipeline](./screenshots/github-actions%20pipeline%20view.png)

---

## ✅ Helm Deploy to EKS — Step-by-Step

*Deploy job: OIDC auth → kubeconfig update → DB secret injection → `helm upgrade` → rollout verification.*

![GitHub Actions Deploy Job](./screenshots/github%20actions%20%20pipeline%20success.png)

---

## ✅ Kubernetes Pods — All Running in Production

*9 pods live in the `production` namespace — all microservices at `1/1 READY`, DB migration Job `Completed` cleanly.*

![kubectl get pods -n production](./screenshots/kubectl%20pods.png)

---

## ✅ Terraform Apply — Full Cloud Infrastructure Provisioned

*Apply complete! — Full VPC, EKS Spot node group, RDS endpoint, and ECR registry provisioned via modular IaC.*

![Terraform Apply Output](./screenshots/terraform%20apply%20.png)

---

## ✅ Amazon ECR — 4 Private Repositories

*All microservice images stored in private ECR repositories, auto-pushed by the CI/CD pipeline on every `main` branch push.*

![ECR Private Repositories](./screenshots/ecr%20repos.png)

---

## ✅ AI Natural Language Query Engine — Live

*POST `/ai/query` with plain English: `"Show me all orders over 50000"` → Llama 3.2 parses intent → queries PostgreSQL → returns structured results. `200 OK`.*

![AI Query Result](./screenshots/ai-query.png)

---

## ✅ Local Dev — Interactive API Docs

*FastAPI's auto-generated Swagger UI at `localhost:8000/docs` — all microservice endpoints documented and testable instantly.*

![FastAPI Swagger UI](./screenshots/api-gateway-swagger.png)

---

## ✅ Docker Compose — Full Stack Running Locally

*All services healthy via `docker compose ps`. Local environment mirrors production perfectly.*

![Docker Compose Status](./screenshots/docker%20compose%20ps.png)

---

## 🔄 CI/CD Pipeline — Design Decisions

```
git push ──▶ main
              │
    ┌─────────▼──────────────────────────────────────────────────┐
    │  PARALLEL MATRIX (4 jobs run simultaneously)               │
    │                                                             │
    │  ci (api-gateway)   ──▶ pytest ──▶ ECR push ──▶ Trivy scan │
    │  ci (user-service)  ──▶ pytest ──▶ ECR push ──▶ Trivy scan │
    │  ci (order-service) ──▶ pytest ──▶ ECR push ──▶ Trivy scan │
    │  ci (ai-service)    ──▶ pytest ──▶ ECR push ──▶ Trivy scan │
    └─────────────────────────────┬───────────────────────────────┘
                                  │  (all 4 must pass)
                        ┌─────────▼─────────────────┐
                        │  DEPLOY JOB                │
                        │  OIDC → kubeconfig update  │
                        │  Inject DB secret          │
                        │  helm upgrade --atomic     │
                        │  Verify all rollouts       │
                        └────────────────────────────┘
```

- **OIDC over static keys** — GitHub Actions federates with AWS IAM using short-lived tokens. No `AWS_SECRET_ACCESS_KEY` ever stored in secrets.
- **`--atomic` Helm flag** — If any pod fails health checks, the deployment auto-rolls back. Zero manual intervention.
- **Trivy SARIF upload** — Vulnerability reports are uploaded directly to GitHub Security tab for audit trails.
- **Testing Strategy** — `pytest` executes available test suites, allowing the pipeline to proceed gracefully if tests are still pending.
- **Trunk-based Development** — PRs run the CI matrix (tests + scans); merges to `main` trigger the CD deploy job.

---

## 🧩 Engineering Challenges Solved

These are real problems I debugged and solved during this project:

| Challenge | Root Cause | Solution |
|:---|:---|:---|
| **ALB Controller no permissions** | EKS worker nodes missing IAM policy | Dynamically attached the required policy via `eks-setup.sh` using the OIDC provider ARN |
| **DB migration ran twice** | Helm re-ran the `post-install` Job on redeploy | Made `init.sql` fully idempotent with `INSERT WHERE NOT EXISTS` guards |
| **Helm resource conflict** | Manual `kubectl apply` resources conflicted with Helm ownership | Deleted orphaned resources and re-created as proper Helm-managed templates |
| **LLM unreachable from EKS** | Ollama running on EC2, EKS pods in private subnet | Exposed port `11434` on EC2 via `0.0.0.0`, secured with AWS Security Group rules allowing only EKS CIDR |
| **DB connection exhaustion** | Each FastAPI request opened a new connection | Implemented `psycopg2.SimpleConnectionPool` with min/max bounds — dramatically reduced latency |

---

## 📊 Project Metrics

| Metric | Value |
|:---|:---|
| AWS Infrastructure | **Full Cloud Environment** *(VPC, Subnets, EKS Cluster, Spot Node Groups, RDS Postgres, ECR Repos, IAM, SGs, ALB)* |
| Microservices deployed | **4** |
| CI/CD pipeline duration | **~3 minutes** |
| Kubernetes pods in production | **9** (incl. DB init Job) |
| Estimated AWS Cost | **~$120/month** *(Optimized via EKS Spot Instances)* |

---

## 🔮 Future Improvements

- **Observability Stack**: Deploy Prometheus & Grafana via Helm, with structured JSON logging via FluentBit to CloudWatch.
- **Security Hardening**: Implement mTLS (Istio or Linkerd) for pod-to-pod communication; move the EC2 LLM behind a private VPC endpoint.
