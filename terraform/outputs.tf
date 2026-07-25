output "rds_endpoint" {
  value       = aws_db_instance.postgres.endpoint
  description = "The connection endpoint for the RDS PostgreSQL database"
}

output "eks_node_role_name" {
  value       = module.eks.eks_managed_node_groups["spot_workers"].iam_role_name
  description = "The IAM role name for the EKS spot workers node group"
}
