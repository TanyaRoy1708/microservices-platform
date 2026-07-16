# GitHub Actions OIDC Setup

One-time setup. Run after `terraform apply`, before pushing to `main` for the first time.
Replaces static AWS keys with per-run temporary credentials — nothing sensitive stored in GitHub.

Replace `<YOUR_ACCOUNT_ID>` and `<YOUR_GITHUB_ORG/REPO>` throughout.

---

## 1. Register GitHub as a trusted OIDC provider in AWS
**Run once per AWS account. Skip if already exists.**

```bash
aws iam create-open-id-connect-provider \
  --url https://token.actions.githubusercontent.com \
  --client-id-list sts.amazonaws.com \
  --thumbprint-list 6938fd4d98bab03faadb97b34396831e3780aea1
```

> Tells AWS: "trust identity tokens issued by GitHub Actions." The thumbprint pins
> GitHub's TLS cert so AWS can verify the token hasn't been tampered with.

Check if it already exists:

```bash
aws iam list-open-id-connect-providers
```

---

## 2. Create the trust policy file

```bash
cat > trust-policy.json << 'EOF'
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Principal": {
      "Federated": "arn:aws:iam::<YOUR_ACCOUNT_ID>:oidc-provider/token.actions.githubusercontent.com"
    },
    "Action": "sts:AssumeRoleWithWebIdentity",
    "Condition": {
      "StringEquals": {
        "token.actions.githubusercontent.com:aud": "sts.amazonaws.com"
      },
      "StringLike": {
        "token.actions.githubusercontent.com:sub": "repo:<YOUR_GITHUB_ORG/REPO>:*"
      }
    }
  }]
}
EOF
```

> `StringLike` with `repo:<org>/<repo>:*` scopes the role to this repo only.
> Any other GitHub repo cannot assume it.

---

## 3. Create the IAM role

```bash
aws iam create-role \
  --role-name gh-actions-oidc-role \
  --assume-role-policy-document file://trust-policy.json \
  --description "GitHub Actions OIDC role for microservices-platform"
```

> This is the role the pipeline assumes. No passwords — GitHub gets a short-lived token per run.

---

## 4. Attach permissions

```bash
# Allows docker build + push to ECR
aws iam attach-role-policy \
  --role-name gh-actions-oidc-role \
  --policy-arn arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryPowerUser

# Allows kubectl and helm deploy against EKS
aws iam attach-role-policy \
  --role-name gh-actions-oidc-role \
  --policy-arn arn:aws:iam::aws:policy/AmazonEKSClusterPolicy
```

---

## 5. Clean up temp file

```bash
rm trust-policy.json
```

---

## 6. Add secrets to GitHub

`Settings ? Secrets and variables ? Actions ? New repository secret`

| Secret | Value |
|---|---|
| `AWS_ACCOUNT_ID` | your 12-digit account ID |
| `ECR_REGISTRY` | `<account-id>.dkr.ecr.ap-south-1.amazonaws.com` |
| `DB_HOST` | output of `terraform output rds_endpoint` |
| `DB_NAME` | `platformdb` |
| `DB_USER` | `postgres` |
| `DB_PASSWORD` | your RDS master password |
| `OLLAMA_EC2_IP` | private IP of the EC2 running Ollama |

> These are the only secrets needed. AWS credentials are never stored — the pipeline
> uses the OIDC role above to get temporary creds at runtime.
