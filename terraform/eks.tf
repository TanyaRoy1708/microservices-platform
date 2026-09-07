module "eks" {
  source  = "terraform-aws-modules/eks/aws"
  version = "~> 20.0"

  cluster_name    = "ai-microservices-platform"
  cluster_version = "1.36"
  vpc_id          = module.vpc.vpc_id
  subnet_ids      = module.vpc.private_subnets

  # The cluster API endpoint is public to allow kubectl from developer machines and CI/CD.
  # Restrict access to specific CIDRs (your office IP + GitHub Actions egress ranges) in production.
  # Full private endpoint requires a VPN or Bastion — appropriate for highly regulated environments.
  cluster_endpoint_public_access       = true
  cluster_endpoint_public_access_cidrs = var.allowed_cidr_blocks

  # Grants the IAM identity that runs Terraform admin access to the cluster via
  # the aws-auth ConfigMap. Without this, Terraform itself can't manage cluster resources.
  enable_cluster_creator_admin_permissions = true

  eks_managed_node_groups = {
    # Spot instances are ~70% cheaper than On-Demand for the same instance type.
    # Trade-off: AWS can reclaim Spot instances with 2-min notice.
    # Mitigated by: multiple instance types, HPA for rapid re-scheduling,
    # and PodDisruptionBudgets ensuring minimum availability during drains.
    spot_workers = {
      min_size       = 1
      max_size       = 5
      desired_size   = 2
      instance_types = ["t3.medium", "t3.large"] # Multiple types = better Spot availability
      capacity_type  = "SPOT"

      # Node labels for workload placement (e.g., use node selectors to avoid
      # scheduling latency-sensitive workloads on Spot nodes)
      labels = {
        "node.kubernetes.io/capacity-type" = "spot"
        "project"                          = "microservices-platform"
      }
    }
  }

  # IRSA (IAM Roles for Service Accounts) — pods get AWS permissions via
  # projected service account tokens, not static IAM keys on the node.
  # When enabled, EKS creates an OIDC Identity Provider automatically.
  # Each pod presents a signed token → AWS STS verifies → issues temp credentials.
  enable_irsa = true
}

# What this creates:
# - 1 EKS Cluster (ai-microservices-platform, v1.36)
# - 1 Managed Spot Node Group (2 nodes desired, scales 1-5, t3.medium/large)
# - 1 OIDC Identity Provider (enables IRSA for pod-level AWS auth)