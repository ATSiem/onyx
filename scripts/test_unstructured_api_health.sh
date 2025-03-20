#!/bin/bash

# Script to test the Unstructured API health by creating a test file,
# uploading it to the API, and verifying the response
# This is meant to be run as part of the pre-merge check to ensure
# Unstructured API integration is working

set -e  # Exit on error

echo "Testing Unstructured API functionality..."

# Get the repository root directory
REPO_ROOT=$(git rev-parse --show-toplevel)
cd "$REPO_ROOT"

# Create a temporary directory and test file
TEMP_DIR=$(mktemp -d)
TEST_FILE="$TEMP_DIR/test.txt"
echo "This is a test document for Unstructured API verification." > "$TEST_FILE"

# Get the Unstructured API URL from the docker-compose file
UNSTRUCTURED_API_URL="http://localhost:8000"

# Check if Unstructured API is running
if ! curl -s "$UNSTRUCTURED_API_URL/healthcheck" | grep -q "HEALTHCHECK STATUS: EVERYTHING OK"; then
  echo "ERROR: Unstructured API is not running or unreachable at $UNSTRUCTURED_API_URL"
  echo "Please run the Unstructured API container with:"
  echo "docker run --platform linux/amd64 -p 8000:8000 -d --name unstructured-api downloads.unstructured.io/unstructured-io/unstructured-api:latest"
  rm -rf "$TEMP_DIR"
  exit 1
else
  echo "PASS: Unstructured API is running and healthy"
fi

# Generate a test API key if none is provided (will only be used for testing)
TEST_API_KEY=${UNSTRUCTURED_API_KEY:-"test-api-key-$(date +%s)"}

# Test file processing
echo "Testing file processing with Unstructured API..."
RESPONSE=$(curl -s -X POST "$UNSTRUCTURED_API_URL/general/v0/general" \
  -H "accept: application/json" \
  -H "Content-Type: multipart/form-data" \
  -H "unstructured-api-key: $TEST_API_KEY" \
  -F "files=@$TEST_FILE" \
  -F "strategy=auto")

# Check if response contains the expected content
if echo "$RESPONSE" | grep -q "This is a test document"; then
  echo "PASS: Unstructured API successfully processed the test file"
else
  echo "ERROR: Unstructured API failed to process the test file"
  echo "Response: $RESPONSE"
  rm -rf "$TEMP_DIR"
  exit 1
fi

# Clean up
rm -rf "$TEMP_DIR"
echo "All Unstructured API health checks passed!"
exit 0 