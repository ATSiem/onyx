import pytest
from unittest.mock import MagicMock, patch

import requests
from onyx.connectors.azure_devops.connector import AzureDevOpsConnector
from onyx.connectors.exceptions import ConnectorMissingCredentialError, ConnectorValidationError


class TestAzureDevOpsCredentialFlow:
    """Test the credential flow for the Azure DevOps connector."""

    def test_credential_flow(self):
        """Test the full credential flow for Azure DevOps connector."""
        # Step 1: Initialize the connector with organization and project
        connector = AzureDevOpsConnector(
            organization="testorg", 
            project="testproject"
        )
        
        # Verify initial state - no credentials loaded
        assert connector.personal_access_token is None
        assert connector.client_config == {}
        
        # Step 2: Load credentials (PAT only)
        connector.load_credentials({
            "personal_access_token": "test_token"
        })
        
        # Verify credentials loaded correctly
        assert connector.personal_access_token == "test_token"
        assert connector.client_config != {}
        assert connector.client_config["organization"] == "testorg"
        assert connector.client_config["project"] == "testproject"
        assert connector.client_config["base_url"] == "https://dev.azure.com/testorg/testproject/"
        assert connector.client_config["auth"] is not None
        
        # Step 3: Validate with a simulated API call
        with patch("requests.request") as mock_request:
            # Mock successful API responses
            org_response = MagicMock()
            org_response.status_code = 200
            org_response.json.return_value = {
                "count": 1,
                "value": [
                    {
                        "id": "project-id-123",
                        "name": "testproject",
                        "url": "https://dev.azure.com/testorg/_apis/projects/project-id-123"
                    }
                ]
            }
            
            types_response = MagicMock()
            types_response.status_code = 200
            types_response.json.return_value = {
                "count": 2,
                "value": [
                    {"name": "Bug"},
                    {"name": "Task"}
                ]
            }
            
            # Set up multiple response sequence
            mock_request.side_effect = [org_response, types_response]
            
            # Should not raise an exception
            connector.validate_connector_settings()
            
            # Verify correct API calls were made
            assert mock_request.call_count == 2
            assert "_apis/projects" in mock_request.call_args_list[0][1]["url"]
    
    def test_credential_flow_missing_token(self):
        """Test the credential flow with missing token."""
        connector = AzureDevOpsConnector(
            organization="testorg", 
            project="testproject"
        )
        
        # Empty credentials should raise exception
        with pytest.raises(ConnectorMissingCredentialError):
            connector.load_credentials({})
        
        # Wrong credential key should raise exception
        with pytest.raises(ConnectorMissingCredentialError):
            connector.load_credentials({"wrong_key": "value"})
    
    @patch("requests.request")
    def test_credential_flow_invalid_token(self, mock_request):
        """Test the credential flow with invalid token."""
        connector = AzureDevOpsConnector(
            organization="testorg", 
            project="testproject"
        )
        
        # Load credentials with a token
        connector.load_credentials({
            "personal_access_token": "invalid_token"
        })
        
        # Mock failed API response
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = requests.exceptions.RequestException(
            "Unauthorized: Authentication failed"
        )
        mock_request.return_value = mock_response
        
        # Should raise a validation error
        with pytest.raises(ConnectorValidationError):
            connector.validate_connector_settings()
            
    def test_no_direct_personal_access_token(self):
        """Test that personal_access_token cannot be passed directly to the connector."""
        # This should raise TypeError because personal_access_token is not an expected parameter
        with pytest.raises(TypeError):
            AzureDevOpsConnector(
                organization="testorg",
                project="testproject",
                personal_access_token="test_token"  # This should cause an error
            ) 