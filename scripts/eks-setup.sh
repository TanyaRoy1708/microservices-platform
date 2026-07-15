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

# Verify the controller is running
kubectl get pods -n kube-system | grep aws-load-balancer
