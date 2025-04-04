## Onyx Development and Deployment Guide

### Environment Setup
We maintain two environments:

#### Development (`onyx-dev`)
- Local development on MacBook Pro at localhost:3000
- Repository: https://github.com/ATSiem/onyx
- Uses `docker-compose.dev.yml`

#### Production (`onyx`)
- Runs on Mac mini at knowledge.solutioncenter.ai
- Pulls from ATSiem/onyx repository
- Uses `docker-compose.prod.yml` for Let's Encrypt SSL
- Uses .env and .env.nginx in deployment/docker_compose

### Unstructured API Setup
Both environments use a local Unstructured API:

> **Note**: Both development and production environments are configured to use `http://host.docker.internal:8000` as the Unstructured API URL in their respective docker-compose files. This is set via the `UNSTRUCTURED_API_URL` environment variable in both `api_server` and `background` services.

```bash
# Option 1: Use the helper script to automatically setup the Unstructured API
# This will check if Docker is running, and if the container is running and start it if needed
./scripts/ensure_unstructured_api.sh

# Option 2: Manual setup
# Download image
docker pull --platform linux/amd64 downloads.unstructured.io/unstructured-io/unstructured-api:latest

# Run locally (no -d flag for interactive mode)
docker run --platform linux/amd64 -p 8000:8000 --name unstructured-api downloads.unstructured.io/unstructured-io/unstructured-api:latest

# Alternatively, run in background with -d flag
# docker run --platform linux/amd64 -p 8000:8000 -d --name unstructured-api downloads.unstructured.io/unstructured-io/unstructured-api:latest

# Generate and set up API key
docker exec -it unstructured-api bash
python3 -c "import uuid; print(uuid.uuid4())"  # Copy this generated UUID

# Set the API key in Onyx UI:
# 1. Go to Settings > Unstructured API
# 2. Paste the generated UUID into the API Key field
# 3. Click Save - this stores the key in Onyx's key-value store

# Verify API is running and healthy
docker ps | grep unstructured-api  # Should show container running
curl http://localhost:8000/healthcheck  # Should return HEALTHCHECK STATUS: EVERYTHING OK!

# Test document processing
# First create a test file
echo "Test document" > test.txt

# Test processing with the correct endpoint
curl -X POST http://localhost:8000/general/v0/general \
    -H 'accept: application/json' \
    -H 'Content-Type: multipart/form-data' \
    -H 'unstructured-api-key: YOUR-UUID-HERE' \
    -F "files=@test.txt" \
    -F "strategy=auto"

# Expected successful response should look like:
# [{
#   "type": "Title",
#   "element_id": "...",
#   "text": "Test document",
#   "metadata": {
#     "languages": ["eng"],
#     "filename": "test.txt",
#     "filetype": "text/plain"
#   }
# }]
```

If the API is not responding or file processing fails:
1. Check logs: `docker logs unstructured-api`
2. Restart container: `docker restart unstructured-api`
3. Verify no port conflicts on 8000
4. Verify API key is properly set in Onyx UI
5. Check background service logs: `docker logs onyx-stack-background-1`

To verify file processing is working:
1. Upload test documents through the Onyx UI
2. Start reindexing the file connector
3. Monitor processing in logs:
   ```bash
   docker logs onyx-stack-background-1 2>&1 | grep -i "Starting to read file\|processing"
   ```
4. Successful processing should show batch processing times around 1.5-2 seconds per batch

### Git Workflow

#### Repository Structure
- **Origin** (`onyx-dot-app/onyx`): Upstream repository, used only as source for new functionality from Onyx team
- **Fork** (`ATSiem/onyx`): Used for:
  1. Submitting PRs to upstream Onyx team
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
git tag -a backup-$(date +%Y%m%d-%H%M) -m "Clean state"
```

#### Submitting PRs
When contributing to upstream Onyx:
```bash
# Create clean branch without environment-specific changes
git checkout -b feature/upstream main
git cherry-pick -x --exclude=429a7e743 <your-feature-commits>  # exclude local config changes as needed i.e. unstructured api changes and local documentation
git push fork feature/upstream
# Create PR at https://github.com/onyx-dot-app/onyx/compare
```

### Deployment

#### to Development Environment

1. **Before rebuilding, ensure all tests pass and the Unstructured API is running:**
```bash
# Run regression tests
./scripts/pre-merge-check.sh

