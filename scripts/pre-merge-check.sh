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

# Run Zulip schema tests
echo "Running Zulip schema compatibility tests..."
python -m pytest tests/unit/connectors/zulip/test_zulip_schema.py -v

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