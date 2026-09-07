resource "aws_db_subnet_group" "default" {
  name       = "microservices-db-subnet-group-${var.environment}"
  subnet_ids = module.vpc.private_subnets

  tags = {
    Name = "microservices-db-subnet-group"
  }
}

resource "aws_security_group" "rds" {
  name        = "microservices-rds-sg-${var.environment}"
  description = "Allow inbound PostgreSQL traffic from within the VPC only"
  vpc_id      = module.vpc.vpc_id

  ingress {
    description = "PostgreSQL from VPC-internal traffic only (EKS pods, Bastion)"
    from_port   = 5432
    to_port     = 5432
    protocol    = "tcp"
    cidr_blocks = [module.vpc.vpc_cidr_block]
  }

  egress {
    description = "Allow all outbound (e.g., for RDS maintenance)"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "microservices-rds-sg"
  }
}

resource "aws_db_instance" "postgres" {
  identifier        = "microservices-db-${var.environment}"
  allocated_storage = 20
  engine            = "postgres"
  engine_version    = "15"
  instance_class    = "db.t3.micro"
  db_name           = var.db_name
  username          = var.db_user
  password          = var.db_password

  db_subnet_group_name   = aws_db_subnet_group.default.name
  vpc_security_group_ids = [aws_security_group.rds.id]

  # Security: RDS is VPC-internal only, never exposed to the public internet.
  publicly_accessible = false

  # Data durability: daily automated backups retained for 7 days.
  # Allows point-in-time recovery to any second within the retention window.
  backup_retention_period = 7
  backup_window           = "03:00-04:00" # UTC — low traffic window

  # Deletion protection prevents accidental `terraform destroy` in production.
  # Set to false only for dev/sandbox environments where teardown is expected.
  deletion_protection = var.environment == "prod" ? true : false
  skip_final_snapshot = var.environment == "prod" ? false : true

  tags = {
    Name = "microservices-postgres"
  }
}

# Outputs what this module creates:
# - 1 RDS PostgreSQL instance (db.t3.micro, engine v15, VPC-private)
# - 1 DB Subnet Group (spanning the private subnets across 2 AZs)
# - 1 Security Group (ingress restricted to VPC CIDR on port 5432)
# - Automated backups with 7-day retention + deletion protection in prod
