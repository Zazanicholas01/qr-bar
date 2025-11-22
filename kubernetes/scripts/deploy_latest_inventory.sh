#!/usr/bin/env bash
set -euo pipefail
shopt -s expand_aliases

# Simple helper to redeploy after GitHub Actions builds finish on the "machine-learning" branch.
# Requirements: gh, jq, helm, kubectl all configured locally with access to the target cluster.
# If using MicroK8s, ensure /snap/bin is in PATH; we alias to microk8s binaries when available.
if command -v microk8s >/dev/null 2>&1; then
  alias kubectl="microk8s kubectl"
  alias helm="microk8s helm3"
elif [ -x /snap/bin/microk8s ]; then
  alias kubectl="/snap/bin/microk8s kubectl"
  alias helm="/snap/bin/microk8s helm3"
else
  alias kubectl="kubectl"
  alias helm="helm"
fi

WORKFLOW_NAME="Build and Publish Docker Images"
BRANCH_NAME="${1:-machine-learning}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

echo "Resolving latest short SHA from workflow \"${WORKFLOW_NAME}\" on branch \"${BRANCH_NAME}\"..."
SHORT_SHA=$(
  gh run list \
    -w "${WORKFLOW_NAME}" \
    -b "${BRANCH_NAME}" \
    -L 1 \
    --json headSha \
    --jq '.[0].headSha[0:7]'
)

if [[ -z "${SHORT_SHA}" || "${SHORT_SHA}" == "null" ]]; then
  echo "Unable to determine short SHA; ensure the workflow has completed successfully." >&2
  exit 1
fi

echo "Using short SHA: ${SHORT_SHA}"

echo "Running helm upgrade with matching backend/frontend images..."
helm upgrade --install qr-app "${REPO_ROOT}/kubernetes/helm_charts/qr-app" -n qr -f "${REPO_ROOT}/kubernetes/helm_charts/qr-app/values.yaml" \
  --set-string image.backend="ghcr.io/zazanicholas01/qr-backend:sha-${SHORT_SHA}" \
  --set-string image.frontend="ghcr.io/zazanicholas01/qr-frontend:sha-${SHORT_SHA}" \
  --set fullnameOverride=qr-app

echo "Restarting deployments..."
kubectl -n qr rollout restart deployment/qr-app-backend
kubectl -n qr rollout restart deployment/qr-app-frontend

echo "Done."

echo "Waiting for Ready Status..."
kubectl -n qr rollout status deployment/qr-app-backend
kubectl -n qr rollout status deployment/qr-app-frontend

echo "Done."
