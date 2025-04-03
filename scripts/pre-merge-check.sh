#!/bin/bash

# Script to run regression tests before merging changes from upstream
# This helps ensure custom fixes in this fork aren't broken by upstream changes

set -e  # Exit on error

echo "Running regression tests before merge..."

# Run backend regression tests
cd "$(git rev-parse --show-toplevel)/backend"
echo "Running backend regression tests..."
source ../.venv/bin/activate
python -m pytest tests/unit/onyx/llm/test_llm_provider_options.py -v
python -m pytest tests/unit/test_email_invites.py -v

# Run Zulip schema tests
echo "Running Zulip schema compatibility tests..."
python -m pytest tests/unit/connectors/zulip/test_zulip_schema.py -v

# Run Azure DevOps tests
echo "Running Azure DevOps backend tests..."
python -m pytest tests/unit/connectors/azure_devops/test_azure_devops_content_scope.py -v
python -m pytest tests/unit/connectors/azure_devops/test_azure_devops_git_commits.py -v

# Temporarily disable frontend tests due to Formik dependency issues
# cd "$(git rev-parse --show-toplevel)/web"
# echo "Running Azure DevOps frontend tests..."
# npm test src/tests/connectors/AzureDevOpsConnector.test.tsx

# Check if Docker is running before trying to run Docker-dependent tests
if ! docker info > /dev/null 2>&1; then
  echo "⚠️ Warning: Docker is not running. Skipping Unstructured API tests."
  echo "Please start Docker Desktop and run this script again to complete all tests."
  exit 0
fi

# Function to ensure Unstructured API is running
ensure_unstructured_api() {
  local CONTAINER_NAME="unstructured-api"
  local API_URL="http://localhost:8000"

  echo "Checking if Unstructured API container is running..."

  # Check if container exists and is running
  if docker ps | grep -q "$CONTAINER_NAME"; then
    echo "✅ Unstructured API container is already running"
    
    # Verify the API is responding correctly
    if curl -s "$API_URL/healthcheck" | grep -q "HEALTHCHECK STATUS: EVERYTHING OK"; then
      echo "✅ Unstructured API is healthy"
      return 0
    else
      echo "⚠️ Unstructured API container is running but not responding correctly"
      echo "Attempting to restart the container..."
      docker restart "$CONTAINER_NAME"
      
      # Wait for container to restart
      sleep 5
      
      # Check if it's healthy after restart
      if curl -s "$API_URL/healthcheck" | grep -q "HEALTHCHECK STATUS: EVERYTHING OK"; then
        echo "✅ Unstructured API is now healthy after restart"
        return 0
      else
        echo "❌ Unstructured API still not responding after restart"
        echo "Please check the container logs: docker logs $CONTAINER_NAME"
        return 1
      fi
    fi
  fi

  # Container not running, check if it exists but is stopped
  if docker ps -a | grep -q "$CONTAINER_NAME"; then
    echo "⚠️ Unstructured API container exists but is not running"
    echo "Starting existing container..."
    docker start "$CONTAINER_NAME"
  else
    echo "⚠️ Unstructured API container not found"
    echo "Creating and starting new container..."
    docker run --platform linux/amd64 -p 8000:8000 -d --name "$CONTAINER_NAME" downloads.unstructured.io/unstructured-io/unstructured-api:latest
  fi

  # Wait for container to start
  echo "Waiting for container to start..."
  sleep 5

  # Verify the API is responding correctly
  if curl -s "$API_URL/healthcheck" | grep -q "HEALTHCHECK STATUS: EVERYTHING OK"; then
    echo "✅ Unstructured API is now running and healthy"
    return 0
  else
    echo "❌ Failed to start Unstructured API"
    echo "Please check the container logs: docker logs $CONTAINER_NAME"
    return 1
  fi
}

# Ensure Unstructured API is running before proceeding
echo "Ensuring Unstructured API is running..."
if ! ensure_unstructured_api; then
  echo "❌ Failed to ensure Unstructured API is running. Exiting tests."
  exit 1
fi

# Run Unstructured API integration check
echo "Running Unstructured API integration check..."
cd "$(git rev-parse --show-toplevel)"
./scripts/check_unstructured_integration.sh

# Run Unstructured API health check
echo "Running Unstructured API health check..."
cd "$(git rev-parse --show-toplevel)"
./scripts/test_unstructured_api_health.sh

echo "All backend regression tests passed!"
exit 0 