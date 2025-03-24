#!/bin/bash

# Script to ensure the Unstructured API container is running
# This can be run during development or as part of system startup

set -e  # Exit on error

CONTAINER_NAME="unstructured-api"
API_URL="http://localhost:8000"

echo "Checking if Docker is running..."
if ! docker info > /dev/null 2>&1; then
  echo "❌ Docker is not running. Please start Docker Desktop first."
  exit 1
fi

echo "Checking if Unstructured API container is running..."

# Check if container exists and is running
if docker ps | grep -q "$CONTAINER_NAME"; then
  echo "✅ Unstructured API container is already running"
  
  # Verify the API is responding correctly
  if curl -s "$API_URL/healthcheck" | grep -q "HEALTHCHECK STATUS: EVERYTHING OK"; then
    echo "✅ Unstructured API is healthy"
    exit 0
  else
    echo "⚠️ Unstructured API container is running but not responding correctly"
    echo "Attempting to restart the container..."
    docker restart "$CONTAINER_NAME"
    
    # Wait for container to restart
    sleep 5
    
    # Check if it's healthy after restart
    if curl -s "$API_URL/healthcheck" | grep -q "HEALTHCHECK STATUS: EVERYTHING OK"; then
      echo "✅ Unstructured API is now healthy after restart"
      exit 0
    else
      echo "❌ Unstructured API still not responding after restart"
      echo "Please check the container logs: docker logs $CONTAINER_NAME"
      exit 1
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
  docker run --platform linux/amd64 -p 8000:8000 --name "$CONTAINER_NAME" downloads.unstructured.io/unstructured-io/unstructured-api:latest
fi

# Wait for container to start
echo "Waiting for container to start..."
sleep 5

# Verify the API is responding correctly
if curl -s "$API_URL/healthcheck" | grep -q "HEALTHCHECK STATUS: EVERYTHING OK"; then
  echo "✅ Unstructured API is now running and healthy"
  exit 0
else
  echo "❌ Failed to start Unstructured API"
  echo "Please check the container logs: docker logs $CONTAINER_NAME"
  exit 1
fi 