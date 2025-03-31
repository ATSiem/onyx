import json
import base64
import requests
from unittest.mock import MagicMock, patch

import pytest
from onyx.connectors.azure_devops.connector import AzureDevOpsConnector
from onyx.connectors.exceptions import ConnectorValidationError


@pytest.fixture
def azure_devops_connector():
    """Create a basic Azure DevOps connector for testing."""
    connector = AzureDevOpsConnector(
        organization="deFactoGlobal",
        project="dF-Integrated-Business-Planning"
    )
    connector.client_config = {
        "auth": None,
        "organization": "deFactoGlobal",
        "project": "dF-Integrated-Business-Planning",
        "base_url": "https://dev.azure.com/deFactoGlobal/dF-Integrated-Business-Planning/",
        "api_version": "7.0"
    }
    return connector


@patch("requests.request")
def test_work_items_url_format_regression(mock_request, azure_devops_connector):
    """Regression test to ensure the work items API uses the correct URL format."""
    # Mock response
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"value": []}
    mock_request.return_value = mock_response
    
    # Call the method
    azure_devops_connector._get_work_item_details([123, 456])
    
    # Verify correct URL format
    assert mock_request.call_count == 1
    call_args = mock_request.call_args[1]
    
    # Check project is in path
    assert "dF-Integrated-Business-Planning/_apis/wit/workitems" in call_args["url"]
    
    # Check no project parameter in query and no $expand
    assert "project" not in call_args["params"]
    assert "$expand" not in call_args["params"]
    
    # Check correct parameters
    assert "ids" in call_args["params"]
    assert call_args["params"]["ids"] == "123,456"


@patch("requests.request")
def test_comments_api_url_and_version_regression(mock_request, azure_devops_connector):
    """Regression test to ensure the comments API uses the correct URL format and preview version."""
    # Mock response
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"comments": []}
    mock_request.return_value = mock_response
    
    # Enable comments
    azure_devops_connector.include_comments = True
    
    # Call the method
    azure_devops_connector._get_work_item_comments(123)
    
    # Verify correct URL format
    assert mock_request.call_count == 1
    call_args = mock_request.call_args[1]
    
    # Check project is in path
    assert "dF-Integrated-Business-Planning/_apis/wit/workItems/123/comments" in call_args["url"]
    
    # Check preview flag is used
    assert call_args["params"]["api-version"] == "7.0-preview" 