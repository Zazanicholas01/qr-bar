#!/usr/bin/env bash
set -euo pipefail
shopt -s expand_aliases

# Simple helper to redeploy after GitHub Actions builds finish on the "inventory" branch.
# Requirements: gh, jq, helm, kubectl all configured locally with access to the target cluster.
# When using MicroK8s we alias kubectl/helm to the bundled binaries for convenience.
alias kubectl="microk8s kubectl"
alias helm="microk8s helm3"

WORKFLOW_NAME="Build and Publish Docker Images"
BRANCH_NAME="${1:-inventory}"

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
helm upgrade --install qr-app charts/qr-app -n qr -f charts/qr-app/values.yaml \
  --set-string image.backend="ghcr.io/zazanicholas01/qr-backend:sha-${SHORT_SHA}" \
  --set-string image.frontend="ghcr.io/zazanicholas01/qr-frontend:sha-${SHORT_SHA}" \
  --set fullnameOverride=qr-app

echo "Restarting deployments..."
kubectl -n qr rollout restart deployment/qr-app-backend
kubectl -n qr rollout restart deployment/qr-app-frontend

echo "Done."
