# Local Setup & Run Guide

This guide will walk you through setting up and running the microservices platform locally.

## 1. Clone the Repository

First, clone the project to your local machine and navigate into the project directory:

```bash
git clone <repository-url>
cd microservices-platform
```

## 2. Prerequisites

Before running the project, ensure you have the following installed on your machine:

- **Docker Desktop**: Version 24.x or higher (`docker --version`)
- **Docker Compose**: Version 2.x or higher (`docker compose version`)
- **Python**: 3.11 or higher (optional, for local non-containerized testing)
- **System Resources**: At least 8 GB of free RAM (Ollama LLM requires significant memory) and 5 GB of free disk space.

## 3. Pre-Setup

The project relies on environment variables for database and caching credentials.

1. Copy the example environment file to create your local `.env` file:
   ```bash
   cp .env.example .env
   ```
2. Open the `.env` file and set strong values for `DB_PASSWORD` and `REDIS_PASSWORD`.

## 4. Run the Platform

You can start the entire platform (PostgreSQL, Redis, Ollama LLM, and all 4 Python services) using Docker Compose.

```bash
docker compose up --build -d
```

> **Note:** The first time you run this command, the `ollama-model-pull` container will download the `llama3.2:1b` model weights (~1.3 GB). This will take a few minutes depending on your internet connection. Subsequent starts will be much faster.

To view the logs and ensure everything is starting up smoothly:
```bash
docker compose logs -f
```

## 5. Verification

Once all containers are running and healthy, you can verify the services by opening your browser or using `curl`.

### Health Check
You can verify the API Gateway is running by navigating to:
- **API Gateway:** http://localhost:8000/health

*(Note: The User, Order, and AI services run on an internal Docker network and do not expose their ports to the host machine for security. All external traffic must pass through the API Gateway.)*
### Testing the Endpoints (In Browser)
You can view the raw JSON responses by navigating to:
- **All Users:** http://localhost:8000/users
- **Specific User:** http://localhost:8000/users/1
- **All Orders:** http://localhost:8000/orders

### Testing the AI Service (Terminal)
To test the natural language AI query, use the following `curl` command in your terminal:

```bash
curl -s -X POST http://localhost:8000/ai/query \
  -H 'Content-Type: application/json' \
  -d '{"query": "Show me all orders placed by Priya"}'
```



## 6. Teardown

When you are finished, you can stop the services. 

To stop the containers but keep your database data and downloaded LLM models:
```bash
docker compose down
```

To stop the containers and **wipe all data** (volumes):
```bash
docker compose down -v
```

---

## 7. Cloud Deployment (AWS EKS & GitHub Actions)

Once you have verified the platform locally, you can deploy it to a production Kubernetes cluster (AWS EKS) using the provided Terraform, Helm charts, and CI/CD pipeline.

### Prerequisites for Cloud
- **Terraform** >= 1.6
- **AWS CLI** configured with appropriate permissions
- **kubectl** and **Helm v3**
- An AWS Account

### Step 7.1: Bootstrap Terraform State
Before provisioning the infrastructure, create an S3 bucket and DynamoDB table in AWS to store your Terraform state securely:
```bash
# Create S3 Bucket
aws s3api create-bucket --bucket <your-bucket-name> --region ap-south-1 --create-bucket-configuration LocationConstraint=ap-south-1
# Enable Versioning
aws s3api put-bucket-versioning --bucket <your-bucket-name> --versioning-configuration Status=Enabled
# Create DynamoDB Table
aws dynamodb create-table --table-name <your-dynamodb-table> --attribute-definitions AttributeName=LockID,AttributeType=S --key-schema AttributeName=LockID,KeyType=HASH --billing-mode PAY_PER_REQUEST --region ap-south-1
```
*(Make sure to update `terraform/main.tf` with your bucket and table names).*

### Step 7.2: Provision Infrastructure (Terraform)
This will provision the VPC, EKS Cluster, RDS PostgreSQL, and ECR Repositories.
```bash
cd terraform
terraform init
terraform apply
```
*(Takes ~15 minutes to complete).*

### Step 7.3: Configure EKS Add-ons
Run the provided script to update your local kubeconfig and install the AWS Load Balancer Controller (required for Ingress routing).
```bash
bash scripts/eks-setup.sh
```

### Step 7.4: Set up GitHub Actions OIDC
Configure GitHub Actions to securely assume an IAM role for deployments without hardcoded AWS keys. Follow the instructions in:
```text
microservices-platform/scripts/setup-oidc.md
```
Then, add the required secrets (like `AWS_ACCOUNT_ID`, `DB_PASSWORD`, etc.) to your GitHub repository settings.

### Step 7.5: Automated Deployment
Push your code to the `main` branch. GitHub Actions will automatically:
1. Build the Docker images for all 4 services.
2. Run Trivy vulnerability scans.
3. Push images to Amazon ECR.
4. Deploy the services to EKS using the `helm/ai-platform` chart.

### Verification in the Cloud
Once deployed, retrieve the ALB hostname:
```bash
kubectl get ingress -n production
```
You can now access your APIs using the public ALB hostname (e.g. `http://<ALB-DNS>/health`).

## 8. Cloud Teardown
To prevent ongoing AWS charges (~$4/day for EKS), tear down the infrastructure when finished:
```bash
# 1. Uninstall Helm release
helm uninstall ai-platform -n production

# 2. Destroy AWS infrastructure
cd terraform
terraform destroy
```