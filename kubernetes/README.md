# Kubernetes Layout

- `helm_charts/qr-app`: Helm chart for the application. Use `values.yaml` as the base and layer env overrides (e.g., `values.dev.yaml`, `values.prod.yaml`).
- `manifests`: Plain Kubernetes YAMLs (namespaces, PDBs, extras) applied alongside Helm.
- `monitoring`: Grafana/Prometheus manifests for the monitoring namespace.
- `certificates`: Certificate resources (self-signed + service certs).

## Typical Apply Flow

```bash
# Create namespaces (qr for app; monitoring already has its own manifest)
kubectl apply -f kubernetes/manifests/namespace-qr.yaml

# Certificates (qr namespace)
kubectl -n qr apply -f kubernetes/certificates/cert-selfsigned.yaml
kubectl -n qr apply -f kubernetes/certificates/app-cert.yaml

# Monitoring stack (monitoring namespace)
kubectl apply -f kubernetes/monitoring

# App hardening bits (PDBs, etc.)
kubectl apply -f kubernetes/manifests/poddisruptionbudgets.yaml

# Deploy app with Helm (choose values)
helm upgrade --install qr-app kubernetes/helm_charts/qr-app -n qr \
  -f kubernetes/helm_charts/qr-app/values.yaml \
  -f kubernetes/helm_charts/qr-app/values.dev.yaml \
  --set fullnameOverride=qr-app
```

## Notes

- Swap in `values.prod.yaml` (or your own overlay) for production and adjust ingress hosts/TLS secrets accordingly.
- Keep `fullnameOverride=qr-app` aligned with PDB selectors; if you change it, update selectors in `manifests/poddisruptionbudgets.yaml`.
- Prefer running `helm lint` and `helm template ... | kubeconform` in CI to catch schema issues early.
