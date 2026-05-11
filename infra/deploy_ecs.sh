#!/usr/bin/env bash
# =============================================================================
# deploy_ecs.sh — Register ECS task definitions and deploy to Fargate
#
# On every run this script:
#   1. Registers a new backend task definition revision (with current image)
#   2. Registers a new frontend task definition revision (with current image)
#   3. Creates ECS services if they don't exist, or updates them in-place
#   4. Waits for both services to reach steady state
#   5. Prints the live ALB URL
#
# The backend task's entrypoint syncs the FAISS index and ML model from S3
# before starting uvicorn, so artifact updates are picked up on each deploy.
#
# Prerequisites:
#   aws-cli v2, jq
#   setup_infra.sh must have been run (infra/.env.infra must exist)
#   build_and_push.sh must have been run (infra/.last_build must exist)
#
# Usage:
#   bash infra/deploy_ecs.sh
#
#   # Deploy a specific image tag instead of the last build:
#   IMAGE_TAG=abc1234 bash infra/deploy_ecs.sh
# =============================================================================
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_INFRA="${REPO_ROOT}/infra/.env.infra"
LAST_BUILD="${REPO_ROOT}/infra/.last_build"

for cmd in aws jq; do
    command -v "$cmd" >/dev/null 2>&1 || { echo "ERROR: $cmd not found."; exit 1; }
done

[[ -f "$ENV_INFRA" ]] || { echo "ERROR: infra/.env.infra not found. Run setup_infra.sh first."; exit 1; }

# shellcheck disable=SC1090
source "$ENV_INFRA"
[[ -f "$LAST_BUILD" ]] && source "$LAST_BUILD"

# Allow overriding the image tag at runtime
if [[ -n "${IMAGE_TAG:-}" ]]; then
    BACKEND_IMAGE="${ECR_REGISTRY}/${APP_NAME}-backend:${IMAGE_TAG}"
    FRONTEND_IMAGE="${ECR_REGISTRY}/${APP_NAME}-frontend:${IMAGE_TAG}"
fi

[[ -z "${BACKEND_IMAGE:-}"  ]] && { echo "ERROR: BACKEND_IMAGE not set. Run build_and_push.sh first."; exit 1; }
[[ -z "${FRONTEND_IMAGE:-}" ]] && { echo "ERROR: FRONTEND_IMAGE not set. Run build_and_push.sh first."; exit 1; }

log()  { echo "[$(date +%H:%M:%S)] $*"; }
ok()   { echo "[$(date +%H:%M:%S)] ✓ $*"; }

BACKEND_SERVICE="${APP_NAME}-backend-svc"
FRONTEND_SERVICE="${APP_NAME}-frontend-svc"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
log "Deploying to ECS Fargate"
log "  Cluster  : $CLUSTER_NAME"
log "  Backend  : $BACKEND_IMAGE"
log "  Frontend : $FRONTEND_IMAGE"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# ── Backend task definition ───────────────────────────────────────────────────
# The backend startup command:
#   1. Syncs FAISS index from S3 → /data/index/
#   2. Syncs ML classifier from S3 → /models/
#   3. Starts uvicorn
#
# Secrets injected as environment variables at container startup via
# AWS Secrets Manager (valueFrom). Never stored in task definition plaintext.
log "Registering backend task definition..."

