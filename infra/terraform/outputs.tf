output "rds_endpoint" {
  value       = aws_db_instance.postgres.endpoint
  description = "RDS PostgreSQL connection endpoint — use this as DB_HOST in your application config"
}

output "eks_cluster_name" {
  value       = module.eks.cluster_name
  description = "EKS cluster name — use with: aws eks update-kubeconfig --name <value>"
}

output "eks_cluster_endpoint" {
  value       = module.eks.cluster_endpoint
  description = "EKS cluster API server endpoint URL"
}

output "eks_oidc_provider_arn" {
  value       = module.eks.oidc_provider_arn
  description = "OIDC provider ARN — used when creating IAM roles for IRSA (pod-level AWS auth)"
}

output "eks_node_role_name" {
  value       = module.eks.eks_managed_node_groups["spot_workers"].iam_role_name
  description = "IAM role name for the Spot worker nodes — used to attach ALB Controller IAM policy"
}

output "ecr_registry" {
  value       = "${data.aws_caller_identity.current.account_id}.dkr.ecr.${var.aws_region}.amazonaws.com"
  description = "ECR registry URL — use as ECR_REGISTRY in GitHub Actions secrets"
}

# Required for the ecr_registry output above
data "aws_caller_identity" "current" {}
