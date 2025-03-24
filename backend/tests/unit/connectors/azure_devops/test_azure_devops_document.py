import json
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime

from onyx.connectors.azure_devops.connector import AzureDevOpsConnector
from onyx.connectors.models import Document, TextSection


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
        assert document.title == "Bug 123: Test Bug"
        
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
        
        # Verify primary owners (should have creator and assignee)
        assert document.primary_owners is not None
        assert len(document.primary_owners) == 2  # Creator and assignee
        
        # Verify that creator and assignee emails are present
        expert_emails = [expert.email for expert in document.primary_owners]
        assert "creator@example.com" in expert_emails
        assert "assignee@example.com" in expert_emails
    
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
        
        # Mock comments
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
        connector._get_work_item_comments = MagicMock(return_value=comments)
        
        # Process the work item
        document = connector._process_work_item(work_item)
        
        # Verify document
        assert document.id == "azuredevops:testorg/testproject/workitem/123"
        assert len(document.sections) == 1
        
        # Verify comments are in the document text
        section_text = document.sections[0].text
        assert "This is comment 1" in section_text
        assert "This is comment 2" in section_text
        assert "Comment Author 1" in section_text
        assert "Comment Author 2" in section_text
        
        # Verify primary owners (comments do not add to primary owners)
        assert document.primary_owners is not None
        assert len(document.primary_owners) == 1  # Just creator since no assignee
        
        # Verify that creator email is present
        expert_emails = [expert.email for expert in document.primary_owners]
        assert "creator@example.com" in expert_emails 