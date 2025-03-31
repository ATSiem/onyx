import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime

from onyx.connectors.azure_devops.connector import AzureDevOpsConnector
from onyx.connectors.models import Document, DocumentSource


class TestAzureDevOpsResolutionStatus:
    """Test the resolution status handling for Azure DevOps connector."""

    def test_determine_resolution_status(self):
        """Test the resolution status determination logic."""
        connector = AzureDevOpsConnector(
            organization="testorg",
            project="testproject"
        )

        # Test case 1: Resolved by date
        fields1 = {
            "System.State": "Active",
            "System.ResolvedDate": "2024-01-02T00:00:00Z",
            "Microsoft.VSTS.Common.ClosedDate": None,
            "Microsoft.VSTS.Common.Resolution": None
        }
        assert connector._determine_resolution_status(fields1) == "Resolved"

        # Test case 2: Resolved by resolution field
        fields2 = {
            "System.State": "Active",
            "System.ResolvedDate": None,
            "Microsoft.VSTS.Common.ClosedDate": None,
            "Microsoft.VSTS.Common.Resolution": "Fixed"
        }
        assert connector._determine_resolution_status(fields2) == "Resolved"

        # Test case 3: Resolved by state
        fields3 = {
            "System.State": "Resolved",
            "System.ResolvedDate": None,
            "Microsoft.VSTS.Common.ClosedDate": None,
            "Microsoft.VSTS.Common.Resolution": None
        }
        assert connector._determine_resolution_status(fields3) == "Resolved"

        # Test case 4: Not resolved
        fields4 = {
            "System.State": "Active",
            "System.ResolvedDate": None,
            "Microsoft.VSTS.Common.ClosedDate": None,
            "Microsoft.VSTS.Common.Resolution": None
        }
        assert connector._determine_resolution_status(fields4) == "Not Resolved"

        # Test case 5: Unknown state
        fields5 = {
            "System.State": "UnknownState",
            "System.ResolvedDate": None,
            "Microsoft.VSTS.Common.ClosedDate": None,
            "Microsoft.VSTS.Common.Resolution": None
        }
        assert connector._determine_resolution_status(fields5) == "Unknown"

    def test_process_work_item_with_resolution_status(self):
        """Test processing a work item with resolution status information."""
        connector = AzureDevOpsConnector(
            organization="testorg",
            project="testproject"
        )
        connector.client_config = {
            "base_url": "https://dev.azure.com/testorg/testproject/"
        }

        # Create a work item with resolution status
        work_item = {
            "id": 123,
            "url": "https://dev.azure.com/testorg/testproject/_apis/wit/workItems/123",
            "fields": {
                "System.Id": 123,
                "System.Title": "Test Bug",
                "System.Description": "<div>This is a test bug description</div>",
                "System.WorkItemType": "Bug",
                "System.State": "Resolved",
                "System.CreatedDate": "2023-01-01T12:00:00Z",
                "System.ChangedDate": "2023-01-02T12:00:00Z",
                "System.ResolvedDate": "2023-01-02T12:00:00Z",
                "Microsoft.VSTS.Common.ClosedDate": "2023-01-02T12:00:00Z",
                "Microsoft.VSTS.Common.Resolution": "Fixed",
                "System.CreatedBy": {
                    "displayName": "Test Creator",
                    "uniqueName": "creator@example.com"
                },
                "System.AssignedTo": {
                    "displayName": "Test Assignee",
                    "uniqueName": "assignee@example.com"
                }
            },
            "_links": {
                "html": {
                    "href": "https://dev.azure.com/testorg/testproject/_workitems/edit/123"
                }
            }
        }

        # Mock connector to return empty comments
        connector._get_work_item_comments = MagicMock(return_value=[])

        # Process the work item
        document = connector._process_work_item(work_item)

        # Verify document
        assert isinstance(document, Document)
        assert document.id == "azuredevops:testorg/testproject/workitem/123"
        assert document.source == DocumentSource.AZURE_DEVOPS
        assert "[Resolved]" in document.title
        assert "Bug 123: Test Bug [Resolved]" in document.semantic_identifier
        
        # Check resolution status in metadata
        assert document.metadata["resolution_status"] == "Resolved"
        assert document.metadata["is_resolved"] == "true"
        assert document.metadata["resolution"] == "Fixed"
        assert document.metadata["resolved_date"] == "2023-01-02T12:00:00Z"
        assert document.metadata["closed_date"] == "2023-01-02T12:00:00Z"
        
        # Verify section content contains resolution status
        assert "Title: Test Bug [Resolved]" in document.sections[0].text
        assert "Resolution Status: Resolved" in document.sections[0].text
        assert "Resolution: Fixed" in document.sections[0].text
        
        # Make sure content doesn't contain extra resolution status
        assert "Title: Test Bug [Resolved] [Resolved]" not in document.sections[0].text

    def test_fetch_additional_context_with_resolution_status(self):
        """Test fetching additional context with resolution status information."""
        connector = AzureDevOpsConnector(
            organization="testorg",
            project="testproject",
            work_item_types=["Bug"],
            include_comments=True,
        )

        # Mock the work item details API call
        connector._get_work_item_details = MagicMock(return_value=[{
            "id": 842,
            "fields": {
                "System.Title": "Test Bug",
                "System.Description": "This is a test bug description",
                "System.WorkItemType": "Bug",
                "System.State": "Resolved",
                "System.CreatedDate": "2024-01-01T00:00:00Z",
                "System.ChangedDate": "2024-01-02T00:00:00Z",
                "System.ResolvedDate": "2024-01-02T00:00:00Z",
                "Microsoft.VSTS.Common.ClosedDate": "2024-01-02T00:00:00Z",
                "Microsoft.VSTS.Common.Resolution": "Fixed",
                "System.CreatedBy": {
                    "displayName": "Test User",
                    "email": "test@example.com"
                }
            }
        }])

        # Mock the comments API call
        connector._get_work_item_comments = MagicMock(return_value=[])

        # Test fetching additional context
        work_item_id = 842
        document = connector.fetch_additional_context(work_item_id)

        # Verify resolution status information
        assert document.metadata["resolution_status"] == "Resolved"
        assert document.metadata["resolution"] == "Fixed"
        assert document.metadata["resolved_date"] == "2024-01-02T00:00:00Z"
        assert document.metadata["closed_date"] == "2024-01-02T00:00:00Z"
        assert document.metadata["state"] == "Resolved"

    def test_fetch_additional_context_batch_with_resolution_status(self):
        """Test fetching additional context in batch with resolution status information."""
        connector = AzureDevOpsConnector(
            organization="testorg",
            project="testproject",
            work_item_types=["Bug"],
            include_comments=True,
        )

        # Mock the work item details API call with multiple items
        connector._get_work_item_details = MagicMock(return_value=[
            {
                "id": 842,
                "fields": {
                    "System.Title": "Test Bug 1",
                    "System.Description": "This is a test bug description",
                    "System.WorkItemType": "Bug",
                    "System.State": "Resolved",
                    "System.CreatedDate": "2024-01-01T00:00:00Z",
                    "System.ChangedDate": "2024-01-02T00:00:00Z",
                    "System.ResolvedDate": "2024-01-02T00:00:00Z",
                    "Microsoft.VSTS.Common.ClosedDate": "2024-01-02T00:00:00Z",
                    "Microsoft.VSTS.Common.Resolution": "Fixed"
                }
            },
            {
                "id": 843,
                "fields": {
                    "System.Title": "Test Bug 2",
                    "System.Description": "This is another test bug description",
                    "System.WorkItemType": "Bug",
                    "System.State": "Active",
                    "System.CreatedDate": "2024-01-01T00:00:00Z",
                    "System.ChangedDate": "2024-01-01T00:00:00Z",
                    "System.ResolvedDate": None,
                    "Microsoft.VSTS.Common.ClosedDate": None,
                    "Microsoft.VSTS.Common.Resolution": None
                }
            }
        ])

        # Mock the comments API call
        connector._get_work_item_comments = MagicMock(return_value=[])

        # Test fetching additional context for multiple work items
        work_item_ids = [842, 843]
        documents = connector.fetch_additional_context_batch(work_item_ids)

        # Verify we got two documents
        assert len(documents) == 2

        # Verify resolution status for first document (resolved)
        doc1 = documents[0]
        assert doc1.metadata["resolution_status"] == "Resolved"
        assert doc1.metadata["resolution"] == "Fixed"
        assert doc1.metadata["resolved_date"] == "2024-01-02T00:00:00Z"
        assert doc1.metadata["closed_date"] == "2024-01-02T00:00:00Z"
        assert doc1.metadata["state"] == "Resolved"

        # Verify resolution status for second document (not resolved)
        doc2 = documents[1]
        assert doc2.metadata["resolution_status"] == "Not Resolved"
        assert "resolution" not in doc2.metadata
        assert "resolved_date" not in doc2.metadata
        assert "closed_date" not in doc2.metadata
        assert doc2.metadata["state"] == "Active" 