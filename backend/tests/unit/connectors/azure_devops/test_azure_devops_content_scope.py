#!/usr/bin/env python3
"""
Tests the Azure DevOps connector with different content_scope values.
"""

import logging
import pytest

from onyx.connectors.azure_devops.connector import AzureDevOpsConnector

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

@pytest.mark.parametrize("content_scope,expected_commits_enabled", [
    ("everything", True),
    ("Everything", True),
    ("everything", True),  # Duplicate to test consistency
    ("work_items_only", False)
])
def test_content_scope_value(content_scope, expected_commits_enabled):
    """Test the connector with a specific content_scope value"""
    logger.info(f"Testing with content_scope='{content_scope}'")
    
    # Create connector instance with the given content_scope value
    connector = AzureDevOpsConnector(
        organization="test-org",
        project="test-project",
        content_scope=content_scope
    )
    
    # Check if DATA_TYPE_COMMITS is included in the data_types
    commits_enabled = connector.DATA_TYPE_COMMITS in connector.data_types
    
    logger.info(f"  Content scope: {content_scope}")
    logger.info(f"  Git commits enabled: {commits_enabled}")
    logger.info(f"  Data types: {connector.data_types}")
    
    assert commits_enabled == expected_commits_enabled, f"With content_scope '{content_scope}', commits enabled should be {expected_commits_enabled}"

def test_content_scope_case_sensitivity():
    """Test that both lowercase and uppercase 'everything' variants work correctly"""
    
    # Test lowercase variant
    lowercase_result = connector_with_scope("everything")
    
    # Test uppercase variant
    uppercase_result = connector_with_scope("Everything")
    
    # Test mixed case variant
    mixedcase_result = connector_with_scope("Everything")
    
    # Test work_items_only for comparison
    workitems_result = connector_with_scope("work_items_only")
    
    # Check results
    assert lowercase_result, "'everything' (lowercase) failed to enable Git commits"
    assert uppercase_result, "'Everything' (uppercase) failed to enable Git commits" 
    assert mixedcase_result, "'Everything' (mixed case) failed to enable Git commits"
    
    # Check work_items_only
    assert not workitems_result, "'work_items_only' incorrectly enabled Git commits"

def connector_with_scope(content_scope):
    """Helper function to create a connector with specific content scope and check if commits are enabled"""
    connector = AzureDevOpsConnector(
        organization="test-org",
        project="test-project",
        content_scope=content_scope
    )
    return connector.DATA_TYPE_COMMITS in connector.data_types 