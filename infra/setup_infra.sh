#!/usr/bin/env bash
# =============================================================================
# setup_infra.sh — Provision all AWS infrastructure for Clinical AI Assistant
#
# What this script creates (all idempotent — safe to run multiple times):
#   VPC + 2 public + 2 private subnets across 2 AZs
#   Internet Gateway, NAT Gateway, route tables
#   Security groups (ALB, backend, frontend, RDS)
#   CloudWatch log groups
#   IAM execution role + task role + inline policies
#   AWS Secrets Manager secrets (Anthropic API key, DB password)
#   RDS PostgreSQL (db.t3.micro, private subnet)
#   S3 bucket (document storage + data/models sync)
#   ECR repositories (backend + frontend)
#   ECS Fargate cluster
#   Application Load Balancer + target groups + listener rules
#   ECS task definitions + services
#
# Prerequisites:
#   aws-cli v2        brew install awscli  /  https://aws.amazon.com/cli/
#   jq                brew install jq      /  apt-get install jq
#   docker            running and logged in
#   AWS credentials   aws configure
#
# Required env var:
#   ANTHROPIC_API_KEY — your Anthropic API key
#
# Usage:
#   export ANTHROPIC_API_KEY=sk-ant-api03-...
#   export AWS_REGION=us-east-1            # optional, default us-east-1
#   export APP_NAME=clinical-ai            # optional, default clinical-ai
#   bash infra/setup_infra.sh
#
# Outputs:
#   infra/.env.infra  — saved ARNs/IDs for use by deploy_ecs.sh
# =============================================================================
set -euo pipefail

# ── Configuration ─────────────────────────────────────────────────────────────
AWS_REGION="${AWS_REGION:-us-east-1}"
APP_NAME="${APP_NAME:-clinical-ai}"
DB_NAME="${DB_NAME:-clinicalai}"
DB_USER="${DB_USER:-clinicalai}"
AZ1="${AWS_REGION}a"
AZ2="${AWS_REGION}b"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# ── Guards ────────────────────────────────────────────────────────────────────
for cmd in aws jq docker openssl; do
    command -v "$cmd" >/dev/null 2>&1 || { echo "ERROR: $cmd is required but not found."; exit 1; }
done

[[ -z "${ANTHROPIC_API_KEY:-}" ]] && {
    echo "ERROR: ANTHROPIC_API_KEY environment variable is not set."
    echo "  export ANTHROPIC_API_KEY=sk-ant-api03-..."
    exit 1
}

AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text --region "$AWS_REGION")
ECR_REGISTRY="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"

log()  { echo "[$(date +%H:%M:%S)] $*"; }
ok()   { echo "[$(date +%H:%M:%S)] ✓ $*"; }
skip() { echo "[$(date +%H:%M:%S)] - $* (already exists)"; }

# Helper: return first non-None value from aws cli output
aws_id() { local v="$1"; [[ "$v" == "None" || -z "$v" ]] && echo "" || echo "$v"; }

log "Account: $AWS_ACCOUNT_ID | Region: $AWS_REGION | App: $APP_NAME"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# ── VPC ───────────────────────────────────────────────────────────────────────
log "VPC..."
VPC_ID=$(aws_id "$(aws ec2 describe-vpcs \
    --filters "Name=tag:Name,Values=${APP_NAME}-vpc" \
    --query "Vpcs[0].VpcId" --output text --region "$AWS_REGION")")

if [[ -z "$VPC_ID" ]]; then
    VPC_ID=$(aws ec2 create-vpc --cidr-block "10.0.0.0/16" --region "$AWS_REGION" \
        --query "Vpc.VpcId" --output text)
    aws ec2 create-tags --resources "$VPC_ID" \
        --tags "Key=Name,Value=${APP_NAME}-vpc" "Key=App,Value=${APP_NAME}" --region "$AWS_REGION"
    aws ec2 modify-vpc-attribute --vpc-id "$VPC_ID" --enable-dns-hostnames --region "$AWS_REGION"
    aws ec2 modify-vpc-attribute --vpc-id "$VPC_ID" --enable-dns-support  --region "$AWS_REGION"
    ok "Created VPC: $VPC_ID"
else
    skip "VPC: $VPC_ID"
fi

