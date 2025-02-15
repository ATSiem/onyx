## Onyx Development and Deployment Guide

### Environment Setup
We maintain two environments:

#### Development (`onyx-dev`)
- Local development on MacBook Pro
- Repository: https://github.com/ATSiem/onyx
- Uses `docker-compose.dev.yml`

#### Production (`onyx`)
- Runs on Mac mini at knowledge.solutioncenter.ai
- Pulls from ATSiem/onyx repository
- Uses `docker-compose.yml` for Let's Encrypt SSL

### Unstructured API Setup
Both environments use a local Unstructured API:
```bash
# Download image
docker pull --platform linux/amd64 downloads.unstructured.io/unstructured-io/unstructured-api:latest

# Run locally
docker run --platform linux/amd64 -p 8000:8000 -d --rm --name unstructured-api downloads.unstructured.io/unstructured-io/unstructured-api:latest
```

### Git Workflow

#### Repository Structure
- **Origin** (`onyx-dot-app/onyx`): Upstream repository, used only as reference
- **Fork** (`ATSiem/onyx`): Used for:
  1. Submitting PRs to upstream
  2. Deploying to production
  3. Sharing changes between development and production

#### Making Changes
```bash
# Start from main
git checkout main

# Create feature branch
git checkout -b feature/your-feature

# Optional: Save work in progress
git stash save "pending changes"
git tag -a backup-$(date +%Y%m%d) -m "Clean state"
```

#### Submitting PRs
When contributing to upstream Onyx:
```bash
# Create clean branch without environment-specific changes
git checkout -b feature/upstream main
git cherry-pick -x --exclude=429a7e743 <your-feature-commits>  # exclude local config changes
git push fork feature/upstream
# Create PR at https://github.com/onyx-dot-app/onyx/compare
```

### Deployment

#### Development
```bash
cd deployment/docker_compose
docker compose -f docker-compose.dev.yml -p onyx-stack up -d --build --force-recreate
open http://localhost:3000
```

#### Production
```bash
# On Mac mini
git fetch fork
git checkout main
git pull fork main

cd deployment/docker_compose
docker compose -f docker-compose.yml -p onyx-stack up -d --build --force-recreate
```
Let's Encrypt will automatically handle SSL for knowledge.solutioncenter.ai

### Notes
- Data persists in Docker volumes (`~/Library/Containers/com.docker.docker/Data/vms/0/data/`)
- No .env file needed for development
- Time Machine backups enabled for Docker Desktop on dev and prod
- Local git tags (`backup-*`) provide restore points
- Development environment pushes only to fork (ATSiem/onyx), never to origin
- Keep feature branches active while PRs are open in upstream (onyx-dot-app/onyx)
