# Clinical AI Assistant

A production-grade Clinical AI Assistant built with FastAPI, React, and Claude (Anthropic).

## Architecture

```
medical-ai-assitant/
├── backend/        FastAPI application (Python 3.12)
├── frontend/       React + Vite SPA
├── infra/          AWS deployment scripts (ECS Fargate)
├── data/           Document storage (synced to S3 in production)
└── tests/          Integration and unit tests
```

**Request flow:** Browser → React (Vite dev proxy / Nginx in prod) → FastAPI → Anthropic API

## Prerequisites

- Python 3.12+
- Node.js 20+
- Docker & Docker Compose
- Anthropic API key

## Local Development (without Docker)

### Backend

```bash
cd backend
cp .env.example .env
# Edit .env and set ANTHROPIC_API_KEY
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

API docs available at: http://localhost:8000/api/docs

### Frontend

```bash
cd frontend
npm install
npm run dev
```

App available at: http://localhost:5173

## Local Development (with Docker)

```bash
cp backend/.env.example backend/.env
# Edit backend/.env and set ANTHROPIC_API_KEY
docker-compose up --build
```

- Frontend: http://localhost:3000
- Backend API: http://localhost:8000/api/docs
- Database: localhost:5432

## Running Tests

```bash
cd backend
pip install -r requirements.txt
pytest ../tests/ -v
```

Run a single test:

```bash
pytest ../tests/test_health.py -v
```

## AWS Deployment

```bash
# 1. Provision infrastructure (one-time)
chmod +x infra/*.sh
AWS_REGION=us-east-1 ./infra/setup_infra.sh

# 2. Build and push images to ECR
IMAGE_TAG=v1.0.0 ./infra/build_and_push.sh

# 3. Deploy to ECS Fargate
./infra/deploy_ecs.sh

# 4. Validate
curl http://<load-balancer-url>/api/health
```

## Environment Variables

See `backend/.env.example` for all required variables. Key ones:

| Variable | Description |
|---|---|
| `ANTHROPIC_API_KEY` | Anthropic API key |
| `DATABASE_URL` | PostgreSQL connection string |
| `ENVIRONMENT` | `local` / `staging` / `production` |
| `AWS_REGION` | AWS region for deployed resources |
| `S3_BUCKET_NAME` | S3 bucket for document storage |
