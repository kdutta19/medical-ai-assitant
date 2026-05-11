#!/usr/bin/env bash
# =============================================================================
# build_and_push.sh — Build Docker images and push to AWS ECR
#
# Tags each image with:
#   <git-sha>  — immutable, used by deploy_ecs.sh for exact version tracking
#   latest     — convenience alias, always points to the most recent push
#
# Prerequisites:
#   aws-cli v2, docker, git
#   AWS credentials configured (aws configure)
#   ECR repos exist (run setup_infra.sh first)
#
# Usage:
#   bash infra/build_and_push.sh
#
#   # Override region or tag:
#   AWS_REGION=us-west-2 IMAGE_TAG=v1.2.3 bash infra/build_and_push.sh
#
# Outputs:
#   infra/.last_build  — image URIs written here for deploy_ecs.sh
# =============================================================================
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_INFRA="${REPO_ROOT}/infra/.env.infra"

# ── Load infra state (or fall back to env vars) ───────────────────────────────
if [[ -f "$ENV_INFRA" ]]; then
    # shellcheck disable=SC1090
    source "$ENV_INFRA"
else
    echo "WARN: infra/.env.infra not found — falling back to environment variables."
    echo "      Run infra/setup_infra.sh first for a fully managed setup."
fi

AWS_REGION="${AWS_REGION:-us-east-1}"
APP_NAME="${APP_NAME:-clinical-ai}"
AWS_ACCOUNT_ID="${AWS_ACCOUNT_ID:-$(aws sts get-caller-identity --query Account --output text)}"
ECR_REGISTRY="${ECR_REGISTRY:-${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com}"

BACKEND_REPO="${APP_NAME}-backend"
FRONTEND_REPO="${APP_NAME}-frontend"

# Use git SHA if available; fall back to timestamp
if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    IMAGE_TAG="${IMAGE_TAG:-$(git rev-parse --short HEAD)}"
else
    IMAGE_TAG="${IMAGE_TAG:-$(date +%Y%m%d%H%M%S)}"
fi

BACKEND_IMAGE="${ECR_REGISTRY}/${BACKEND_REPO}:${IMAGE_TAG}"
FRONTEND_IMAGE="${ECR_REGISTRY}/${FRONTEND_REPO}:${IMAGE_TAG}"

for cmd in aws docker; do
    command -v "$cmd" >/dev/null 2>&1 || { echo "ERROR: $cmd not found."; exit 1; }
done

log()  { echo "[$(date +%H:%M:%S)] $*"; }
ok()   { echo "[$(date +%H:%M:%S)] ✓ $*"; }

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
log "Building and pushing images"
log "  Tag      : $IMAGE_TAG"
log "  Registry : $ECR_REGISTRY"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# ── Authenticate with ECR ─────────────────────────────────────────────────────
log "Authenticating with ECR..."
aws ecr get-login-password --region "$AWS_REGION" \
    | docker login --username AWS --password-stdin "$ECR_REGISTRY"
ok "ECR login successful"

# ── Ensure ECR repos exist ────────────────────────────────────────────────────
for repo in "$BACKEND_REPO" "$FRONTEND_REPO"; do
    aws ecr describe-repositories --repository-names "$repo" \
        --region "$AWS_REGION" >/dev/null 2>&1 || {
        log "Creating ECR repo: $repo"
        aws ecr create-repository --repository-name "$repo" \
            --image-scanning-configuration scanOnPush=true \
            --region "$AWS_REGION" >/dev/null
        ok "Created ECR repo: $repo"
    }
done

# ── Build backend ─────────────────────────────────────────────────────────────
log "Building backend image..."
log "  (first build takes ~10 min — BGE model download baked in)"
docker build \
    --platform linux/amd64 \
    --file  "${REPO_ROOT}/backend/Dockerfile" \
    --tag   "${BACKEND_IMAGE}" \
    --tag   "${ECR_REGISTRY}/${BACKEND_REPO}:latest" \
    --cache-from "${ECR_REGISTRY}/${BACKEND_REPO}:latest" \
    --build-arg BUILDKIT_INLINE_CACHE=1 \
    "${REPO_ROOT}/backend"
ok "Backend image built: $BACKEND_IMAGE"

# ── Build frontend ────────────────────────────────────────────────────────────
log "Building frontend image..."
docker build \
    --platform linux/amd64 \
    --file  "${REPO_ROOT}/frontend/Dockerfile" \
    --tag   "${FRONTEND_IMAGE}" \
    --tag   "${ECR_REGISTRY}/${FRONTEND_REPO}:latest" \
    --cache-from "${ECR_REGISTRY}/${FRONTEND_REPO}:latest" \
    --build-arg BUILDKIT_INLINE_CACHE=1 \
    "${REPO_ROOT}/frontend"
ok "Frontend image built: $FRONTEND_IMAGE"

# ── Push images ───────────────────────────────────────────────────────────────
log "Pushing backend image..."
docker push "${BACKEND_IMAGE}"
docker push "${ECR_REGISTRY}/${BACKEND_REPO}:latest"
ok "Backend pushed"

log "Pushing frontend image..."
docker push "${FRONTEND_IMAGE}"
docker push "${ECR_REGISTRY}/${FRONTEND_REPO}:latest"
ok "Frontend pushed"

# ── Save image URIs for deploy_ecs.sh ─────────────────────────────────────────
cat > "${REPO_ROOT}/infra/.last_build" <<EOF
# Written by build_and_push.sh on $(date -u +"%Y-%m-%dT%H:%M:%SZ")
IMAGE_TAG=${IMAGE_TAG}
BACKEND_IMAGE=${BACKEND_IMAGE}
FRONTEND_IMAGE=${FRONTEND_IMAGE}
EOF

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
ok "Build and push complete"
echo ""
echo "  Backend  : $BACKEND_IMAGE"
echo "  Frontend : $FRONTEND_IMAGE"
echo ""
echo "  Next step: bash infra/deploy_ecs.sh"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"