# ── Internet Gateway ──────────────────────────────────────────────────────────
log "Internet Gateway..."
IGW_ID=$(aws_id "$(aws ec2 describe-internet-gateways \
    --filters "Name=tag:Name,Values=${APP_NAME}-igw" \
    --query "InternetGateways[0].InternetGatewayId" --output text --region "$AWS_REGION")")

if [[ -z "$IGW_ID" ]]; then
    IGW_ID=$(aws ec2 create-internet-gateway --region "$AWS_REGION" \
        --query "InternetGateway.InternetGatewayId" --output text)
    aws ec2 create-tags --resources "$IGW_ID" \
        --tags "Key=Name,Value=${APP_NAME}-igw" --region "$AWS_REGION"
    aws ec2 attach-internet-gateway \
        --internet-gateway-id "$IGW_ID" --vpc-id "$VPC_ID" --region "$AWS_REGION"
    ok "Created IGW: $IGW_ID"
else
    skip "IGW: $IGW_ID"
fi

# ── Subnets ───────────────────────────────────────────────────────────────────
make_subnet() {
    local name="$1" cidr="$2" az="$3"
    local id
    id=$(aws_id "$(aws ec2 describe-subnets \
        --filters "Name=tag:Name,Values=$name" "Name=vpc-id,Values=$VPC_ID" \
        --query "Subnets[0].SubnetId" --output text --region "$AWS_REGION")")
    if [[ -z "$id" ]]; then
        id=$(aws ec2 create-subnet \
            --vpc-id "$VPC_ID" --cidr-block "$cidr" --availability-zone "$az" \
            --region "$AWS_REGION" --query "Subnet.SubnetId" --output text)
        aws ec2 create-tags --resources "$id" \
            --tags "Key=Name,Value=$name" --region "$AWS_REGION"
        ok "Created subnet $name: $id"
    else
        skip "Subnet $name: $id"
    fi
    echo "$id"
}

log "Subnets..."
PUB_SUBNET_1=$(make_subnet "${APP_NAME}-pub-1" "10.0.1.0/24" "$AZ1")
PUB_SUBNET_2=$(make_subnet "${APP_NAME}-pub-2" "10.0.2.0/24" "$AZ2")
PRV_SUBNET_1=$(make_subnet "${APP_NAME}-prv-1" "10.0.3.0/24" "$AZ1")
PRV_SUBNET_2=$(make_subnet "${APP_NAME}-prv-2" "10.0.4.0/24" "$AZ2")

aws ec2 modify-subnet-attribute --subnet-id "$PUB_SUBNET_1" --map-public-ip-on-launch \
    --region "$AWS_REGION" 2>/dev/null || true
aws ec2 modify-subnet-attribute --subnet-id "$PUB_SUBNET_2" --map-public-ip-on-launch \
    --region "$AWS_REGION" 2>/dev/null || true

# ── NAT Gateway ───────────────────────────────────────────────────────────────
log "NAT Gateway (Fargate in private subnet needs outbound internet for ECR pull)..."
NAT_ID=$(aws_id "$(aws ec2 describe-nat-gateways \
    --filter "Name=tag:Name,Values=${APP_NAME}-nat" "Name=state,Values=available,pending" \
    --query "NatGateways[0].NatGatewayId" --output text --region "$AWS_REGION")")

if [[ -z "$NAT_ID" ]]; then
    EIP_ALLOC=$(aws ec2 allocate-address --domain vpc \
        --region "$AWS_REGION" --query "AllocationId" --output text)
    NAT_ID=$(aws ec2 create-nat-gateway \
        --subnet-id "$PUB_SUBNET_1" --allocation-id "$EIP_ALLOC" \
        --region "$AWS_REGION" --query "NatGateway.NatGatewayId" --output text)
    aws ec2 create-tags --resources "$NAT_ID" \
        --tags "Key=Name,Value=${APP_NAME}-nat" --region "$AWS_REGION"
    log "  Waiting for NAT Gateway (~90 s)..."
    aws ec2 wait nat-gateway-available --nat-gateway-ids "$NAT_ID" --region "$AWS_REGION"
    ok "Created NAT Gateway: $NAT_ID"
else
    skip "NAT Gateway: $NAT_ID"
fi

