# Repository & Deployment Management Rules

## Purpose

Claude must act as a **disciplined engineering agent** that maintains code quality, git hygiene, and deployability to AWS at all times.

Claude does NOT directly access Git or AWS, but must produce outputs that can be applied safely and consistently.

---

## 1. Git Repository Discipline

Claude MUST structure all changes as if contributing to a professional Git repository.

### For every change:

1. Clearly list:

   * Files created
   * Files modified
   * Files deleted (if any)

2. Provide a commit message in this format:

```
<type>: <short description>

<detailed explanation of what changed and why>
```

Examples:

* feat: add FAISS-based retrieval pipeline
* fix: correct PostgreSQL connection handling
* chore: update docker-compose for local development

---

### Branching Strategy

Claude must assume:

* `main` → stable, deployable
* `dev` → active development

All changes should be treated as:

> “feature branch → merged into dev → tested → merged into main”

---

## 2. Code Must Always Be Deployable

Claude must ensure:

* The system builds successfully
* No missing dependencies
* Environment variables are clearly defined
* Docker builds without errors

Every phase must end with:

### “Deployment Readiness Checklist”

* [ ] Backend starts without errors
* [ ] Frontend builds successfully
* [ ] Docker containers run
* [ ] API endpoints respond
* [ ] No hardcoded secrets

---

## 3. AWS Compatibility Requirements

Claude must ensure the code is always compatible with deployment on AWS.

---

### Required AWS Services

* ECS Fargate → backend deployment
* ECR → container registry
* RDS (PostgreSQL) → database
* S3 → document storage
* CloudWatch → logging
* IAM → permissions
* Secrets Manager → API keys

---

### AWS-Safe Coding Rules

Claude MUST:

1. Never hardcode:

   * API keys
   * database credentials
   * AWS credentials

2. Always use environment variables:

Example:

```
DATABASE_URL=postgresql://user:password@host:5432/db
ANTHROPIC_API_KEY=...
```

---

### Config Abstraction

All config must be centralized:

* `config.py` (backend)
* `.env` files
* environment-based switching (local vs AWS)

---

## 4. Docker-First Development

Claude must ensure:

* Everything runs via Docker
* Local and AWS environments are consistent

Every service must include:

* Dockerfile
* Proper ports
* Environment variables

---

## 5. Deployment Scripts Requirement

Claude must maintain working deployment scripts:

* `infra/build_and_push.sh`
* `infra/deploy_ecs.sh`
* `infra/setup_infra.sh`

Scripts must:

* Be idempotent where possible
* Use AWS CLI
* Include comments explaining each step

---

## 6. Connectivity Validation

Claude must ensure AWS connectivity can be verified.

For every deployment step, include commands to validate:

### Backend Health Check

```
curl http://<load-balancer-url>/api/health
```

---

### Database Connectivity

* Test DB connection from backend
* Log success/failure clearly

---

### Logs

Claude must ensure logs are visible in CloudWatch.

---

## 7. CI/CD Readiness (Important)

Claude must structure the repo so it can later integrate with:

* GitHub Actions

This includes:

* deterministic builds
* script-based deployment
* no manual steps hidden in explanations

---

## 8. Error Handling & Observability

Claude must include:

* Structured logging
* Clear error messages
* Retry logic (where appropriate)

---

## 9. Security Requirements (Healthcare Context)

Claude must ensure:

* No sensitive data leakage in logs
* Secure handling of API keys
* Input validation on all endpoints

---

## 10. Output Requirements for Every Phase

At the end of each phase, Claude MUST include:

### 1. Files changed

### 2. Full code

### 3. Run instructions

### 4. Test instructions

### 5. Deployment readiness checklist

### 6. Suggested git commit message

---

## Summary

Claude is responsible for producing:

* Production-quality code
* Git-ready changes
* AWS-deployable system
* Fully testable components

Claude is NOT writing examples—it is maintaining a real system.
