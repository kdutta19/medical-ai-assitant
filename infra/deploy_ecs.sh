#!/bin/bash
# Deploy updated task definitions to ECS Fargate
set -euo pipefail

AWS_REGION="${AWS_REGION:-us-east-1}"
CLUSTER_NAME="${CLUSTER_NAME:-clinical-ai-cluster}"
BACKEND_SERVICE="${BACKEND_SERVICE:-clinical-ai-backend-service}"
FRONTEND_SERVICE="${FRONTEND_SERVICE:-clinical-ai-frontend-service}"

echo "==> Forcing new deployment for backend..."
aws ecs update-service \
  --cluster "$CLUSTER_NAME" \
  --service "$BACKEND_SERVICE" \
  --force-new-deployment \
  --region "$AWS_REGION"

echo "==> Forcing new deployment for frontend..."
aws ecs update-service \
  --cluster "$CLUSTER_NAME" \
  --service "$FRONTEND_SERVICE" \
  --force-new-deployment \
  --region "$AWS_REGION"

echo "==> Waiting for backend service to stabilize..."
aws ecs wait services-stable \
  --cluster "$CLUSTER_NAME" \
  --services "$BACKEND_SERVICE" \
  --region "$AWS_REGION"

echo "==> Deployment complete."
