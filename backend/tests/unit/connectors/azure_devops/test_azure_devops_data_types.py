"""Test the data type settings for the Azure DevOps connector."""
import pytest
from unittest.mock import MagicMock, patch

from onyx.connectors.azure_devops.connector import AzureDevOpsConnector


class TestAzureDevOpsDataTypes:
    """Test the data type settings for the Azure DevOps connector."""

    def test_default_data_types(self):
        """Test that the connector initializes with the correct default data types."""
        # Basic initialization
        connector = AzureDevOpsConnector(
            organization="testorg",
            project="testproject"
        )
        
        # Verify default data types
        assert connector.data_types == ["work_items"]
        
        # Verify default work item types
        assert connector.work_item_types == ["Bug", "Epic", "Feature", "Issue", "Task", "TestCase", "UserStory"]

    def test_custom_data_types(self):
        """Test that the connector can be initialized with custom data types."""
        # Initialize with all data types
        connector = AzureDevOpsConnector(
            organization="testorg",
            project="testproject",
            data_types=["work_items", "commits", "test_results", "test_stats", "releases", "release_details", "wikis"]
        )
        
        # Verify all data types are set
        assert "work_items" in connector.data_types
        assert "commits" in connector.data_types
        assert "test_results" in connector.data_types
        assert "test_stats" in connector.data_types
        assert "releases" in connector.data_types
        assert "release_details" in connector.data_types
        assert "wikis" in connector.data_types

    def test_custom_work_item_types(self):
        """Test that the connector can be initialized with custom work item types."""
        # Initialize with custom work item types
        custom_types = ["Bug", "Task", "TestCase"]
        connector = AzureDevOpsConnector(
            organization="testorg",
            project="testproject",
            work_item_types=custom_types
        )
        
        # Verify custom work item types are set
        assert connector.work_item_types == custom_types

    def test_content_scope_everything_enables_all_data_types(self):
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
    
    def test_content_scope_work_items_only(self):
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

    @patch("requests.request")
    def test_validate_work_item_types(self, mock_request):
        """Test that the connector validates work item types against available types."""
        # Setup connector
        connector = AzureDevOpsConnector(
            organization="testorg",
            project="testproject",
            work_item_types=["Bug", "Task", "InvalidType"]
        )
        
        connector.client_config = {
            "auth": None,
            "organization": "testorg",
            "project": "testproject",
            "base_url": "https://dev.azure.com/testorg/testproject/",
            "api_version": "7.0"
        }
        
        # Mock organization API response
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
        
        # Mock work item types API response
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
        
        # Validate settings
        connector.validate_connector_settings()
        
        # Verify that invalid type was removed
        assert "InvalidType" not in connector.work_item_types
        assert "Bug" in connector.work_item_types
        assert "Task" in connector.work_item_types

    def test_data_type_combinations(self):
        """Test various combinations of data types and work item types."""
        # Test with work items and commits
        connector1 = AzureDevOpsConnector(
            organization="testorg",
            project="testproject",
            data_types=["work_items", "commits"]
        )
        assert "work_items" in connector1.data_types
        assert "commits" in connector1.data_types
        assert len(connector1.data_types) == 2
        
        # Test with work items, commits, and test results
        connector2 = AzureDevOpsConnector(
            organization="testorg",
            project="testproject",
            data_types=["work_items", "commits", "test_results"]
        )
        assert "work_items" in connector2.data_types
        assert "commits" in connector2.data_types
        assert "test_results" in connector2.data_types
        assert len(connector2.data_types) == 3
