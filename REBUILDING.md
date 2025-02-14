## Rebuilding Onyx After Local Changes

We are running a local fork of Onyx with a local instance of Unstructured. We are not pushing all our changes back to the Onyx repo. We will share specific changes i.e. enhancements to connectors as PRs.

When you need to rebuild the local Onyx stack after code changes or updates, follow these steps:

### 1. Save Current State
```bash
# If any local uncommitted changes, stash them
# git stash save "pending changes before update"

# Create backup tag of clean state
git tag -a backup-$(date +%Y%m%d) -m "Clean state before update"

# Verify tag
git show backup-$(date +%Y%m%d)
```

### 2. Update Code
```bash
# Update from remote repo
git pull origin main

# If pull succeeds and there are pending stashed changes, apply them
# git stash apply

# If pull fails:
# git checkout backup-$(date +%Y%m%d)  # return to last working state
```

### 3. Rebuild Stack
```bash
cd deployment/docker_compose
docker compose -f docker-compose.dev.yml -p onyx-stack up -d --build --force-recreate
```

### 4. Verify
```bash
# Check containers
docker ps

# Test web interface
open http://localhost:3000
```

### Notes
- The `-p onyx-stack` flag ensures we're updating the correct stack
- Data persists across rebuilds (stored in Docker volumes)
- No .env file needed for dev configuration

### Disaster Recovery
- Docker Desktop's "Include VM in Time Machine backups" is enabled
  - Backs up entire Docker environment including volumes
- Local backup tags provide restore points
  - Created in Step 1 using: `git tag -a backup-$(date +%Y%m%d)`
  - These tags are local only
  - To list backups: `git tag -l "backup-*"`
  - To restore: `git checkout backup-YYYYMMDD`
- Docker volumes persist in: `~/Library/Containers/com.docker.docker/Data/vms/0/data/`
