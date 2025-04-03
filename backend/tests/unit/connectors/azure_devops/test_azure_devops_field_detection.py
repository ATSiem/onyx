#!/usr/bin/env python3
"""
Test that the Azure DevOps connector is properly initialized and has the expected methods.
"""

import logging
import pytest

# Configure logging
logging.basicConfig(level=logging.DEBUG, 
                    format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("test_field_detection")

def test_azure_devops_connector_initialization():
    """Test that the Azure DevOps connector can be properly initialized."""
    from onyx.connectors.azure_devops.connector import AzureDevOpsConnector
    
    # Create a connector instance with minimal parameters
    connector = AzureDevOpsConnector(
        organization="test-org",
        project="test-project"
    )
    
    # Verify the connector has expected attributes
    assert hasattr(connector, "organization"), "Connector missing 'organization' attribute"
    assert hasattr(connector, "project"), "Connector missing 'project' attribute"
    assert connector.organization == "test-org"
    assert connector.project == "test-project"
    
    logger.info("Connector initialization test passed")

def test_azure_devops_connector_methods():
    """Test that the Azure DevOps connector has the expected methods."""
    from onyx.connectors.azure_devops.connector import AzureDevOpsConnector
    
    # Verify the connector class has expected methods
    assert hasattr(AzureDevOpsConnector, "_get_work_item_details"), "Connector missing '_get_work_item_details' method"
    assert hasattr(AzureDevOpsConnector, "validate_connector_settings"), "Connector missing 'validate_connector_settings' method"
    assert hasattr(AzureDevOpsConnector, "load_credentials"), "Connector missing 'load_credentials' method"
    
    logger.info("Connector methods test passed") 