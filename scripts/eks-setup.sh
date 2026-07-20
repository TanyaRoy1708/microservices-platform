# Connect kubectl to your new cluster
aws eks update-kubeconfig \
  --name ai-microservices-platform \
  --region ap-south-1

# Verify connection
kubectl get nodes

# Install AWS Load Balancer Controller (manages ALB for Ingress resources)
helm repo add eks https://aws.github.io/eks-charts
helm repo update

helm install aws-load-balancer-controller eks/aws-load-balancer-controller \
  -n kube-system \
  --set clusterName=ai-microservices-platform \
  --set serviceAccount.create=true

# Wait for controller pods to be ready
kubectl rollout status deployment aws-load-balancer-controller -n kube-system

# Download and attach the official ALB IAM policy (v3.4.2)
# (Replace <YOUR_EKS_NODE_ROLE_NAME> with your actual worker node role name, e.g. spot_workers-eks-node-group-xxx)
echo "IMPORTANT: You must attach the official ALB permissions to your EKS worker node IAM role!"
echo "Run the following commands to download the v3.4.2 policy and attach it:"
echo ""
echo "curl -O https://raw.githubusercontent.com/kubernetes-sigs/aws-load-balancer-controller/v3.4.2/docs/install/iam_policy.json"
echo ""
echo "aws iam put-role-policy \\"
echo "    --role-name <YOUR_EKS_NODE_ROLE_NAME> \\"
echo "    --policy-name AWSLoadBalancerControllerIAMPolicy \\"
echo "    --policy-document file://iam_policy.json"
echo ""

# Verify the controller is running
kubectl get pods -n kube-system | grep aws-load-balancer
