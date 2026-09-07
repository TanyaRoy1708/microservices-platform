terraform {
  required_version = ">= 1.7"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  # Remote state in S3 with native locking (no DynamoDB table needed, uses S3 conditional writes).
  # This prevents concurrent terraform applies from corrupting the state file.
  backend "s3" {
    bucket       = "tanya-tfstate-2026"
    key          = "microservices-platform/terraform.tfstate"
    region       = "ap-south-1"
    use_lockfile = true
  }
}

provider "aws" {
  region = var.aws_region

  # default_tags applies these tags to EVERY AWS resource created by this provider.
  # This enables cost allocation dashboards, resource filtering, and compliance tracking
  # without having to add tags manually to every resource block.
  default_tags {
    tags = {
      Project     = "microservices-platform"
      Environment = var.environment
      ManagedBy   = "terraform"
      Repository  = "github.com/TanyaRoy1708/microservices-platform"
    }
  }
}