# ── Route Tables ──────────────────────────────────────────────────────────────
log "Route tables..."
setup_rtb() {
    local name="$1" target_type="$2" target_id="$3"; shift 3
    local subnet_ids=("$@")
    local rtb_id
    rtb_id=$(aws_id "$(aws ec2 describe-route-tables \
        --filters "Name=tag:Name,Values=$name" "Name=vpc-id,Values=$VPC_ID" \
        --query "RouteTables[0].RouteTableId" --output text --region "$AWS_REGION")")
    if [[ -z "$rtb_id" ]]; then
        rtb_id=$(aws ec2 create-route-table --vpc-id "$VPC_ID" \
            --region "$AWS_REGION" --query "RouteTable.RouteTableId" --output text)
        aws ec2 create-tags --resources "$rtb_id" \
            --tags "Key=Name,Value=$name" --region "$AWS_REGION"
        if [[ "$target_type" == "igw" ]]; then
            aws ec2 create-route --route-table-id "$rtb_id" \
                --destination-cidr-block "0.0.0.0/0" --gateway-id "$target_id" \
                --region "$AWS_REGION" >/dev/null
        else
            aws ec2 create-route --route-table-id "$rtb_id" \
                --destination-cidr-block "0.0.0.0/0" --nat-gateway-id "$target_id" \
                --region "$AWS_REGION" >/dev/null
        fi
        for sn in "${subnet_ids[@]}"; do
            aws ec2 associate-route-table --route-table-id "$rtb_id" \
                --subnet-id "$sn" --region "$AWS_REGION" >/dev/null
        done
        ok "Created route table $name: $rtb_id"
    else
        skip "Route table $name: $rtb_id"
    fi
}

setup_rtb "${APP_NAME}-pub-rt" igw "$IGW_ID" "$PUB_SUBNET_1" "$PUB_SUBNET_2"
setup_rtb "${APP_NAME}-prv-rt" nat "$NAT_ID" "$PRV_SUBNET_1" "$PRV_SUBNET_2"

# ── Security Groups ───────────────────────────────────────────────────────────
log "Security groups..."
make_sg() {
    local name="$1" desc="$2"
    local sg_id
    sg_id=$(aws_id "$(aws ec2 describe-security-groups \
        --filters "Name=tag:Name,Values=$name" "Name=vpc-id,Values=$VPC_ID" \
        --query "SecurityGroups[0].GroupId" --output text --region "$AWS_REGION")")
    if [[ -z "$sg_id" ]]; then
        sg_id=$(aws ec2 create-security-group \
            --group-name "$name" --description "$desc" --vpc-id "$VPC_ID" \
            --region "$AWS_REGION" --query "GroupId" --output text)
        aws ec2 create-tags --resources "$sg_id" \
            --tags "Key=Name,Value=$name" --region "$AWS_REGION"
        ok "Created SG $name: $sg_id"
    else
        skip "SG $name: $sg_id"
    fi
    echo "$sg_id"
}

SG_ALB=$(make_sg "${APP_NAME}-alb-sg"     "ALB: HTTP/HTTPS from internet")
SG_BACKEND=$(make_sg "${APP_NAME}-backend-sg"  "Backend: port 8000 from ALB only")
SG_FRONTEND=$(make_sg "${APP_NAME}-frontend-sg" "Frontend: port 80 from ALB only")
SG_RDS=$(make_sg "${APP_NAME}-rds-sg"     "RDS: port 5432 from backend only")

add_ingress() {
    local sg="$1" proto="$2" port="$3" src="$4"
    aws ec2 authorize-security-group-ingress \
        --group-id "$sg" --protocol "$proto" --port "$port" --source-group "$src" \
        --region "$AWS_REGION" 2>/dev/null || true
}
add_cidr_ingress() {
    local sg="$1" proto="$2" port="$3" cidr="$4"
    aws ec2 authorize-security-group-ingress \
        --group-id "$sg" --protocol "$proto" --port "$port" --cidr "$cidr" \
        --region "$AWS_REGION" 2>/dev/null || true
}

# ALB: accept HTTP + HTTPS from anywhere
add_cidr_ingress "$SG_ALB" tcp 80  "0.0.0.0/0"
add_cidr_ingress "$SG_ALB" tcp 443 "0.0.0.0/0"
# Backend: accept 8000 from ALB only
add_ingress "$SG_BACKEND"  tcp 8000 "$SG_ALB"
# Frontend: accept 80 from ALB only
add_ingress "$SG_FRONTEND" tcp 80   "$SG_ALB"
# RDS: accept 5432 from backend only
add_ingress "$SG_RDS"      tcp 5432 "$SG_BACKEND"

ok "Security group rules applied"

