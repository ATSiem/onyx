# Azure DevOps Debug and Utility Scripts

This directory contains scripts used to diagnose and fix issues with the Azure DevOps connector. 
These scripts are kept for reference and debugging purposes.

## Scripts

### azure_devops_connector_fix.py
- **Purpose**: Fixes the hardcoded "master" branch issue in the connector
- **Issue**: The connector was failing with "TF401175:The version descriptor <Branch: master> could not be resolved" error
- **Status**: Fix integrated into main connector code - see `connector.py` around line 1788-1789

### branch_detection_fix.py
- **Purpose**: Detects available branches in Azure DevOps repositories
- **Usage**: Run to diagnose branch-related issues with Azure DevOps Git repositories
- **Note**: Useful for troubleshooting branch access issues

### check_devops_connector_config.py
- **Purpose**: Validates the Azure DevOps connector configuration
- **Usage**: Run to check if the connector is properly configured

### debug_azure_devops_connector.py
- **Purpose**: General debugging script for the Azure DevOps connector
- **Usage**: Run to output detailed logs of connector operations

### list_azure_devops_projects.py
- **Purpose**: Lists available projects in an Azure DevOps organization
- **Usage**: Run to verify project access and check available projects

### verify_azure_pat_permissions.py
- **Purpose**: Verifies if a Personal Access Token (PAT) has sufficient permissions
- **Usage**: Run to check if a PAT has all required permissions for the connector to function properly

## Notes

These scripts were used to diagnose and fix issues with the Azure DevOps connector, particularly related to:
1. Case sensitivity in content_scope parameter
2. Git commit access with different branch names
3. PAT permission verification

The fixes implemented by these scripts have been integrated into the main codebase and are covered by tests in `backend/tests/unit/connectors/azure_devops/`. 