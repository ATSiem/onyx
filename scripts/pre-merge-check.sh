#!/bin/bash

# Script to run regression tests before merging changes from upstream
# This helps ensure custom fixes in this fork aren't broken by upstream changes

set -e  # Exit on error

echo "Running regression tests before merge..."

# Run backend regression tests
cd "$(git rev-parse --show-toplevel)/backend"
echo "Running backend regression tests..."
python -m pytest tests/unit/onyx/llm/test_llm_provider_options.py -v
python -m pytest tests/unit/test_email_invites.py -v

# Run Unstructured API integration check
echo "Running Unstructured API integration check..."
cd "$(git rev-parse --show-toplevel)"
./scripts/check_unstructured_integration.sh

# Run frontend regression tests
cd "$(git rev-parse --show-toplevel)/web"
echo "Running frontend regression tests..."
npm test -- src/components/llm/LLMSelector.test.tsx

echo "All regression tests passed!"
exit 0 