# ── CloudWatch Log Groups ─────────────────────────────────────────────────────
log "CloudWatch log groups..."
for lg in "/ecs/${APP_NAME}/backend" "/ecs/${APP_NAME}/frontend"; do
    aws logs create-log-group --log-group-name "$lg" \
        --region "$AWS_REGION" 2>/dev/null && ok "Created log group $lg" || skip "$lg"
    aws logs put-retention-policy --log-group-name "$lg" \
        --retention-in-days 30 --region "$AWS_REGION" 2>/dev/null || true
done

# ── IAM Roles ─────────────────────────────────────────────────────────────────
log "IAM roles..."

ECS_TRUST_POLICY='{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Principal": {"Service": "ecs-tasks.amazonaws.com"},
    "Action": "sts:AssumeRole"
  }]
}'

# Execution role (used by ECS control plane to pull images + push logs)
EXEC_ROLE_NAME="${APP_NAME}-ecs-execution-role"
EXEC_ROLE_ARN=$(aws_id "$(aws iam get-role --role-name "$EXEC_ROLE_NAME" \
    --query "Role.Arn" --output text 2>/dev/null || echo "")")
if [[ -z "$EXEC_ROLE_ARN" ]]; then
    EXEC_ROLE_ARN=$(aws iam create-role \
        --role-name "$EXEC_ROLE_NAME" \
        --assume-role-policy-document "$ECS_TRUST_POLICY" \
        --query "Role.Arn" --output text)
    aws iam attach-role-policy \
        --role-name "$EXEC_ROLE_NAME" \
        --policy-arn "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
    ok "Created execution role: $EXEC_ROLE_ARN"
else
    skip "Execution role: $EXEC_ROLE_ARN"
fi

# Add Secrets Manager read access to execution role (needed to inject secrets into containers)
EXEC_SECRETS_POLICY='{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Action": ["secretsmanager:GetSecretValue"],
    "Resource": "*"
  }]
}'
aws iam put-role-policy \
    --role-name "$EXEC_ROLE_NAME" \
    --policy-name "SecretsManagerRead" \
    --policy-document "$EXEC_SECRETS_POLICY" 2>/dev/null || true

# Task role (used by the running container for AWS API calls: S3, CloudWatch)
TASK_ROLE_NAME="${APP_NAME}-ecs-task-role"
TASK_ROLE_ARN=$(aws_id "$(aws iam get-role --role-name "$TASK_ROLE_NAME" \
    --query "Role.Arn" --output text 2>/dev/null || echo "")")
if [[ -z "$TASK_ROLE_ARN" ]]; then
    TASK_ROLE_ARN=$(aws iam create-role \
        --role-name "$TASK_ROLE_NAME" \
        --assume-role-policy-document "$ECS_TRUST_POLICY" \
        --query "Role.Arn" --output text)
    ok "Created task role: $TASK_ROLE_ARN"
else
    skip "Task role: $TASK_ROLE_ARN"
fi

S3_BUCKET="${APP_NAME}-documents-${AWS_ACCOUNT_ID}"
TASK_POLICY=$(cat <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["s3:GetObject", "s3:PutObject", "s3:DeleteObject", "s3:ListBucket"],
      "Resource": [
        "arn:aws:s3:::${S3_BUCKET}",
        "arn:aws:s3:::${S3_BUCKET}/*"
      ]
    },
    {
      "Effect": "Allow",
      "Action": ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"],
      "Resource": "arn:aws:logs:${AWS_REGION}:${AWS_ACCOUNT_ID}:log-group:/ecs/${APP_NAME}/*"
    },
    {
      "Effect": "Allow",
      "Action": ["secretsmanager:GetSecretValue"],
      "Resource": "arn:aws:secretsmanager:${AWS_REGION}:${AWS_ACCOUNT_ID}:secret:${APP_NAME}/*"
    }
  ]
}
EOF
)
aws iam put-role-policy \
    --role-name "$TASK_ROLE_NAME" \
    --policy-name "${APP_NAME}-task-policy" \
    --policy-document "$TASK_POLICY"
ok "Task role policy attached"

# ── AWS Secrets Manager ───────────────────────────────────────────────────────
log "Secrets Manager..."

