#!/bin/bash

# =====================================================================
# EKS Cluster Setup & AWS Load Balancer Controller Installation
# =====================================================================

# Update the local kubeconfig file so kubectl can communicate with the new EKS cluster.
# It fetches the authentication token and cluster endpoint for 'ai-microservices-platform' in ap-south-1.
aws eks update-kubeconfig \
  --name ai-microservices-platform \
  --region ap-south-1

# Verify that the cluster is reachable and list all connected worker nodes.
kubectl get nodes

# =====================================================================
# Install AWS Load Balancer Controller
# =====================================================================
# The ALB Controller automatically provisions AWS Application Load Balancers
# when you create Kubernetes 'Ingress' resources.

# Add the official Amazon EKS Helm chart repository to your local Helm client.
helm repo add eks https://aws.github.io/eks-charts

# Fetch the latest list of charts from all configured repositories (including the 'eks' one we just added).
helm repo update

# Install the AWS Load Balancer Controller into the cluster using Helm.
# -n kube-system: Installs it into the protected 'kube-system' namespace (best practice).
# --set clusterName: Tells the controller which EKS cluster it is managing.
# --set serviceAccount.create=true: Automatically creates a Kubernetes ServiceAccount for it to use.
helm install aws-load-balancer-controller eks/aws-load-balancer-controller \
  -n kube-system \
  --set clusterName=ai-microservices-platform \
  --set serviceAccount.create=true

# Pause script execution and wait until the ALB controller pods are fully running and healthy.
kubectl rollout status deployment aws-load-balancer-controller -n kube-system

# =====================================================================
# IAM Policy Instructions
# =====================================================================
# The ALB Controller needs AWS IAM permissions to actually create/delete Load Balancers in your AWS account.
# These lines print out manual instructions for the user to attach the required IAM policy to the EC2 worker nodes.

echo "Attaching ALB permissions to your EKS worker node IAM role automatically..."

# Extract the exact role name dynamically
CLUSTER_NAME="ai-microservices-platform"
NODEGROUP_NAME=$(aws eks list-nodegroups --cluster-name $CLUSTER_NAME --query "nodegroups[0]" --output text)
NODE_ROLE_ARN=$(aws eks describe-nodegroup --cluster-name $CLUSTER_NAME --nodegroup-name $NODEGROUP_NAME --query "nodegroup.nodeRole" --output text)
NODE_ROLE_NAME=$(basename $NODE_ROLE_ARN)

# Download the valid policy from the main branch (v3.4.2 does not exist on GitHub releases)
curl -s -O https://raw.githubusercontent.com/kubernetes-sigs/aws-load-balancer-controller/main/docs/install/iam_policy.json

# Attach the policy automatically
aws iam put-role-policy \
    --role-name $NODE_ROLE_NAME \
    --policy-name AWSLoadBalancerControllerIAMPolicy \
    --policy-document file://iam_policy.json

echo "Successfully attached ALB policy to $NODE_ROLE_NAME!"

# Run a final check to list the pods and grep for the load balancer to visually prove it is running.
kubectl get pods -n kube-system | grep aws-load-balancer
