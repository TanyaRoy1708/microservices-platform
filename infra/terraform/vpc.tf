module "vpc" {
  source  = "terraform-aws-modules/vpc/aws"
  version = "~> 5.0"

  name = "microservices-vpc"
  cidr = "10.0.0.0/16"

  azs             = ["ap-south-1a","ap-south-1b"]
  private_subnets = ["10.0.1.0/24", "10.0.2.0/24"]
  public_subnets  = ["10.0.101.0/24", "10.0.102.0/24"]

  enable_nat_gateway = true
  single_nat_gateway = true
  
  # Required tags for ALB Ingress Controller to discover subnets
  public_subnet_tags = {
    "kubernetes.io/role/elb" = "1"
  }
  private_subnet_tags = {
    "kubernetes.io/role/internal-elb" = "1"
  }

}


# 1 Virtual Private Cloud (VPC) (named microservices-vpc)
# 2 Public Subnets (across 2 availability zones)
# 2 Private Subnets (across 2 availability zones)
# 1 NAT Gateway (since single_nat_gateway = true is set)
# The VPC module also automatically creates 1 
# Internet Gateway and necessary route tables behind the scenes.