BACKEND_TASK_DEF=$(cat <<EOF
{
  "family": "${APP_NAME}-backend",
  "networkMode": "awsvpc",
  "requiresCompatibilities": ["FARGATE"],
  "cpu": "1024",
  "memory": "2048",
  "executionRoleArn": "${EXEC_ROLE_ARN}",
  "taskRoleArn": "${TASK_ROLE_ARN}",
  "containerDefinitions": [
    {
      "name": "backend",
      "image": "${BACKEND_IMAGE}",
      "essential": true,
      "portMappings": [
        {"containerPort": 8000, "hostPort": 8000, "protocol": "tcp"}
      ],
      "command": [
        "/bin/sh", "-c",
        "mkdir -p /data/index /models && aws s3 sync s3://${S3_BUCKET}/index/ /data/index/ --region ${AWS_REGION} --quiet; aws s3 sync s3://${S3_BUCKET}/models/ /models/ --region ${AWS_REGION} --quiet; exec uvicorn app.main:app --host 0.0.0.0 --port 8000"
      ],
      "environment": [
        {"name": "ENVIRONMENT",   "value": "production"},
        {"name": "S3_BUCKET_NAME","value": "${S3_BUCKET}"},
        {"name": "AWS_REGION",    "value": "${AWS_REGION}"},
        {"name": "ALLOWED_ORIGINS",
         "value": "[\"http://${ALB_DNS}\",\"https://${ALB_DNS}\"]"}
      ],
      "secrets": [
        {
          "name": "ANTHROPIC_API_KEY",
          "valueFrom": "${ANTHROPIC_SECRET_ARN}"
        },
        {
          "name": "DATABASE_URL",
          "valueFrom": "${DB_URL_SECRET_ARN}"
        }
      ],
      "logConfiguration": {
        "logDriver": "awslogs",
        "options": {
          "awslogs-group":         "/ecs/${APP_NAME}/backend",
          "awslogs-region":        "${AWS_REGION}",
          "awslogs-stream-prefix": "backend"
        }
      },
      "healthCheck": {
        "command": ["CMD-SHELL", "curl -sf http://localhost:8000/api/health || exit 1"],
        "interval": 30,
        "timeout": 10,
        "retries": 3,
        "startPeriod": 90
      }
    }
  ]
}
EOF
)

BACKEND_TASK_ARN=$(aws ecs register-task-definition \
    --cli-input-json "$BACKEND_TASK_DEF" \
    --region "$AWS_REGION" \
    --query "taskDefinition.taskDefinitionArn" --output text)
ok "Backend task definition: $BACKEND_TASK_ARN"

# ── Frontend task definition ──────────────────────────────────────────────────
log "Registering frontend task definition..."

FRONTEND_TASK_DEF=$(cat <<EOF
{
  "family": "${APP_NAME}-frontend",
  "networkMode": "awsvpc",
  "requiresCompatibilities": ["FARGATE"],
  "cpu": "256",
  "memory": "512",
  "executionRoleArn": "${EXEC_ROLE_ARN}",
  "taskRoleArn": "${TASK_ROLE_ARN}",
  "containerDefinitions": [
    {
      "name": "frontend",
      "image": "${FRONTEND_IMAGE}",
      "essential": true,
      "portMappings": [
        {"containerPort": 80, "hostPort": 80, "protocol": "tcp"}
      ],
      "logConfiguration": {
        "logDriver": "awslogs",
        "options": {
          "awslogs-group":         "/ecs/${APP_NAME}/frontend",
          "awslogs-region":        "${AWS_REGION}",
          "awslogs-stream-prefix": "frontend"
        }
      },
      "healthCheck": {
        "command": ["CMD-SHELL", "wget -qO- http://localhost/ || exit 1"],
        "interval": 30,
        "timeout": 5,
        "retries": 3,
        "startPeriod": 15
      }
    }
  ]
}
EOF
)

FRONTEND_TASK_ARN=$(aws ecs register-task-definition \
    --cli-input-json "$FRONTEND_TASK_DEF" \
    --region "$AWS_REGION" \
    --query "taskDefinition.taskDefinitionArn" --output text)
ok "Frontend task definition: $FRONTEND_TASK_ARN"

