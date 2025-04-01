#!/usr/bin/env python3
"""
This script verifies that the Azure DevOps connector correctly handles content_scope
values sent from the simplified UI.

Usage:
    python verify_azure_devops_connector.py
"""
import sys
import json
import logging
from typing import List, Optional, Dict, Any

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

try:
    from onyx.connectors.azure_devops.connector import AzureDevOpsConnector
except ImportError:
    logger.error("Failed to import AzureDevOpsConnector. Make sure you're running this script from the correct environment.")
    sys.exit(1)

def test_content_scope_handling():
    """Test that content_scope correctly controls data_types"""
    
    # Test Case 1: content_scope = "work_items_only" (default radio option)
    logger.info("=== Test Case 1: content_scope = 'work_items_only' (default option) ===")
    connector1 = AzureDevOpsConnector(
        organization="test-org",
        project="test-project",
        content_scope="work_items_only"
    )
    logger.info(f"data_types: {connector1.data_types}")
    assert "work_items" in connector1.data_types, "work_items should be in data_types"
    assert len(connector1.data_types) == 1, "Only work_items should be in data_types"
    
    # Test Case 2: content_scope = "everything" (selected radio option)
    logger.info("=== Test Case 2: content_scope = 'everything' (selected option) ===")
    connector2 = AzureDevOpsConnector(
        organization="test-org",
        project="test-project",
        content_scope="everything"
    )
    logger.info(f"data_types: {connector2.data_types}")
    
    # Verify all expected data types are included
    expected_types = [
        "work_items", 
        "commits", 
        "test_results", 
        "test_stats", 
        "releases", 
        "release_details", 
        "wikis"
    ]
    for data_type in expected_types:
        assert data_type in connector2.data_types, f"{data_type} should be in data_types"
    
    # Test Case 3: No content_scope specified (UI didn't send it)
    logger.info("=== Test Case 3: No content_scope specified (UI default handling) ===")
    connector3 = AzureDevOpsConnector(
        organization="test-org",
        project="test-project",
    )
    logger.info(f"data_types: {connector3.data_types}")
    
    # Should default to work_items only
    assert "work_items" in connector3.data_types, "work_items should be in data_types"
    assert len(connector3.data_types) == 1, "Only work_items should be in data_types when no content_scope is specified"
    
    logger.info("All tests passed successfully!")
    return True

if __name__ == "__main__":
    try:
        success = test_content_scope_handling()
        sys.exit(0 if success else 1)
    except Exception as e:
        logger.error(f"Test failed with exception: {e}")
        sys.exit(1) 