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
```bash
# From repository root
docker compose -f deployment/docker_compose/docker-compose.dev.yml -p onyx-stack up -d --build --force-recreate
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

#### Pre-Merge and Azure DevOps Tests
Before rebuilding the development environment, run the pre-merge check script which includes:
1. Backend regression tests
2. Email invite tests
3. Zulip schema compatibility tests
4. Unstructured API integration checks
5. Unstructured API health check
6. Azure DevOps connector tests (40 tests)

```bash
# Run all pre-merge checks and Azure DevOps tests
./scripts/pre-merge-check.sh
```

The pre-merge check script will run all necessary tests in sequence. If any test fails, the script will stop and report the error.

#### Frontend Testing
The Onyx codebase uses Jest for frontend testing with the following setup:

```bash
# Run all tests
cd web
npm test

# Run specific test file
npm test -- src/components/llm/LLMSelector.test.tsx

# Run tests with coverage
npm test -- --coverage
```

Frontend tests use:
- Jest as the test runner
- jsdom for DOM simulation
- @testing-library/react for component testing
- TypeScript support via babel-jest

The Jest configuration is in `web/jest.config.js` and Babel configuration in `web/babel.config.js`.

> **Note**: E2E tests using Playwright are not currently set up in this fork.

#### Backend Testing
The backend uses pytest for testing with the following structure:

```bash
# Run all backend tests
cd backend
python -m pytest

# Run specific test file
python -m pytest tests/unit/connectors/azure_devops/test_azure_devops_connector.py -v

# Run all Azure DevOps connector tests (40 tests)
python -m pytest tests/unit/connectors/azure_devops/test_*.py -v
```

Backend test categories:
- **Unit Tests**: Individual function/class testing
- **Integration Tests**: Component interaction testing
- **Regression Tests**: Bug fix verification
- **Connector Tests**: Specific tests for data connectors (e.g., Azure DevOps)

#### Azure DevOps Connector Tests
The Azure DevOps connector has 40 tests across multiple files:
- `test_azure_devops_connector.py`: Core connector functionality
- `test_azure_devops_credential_flow.py`: Authentication
- `test_azure_devops_document.py`: Document processing
- `test_azure_devops_independent.py`: Utility functions
- `test_azure_devops_pagination.py`: Pagination and batching
- `test_azure_devops_regression.py`: Bug fixes
- `test_azure_devops_resolution_status.py`: Resolution status handling
- `test_azure_devops_utils.py`: Helper functions

#### Fork-Specific Regression Tests
This fork contains specific regression tests to verify our custom fixes are maintained when merging from upstream:

```bash
# Run regression tests
./scripts/pre-merge-check.sh
```

The pre-merge check script runs:
1. Backend regression tests
2. Email invite tests
3. Zulip schema compatibility tests
4. Unstructured API integration checks
5. Unstructured API health check
6. Azure DevOps connector tests

See `REGRESSION_TESTS.md` for details on the regression tests and how they protect our custom functionality.

#### Best Practices
1. Write tests for any bugs found in production
2. Use descriptive test names that explain what's being tested
3. Keep tests focused on testing behavior, not implementation
4. Run tests before pushing to main branch
5. Add appropriate comments to regression tests explaining the issue they're addressing

#### Example: Regression Test
See `web/src/components/llm/LLMSelector.test.tsx` for an example of a regression test that ensures specific model names are properly filtered.
