## Rebuilding Onyx After Local Changes

When you make changes to the local codebase and need to rebuild the Docker containers, follow these steps:

### 1. Navigate to the Docker Compose Directory
```bash
cd deployment/docker_compose
```

### 2. Stop the Current Stack
```bash
docker compose -f docker-compose.dev.yml -p onyx-stack down
```

### 3. Rebuild and Start the Stack
```bash
docker compose -f docker-compose.dev.yml -p onyx-stack up -d --build --force-recreate
```

### 4. Verify the Stack is Running
```bash
docker ps
```

### Notes
- The rebuild process will take a few minutes as it rebuilds the affected containers
- Your data will persist as it's stored in Docker volumes
- We're using the development configuration (`docker-compose.dev.yml`) which includes hot reloading and development defaults
- No .env file is needed as the dev configuration includes default values
- During rebuilds:
  - Only containers affected by code changes will be rebuilt
  - The web interface (localhost:3000) may still be available while other containers rebuild
  - Backend changes (like Zulip connector updates) will rebuild faster than model servers
- The `-p onyx-stack` flag ensures we're working with the correct stack name

### Stashing local changes

To merge a `git stash` into the `main` branch after performing a `git stash` and then a `git pull`, follow these steps:

1. **Stash your changes**:
   ```bash
   git stash
   ```

2. **Pull the latest changes from the remote**:
   ```bash
   git pull origin main
   ```

3. **Apply the stashed changes**:
   ```bash
   git stash apply
   ```
   - This will apply the stashed changes to your working directory.

4. **Resolve any conflicts** (if necessary):
   - If there are conflicts, resolve them manually, then stage the resolved files.

5. **Commit the merged changes**:
   ```bash
   git add .
   git commit -m "Merged stashed changes"
   ```

6. **(Optional) Drop the stash if no longer needed**:
   ```bash
   git stash drop
   ```
   - Or use `git stash pop` instead of `git stash apply` to apply and immediately drop the stash in one command.

This process will merge your stashed changes into the `main` branch after pulling the latest updates.