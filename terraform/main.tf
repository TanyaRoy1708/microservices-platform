terraform {
  required_version = ">= 1.7"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
  # Store state remotely - prevents state file loss (using S3 native locking)
  backend "s3" {
    bucket       = "tanya-tfstate-2026"
    key          = "microservices-platform/terraform.tfstate"
    region       = "ap-south-1"
    use_lockfile = true
  }
}

provider "aws" {
  region = var.aws_region
}
