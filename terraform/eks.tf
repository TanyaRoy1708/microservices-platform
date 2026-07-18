module "eks" {
  source  = "terraform-aws-modules/eks/aws"
  version = "~> 20.0"

  cluster_name    = "ai-microservices-platform"
  cluster_version = "1.30"
  vpc_id          = module.vpc.vpc_id
  subnet_ids      = module.vpc.private_subnets

  # Allow kubectl from your machine
  cluster_endpoint_public_access = true

  # Grants the IAM role running Terraform admin access to the cluster
  enable_cluster_creator_admin_permissions = true

  eks_managed_node_groups = {
    spot_workers = {                         #spot_workers is node group name
      min_size       = 1
      max_size       = 5
      desired_size   = 2
      instance_types = ["t3.medium", "t3.large"]
      capacity_type  = "SPOT"   # ~70% cheaper than On-Demand
    }
  }

  # Enable IRSA - pods get AWS permissions via IAM roles, no static keys
  # When IRSA is enabled EKS creates an OIDC Identity Provider.
  # Every Pod gets a signed identity token.
  # AWS verifies this token. If it trusts the token it issued temporary creds.
  enable_irsa = true
}


# 1 Elastic Kubernetes Service (EKS) Cluster (named ai-microservices-platform running version 1.30)
# 1 Managed Node Group (named spot_workers, using SPOT instances with a desired capacity of 2 nodes, scaling between 1 to 5)
# 1 OIDC Identity Provider (created automatically because enable_irsa = true is set, allowing pods to assume IAM roles).