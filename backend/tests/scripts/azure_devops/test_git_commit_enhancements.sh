#!/bin/bash
# Script to test the Azure DevOps Git commit enhancements

set -e

echo "===================================================="
echo "TESTING AZURE DEVOPS GIT COMMIT ENHANCEMENTS"
echo "===================================================="

# Get script directory
SCRIPT_DIR=$(dirname "$(readlink -f "$0")")
BACKEND_DIR=$(realpath "$SCRIPT_DIR/../../../")

cd "$BACKEND_DIR"

echo "Running Git commit tests..."
python -m pytest tests/unit/connectors/azure_devops/test_azure_devops_git.py::TestAzureDevOpsGitConnector::test_get_commits tests/unit/connectors/azure_devops/test_azure_devops_git.py::TestAzureDevOpsGitConnector::test_process_commit_with_work_items -v

echo "Running slim document tests..."
python -m pytest tests/unit/connectors/azure_devops/test_azure_devops_slim_docs.py::TestAzureDevOpsSlimDocs::test_slim_documents_for_git_commits -v

echo "Tests completed!"

# Check if we're running in a development environment
if [ -f "./data/onyx.db" ]; then
    echo "Development database found. Would you like to check for existing Azure DevOps connectors? (y/n)"
    read -r check_connectors
    
    if [ "$check_connectors" = "y" ]; then
        python tests/scripts/azure_devops/check_devops_connector_config.py
        
        echo "To reindex your Azure DevOps connector with the new improvements:"
        echo "1. Go to the Onyx admin interface"
        echo "2. Navigate to the Connectors page"
        echo "3. Find your Azure DevOps connector"
        echo "4. Click 'Run Connector Now'"
    fi
fi 