# Ensure Unstructured API is running
./scripts/ensure_unstructured_api.sh
```

2. **Choose a rebuild approach:**

```bash
# Option 1: Standard rebuild (recommended for most cases)
docker compose -f deployment/docker_compose/docker-compose.dev.yml -p onyx-stack up -d --build --force-recreate

# Option 2: Complete clean rebuild (use when troubleshooting build issues)
# Step 1: Build with no cache
docker compose -f deployment/docker_compose/docker-compose.dev.yml -p onyx-stack build --no-cache
# Step 2: Start containers
docker compose -f deployment/docker_compose/docker-compose.dev.yml -p onyx-stack up -d --force-recreate
```

3. **Verify the rebuild:**
```bash
# Check container status
docker compose -f deployment/docker_compose/docker-compose.dev.yml -p onyx-stack ps

# Watch logs for any errors during startup
docker compose -f deployment/docker_compose/docker-compose.dev.yml -p onyx-stack logs -f

# Access the application
open http://localhost:3000
```

Remember: Always commit your changes and push to fork before major operations. Use git tags for safety:
```bash
git tag -a backup-$(date +%Y%m%d-%H%M) -m "Pre-operation backup"
```

#### to Production Environment
```bash
# On Mac mini, from repository root
git fetch fork
git checkout main
git pull fork main

# Ensure Unstructured API is running
./scripts/ensure_unstructured_api.sh

# Create backup tag
git tag -a backup-$(date +%Y%m%d-%H%M) -m "Pre-deployment backup"

# Run pre-deployment tests
./scripts/pre-merge-check.sh

# Deploy to production
docker compose -f deployment/docker_compose/docker-compose.prod.yml -p onyx-stack up -d --build --force-recreate

# Verify deployment
echo "Verifying deployment..."
docker compose -f deployment/docker_compose/docker-compose.prod.yml -p onyx-stack ps
curl http://localhost:8000/healthcheck
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
curl http://localhost:8000/healthcheck  # Should return HEALTHCHECK STATUS: EVERYTHING OK!
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
git clean -fd                 # Aggressive! Remove untracked files

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

4. **Rebuild Failures or Lingering Issues**
```bash
# Deep clean (use when standard rebuilds fail)
docker compose -f deployment/docker_compose/docker-compose.dev.yml -p onyx-stack down -v  # WARNING: This removes volumes!
docker system prune -a  # WARNING: This removes all unused images!
docker compose -f deployment/docker_compose/docker-compose.dev.yml -p onyx-stack build --no-cache
docker compose -f deployment/docker_compose/docker-compose.dev.yml -p onyx-stack up -d
```

### Notes
- Data persists in Docker volumes (`~/Library/Containers/com.docker.docker/Data/vms/0/data/`)
- Time Machine backups enabled for Docker Desktop on dev and prod
- Local git tags (`backup-*`) provide restore points
  - `git tag -l "backup-*" -n1 --sort=-creatordate` to review all backups
- Development environment pushes only to fork (ATSiem/onyx), never to upstream origin to Onyx team
- Keep feature branches active while PRs are open in upstream (onyx-dot-app/onyx)

### Email Configuration
For email invites to work properly, ensure `MULTI_TENANT=true` is set in your `.env` file.

### Testing

#### Pre-Merge and Regression Tests
Before rebuilding the development environment or merging upstream changes, run the pre-merge check script:

```bash
# Run all pre-merge checks
./scripts/pre-merge-check.sh
```

This script runs:
1. Backend regression tests for our custom fixes
2. Integration tests for connectors with our modifications
3. Unstructured API integration and health checks
4. Other fork-specific tests

For detailed documentation of all regression tests and the fixes they protect, see `TESTING.md`.

#### Running Specific Tests

```bash
# Backend tests
cd backend
python -m pytest                             # All tests
python -m pytest tests/unit/path/to/test.py  # Specific test

# Frontend tests
cd web
npm test                                     # All tests
npm test -- src/path/to/test.tsx             # Specific test
```

#### Best Practices
1. Write tests for any bugs found in production
2. Run tests before pushing to main branch
3. Ensure the pre-merge tests pass before merging from upstream
4. Document all fork-specific modifications in TESTING.md
