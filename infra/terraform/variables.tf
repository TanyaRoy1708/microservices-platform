variable "aws_region" {
  description = "AWS region to deploy all resources into"
  type        = string
  default     = "ap-south-1"
}

variable "environment" {
  description = "Deployment environment name (dev / staging / prod). Used for resource tagging and naming."
  type        = string
  default     = "dev"

  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "environment must be one of: dev, staging, prod."
  }
}

variable "db_name" {
  description = "PostgreSQL database name"
  type        = string
  default     = "platformdb"
}

variable "db_user" {
  description = "PostgreSQL master username"
  type        = string
  default     = "postgres"
}

variable "db_password" {
  description = <<-EOT
    RDS master password. Never set a default here.
    Pass via environment variable: export TF_VAR_db_password="your-secure-password"
    Or in CI: set as a GitHub Actions secret and pass via -var flag.
    Minimum 16 characters required.
  EOT
  type      = string
  sensitive = true
  nullable  = false

  validation {
    condition     = length(var.db_password) >= 16
    error_message = "db_password must be at least 16 characters for RDS compliance."
  }
}

variable "allowed_cidr_blocks" {
  description = "CIDR blocks allowed to reach the EKS cluster API endpoint (e.g., your office IP, CI/CD egress IPs)"
  type        = list(string)
  default     = ["0.0.0.0/0"] # Restrict this in production to specific CIDRs
}
