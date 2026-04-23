#!/bin/bash
# Provision core AWS infrastructure for Clinical AI Assistant
# Idempotent: safe to run multiple times
set -euo pipefail

AWS_REGION="${AWS_REGION:-us-east-1}"
CLUSTER_NAME="${CLUSTER_NAME:-clinical-ai-cluster}"
S3_BUCKET="${S3_BUCKET:-clinical-ai-documents}"
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)

echo "==> Setting up ECS cluster: $CLUSTER_NAME"
aws ecs describe-clusters --clusters "$CLUSTER_NAME" --region "$AWS_REGION" \
  | grep -q "ACTIVE" \
  || aws ecs create-cluster --cluster-name "$CLUSTER_NAME" --region "$AWS_REGION"

echo "==> Setting up S3 bucket: $S3_BUCKET"
aws s3api head-bucket --bucket "$S3_BUCKET" 2>/dev/null \
  || aws s3api create-bucket \
      --bucket "$S3_BUCKET" \
      --region "$AWS_REGION" \
      --create-bucket-configuration LocationConstraint="$AWS_REGION"

# Block all public access
aws s3api put-public-access-block \
  --bucket "$S3_BUCKET" \
  --public-access-block-configuration \
    "BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true"

echo "==> Creating CloudWatch log group..."
aws logs create-log-group \
  --log-group-name "/ecs/clinical-ai" \
  --region "$AWS_REGION" 2>/dev/null || true

echo "==> Infrastructure setup complete."
echo "    Account:  $AWS_ACCOUNT_ID"
echo "    Region:   $AWS_REGION"
echo "    Cluster:  $CLUSTER_NAME"
echo "    S3:       s3://$S3_BUCKET"
