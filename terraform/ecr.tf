data "aws_caller_identity" "current" {}

resource "aws_ecr_repository" "services" {
  for_each = toset(["api-gateway", "user-service", "order-service", "ai-service"])

  name                 = each.key
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = true   # ECR built-in basic scanning
  }
}

output "ecr_registry" {
  value = "${data.aws_caller_identity.current.account_id}.dkr.ecr.${var.aws_region}.amazonaws.com"
}


# 4 Elastic Container Registry (ECR) Repositories (specifically named api-gateway, user-service, order-service, and ai-service)