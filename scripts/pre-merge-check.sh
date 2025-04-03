#!/bin/bash

# Script to run regression tests before merging changes from upstream
# This helps ensure custom fixes in this fork aren't broken by upstream changes

set -e  # Exit on error

echo "Running regression tests before merge..."
ROOT_DIR="$(git rev-parse --show-toplevel)"
FAILED_TESTS=()
SUCCESS=true

# Print section header
print_header() {
  echo
  echo "==============================================="
  echo "  $1"
  echo "==============================================="
  echo
}

# Run a test and track failures
run_test() {
  local test_name=$1
  local test_cmd=$2
  
  echo "🔍 Running $test_name..."
  
  if eval "$test_cmd"; then
    echo "✅ $test_name passed"
  else
    echo "❌ $test_name failed"
    FAILED_TESTS+=("$test_name")
    SUCCESS=false
    # Exit immediately on regression test failure
    return 1
  fi
  echo
}

# Check if Docker is running
check_docker() {
  if ! docker info > /dev/null 2>&1; then
    echo "⚠️ Warning: Docker is not running. Some tests will be skipped."
    echo "Please start Docker Desktop to run all tests."
    return 1
  fi
  return 0
}

# Run backend regression tests
print_header "REGRESSION TESTS"

# LLM Model Filtering
run_test "LLM Provider Options" "cd $ROOT_DIR/backend && source ../.venv/bin/activate && python -m pytest tests/unit/onyx/llm/test_llm_provider_options.py -v" || exit 1

# Email Invites
run_test "Email Invites" "cd $ROOT_DIR/backend && source ../.venv/bin/activate && python -m pytest tests/unit/test_email_invites.py -v" || exit 1

# Zulip schema tests
print_header "CONNECTOR TESTS"
run_test "Zulip Schema Compatibility" "cd $ROOT_DIR/backend && source ../.venv/bin/activate && python -m pytest tests/unit/connectors/zulip/test_zulip_schema.py -v" || exit 1

# Azure DevOps tests
run_test "Azure DevOps Content Scope" "cd $ROOT_DIR/backend && source ../.venv/bin/activate && python -m pytest tests/unit/connectors/azure_devops/test_azure_devops_content_scope.py -v" || exit 1
run_test "Azure DevOps Git Commits" "cd $ROOT_DIR/backend && source ../.venv/bin/activate && python -m pytest tests/unit/connectors/azure_devops/test_azure_devops_git_commits.py -v" || exit 1

# Check if Docker is running before trying to run Docker-dependent tests
if check_docker; then
  print_header "UNSTRUCTURED API TESTS"
  
  # Ensure Unstructured API is running
  run_test "Ensure Unstructured API" "$ROOT_DIR/scripts/ensure_unstructured_api.sh" || exit 1
  
  # Run Unstructured API integration check
  run_test "Unstructured API Integration" "$ROOT_DIR/scripts/check_unstructured_integration.sh" || exit 1

  # Run Unstructured API health check
  run_test "Unstructured API Health" "$ROOT_DIR/scripts/test_unstructured_api_health.sh" || exit 1
fi

# Summary
print_header "TEST SUMMARY"

if [ "$SUCCESS" = true ]; then
  echo "🎉 All pre-merge regression tests passed successfully!"
  exit 0
else
  echo "❌ The following tests failed:"
  for test in "${FAILED_TESTS[@]}"; do
    echo "  - $test"
  done
  echo
  echo "❌ Pre-merge tests failed. Please fix these issues before merging."
  exit 1
fi 