# ── Helper: create or update an ECS service ───────────────────────────────────
deploy_service() {
    local svc_name="$1"
    local task_arn="$2"
    local tg_arn="$3"
    local subnets="$4"        # comma-separated subnet IDs
    local sg="$5"             # single security group ID
    local desired_count="${6:-1}"

    local svc_status
    svc_status=$(aws ecs describe-services \
        --cluster "$CLUSTER_NAME" --services "$svc_name" \
        --query "services[0].status" --output text --region "$AWS_REGION" 2>/dev/null || echo "")

    if [[ "$svc_status" == "ACTIVE" ]]; then
        log "Updating service: $svc_name"
        aws ecs update-service \
            --cluster "$CLUSTER_NAME" \
            --service "$svc_name" \
            --task-definition "$task_arn" \
            --desired-count "$desired_count" \
            --force-new-deployment \
            --deployment-configuration \
              "minimumHealthyPercent=100,maximumPercent=200" \
            --region "$AWS_REGION" >/dev/null
        ok "Service updated: $svc_name"
    else
        log "Creating service: $svc_name"
        # Convert comma-separated strings to space-separated for CLI
        local subnet_list
        subnet_list=$(echo "$subnets" | tr ',' ' ')
        aws ecs create-service \
            --cluster "$CLUSTER_NAME" \
            --service-name "$svc_name" \
            --task-definition "$task_arn" \
            --desired-count "$desired_count" \
            --launch-type FARGATE \
            --network-configuration \
              "awsvpcConfiguration={subnets=[${subnets}],securityGroups=[${sg}],assignPublicIp=DISABLED}" \
            --load-balancers \
              "targetGroupArn=${tg_arn},containerName=$(echo "$svc_name" | sed 's/.*-\([a-z]*\)-svc/\1/'),containerPort=$([ "$svc_name" = "${APP_NAME}-backend-svc" ] && echo 8000 || echo 80)" \
            --deployment-configuration \
              "minimumHealthyPercent=100,maximumPercent=200" \
            --health-check-grace-period-seconds 90 \
            --region "$AWS_REGION" >/dev/null
        ok "Service created: $svc_name"
    fi
}

# ── Deploy backend (private subnets) ─────────────────────────────────────────
deploy_service \
    "$BACKEND_SERVICE" \
    "$BACKEND_TASK_ARN" \
    "$TG_BACKEND_ARN" \
    "${PRV_SUBNET_1},${PRV_SUBNET_2}" \
    "$SG_BACKEND" \
    1

# ── Deploy frontend (private subnets, reached via ALB) ───────────────────────
deploy_service \
    "$FRONTEND_SERVICE" \
    "$FRONTEND_TASK_ARN" \
    "$TG_FRONTEND_ARN" \
    "${PRV_SUBNET_1},${PRV_SUBNET_2}" \
    "$SG_FRONTEND" \
    1

# ── Wait for steady state ─────────────────────────────────────────────────────
log "Waiting for backend service to stabilize (may take 2-3 min)..."
aws ecs wait services-stable \
    --cluster "$CLUSTER_NAME" \
    --services "$BACKEND_SERVICE" \
    --region "$AWS_REGION"
ok "Backend service stable"

log "Waiting for frontend service to stabilize..."
aws ecs wait services-stable \
    --cluster "$CLUSTER_NAME" \
    --services "$FRONTEND_SERVICE" \
    --region "$AWS_REGION"
ok "Frontend service stable"

# ── Verify health ─────────────────────────────────────────────────────────────
log "Verifying backend health via ALB..."
HTTP_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "http://${ALB_DNS}/api/health" || echo "000")
if [[ "$HTTP_STATUS" == "200" ]]; then
    ok "Health check passed (HTTP $HTTP_STATUS)"
else
    echo "  WARN: Health check returned HTTP $HTTP_STATUS — containers may still be warming up."
    echo "        Try: curl http://${ALB_DNS}/api/health"
fi

# ── Print deployment summary ──────────────────────────────────────────────────
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
ok "Deployment complete"
echo ""
echo "  App URL         : http://${ALB_DNS}"
echo "  Health check    : http://${ALB_DNS}/api/health"
echo "  Backend image   : ${BACKEND_IMAGE}"
echo "  Frontend image  : ${FRONTEND_IMAGE}"
echo ""
echo "  CloudWatch logs:"
echo "    Backend  : aws logs tail /ecs/${APP_NAME}/backend --follow --region ${AWS_REGION}"
echo "    Frontend : aws logs tail /ecs/${APP_NAME}/frontend --follow --region ${AWS_REGION}"
echo ""
echo "  ECS console:"
echo "    https://console.aws.amazon.com/ecs/home?region=${AWS_REGION}#/clusters/${CLUSTER_NAME}/services"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"