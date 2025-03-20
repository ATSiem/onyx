#!/bin/bash

# Script to check for Unstructured API integration files and code references
# This is run as part of the pre-merge check to ensure fork-specific customizations are preserved

set -e  # Exit on error

echo "Checking Unstructured API integration..."

# Get the repository root directory
REPO_ROOT=$(git rev-parse --show-toplevel)
cd "$REPO_ROOT"

# Check that unstructured.py exists
if [ ! -f "backend/onyx/file_processing/unstructured.py" ]; then
  echo "FAIL: unstructured.py does not exist!"
  exit 1
else
  echo "PASS: unstructured.py exists"
fi

# Check for Unstructured API key management functions in unstructured.py
grep -q "def get_unstructured_api_key" "backend/onyx/file_processing/unstructured.py" || { echo "FAIL: get_unstructured_api_key function not found!"; exit 1; }
grep -q "def update_unstructured_api_key" "backend/onyx/file_processing/unstructured.py" || { echo "FAIL: update_unstructured_api_key function not found!"; exit 1; }
grep -q "def delete_unstructured_api_key" "backend/onyx/file_processing/unstructured.py" || { echo "FAIL: delete_unstructured_api_key function not found!"; exit 1; }
grep -q "def unstructured_to_text" "backend/onyx/file_processing/unstructured.py" || { echo "FAIL: unstructured_to_text function not found!"; exit 1; }
echo "PASS: Unstructured API key management functions exist"

# Check that extract_file_text.py imports unstructured API functions
grep -q "from onyx.file_processing.unstructured import get_unstructured_api_key" "backend/onyx/file_processing/extract_file_text.py" || { echo "FAIL: extract_file_text.py does not import get_unstructured_api_key!"; exit 1; }
grep -q "from onyx.file_processing.unstructured import unstructured_to_text" "backend/onyx/file_processing/extract_file_text.py" || { echo "FAIL: extract_file_text.py does not import unstructured_to_text!"; exit 1; }
echo "PASS: extract_file_text.py imports Unstructured API functions"

# Check that extract_file_text uses Unstructured API
grep -q "if get_unstructured_api_key():" "backend/onyx/file_processing/extract_file_text.py" || { echo "FAIL: extract_file_text does not check for Unstructured API key!"; exit 1; }
grep -q "return unstructured_to_text(file, file_name)" "backend/onyx/file_processing/extract_file_text.py" || { echo "FAIL: extract_file_text does not use unstructured_to_text!"; exit 1; }
echo "PASS: extract_file_text uses Unstructured API"

# Check for Unstructured API URL in docker-compose files
grep -q "UNSTRUCTURED_API_URL=http://host.docker.internal:8000" "deployment/docker_compose/docker-compose.dev.yml" || { echo "FAIL: UNSTRUCTURED_API_URL not found in docker-compose.dev.yml!"; exit 1; }
grep -q "UNSTRUCTURED_API_URL=http://host.docker.internal:8000" "deployment/docker_compose/docker-compose.prod.yml" || { echo "FAIL: UNSTRUCTURED_API_URL not found in docker-compose.prod.yml!"; exit 1; }
echo "PASS: Docker Compose files contain UNSTRUCTURED_API_URL"

# Check for Unstructured API key setting in API endpoints
grep -q "unstructured_api_key" "backend/onyx/server/manage/search_settings.py" || { echo "FAIL: Unstructured API key settings not found in search_settings.py!"; exit 1; }
echo "PASS: API endpoints for Unstructured API key management exist"

echo "All Unstructured API integration checks passed!"
exit 0 