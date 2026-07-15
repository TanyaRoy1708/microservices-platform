variable "aws_region" {
  default = "ap-south-1"
}

variable "db_name" {
  default     = "platformdb"
  description = "Database name"
}

variable "db_user" {
  default     = "postgres"
  description = "Database master user"
}

variable "db_password" {
  default     = "supersecret123" # In production, avoid hardcoding passwords and use AWS Secrets Manager or TF_VARs
  description = "Database master password"
  sensitive   = true
}
