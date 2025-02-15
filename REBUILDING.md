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
- Uses `docker-compose.prod.yml` for Let's Encrypt SSL

### Unstructured API Setup
Both environments use a local Unstructured API:
```bash
# Download image
docker pull --platform linux/amd64 downloads.unstructured.io/unstructured-io/unstructured-api:latest

# Run locally
docker run --platform linux/amd64 -p 8000:8000 -d --rm --name unstructured-api downloads.unstructured.io/unstructured-io/unstructured-api:latest

# Verify API is running and healthy
docker ps | grep unstructured-api  # Should show container running

# Test document processing
curl -X POST http://localhost:8000/partition \
    -H 'accept: application/json' \
    -H 'Content-Type: application/json' \
    -d '{"strategy": "auto", "text": "Test document"}'
```

If the API is not responding:
1. Check logs: `docker logs unstructured-api`
2. Restart container: `docker restart unstructured-api`
3. Verify no port conflicts on 8000

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
# From repository root
docker compose -f deployment/docker_compose/docker-compose.dev.yml -p onyx-stack up -d --build --force-recreate
open http://localhost:3000
```

Remember: Always commit your changes and push to fork before major operations. Use git tags for safety:
```bash
git tag -a backup-$(date +%Y%m%d) -m "Pre-operation backup"
```

#### Production
```bash
# On Mac mini, from repository root
git fetch fork
git checkout main
git pull fork main

docker compose -f deployment/docker_compose/docker-compose.prod.yml -p onyx-stack up -d --build --force-recreate
```
Let's Encrypt will automatically handle SSL for knowledge.solutioncenter.ai

### Environment Verification

#### Checking Environment State
```bash
# Verify git configuration
git remote -v                    # Should show fork (ATSiem/onyx) and origin (onyx-dot-app/onyx)
git branch --show-current       # Confirm you're on main branch
git log --oneline -n 3         # Review latest commits

# Check Docker stack
docker compose -f deployment/docker_compose/docker-compose.prod.yml -p onyx-stack ps  # View container status
docker volume ls | grep onyx    # Verify persistent volumes
docker logs -f onyx-stack-app-1 # Monitor application logs

# Verify Unstructured API
curl -I http://localhost:8000/health  # Should return HTTP 200
```

### Troubleshooting Guide

#### Common Issues and Solutions

1. **Container Start Failures**
```bash
# Clear all containers and rebuild
docker compose -f deployment/docker_compose/docker-compose.prod.yml -p onyx-stack down
docker system prune -f  # Remove unused containers/networks
docker compose -f deployment/docker_compose/docker-compose.prod.yml -p onyx-stack up -d --build
```

2. **Environment Sync Issues**
```bash
# On development (MacBook Pro)
git fetch fork
git reset --hard fork/main    # Warning: discards local changes
git clean -fd                 # Remove untracked files

# On production (Mac mini)
git fetch fork
git reset --hard fork/main
```

3. **Certificate Issues**
```bash
# Check certificate status
docker compose -f deployment/docker_compose/docker-compose.prod.yml -p onyx-stack exec certbot certbot certificates

# Force certificate renewal
docker compose -f deployment/docker_compose/docker-compose.prod.yml -p onyx-stack exec certbot certbot renew --force-renewal
```

### Notes
- Data persists in Docker volumes (`~/Library/Containers/com.docker.docker/Data/vms/0/data/`)
- No .env file needed for development
- Time Machine backups enabled for Docker Desktop on dev and prod
- Local git tags (`backup-*`) provide restore points
- Development environment pushes only to fork (ATSiem/onyx), never to origin
- Keep feature branches active while PRs are open in upstream (onyx-dot-app/onyx)
