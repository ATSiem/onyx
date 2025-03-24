import inspect
import pytest
from unittest.mock import MagicMock, patch

import requests
from onyx.connectors.azure_devops.connector import AzureDevOpsConnector
from onyx.connectors.azure_devops.connector import AzureDevOpsConnectorCheckpoint
from onyx.connectors.exceptions import ConnectorMissingCredentialError, ConnectorValidationError


class TestAzureDevOpsConnector:
    """Test basic functionality of the Azure DevOps connector."""

    def test_init(self):
        """Test that the connector initializes with the expected attributes."""
        # Basic initialization
        connector = AzureDevOpsConnector(
            organization="testorg", 
            project="testproject"
        )
        
        assert connector.organization == "testorg"
        assert connector.project == "testproject"
        assert connector.work_item_types == ["Bug", "Epic", "Feature", "Issue", "Task", "TestCase", "UserStory"]
        assert connector.include_comments is True
        assert connector.include_attachments is False
        assert connector.client_config == {}
        assert connector.personal_access_token is None
        
        # Custom initialization
        connector = AzureDevOpsConnector(
            organization="testorg", 
            project="testproject",
            work_item_types=["Bug", "Task"],
            include_comments=False,
            include_attachments=True
        )
        
        assert connector.work_item_types == ["Bug", "Task"]
        assert connector.include_comments is False
        assert connector.include_attachments is True

    def test_load_credentials_missing(self):
        """Test that the connector raises an exception when credentials are missing."""
        connector = AzureDevOpsConnector(
            organization="testorg", 
            project="testproject"
        )
        
        with pytest.raises(ConnectorMissingCredentialError):
            connector.load_credentials({})
            
        with pytest.raises(ConnectorMissingCredentialError):
            connector.load_credentials({"invalid_key": "value"})

    def test_load_credentials_success(self):
        """Test that the connector loads credentials successfully."""
        connector = AzureDevOpsConnector(
            organization="testorg", 
            project="testproject"
        )
        
        result = connector.load_credentials({
            "personal_access_token": "test_token"
        })
        
        assert result is None  # Should return None as per interface
        assert connector.personal_access_token == "test_token"
        assert connector.client_config != {}  # Should have been populated
        assert connector.client_config["organization"] == "testorg"
        assert connector.client_config["project"] == "testproject"
        assert connector.client_config["base_url"] == "https://dev.azure.com/testorg/testproject/"

    @patch("requests.request")
    def test_validate_connector_settings_error(self, mock_request):
        """Test validation when the connector settings are invalid."""
        # Setup connector without client config
        connector = AzureDevOpsConnector(
            organization="testorg", 
            project="testproject"
        )
        
        # Test without client config
        with pytest.raises(ConnectorValidationError):
            connector.validate_connector_settings()
        
        # Setup connector with client config but API error
        connector.client_config = {
            "auth": None,
            "organization": "testorg",
            "project": "testproject",
            "base_url": "https://dev.azure.com/testorg/testproject/",
            "api_version": "7.0"
        }
        
        # Mock API error
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = requests.exceptions.RequestException("Test error")
        mock_request.return_value = mock_response
        
        # Test with API error
        with pytest.raises(ConnectorValidationError):
            connector.validate_connector_settings()

    @patch("requests.request")
    def test_validate_connector_settings_success(self, mock_request):
        """Test validation when the connector settings are valid."""
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
        
        # Mock successful API response
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_request.return_value = mock_response
        
        # Should not raise an exception
        connector.validate_connector_settings()

    def test_build_dummy_checkpoint(self):
        """Test that the connector builds a dummy checkpoint correctly."""
        connector = AzureDevOpsConnector(
            organization="testorg", 
            project="testproject"
        )
        
        checkpoint = connector.build_dummy_checkpoint()
        
        assert isinstance(checkpoint, AzureDevOpsConnectorCheckpoint)
        assert checkpoint.has_more is True
        assert checkpoint.continuation_token is None

    def test_validate_checkpoint_json(self):
        """Test that the connector validates checkpoint JSON correctly."""
        connector = AzureDevOpsConnector(
            organization="testorg", 
            project="testproject"
        )
        
        # Valid checkpoint
        valid_json = '{"has_more": true, "continuation_token": "test_token"}'
        checkpoint = connector.validate_checkpoint_json(valid_json)
        
        assert isinstance(checkpoint, AzureDevOpsConnectorCheckpoint)
        assert checkpoint.has_more is True
        assert checkpoint.continuation_token == "test_token"
        
        # Invalid JSON should raise exception
        with pytest.raises(Exception):
            connector.validate_checkpoint_json("invalid json{") 