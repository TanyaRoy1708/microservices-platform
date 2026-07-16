# K8sGPT Operator Setup

Run after the first successful Helm deploy. Installs K8sGPT into the cluster so it
continuously scans for problems and posts AI-explained findings to Slack every 5 minutes.

**Prereqs:** `kubectl` pointing at the EKS cluster (run `eks-setup.sh` first), Helm 3.

Replace `<OLLAMA_EC2_IP>` and `<SLACK_WEBHOOK_URL>` throughout.

---

## 1. Add the K8sGPT Helm repo

```bash
helm repo add k8sgpt https://charts.k8sgpt.ai/
helm repo update
```

> Registers the K8sGPT chart repository locally so Helm can find the operator package.

---

## 2. Install the K8sGPT operator

```bash
helm upgrade --install k8sgpt-operator k8sgpt/k8sgpt-operator \
  --namespace k8sgpt-operator-system \
  --create-namespace \
  --wait
```

> `upgrade --install` is idempotent — safe to re-run if the operator is already there.
> `--wait` blocks until the controller pod is running before returning.

Verify it is running:

```bash
kubectl get pods -n k8sgpt-operator-system
```

---

## 3. Apply the K8sGPT custom resource

This tells the operator what to scan, how often, and where to send alerts.

```bash
kubectl apply -f k8sgpt-config.yaml
```

> `k8sgpt-config.yaml` in the repo root contains placeholder values.
> Before applying, edit it and set the real `baseUrl` and Slack `webhook`, or
> apply inline with the values substituted:

```bash
kubectl apply -f - << 'EOF'
apiVersion: core.k8sgpt.ai/v1alpha1
kind: K8sGPT
metadata:
  name: k8sgpt-ollama
  namespace: k8sgpt-operator-system
spec:
  ai:
    enabled: true
    model: llama3.2:1b
    backend: localai
    baseUrl: http://<OLLAMA_EC2_IP>:11434/v1   # Ollama on EC2, not inside the cluster
  noCache: false
  filters: [Pod, Deployment, ReplicaSet, Service, Ingress, HorizontalPodAutoscaler]
  sink:
    type: slack
    webhook: <SLACK_WEBHOOK_URL>
  schedule: "*/5 * * * *"                      # scan every 5 minutes
EOF
```

---

## 4. Verify and monitor results

```bash
# Watch scan results appear in real time
kubectl get results -n k8sgpt-operator-system -w

# Read the full AI explanation for a result
kubectl describe result <result-name> -n k8sgpt-operator-system

# Check operator logs if something looks wrong
kubectl logs -l control-plane=controller-manager -n k8sgpt-operator-system --tail=50
```

> Results are stored as Kubernetes CRDs and simultaneously sent to Slack.

---

## 5. Trigger a one-off manual scan (optional)

Useful for testing before the 5-minute schedule fires.

```bash
k8sgpt analyze \
  --backend localai \
  --base-url http://<OLLAMA_EC2_IP>:11434/v1 \
  --model llama3.2:1b \
  --namespace production
```

> Requires the K8sGPT CLI installed locally. The pipeline installs it automatically
> during the CD job — see `.github/workflows/deploy.yaml`.

---

## Stop scanning (if needed)

```bash
kubectl delete k8sgpt k8sgpt-ollama -n k8sgpt-operator-system
```

> Deletes the custom resource only. The operator stays installed.
> Re-apply step 3 to resume scanning.
