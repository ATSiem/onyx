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
        
        # First mock the organization API call to return a list of projects
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
        
        # Then mock the work item types API call
        types_response = MagicMock()
        types_response.status_code = 200
        types_response.json.return_value = {
            "count": 2,
            "value": [
                {"name": "Bug"},
                {"name": "Task"}
            ]
        }
        
        # Setup the mock to return different responses for different calls
        mock_request.side_effect = [org_response, types_response]
        
        # Should not raise an exception
        connector.validate_connector_settings()
        
        # Verify the calls were made with correct URLs
        assert mock_request.call_count == 2
        first_call = mock_request.call_args_list[0]
        assert "_apis/projects" in first_call[1]["url"]
        
        second_call = mock_request.call_args_list[1]
        assert "_apis/wit/workitemtypes" in second_call[1]["url"]
        assert second_call[1]["params"]["project"] == "testproject"

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

    @patch("requests.request")
    def test_authentication_failure_401(self, mock_request):
        """Test that 401 authentication errors are properly handled with clear error messages."""
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
            "api_version": "7.0",
            "alt_base_url": "https://testorg.visualstudio.com/testproject/"
        }
        
        # Mock 401 Unauthorized response
        mock_response = MagicMock()
        http_error = requests.exceptions.HTTPError("401 Client Error: Unauthorized")
        http_error.response = MagicMock()
        http_error.response.status_code = 401
        mock_response.raise_for_status.side_effect = http_error
        mock_response.status_code = 401
        mock_request.return_value = mock_response
        
        # Test the error handling and message
        with pytest.raises(ConnectorValidationError) as exc_info:
            connector.validate_connector_settings()
            
        # Verify the error message is user-friendly and specific
        error_message = str(exc_info.value)
        assert "Authentication failed" in error_message
        assert "Personal Access Token" in error_message
        assert "expired" in error_message
        assert "sufficient scopes" in error_message
        
        # Verify the organization-level URL was used
        assert mock_request.call_count == 1
        first_call_args = mock_request.call_args_list[0]
        assert "dev.azure.com/testorg/_apis/projects" in first_call_args[1]["url"]
        assert "testproject" not in first_call_args[1]["url"]

    @patch("requests.request")
    def test_get_work_item_details_includes_project(self, mock_request):
        """Test that the _get_work_item_details method includes the project parameter."""
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
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "count": 2,
            "value": [
                {"id": 123, "fields": {"System.Title": "Test Item 1"}},
                {"id": 456, "fields": {"System.Title": "Test Item 2"}}
            ]
        }
        mock_request.return_value = mock_response

        # Call the method
        result = connector._get_work_item_details([123, 456])

        # Verify the request included the project parameter in the URL path, not as a query parameter
        assert mock_request.call_count == 1
        call_args = mock_request.call_args_list[0]

        # Check the URL includes project in path
        assert "testproject/_apis/wit/workitems" in call_args[1]["url"]
        
        # Project shouldn't be in params since it's now in the path
        assert "project" not in call_args[1]["params"]
        
        # Verify other expected params
        assert "ids" in call_args[1]["params"]
        assert call_args[1]["params"]["ids"] == "123,456"

    @patch("requests.request")
    def test_get_work_item_details_url_format(self, mock_request):
        """Test that the work item details API uses the correct URL format with project in path."""
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
        
        # Mock response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"value": []}
        mock_request.return_value = mock_response
        
        # Call the method
        connector._get_work_item_details([1, 2, 3])
        
        # Verify the URL format - project should be in the path, not in query params
        assert mock_request.call_count == 1
        call_args = mock_request.call_args[1]
        
        # Check URL contains project in path
        assert "testproject/_apis/wit/workitems" in call_args["url"]
        
        # Check query params don't have project
        assert "project" not in call_args["params"]
        
        # No $expand parameter should be used since it conflicts with fields
        assert "$expand" not in call_args["params"]
        
        # Validate other expected params are present
        assert "ids" in call_args["params"]
        assert "fields" in call_args["params"]
        
    @patch("requests.request")
    def test_get_work_item_comments_url_format(self, mock_request):
        """Test that the work item comments API uses the correct URL format with project in path."""
        # Setup connector
        connector = AzureDevOpsConnector(
            organization="testorg", 
            project="testproject",
            include_comments=True
        )
        
        connector.client_config = {
            "auth": None,
            "organization": "testorg",
            "project": "testproject",
            "base_url": "https://dev.azure.com/testorg/testproject/",
            "api_version": "7.0"
        }
        
        # Mock response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"comments": []}
        mock_request.return_value = mock_response
        
        # Call the method
        connector._get_work_item_comments(123)
        
        # Verify the URL format - project should be in the path
        assert mock_request.call_count == 1
        call_args = mock_request.call_args[1]
        
        # Check URL contains project in path and the work item ID
        assert "testproject/_apis/wit/workItems/123/comments" in call_args["url"] 

    @patch("requests.request")
    def test_get_work_item_comments_preview_api(self, mock_request):
        """Test that the work item comments API uses the preview flag in the API version."""
        # Setup connector
        connector = AzureDevOpsConnector(
            organization="testorg", 
            project="testproject",
            include_comments=True
        )
        
        connector.client_config = {
            "auth": None,
            "organization": "testorg",
            "project": "testproject",
            "base_url": "https://dev.azure.com/testorg/testproject/",
            "api_version": "7.0"
        }
        
        # Mock response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"comments": []}
        mock_request.return_value = mock_response
        
        # Call the method
        connector._get_work_item_comments(123)
        
        # Verify the API version includes the preview flag
        assert mock_request.call_count == 1
        call_args = mock_request.call_args[1]
        
        # Check API version has preview flag
        assert call_args["params"]["api-version"] == "7.0-preview" 