#!/usr/bin/env python3
"""
Tests to verify data types configuration in Azure DevOps connector.
"""

import pytest
from onyx.connectors.azure_devops.connector import AzureDevOpsConnector

def test_content_scope_everything_enables_all_data_types():
    """Test that 'everything' content scope enables all data types including commits"""
    # Create connector with content_scope=everything
    connector = AzureDevOpsConnector(
        organization="test-org",
        project="test-project",
        content_scope="everything"
    )
    
    # Verify that commits data type is enabled
    assert connector.DATA_TYPE_COMMITS in connector.data_types, "Commits data type should be enabled with content_scope='everything'"
    
    # Verify that work items data type is enabled
    assert connector.DATA_TYPE_WORK_ITEMS in connector.data_types, "Work items data type should be enabled with content_scope='everything'"
    
def test_content_scope_work_items_only():
    """Test that 'work_items_only' content scope disables commits data type"""
    # Create connector with content_scope=work_items_only
    connector = AzureDevOpsConnector(
        organization="test-org",
        project="test-project",
        content_scope="work_items_only"
    )
    
    # Verify that commits data type is NOT enabled
    assert connector.DATA_TYPE_COMMITS not in connector.data_types, "Commits data type should NOT be enabled with content_scope='work_items_only'"
    
    # Verify that work items data type is still enabled
    assert connector.DATA_TYPE_WORK_ITEMS in connector.data_types, "Work items data type should be enabled with content_scope='work_items_only'" 