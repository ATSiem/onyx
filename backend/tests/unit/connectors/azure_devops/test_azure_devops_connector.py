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

        # Mock successful API response for both essential and additional fields
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "count": 2,
            "value": [
                {"id": 123, "fields": {"System.Title": "Test Item 1"}},
                {"id": 456, "fields": {"System.Title": "Test Item 2"}}
            ]
        }
        # Set same response for both calls
        mock_request.return_value = mock_response

        # Call the method
        result = connector._get_work_item_details([123, 456])

        # Verify the request included the project parameter in the URL path, not as a query parameter
        # We expect 2 calls now due to splitting fields into essential and additional
        assert mock_request.call_count == 2
        
        # Check both calls to ensure project is in the URL path
        for call_args in mock_request.call_args_list:
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

    @patch("onyx.connectors.azure_devops.connector.AzureDevOpsConnector._get_work_items")
    @patch("onyx.connectors.azure_devops.connector.AzureDevOpsConnector._get_work_item_details")
    @patch("onyx.connectors.azure_devops.connector.AzureDevOpsConnector._process_work_item")
    def test_load_from_checkpoint_generator(self, mock_process_work_item, mock_get_details, mock_get_items):
        """Test that load_from_checkpoint correctly yields Document or ConnectorFailure objects one at a time."""
        # Setup connector
        connector = AzureDevOpsConnector(
            organization="testorg", 
            project="testproject"
        )
        
        connector.personal_access_token = "test_token"
        connector.client_config = {
            "auth": None,
            "organization": "testorg",
            "project": "testproject",
            "base_url": "https://dev.azure.com/testorg/testproject/",
            "api_version": "7.0"
        }
        
        # Mock the _get_work_items response
        mock_get_items.return_value = {
            "workItems": [
                {"id": 123},
                {"id": 456}
            ],
            "continuationToken": "next_token"
        }
        
        # Mock the _get_work_item_details response
        mock_get_details.return_value = [
            {
                "id": 123,
                "fields": {
                    "System.Title": "Test Bug",
                    "System.WorkItemType": "Bug",
                    "System.State": "Active",
                    "System.CreatedDate": "2023-01-01T00:00:00Z",
                    "System.ChangedDate": "2023-01-02T00:00:00Z",
                    "System.Description": "Test description"
                }
            },
            {
                "id": 456,
                "fields": {
                    "System.Title": "Test Task",
                    "System.WorkItemType": "Task",
                    "System.State": "New",
                    "System.CreatedDate": "2023-01-03T00:00:00Z",
                    "System.ChangedDate": "2023-01-04T00:00:00Z",
                    "System.Description": "Another test description"
                }
            }
        ]
        
        # Mock _process_work_item to return proper Documents
        from onyx.connectors.models import Document, TextSection
        from onyx.configs.constants import DocumentSource
        
        def create_mock_document(work_item, comments=None):
            work_item_id = work_item["id"]
            fields = work_item["fields"]
            title = fields.get("System.Title", "")
            work_item_type = fields.get("System.WorkItemType", "")
            description = fields.get("System.Description", "")
            
            return Document(
                id=f"azuredevops:testorg/testproject/workitem/{work_item_id}",
                source=DocumentSource.AZURE_DEVOPS,
                title=f"[Not Resolved] {work_item_type} {work_item_id}: {title} [Not Resolved]",
                semantic_identifier=f"Work Item {work_item_id}: {title}",
                sections=[
                    TextSection(
                        text=description,
                        link=f"https://dev.azure.com/testorg/testproject/_workitems/edit/{work_item_id}"
                    )
                ],
                metadata={}
            )
        
        # Setup the mock function
        mock_process_work_item.side_effect = create_mock_document
        
        # Create a checkpoint
        checkpoint = AzureDevOpsConnectorCheckpoint(
            has_more=True,
            continuation_token="test_token"
        )
        
        # Get the generator
        generator = connector.load_from_checkpoint(
            start=1672531200,  # 2023-01-01T00:00:00Z
            end=1672617600,    # 2023-01-02T00:00:00Z
            checkpoint=checkpoint
        )
        
        # Use CheckpointOutputWrapper to wrap the generator
        from onyx.connectors.connector_runner import CheckpointOutputWrapper
        
        # Collect all yielded items
        documents = []
        failures = []
        final_checkpoint = None
        
        # Use the wrapper as it's used in production
        wrapper = CheckpointOutputWrapper[AzureDevOpsConnectorCheckpoint]()
        wrapped_generator = wrapper(generator)
        
        for doc, failure, next_checkpoint in wrapped_generator:
            if doc is not None:
                documents.append(doc)
            if failure is not None:
                failures.append(failure)
            if next_checkpoint is not None:
                final_checkpoint = next_checkpoint
        
        # Check that we got the expected number of documents
        assert len(documents) == 2
        
        # Verify Document structure
        assert documents[0].id == "azuredevops:testorg/testproject/workitem/123"
        assert "[Not Resolved] Bug 123: Test Bug [Not Resolved]" == documents[0].title
        # Check text in the sections
        assert documents[0].sections[0].text == "Test description"
        
        assert documents[1].id == "azuredevops:testorg/testproject/workitem/456"  
        assert "[Not Resolved] Task 456: Test Task [Not Resolved]" == documents[1].title
        # Check text in the sections
        assert documents[1].sections[0].text == "Another test description"
        
        # Verify no failures
        assert len(failures) == 0
        
        # Verify we received a checkpoint
        assert final_checkpoint is not None
        assert isinstance(final_checkpoint, AzureDevOpsConnectorCheckpoint)
        assert final_checkpoint.has_more is True
        assert final_checkpoint.continuation_token == "next_token"
        
        # Verify mock calls
        mock_get_items.assert_called_once()
        assert mock_get_details.call_count == 1
        assert mock_process_work_item.call_count == 2 

    @patch("onyx.connectors.azure_devops.connector.AzureDevOpsConnector._get_work_items")
    def test_load_from_checkpoint_error_handling(self, mock_get_items):
        """Test that load_from_checkpoint correctly handles API errors and yields the checkpoint."""
        # Setup connector
        connector = AzureDevOpsConnector(
            organization="testorg", 
            project="testproject"
        )
        
        connector.personal_access_token = "test_token"
        connector.client_config = {
            "auth": None,
            "organization": "testorg",
            "project": "testproject",
            "base_url": "https://dev.azure.com/testorg/testproject/",
            "api_version": "7.0"
        }
        
        # Mock API error
        mock_get_items.side_effect = requests.exceptions.RequestException("Test API error")
        
        # Create a checkpoint
        checkpoint = AzureDevOpsConnectorCheckpoint(
            has_more=True,
            continuation_token="test_token"
        )
        
        # Get the generator
        generator = connector.load_from_checkpoint(
            start=1672531200,  # 2023-01-01T00:00:00Z
            end=1672617600,    # 2023-01-02T00:00:00Z
            checkpoint=checkpoint
        )
        
        # Use CheckpointOutputWrapper to wrap the generator
        from onyx.connectors.connector_runner import CheckpointOutputWrapper
        
        # Collect all yielded items
        failures = []
        final_checkpoint = None
        
        # Use the wrapper as it's used in production
        wrapper = CheckpointOutputWrapper[AzureDevOpsConnectorCheckpoint]()
        wrapped_generator = wrapper(generator)
        
        for doc, failure, next_checkpoint in wrapped_generator:
            # In the error handling test, we don't expect any documents, only failures
            if failure is not None:
                failures.append(failure)
            if next_checkpoint is not None:
                final_checkpoint = next_checkpoint
        
        # Verify we got an entity failure
        assert len(failures) == 1
        assert hasattr(failures[0], 'entity_id')
        assert failures[0].entity_id == "azure_devops_work_items"
        
        # Verify we received the original checkpoint back
        assert final_checkpoint is not None
        assert isinstance(final_checkpoint, AzureDevOpsConnectorCheckpoint)
        assert final_checkpoint.has_more is True
        assert final_checkpoint.continuation_token == "test_token" 

    @patch("requests.request")
    def test_get_work_item_details_split_field_requests(self, mock_request):
        """Test that _get_work_item_details handles large field sets by splitting requests."""
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
        
        # Essential fields response
        essential_response = MagicMock()
        essential_response.status_code = 200
        essential_response.json.return_value = {
            "value": [
                {
                    "id": 123,
                    "fields": {
                        "System.Id": 123,
                        "System.Title": "Test Bug",
                        "System.Description": "Test description",
                        "System.WorkItemType": "Bug",
                        "System.State": "Active",
                        "System.CreatedDate": "2023-01-01T00:00:00Z",
                        "System.ChangedDate": "2023-01-02T00:00:00Z",
                        "System.Tags": "Tag1; Tag2",
                        "System.AssignedTo": {"displayName": "Test User", "uniqueName": "test@example.com"}
                    }
                }
            ]
        }
        
        # Additional fields response
        additional_response = MagicMock()
        additional_response.status_code = 200
        additional_response.json.return_value = {
            "value": [
                {
                    "id": 123,
                    "fields": {
                        "System.AreaPath": "Test Area",
                        "System.IterationPath": "Sprint 1",
                        "Microsoft.VSTS.Common.Priority": 1,
                        "Microsoft.VSTS.Common.Severity": 2,
                        "System.ResolvedDate": "2023-01-03T00:00:00Z",
                        "Microsoft.VSTS.Common.ClosedDate": "2023-01-04T00:00:00Z",
                        "Microsoft.VSTS.Common.Resolution": "Fixed",
                        "System.ResolvedBy": {"displayName": "Resolver", "uniqueName": "resolver@example.com"},
                        "System.ClosedBy": {"displayName": "Closer", "uniqueName": "closer@example.com"},
                        "System.ClosedDate": "2023-01-04T00:00:00Z"
                    }
                }
            ]
        }
        
        # Set up mock to return different responses for each call
        mock_request.side_effect = [essential_response, additional_response]
        
        # Call the method
        result = connector._get_work_item_details([123])
        
        # Verify the method was called twice (once for each field set)
        assert mock_request.call_count == 2
        
        # Verify the first call contained only essential fields
        first_call = mock_request.call_args_list[0]
        assert "ids" in first_call[1]["params"]
        assert "fields" in first_call[1]["params"]
        assert "System.Title" in first_call[1]["params"]["fields"]
        assert "System.ResolvedDate" not in first_call[1]["params"]["fields"]
        
        # Verify the second call contained only additional fields
        second_call = mock_request.call_args_list[1]
        assert "ids" in second_call[1]["params"]
        assert "fields" in second_call[1]["params"]
        assert "System.AreaPath" in second_call[1]["params"]["fields"]
        assert "System.Title" not in second_call[1]["params"]["fields"]
        
        # Verify the result contains merged fields
        assert len(result) == 1
        work_item = result[0]
        assert work_item["id"] == 123
        
        # Verify fields from both requests are included
        fields = work_item["fields"]
        assert fields["System.Title"] == "Test Bug"
        assert fields["System.WorkItemType"] == "Bug"
        assert fields["System.AreaPath"] == "Test Area"
        assert fields["Microsoft.VSTS.Common.Resolution"] == "Fixed"
        
    @patch("requests.request")
    def test_get_work_item_details_handles_additional_fields_failure(self, mock_request):
        """Test that _get_work_item_details continues with essential fields if additional fields request fails."""
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
        
        # Essential fields successful response
        essential_response = MagicMock()
        essential_response.status_code = 200
        essential_response.json.return_value = {
            "value": [
                {
                    "id": 123,
                    "fields": {
                        "System.Id": 123,
                        "System.Title": "Test Bug",
                        "System.Description": "Test description",
                        "System.WorkItemType": "Bug",
                        "System.State": "Active"
                    }
                }
            ]
        }
        
        # Additional fields failed response
        error_response = MagicMock()
        error_response.status_code = 400
        error_response.raise_for_status.side_effect = requests.exceptions.HTTPError("400 Client Error: Bad Request")
        error_response.json.return_value = {"message": "Invalid field names"}
        
        # Set up mock to return success for first call and error for second
        mock_request.side_effect = [essential_response, error_response]
        
        # Call the method
        result = connector._get_work_item_details([123])
        
        # Verify the method was called twice (once for each field set)
        assert mock_request.call_count == 2
        
        # Verify we still have the work item with essential fields
        assert len(result) == 1
        work_item = result[0]
        assert work_item["id"] == 123
        assert work_item["fields"]["System.Title"] == "Test Bug"
        assert work_item["fields"]["System.WorkItemType"] == "Bug"
        
        # Verify no additional fields were added
        assert "System.AreaPath" not in work_item["fields"]
        assert "Microsoft.VSTS.Common.Resolution" not in work_item["fields"] 