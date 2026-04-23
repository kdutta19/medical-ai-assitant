#!/bin/bash
# Build Docker images and push to AWS ECR
set -euo pipefail

AWS_REGION="${AWS_REGION:-us-east-1}"
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
ECR_REGISTRY="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"
BACKEND_REPO="clinical-ai-backend"
FRONTEND_REPO="clinical-ai-frontend"
IMAGE_TAG="${IMAGE_TAG:-latest}"

echo "==> Authenticating with ECR..."
aws ecr get-login-password --region "$AWS_REGION" \
  | docker login --username AWS --password-stdin "$ECR_REGISTRY"

echo "==> Creating ECR repos if they don't exist..."
aws ecr describe-repositories --repository-names "$BACKEND_REPO" --region "$AWS_REGION" 2>/dev/null \
  || aws ecr create-repository --repository-name "$BACKEND_REPO" --region "$AWS_REGION"

aws ecr describe-repositories --repository-names "$FRONTEND_REPO" --region "$AWS_REGION" 2>/dev/null \
  || aws ecr create-repository --repository-name "$FRONTEND_REPO" --region "$AWS_REGION"

echo "==> Building backend image..."
docker build -t "${ECR_REGISTRY}/${BACKEND_REPO}:${IMAGE_TAG}" ./backend

echo "==> Building frontend image..."
docker build -t "${ECR_REGISTRY}/${FRONTEND_REPO}:${IMAGE_TAG}" ./frontend

echo "==> Pushing images..."
docker push "${ECR_REGISTRY}/${BACKEND_REPO}:${IMAGE_TAG}"
docker push "${ECR_REGISTRY}/${FRONTEND_REPO}:${IMAGE_TAG}"

echo "==> Done. Images pushed:"
echo "    ${ECR_REGISTRY}/${BACKEND_REPO}:${IMAGE_TAG}"
echo "    ${ECR_REGISTRY}/${FRONTEND_REPO}:${IMAGE_TAG}"
