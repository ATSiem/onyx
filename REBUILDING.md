## Rebuilding Onyx After Local Changes

When you need to rebuild the local Onyx stack after code changes or updates, follow these steps:

### 1. Save Local Changes
```bash
# Stash any local changes
git stash save "describe your changes"
```

### 2. Update from Main
```bash
# Configure git to use merge strategy
git config pull.rebase false

# Pull latest changes
git pull origin main

# Apply your local changes back
git stash apply
```

### 3. Rebuild the Stack
```bash
# Navigate to docker compose directory
cd deployment/docker_compose

# Rebuild with the correct stack name
docker compose -f docker-compose.dev.yml -p onyx-stack up -d --build --force-recreate
```

### 4. Verify
```bash
# Check all containers are running
docker ps

# Test the web interface
open http://localhost:3000
```

### Notes
- The `-p onyx-stack` flag is crucial - it ensures we're updating the correct stack
- Your data persists across rebuilds (stored in Docker volumes)
- The development configuration includes hot reloading for future changes
- No .env file is needed as the dev configuration includes defaults

### Disaster Recovery
- Docker Desktop's "Include VM in Time Machine backups" is enabled on MacOS
  - This backs up the entire Docker environment, including volumes
  - Provides a full system restore point if needed
- Git tags provide code-level recovery points
- Docker volumes persist data even if containers are removed
  - Located in `~/Library/Containers/com.docker.docker/Data/vms/0/data/`
  - Backed up with Time Machine when VM backups are enabled

### After Successful Rebuild
```bash
# Clean up the stash if everything works
git stash drop

# Optionally, tag the working version
git tag -a v1.x.x -m "Working local build with [describe changes]"
```