import pytest
from unittest.mock import MagicMock, patch

import requests
from onyx.connectors.azure_devops.connector import AzureDevOpsConnector
from onyx.connectors.exceptions import ConnectorValidationError


class TestAzureDevOpsRegressions:
    """Regression tests for the Azure DevOps connector based on real-world issues."""

    @patch("requests.request")
    def test_regression_project_api_401_error(self, mock_request):
        """Regression test for the specific 401 error on the projects API endpoint.
        
        This test reproduces the exact error pattern observed in production:
        401 Client Error: Unauthorized for url: https://dev.azure.com/deFactoGlobal/dF-Integrated-Business-Planning/_apis/projects/dF-Integrated-Business-Planning?api-version=7.0
        """
        # Setup connector with a complex project name that includes hyphens
        connector = AzureDevOpsConnector(
            organization="deFactoGlobal", 
            project="dF-Integrated-Business-Planning"
        )
        
        connector.client_config = {
            "auth": None,
            "organization": "deFactoGlobal",
            "project": "dF-Integrated-Business-Planning",
            "base_url": "https://dev.azure.com/deFactoGlobal/dF-Integrated-Business-Planning/",
            "api_version": "7.0",
            "alt_base_url": "https://deFactoGlobal.visualstudio.com/dF-Integrated-Business-Planning/"
        }
        
        # Mock the 401 Unauthorized response
        mock_response = MagicMock()
        url = "https://dev.azure.com/deFactoGlobal/_apis/projects?api-version=7.0"
        http_error = requests.exceptions.HTTPError(f"401 Client Error: Unauthorized for url: {url}")
        http_error.response = MagicMock()
        http_error.response.status_code = 401
        mock_response.raise_for_status.side_effect = http_error
        mock_response.status_code = 401
        mock_request.return_value = mock_response
        
        # Test the error handling and message
        with pytest.raises(ConnectorValidationError) as exc_info:
            connector.validate_connector_settings()
            
        # Verify the error message contains the expected information
        error_message = str(exc_info.value)
        assert "Authentication failed" in error_message
        assert "Personal Access Token" in error_message
        assert "expired" in error_message
        assert "sufficient scopes" in error_message
        
        # Verify the request was made with the correct URL (organization-level endpoint)
        call_args = mock_request.call_args_list[0]
        assert "deFactoGlobal" in call_args[1]["url"]
        assert "_apis/projects" in call_args[1]["url"]

    @patch("requests.request")
    def test_regression_expired_pat_error_message(self, mock_request):
        """Test that the error message specifically suggests checking for expired tokens."""
        # Setup connector
        connector = AzureDevOpsConnector(
            organization="testorg", 
            project="testproject"
        )
        
        connector.client_config = {
            "auth": None,
            "organization": "testorg",
            "project": "testproject",
            "base_url": "https://dev.azure.com/testorg/testproject/",
            "api_version": "7.0"
        }
        
        # Mock a response that includes a message about token expiration
        mock_response = MagicMock()
        http_error = requests.exceptions.HTTPError("401 Client Error: Unauthorized")
        http_error.response = MagicMock()
        http_error.response.status_code = 401
        http_error.response.json.return_value = {
            "message": "TF400813: The user 'X-MS-VSS-Token' could not be authenticated."
        }
        mock_response.raise_for_status.side_effect = http_error
        mock_response.status_code = 401
        mock_response.json.return_value = {
            "message": "TF400813: The user 'X-MS-VSS-Token' could not be authenticated."
        }
        mock_request.return_value = mock_response
        
        # Test the error handling and message
        with pytest.raises(ConnectorValidationError) as exc_info:
            connector.validate_connector_settings()
            
        # Verify the error message mentions token expiration
        error_message = str(exc_info.value)
        assert "Authentication failed" in error_message
        assert "Personal Access Token" in error_message
        assert "expired" in error_message 