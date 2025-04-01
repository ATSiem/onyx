#!/bin/bash

# Production deployment script
# Run this on the Mac mini (knowledge.solutioncenter.ai)

# 1. Fetch latest changesI made changes on March 31, 2025 at 4:29 PM
git fetch fork
git checkout main
git pull fork main

# 2. Ensure Unstructured API is running
./scripts/ensure_unstructured_api.sh

# 3. Create backup tag
git tag -a backup-$(date +%Y%m%d-%H%M) -m "Pre-deployment backup"

# 4. Run pre-deployment tests
./scripts/pre-merge-check.sh

# 5. Deploy to production
docker compose -f deployment/docker_compose/docker-compose.prod.yml -p onyx-stack up -d --build --force-recreate

# 6. Verify deployment
echo "Verifying deployment..."
docker compose -f deployment/docker_compose/docker-compose.prod.yml -p onyx-stack ps
curl http://localhost:8000/healthcheck

echo "Deployment complete. Check https://knowledge.solutioncenter.ai" 