store_secret() {
    local name="$1" value="$2"
    local arn
    arn=$(aws_id "$(aws secretsmanager describe-secret --secret-id "$name" \
        --query "ARN" --output text --region "$AWS_REGION" 2>/dev/null || echo "")")
    if [[ -z "$arn" ]]; then
        arn=$(aws secretsmanager create-secret \
            --name "$name" --secret-string "$value" \
            --region "$AWS_REGION" --query "ARN" --output text)
        ok "Created secret $name"
    else
        aws secretsmanager put-secret-value --secret-id "$name" \
            --secret-string "$value" --region "$AWS_REGION" >/dev/null
        skip "Updated secret $name"
    fi
    echo "$arn"
}

DB_PASSWORD=$(openssl rand -hex 20)
ANTHROPIC_SECRET_ARN=$(store_secret "${APP_NAME}/anthropic-api-key" "$ANTHROPIC_API_KEY")
DB_SECRET_ARN=$(store_secret "${APP_NAME}/db-password" "$DB_PASSWORD")

# ── RDS ───────────────────────────────────────────────────────────────────────
log "RDS subnet group..."
DB_SUBNET_GROUP="${APP_NAME}-db-subnet-group"
aws rds describe-db-subnet-groups --db-subnet-group-name "$DB_SUBNET_GROUP" \
    --region "$AWS_REGION" >/dev/null 2>&1 || \
aws rds create-db-subnet-group \
    --db-subnet-group-name "$DB_SUBNET_GROUP" \
    --db-subnet-group-description "Private subnets for ${APP_NAME} RDS" \
    --subnet-ids "$PRV_SUBNET_1" "$PRV_SUBNET_2" \
    --region "$AWS_REGION" >/dev/null
ok "DB subnet group: $DB_SUBNET_GROUP"

log "RDS PostgreSQL instance (db.t3.micro)..."
DB_IDENTIFIER="${APP_NAME}-postgres"
DB_STATUS=$(aws rds describe-db-instances \
    --db-instance-identifier "$DB_IDENTIFIER" \
    --query "DBInstances[0].DBInstanceStatus" --output text \
    --region "$AWS_REGION" 2>/dev/null || echo "")

if [[ -z "$DB_STATUS" ]]; then
    aws rds create-db-instance \
        --db-instance-identifier  "$DB_IDENTIFIER" \
        --db-instance-class       "db.t3.micro" \
        --engine                  "postgres" \
        --engine-version          "16.3" \
        --master-username         "$DB_USER" \
        --master-user-password    "$DB_PASSWORD" \
        --db-name                 "$DB_NAME" \
        --allocated-storage       20 \
        --storage-type            gp3 \
        --no-publicly-accessible \
        --vpc-security-group-ids  "$SG_RDS" \
        --db-subnet-group-name    "$DB_SUBNET_GROUP" \
        --backup-retention-period 7 \
        --deletion-protection \
        --region                  "$AWS_REGION" >/dev/null
    log "  Waiting for RDS to become available (~5 min)..."
    aws rds wait db-instance-available \
        --db-instance-identifier "$DB_IDENTIFIER" --region "$AWS_REGION"
    ok "Created RDS instance: $DB_IDENTIFIER"
else
    skip "RDS instance: $DB_IDENTIFIER (status: $DB_STATUS)"
fi

DB_ENDPOINT=$(aws rds describe-db-instances \
    --db-instance-identifier "$DB_IDENTIFIER" \
    --query "DBInstances[0].Endpoint.Address" --output text --region "$AWS_REGION")
DATABASE_URL="postgresql://${DB_USER}:${DB_PASSWORD}@${DB_ENDPOINT}:5432/${DB_NAME}"
DB_URL_ARN=$(store_secret "${APP_NAME}/database-url" "$DATABASE_URL")

# ── S3 Bucket ─────────────────────────────────────────────────────────────────
log "S3 bucket: $S3_BUCKET"
if ! aws s3api head-bucket --bucket "$S3_BUCKET" --region "$AWS_REGION" 2>/dev/null; then
    if [[ "$AWS_REGION" == "us-east-1" ]]; then
        aws s3api create-bucket --bucket "$S3_BUCKET" --region "$AWS_REGION" >/dev/null
    else
        aws s3api create-bucket --bucket "$S3_BUCKET" --region "$AWS_REGION" \
            --create-bucket-configuration LocationConstraint="$AWS_REGION" >/dev/null
    fi
    aws s3api put-public-access-block --bucket "$S3_BUCKET" \
        --public-access-block-configuration \
        "BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true" \
        --region "$AWS_REGION"
    ok "Created S3 bucket: $S3_BUCKET"
