#!/bin/bash
set -e

echo "======================================="
echo "Updating system packages..."
echo "======================================="
sudo apt update -y

echo "======================================="
echo "Installing prerequisites..."
echo "======================================="
sudo apt install -y curl wget unzip gnupg lsb-release

###########################################################
# Terraform
###########################################################
echo "======================================="
echo "Installing Terraform..."
echo "======================================="
wget -O- https://apt.releases.hashicorp.com/gpg | gpg --dearmor | sudo tee /usr/share/keyrings/hashicorp-archive-keyring.gpg >/dev/null
echo "deb [signed-by=/usr/share/keyrings/hashicorp-archive-keyring.gpg] https://apt.releases.hashicorp.com $(lsb_release -cs) main" | sudo tee /etc/apt/sources.list.d/hashicorp.list
sudo apt update
sudo apt install -y terraform

###########################################################
# AWS CLI v2
###########################################################
echo "======================================="
echo "Installing AWS CLI..."
echo "======================================="
cd /tmp
curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"
unzip -q awscliv2.zip
sudo ./aws/install --update
# Clean up temporary installation files to save disk space
rm -rf aws awscliv2.zip

###########################################################
# kubectl
###########################################################
echo "======================================="
echo "Installing kubectl..."
echo "======================================="
curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl"
chmod +x kubectl
sudo mv kubectl /usr/local/bin/

###########################################################
# Helm
###########################################################
echo "======================================="
echo "Installing Helm..."
echo "======================================="
curl https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash

###########################################################
# Versions
###########################################################
echo
echo "======================================="
echo "Installed Versions"
echo "======================================="
terraform version
aws --version
kubectl version --client
helm version

echo
echo "======================================="
echo "Bootstrapping Terraform S3 Backend..."
echo "======================================="
BUCKET_NAME="tanya-tfstate-2026"
REGION="ap-south-1"

if aws s3api head-bucket --bucket "$BUCKET_NAME" 2>/dev/null; then
  echo "Bucket $BUCKET_NAME already exists."
else
  echo "Creating bucket $BUCKET_NAME..."
  aws s3api create-bucket \
    --bucket "$BUCKET_NAME" \
    --region "$REGION" \
    --create-bucket-configuration LocationConstraint="$REGION"
  
  # Enable versioning (best practice for terraform state)
  aws s3api put-bucket-versioning \
    --bucket "$BUCKET_NAME" \
    --versioning-configuration Status=Enabled
  echo "Bucket $BUCKET_NAME created and versioning enabled!"
fi

echo
echo "======================================="
echo "Cloud Tools Installation Complete!"
echo "======================================="
