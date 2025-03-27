import json
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime

from onyx.connectors.azure_devops.connector import AzureDevOpsConnector
from onyx.connectors.models import Document, TextSection, DocumentSource


class TestAzureDevOpsDocument:
    """Test the document processing for Azure DevOps connector."""
    
    def test_process_work_item(self):
        """Test processing a work item into a Document."""
        # Create connector instance
        connector = AzureDevOpsConnector(
            organization="testorg", 
            project="testproject"
        )
        connector.client_config = {
            "base_url": "https://dev.azure.com/testorg/testproject/"
        }
        
        # Create a realistic work item
        work_item = {
            "id": 123,
            "url": "https://dev.azure.com/testorg/testproject/_apis/wit/workItems/123",
            "fields": {
                "System.Id": 123,
                "System.Title": "Test Bug",
                "System.Description": "<div>This is a test bug description</div>",
                "System.WorkItemType": "Bug",
                "System.State": "Active",
                "System.CreatedDate": "2023-01-01T12:00:00Z",
                "System.ChangedDate": "2023-01-02T12:00:00Z",
                "System.CreatedBy": {
                    "displayName": "Test Creator",
                    "uniqueName": "creator@example.com"
                },
                "System.AssignedTo": {
                    "displayName": "Test Assignee",
                    "uniqueName": "assignee@example.com"
                },
                "System.AreaPath": "TestProject\\Area",
                "System.IterationPath": "TestProject\\Iteration",
                "Microsoft.VSTS.Common.Priority": 1,
                "Microsoft.VSTS.Common.Severity": "2 - High",
                "System.Tags": "Tag1; Tag2"
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
        assert document.sections[0].link == "https://dev.azure.com/testorg/testproject/_workitems/edit/123"
        assert document.source.value == "azure_devops"
        assert document.metadata["type"] == "Bug"
        assert "[Not Resolved]" in document.title
        assert "Bug 123: Test Bug [Not Resolved]" in document.title
        
        # Check semantic identifier contains resolution status
        assert document.semantic_identifier == "Bug 123: Test Bug [Not Resolved]"

        # Verify primary owners
        assert len(document.primary_owners) == 2
        assert document.primary_owners[0].display_name == "Test Creator"
        assert document.primary_owners[0].email == "creator@example.com"
        assert document.primary_owners[1].display_name == "Test Assignee"
        assert document.primary_owners[1].email == "assignee@example.com"
        
        # Check resolution status in metadata
        assert document.metadata["resolution_status"] == "Not Resolved"
        assert document.metadata["is_resolved"] == "false"
        
        # Verify document content
        assert len(document.sections) == 1
        assert isinstance(document.sections[0], TextSection)
        assert "This is a test bug description" in document.sections[0].text
        
        # Verify metadata
        assert document.metadata["type"] == "Bug"
        assert document.metadata["state"] == "Active"
        assert document.metadata["priority"] == "1"
        assert document.metadata["severity"] == "2 - High"
        assert document.metadata["area_path"] == "TestProject\\Area"
        assert document.metadata["iteration_path"] == "TestProject\\Iteration"
        assert "Tag1" in document.metadata["tags"]
        assert "Tag2" in document.metadata["tags"]
    
    def test_process_work_item_with_comments(self):
        """Test processing a work item with comments."""
        # Create connector instance
        connector = AzureDevOpsConnector(
            organization="testorg",
            project="testproject",
            include_comments=True
        )
        connector.client_config = {
            "base_url": "https://dev.azure.com/testorg/testproject/"
        }

        # Create a simple work item
        work_item = {
            "id": 123,
            "url": "https://dev.azure.com/testorg/testproject/_apis/wit/workItems/123",
            "fields": {
                "System.Id": 123,
                "System.Title": "Test Bug",
                "System.Description": "<div>This is a test bug description</div>",
                "System.WorkItemType": "Bug",
                "System.CreatedDate": "2023-01-01T12:00:00Z",
                "System.ChangedDate": "2023-01-02T12:00:00Z",
                "System.CreatedBy": {
                    "displayName": "Test Creator",
                    "uniqueName": "creator@example.com"
                }
            },
            "_links": {
                "html": {
                    "href": "https://dev.azure.com/testorg/testproject/_workitems/edit/123"
                }
            }
        }

        # Create test comments
        comments = [
            {
                "id": 1,
                "text": "This is comment 1",
                "createdBy": {
                    "displayName": "Comment Author 1",
                    "uniqueName": "author1@example.com"
                },
                "createdDate": "2023-01-03T12:00:00Z"
            },
            {
                "id": 2,
                "text": "This is comment 2",
                "createdBy": {
                    "displayName": "Comment Author 2",
                    "uniqueName": "author2@example.com"
                },
                "createdDate": "2023-01-04T12:00:00Z"
            }
        ]

        # Process the work item with comments
        document = connector._process_work_item(work_item, comments)

        # Verify document
        assert document.id == "azuredevops:testorg/testproject/workitem/123"
        assert len(document.sections) == 1

        # Verify comments are in the document text
        section_text = document.sections[0].text
        assert "This is comment 1" in section_text
        assert "This is comment 2" in section_text
        assert "Comment Author 1" in section_text
        assert "Comment Author 2" in section_text
        assert "2023-01-03T12:00:00Z" in section_text
        assert "2023-01-04T12:00:00Z" in section_text
        
        # Verify primary owners (comments do not add to primary owners)
        assert document.primary_owners is not None
        assert len(document.primary_owners) == 1  # Just creator since no assignee
        
        # Verify that creator email is present
        expert_emails = [expert.email for expert in document.primary_owners]
        assert "creator@example.com" in expert_emails 

    def test_fetch_additional_context(self):
        """Test that the connector can fetch additional context for a work item when needed."""
        # Create a connector instance
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
                "System.State": "Active",
                "System.CreatedBy": {
                    "displayName": "Test User",
                    "email": "test@example.com"
                },
                "System.CreatedDate": "2024-01-01T00:00:00Z",
                "System.ChangedBy": {
                    "displayName": "Test User",
                    "email": "test@example.com"
                },
                "System.ChangedDate": "2024-01-01T00:00:00Z",
                "System.Tags": "Tag1; Tag2",
                "System.AssignedTo": {
                    "displayName": "Test User",
                    "email": "test@example.com"
                },
                "System.AreaPath": "TestProject\\Area",
                "System.IterationPath": "TestProject\\Iteration",
                "Microsoft.VSTS.Common.Priority": "1",
                "Microsoft.VSTS.Common.Severity": "2 - High",
                "System.ResolvedDate": "2024-01-02T00:00:00Z",
                "Microsoft.VSTS.Common.ClosedDate": "2024-01-02T00:00:00Z",
                "Microsoft.VSTS.Common.Resolution": "Fixed"
            }
        }])
        
        # Mock the comments API call
        connector._get_work_item_comments = MagicMock(return_value=[{
            "createdBy": {
                "displayName": "Test User",
                "email": "test@example.com"
            },
            "text": "This is a test comment",
            "createdDate": "2024-01-01T00:00:00Z"
        }])
        
        # Test fetching additional context for a work item
        work_item_id = 842
        document = connector.fetch_additional_context(work_item_id)
        
        # Verify that the API was called with the correct work item ID
        connector._get_work_item_details.assert_called_once_with([work_item_id])
        
        # Verify the document was created correctly
        assert document is not None
        assert document.id == "azuredevops:testorg/testproject/workitem/842"
        assert document.source == DocumentSource.AZURE_DEVOPS
        assert document.semantic_identifier == "Bug 842: Test Bug [Resolved]"
        assert "[Resolved]" in document.title
        assert "Bug 842: Test Bug [Resolved]" in document.title

        # Verify the document has the correct metadata
        assert document.metadata["resolution_status"] == "Resolved"
        assert document.metadata["is_resolved"] == "true"
        assert document.metadata["resolution"] == "Fixed"

        # Verify that comments were included
        assert "This is a test comment" in document.sections[0].text
        
        # Test caching
        # Reset the mock to verify it's not called again
        connector._get_work_item_details.reset_mock()
        connector._get_work_item_comments.reset_mock()
        
        # Fetch the same work item again
        cached_document = connector.fetch_additional_context(work_item_id)
        
        # Verify the cached document matches the original
        assert cached_document is not None
        assert cached_document.id == document.id
        assert cached_document.semantic_identifier == document.semantic_identifier
        
        # Verify that the API methods were not called again
        connector._get_work_item_details.assert_not_called()
        connector._get_work_item_comments.assert_not_called()
        
        # Test with non-existent work item
        connector._get_work_item_details.return_value = []
        document = connector.fetch_additional_context(999)
        assert document is None

    def test_fetch_additional_context_batch(self):
        """Test fetching additional context for multiple work items in parallel."""
        # Create a connector instance
        connector = AzureDevOpsConnector(
            organization="testorg",
            project="testproject",
            work_item_types=["Bug"],
            include_comments=True,
        )
        
        # Clear the cache
        connector._context_cache = {}
        
        # Mock the work item details API call
        connector._get_work_item_details = MagicMock(return_value=[{
            "id": 842,
            "fields": {
                "System.Title": "Test Bug 1",
                "System.Description": "This is a test bug description",
                "System.WorkItemType": "Bug",
                "System.State": "Active",
                "System.CreatedBy": {
                    "displayName": "Test User",
                    "email": "test@example.com"
                },
                "System.CreatedDate": "2024-01-01T00:00:00Z",
                "System.ChangedBy": {
                    "displayName": "Test User",
                    "email": "test@example.com"
                },
                "System.ChangedDate": "2024-01-01T00:00:00Z",
                "System.Tags": "Tag1; Tag2",
                "System.AssignedTo": {
                    "displayName": "Test User",
                    "email": "test@example.com"
                },
                "System.AreaPath": "TestProject\\Area",
                "System.IterationPath": "TestProject\\Iteration",
                "Microsoft.VSTS.Common.Priority": "1",
                "Microsoft.VSTS.Common.Severity": "2 - High",
                "System.ResolvedDate": "2024-01-02T00:00:00Z",
                "Microsoft.VSTS.Common.ClosedDate": "2024-01-02T00:00:00Z",
                "Microsoft.VSTS.Common.Resolution": "Fixed"
            }
        }, {
            "id": 843,
            "fields": {
                "System.Title": "Test Bug 2",
                "System.Description": "This is another test bug description",
                "System.WorkItemType": "Bug",
                "System.State": "Active",
                "System.CreatedBy": {
                    "displayName": "Test User",
                    "email": "test@example.com"
                },
                "System.CreatedDate": "2024-01-01T00:00:00Z",
                "System.ChangedBy": {
                    "displayName": "Test User",
                    "email": "test@example.com"
                },
                "System.ChangedDate": "2024-01-01T00:00:00Z",
                "System.Tags": "Tag1; Tag2",
                "System.AssignedTo": {
                    "displayName": "Test User",
                    "email": "test@example.com"
                },
                "System.AreaPath": "TestProject\\Area",
                "System.IterationPath": "TestProject\\Iteration",
                "Microsoft.VSTS.Common.Priority": "1",
                "Microsoft.VSTS.Common.Severity": "2 - High",
                "System.ResolvedDate": "2024-01-02T00:00:00Z",
                "Microsoft.VSTS.Common.ClosedDate": "2024-01-02T00:00:00Z",
                "Microsoft.VSTS.Common.Resolution": "Fixed"
            }
        }])
        
        # Mock the comments API call
        connector._get_work_item_comments = MagicMock(return_value=[{
            "createdBy": {
                "displayName": "Test User",
                "email": "test@example.com"
            },
            "text": "This is a test comment",
            "createdDate": "2024-01-01T00:00:00Z"
        }])
        
        # Test fetching additional context for multiple work items
        work_item_ids = [842, 843]
        documents = connector.fetch_additional_context_batch(work_item_ids)
        
        # Verify that we got two documents
        assert len(documents) == 2
        
        # Verify the documents were created correctly
        assert documents[0].id == "azuredevops:testorg/testproject/workitem/842"
        assert documents[1].id == "azuredevops:testorg/testproject/workitem/843"
        assert documents[0].semantic_identifier == "Bug 842: Test Bug 1 [Resolved]"
        assert documents[1].semantic_identifier == "Bug 843: Test Bug 2 [Resolved]"
        assert "[Resolved]" in documents[0].title
        assert "[Resolved]" in documents[1].title
        
        # Verify the documents have the correct metadata
        assert documents[0].metadata["resolution_status"] == "Resolved"
        assert documents[0].metadata["is_resolved"] == "true"
        assert documents[0].metadata["resolution"] == "Fixed"

        assert documents[1].metadata["resolution_status"] == "Resolved"
        assert documents[1].metadata["is_resolved"] == "true"
        assert documents[1].metadata["resolution"] == "Fixed"
        
        # Verify the documents were cached
        assert 842 in connector._context_cache
        assert 843 in connector._context_cache
        
        # Clear the cache before testing with non-existent work items
        connector._context_cache = {}
        
        # Test with a mix of existing and non-existent work items
        connector._get_work_item_details.return_value = [{
            "id": 842,
            "fields": {
                "System.Title": "Test Bug 1",
                "System.Description": "This is a test bug description",
                "System.WorkItemType": "Bug",
                "System.State": "Active",
                "System.CreatedBy": {
                    "displayName": "Test User",
                    "email": "test@example.com"
                },
                "System.CreatedDate": "2024-01-01T00:00:00Z",
                "System.ChangedBy": {
                    "displayName": "Test User",
                    "email": "test@example.com"
                },
                "System.ChangedDate": "2024-01-01T00:00:00Z",
                "System.Tags": "Tag1; Tag2",
                "System.AssignedTo": {
                    "displayName": "Test User",
                    "email": "test@example.com"
                },
                "System.AreaPath": "TestProject\\Area",
                "System.IterationPath": "TestProject\\Iteration",
                "Microsoft.VSTS.Common.Priority": "1",
                "Microsoft.VSTS.Common.Severity": "2 - High",
                "System.ResolvedDate": "2024-01-02T00:00:00Z",
                "Microsoft.VSTS.Common.ClosedDate": "2024-01-02T00:00:00Z",
                "Microsoft.VSTS.Common.Resolution": "Fixed"
            }
        }]
        
        work_item_ids = [842, 999, 843]
        documents = connector.fetch_additional_context_batch(work_item_ids)
        
        # Verify that we only got one document (the existing one)
        assert len(documents) == 1
        assert documents[0].id == "azuredevops:testorg/testproject/workitem/842" 