else
    skip "S3 bucket: $S3_BUCKET"
fi

# Upload FAISS index and ML model artifacts to S3
log "Uploading data/models to S3..."
if [[ -d "${REPO_ROOT}/data/index" ]]; then
    aws s3 sync "${REPO_ROOT}/data/index/" "s3://${S3_BUCKET}/index/" \
        --region "$AWS_REGION" --quiet
    ok "Uploaded data/index/ → s3://${S3_BUCKET}/index/"
else
    echo "  WARN: data/index/ not found — run scripts/ingest_data.py first"
fi
if [[ -d "${REPO_ROOT}/models" ]]; then
    aws s3 sync "${REPO_ROOT}/models/" "s3://${S3_BUCKET}/models/" \
        --region "$AWS_REGION" --quiet
    ok "Uploaded models/ → s3://${S3_BUCKET}/models/"
else
    echo "  WARN: models/ not found — run backend/app/ml/train.py first"
fi

# ── ECR Repositories ──────────────────────────────────────────────────────────
log "ECR repositories..."
for repo in "${APP_NAME}-backend" "${APP_NAME}-frontend"; do
    aws ecr describe-repositories --repository-names "$repo" \
        --region "$AWS_REGION" >/dev/null 2>&1 || \
    aws ecr create-repository --repository-name "$repo" \
        --image-scanning-configuration scanOnPush=true \
        --region "$AWS_REGION" >/dev/null
    # Keep only the last 10 images to control storage costs
    aws ecr put-lifecycle-policy --repository-name "$repo" \
        --lifecycle-policy-text '{
          "rules": [{
            "rulePriority": 1,
            "description": "Keep last 10 images",
            "selection": {"tagStatus": "any", "countType": "imageCountMoreThan", "countNumber": 10},
            "action": {"type": "expire"}
          }]
        }' --region "$AWS_REGION" >/dev/null 2>&1 || true
    ok "ECR repo: $repo"
done

# ── ECS Cluster ───────────────────────────────────────────────────────────────
log "ECS cluster..."
CLUSTER_NAME="${APP_NAME}-cluster"
CLUSTER_STATUS=$(aws ecs describe-clusters --clusters "$CLUSTER_NAME" \
    --query "clusters[0].status" --output text --region "$AWS_REGION" 2>/dev/null || echo "")
if [[ "$CLUSTER_STATUS" != "ACTIVE" ]]; then
    aws ecs create-cluster --cluster-name "$CLUSTER_NAME" \
        --capacity-providers FARGATE FARGATE_SPOT \
        --region "$AWS_REGION" >/dev/null
    ok "Created ECS cluster: $CLUSTER_NAME"
else
    skip "ECS cluster: $CLUSTER_NAME"
fi

# ── Application Load Balancer ─────────────────────────────────────────────────
log "Application Load Balancer..."
ALB_NAME="${APP_NAME}-alb"
ALB_ARN=$(aws_id "$(aws elbv2 describe-load-balancers \
    --names "$ALB_NAME" --query "LoadBalancers[0].LoadBalancerArn" \
    --output text --region "$AWS_REGION" 2>/dev/null || echo "")")

if [[ -z "$ALB_ARN" ]]; then
    ALB_ARN=$(aws elbv2 create-load-balancer \
        --name "$ALB_NAME" \
        --subnets "$PUB_SUBNET_1" "$PUB_SUBNET_2" \
        --security-groups "$SG_ALB" \
        --scheme internet-facing \
        --type application \
        --ip-address-type ipv4 \
        --region "$AWS_REGION" \
        --query "LoadBalancers[0].LoadBalancerArn" --output text)
    ok "Created ALB: $ALB_ARN"
else
    skip "ALB: $ALB_ARN"
fi

ALB_DNS=$(aws elbv2 describe-load-balancers \
    --load-balancer-arns "$ALB_ARN" \
    --query "LoadBalancers[0].DNSName" --output text --region "$AWS_REGION")

