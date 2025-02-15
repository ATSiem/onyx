## Onyx Development and Deployment Guide

### Environment Setup
We maintain two environments:
- **Development** (`onyx-dev`): 
  - Local development on MacBook Pro
  - Repository: https://github.com/ATSiem/onyx
  - Uses `docker-compose.dev.yml`
  - Local Unstructured API at `host.docker.internal:8000` via https://github.com/Unstructured-IO/unstructured-api
  - download: `docker pull --platform linux/amd64 downloads.unstructured.io/unstructured-io/unstructured-api:latest`
  - run: `docker run --platform linux/amd64 -p 8000:8000 -d --rm --name unstructured-api downloads.unstructured.io/unstructured-io/unstructured-api:latest`


- **Production** (`onyx`):
  - Runs on Mac mini at knowledge.solutioncenter.ai
  - Pulls from ATSiem/onyx repository
  - Will use `docker-compose.yml` for Let's Encrypt SSL
  - Same local Unstructured API configuration

### Development Workflow

#### 1. Making Changes
```bash
# Start from updated main
git checkout main
git pull origin main

# Create feature branch
git checkout -b feature/your-feature

# Save work in progress (if needed)
git stash save "pending changes"
git tag -a backup-$(date +%Y%m%d) -m "Clean state"
```

#### 2. Rebuilding After Changes
```bash
# Development Environment
cd deployment/docker_compose
docker compose -f docker-compose.dev.yml -p onyx-stack up -d --build --force-recreate

# Verify
docker ps
open http://localhost:3000
```

#### 3. Creating PRs
When contributing back to upstream Onyx:
```bash
# Create clean branch without environment-specific changes
git checkout -b feature/upstream main
git cherry-pick -x --exclude=429a7e743 <your-feature-commits> # i.e. local Unstructured API URL change
git push fork feature/upstream
# then submit PR via https://github.com/onyx-dot-app/onyx/compare
```

### Production Deployment

0. Ensure you have the latest changes from upstream:
```bash
# On Mac mini
git remote add fork https://github.com/ATSiem/onyx.git # if not already added
git fetch fork
git checkout main
git pull fork main
```

1. On Mac mini:
  ```bash
  cd deployment/docker_compose
  docker compose -f docker-compose.yml -p onyx-stack up -d --build --force-recreate
  ```
2. Let's Encrypt will automatically handle SSL for knowledge.solutioncenter.ai

### Notes
- Data persists in Docker volumes

- No .env file needed for development
- Time Machine backups enabled for Docker Desktop on dev and prod
- Local git tags (`backup-*`) provide restore points
- Docker volumes: `~/Library/Containers/com.docker.docker/Data/vms/0/data/`
