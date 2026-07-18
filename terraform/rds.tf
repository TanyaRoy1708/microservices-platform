resource "aws_db_subnet_group" "default" {
  name       = "microservices-db-subnet-group"
  subnet_ids = module.vpc.private_subnets

  tags = {
    Name = "microservices-db-subnet-group"
  }
}

resource "aws_security_group" "rds" {
  name        = "microservices-rds-sg"
  description = "Allow inbound traffic to RDS from VPC"
  vpc_id      = module.vpc.vpc_id

  ingress {
    description = "Allow PostgreSQL traffic from within VPC"
    from_port   = 5432
    to_port     = 5432
    protocol    = "tcp"
    cidr_blocks = [module.vpc.vpc_cidr_block]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_db_instance" "postgres" {
  identifier           = "microservices-db"
  allocated_storage    = 20
  engine               = "postgres"
  engine_version       = "15"
  instance_class       = "db.t3.micro"
  db_name              = var.db_name
  username             = var.db_user
  password             = var.db_password
  db_subnet_group_name = aws_db_subnet_group.default.name
  vpc_security_group_ids = [aws_security_group.rds.id]
  
  # For non-prod environments, it's safe to skip snapshots before destroying
  skip_final_snapshot  = true
  publicly_accessible  = false
}


# 1 RDS PostgreSQL Database Instance (named microservices-db running engine version 15 on a db.t3.micro)
# 1 DB Subnet Group (named microservices-db-subnet-group to place the DB in the private subnets)
# 1 Security Group (named microservices-rds-sg to allow inbound PostgreSQL traffic on port 5432 from within the VPC)