# Backend target group (port 8000, /api/health health check)
log "Target groups..."
make_tg() {
    local name="$1" port="$2" hc_path="$3"
    local tg_arn
    tg_arn=$(aws_id "$(aws elbv2 describe-target-groups \
        --names "$name" --query "TargetGroups[0].TargetGroupArn" \
        --output text --region "$AWS_REGION" 2>/dev/null || echo "")")
    if [[ -z "$tg_arn" ]]; then
        tg_arn=$(aws elbv2 create-target-group \
            --name "$name" --protocol HTTP --port "$port" \
            --vpc-id "$VPC_ID" --target-type ip \
            --health-check-path "$hc_path" \
            --health-check-interval-seconds 30 \
            --healthy-threshold-count 2 \
            --unhealthy-threshold-count 3 \
            --region "$AWS_REGION" \
            --query "TargetGroups[0].TargetGroupArn" --output text)
        ok "Created target group $name: $tg_arn"
    else
        skip "Target group $name"
    fi
    echo "$tg_arn"
}

TG_BACKEND_ARN=$(make_tg "${APP_NAME}-backend-tg"  8000 "/api/health")
TG_FRONTEND_ARN=$(make_tg "${APP_NAME}-frontend-tg" 80   "/")

# ALB listener: default → frontend; /api/* → backend
log "ALB listener rules..."
LISTENER_ARN=$(aws_id "$(aws elbv2 describe-listeners \
    --load-balancer-arn "$ALB_ARN" \
    --query "Listeners[?Port==\`80\`].ListenerArn | [0]" \
    --output text --region "$AWS_REGION" 2>/dev/null || echo "")")

if [[ -z "$LISTENER_ARN" ]]; then
    LISTENER_ARN=$(aws elbv2 create-listener \
        --load-balancer-arn "$ALB_ARN" \
        --protocol HTTP --port 80 \
        --default-actions Type=forward,TargetGroupArn="$TG_FRONTEND_ARN" \
        --region "$AWS_REGION" \
        --query "Listeners[0].ListenerArn" --output text)
    # Add /api/* → backend rule (priority 10, lower number = higher priority)
    aws elbv2 create-rule \
        --listener-arn "$LISTENER_ARN" \
        --priority 10 \
        --conditions '[{"Field":"path-pattern","Values":["/api/*"]}]' \
        --actions "[{\"Type\":\"forward\",\"TargetGroupArn\":\"${TG_BACKEND_ARN}\"}]" \
        --region "$AWS_REGION" >/dev/null
    ok "Created ALB listener + routing rules"
else
    skip "ALB listener: $LISTENER_ARN"
fi

# ── Save infrastructure state ──────────────────────────────────────────────────
log "Saving infra state to infra/.env.infra..."
cat > "${REPO_ROOT}/infra/.env.infra" <<EOF
# Auto-generated by setup_infra.sh — do not edit manually
AWS_REGION=${AWS_REGION}
AWS_ACCOUNT_ID=${AWS_ACCOUNT_ID}
APP_NAME=${APP_NAME}
ECR_REGISTRY=${ECR_REGISTRY}
VPC_ID=${VPC_ID}
PUB_SUBNET_1=${PUB_SUBNET_1}
PUB_SUBNET_2=${PUB_SUBNET_2}
PRV_SUBNET_1=${PRV_SUBNET_1}
PRV_SUBNET_2=${PRV_SUBNET_2}
SG_ALB=${SG_ALB}
SG_BACKEND=${SG_BACKEND}
SG_FRONTEND=${SG_FRONTEND}
SG_RDS=${SG_RDS}
CLUSTER_NAME=${CLUSTER_NAME}
EXEC_ROLE_ARN=${EXEC_ROLE_ARN}
TASK_ROLE_ARN=${TASK_ROLE_ARN}
ANTHROPIC_SECRET_ARN=${ANTHROPIC_SECRET_ARN}
DB_URL_SECRET_ARN=${DB_URL_ARN}
S3_BUCKET=${S3_BUCKET}
ALB_ARN=${ALB_ARN}
ALB_DNS=${ALB_DNS}
TG_BACKEND_ARN=${TG_BACKEND_ARN}
TG_FRONTEND_ARN=${TG_FRONTEND_ARN}
EOF

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
log "Infrastructure setup complete."
echo ""
echo "  ALB endpoint : http://${ALB_DNS}"
echo "  S3 bucket    : s3://${S3_BUCKET}"
echo "  RDS endpoint : ${DB_ENDPOINT}"
echo "  ECS cluster  : ${CLUSTER_NAME}"
echo ""
echo "  Next steps:"
echo "    1. bash infra/build_and_push.sh"
echo "    2. bash infra/deploy_ecs.sh"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"