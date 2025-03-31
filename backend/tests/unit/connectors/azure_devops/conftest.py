import pytest
from unittest.mock import MagicMock, patch

from onyx.connectors.azure_devops.connector import AzureDevOpsConnector


@pytest.fixture
def azure_devops_connector():
    """
    Create a basic Azure DevOps connector for testing.
    """
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
    return connector


@pytest.fixture
def mock_work_items_response():
    """
    Mock response for work items query.
    """
    return {
        "workItems": [
            {"id": 101, "url": "https://dev.azure.com/testorg/testproject/_apis/wit/workItems/101"},
            {"id": 102, "url": "https://dev.azure.com/testorg/testproject/_apis/wit/workItems/102"}
        ],
        "count": 2,
        "continuationToken": "next-page-token"
    }


@pytest.fixture
def mock_work_item_details():
    """
    Mock response for work item details.
    """
    return [
        {
            "id": 101,
            "url": "https://dev.azure.com/testorg/testproject/_apis/wit/workItems/101",
            "fields": {
                "System.Id": 101,
                "System.Title": "Bug #1",
                "System.Description": "<div>Bug description 1</div>",
                "System.WorkItemType": "Bug",
                "System.State": "Active",
                "System.CreatedDate": "2023-01-01T12:00:00Z",
                "System.ChangedDate": "2023-01-02T12:00:00Z",
                "System.CreatedBy": {
                    "displayName": "User 1",
                    "uniqueName": "user1@example.com"
                }
            },
            "_links": {
                "html": {
                    "href": "https://dev.azure.com/testorg/testproject/_workitems/edit/101"
                }
            }
        },
        {
            "id": 102,
            "url": "https://dev.azure.com/testorg/testproject/_apis/wit/workItems/102",
            "fields": {
                "System.Id": 102,
                "System.Title": "User Story #1",
                "System.Description": "<div>User story description</div>",
                "System.WorkItemType": "UserStory",
                "System.State": "New",
                "System.CreatedDate": "2023-01-01T13:00:00Z",
                "System.ChangedDate": "2023-01-02T13:00:00Z",
                "System.CreatedBy": {
                    "displayName": "User 2",
                    "uniqueName": "user2@example.com"
                }
            },
            "_links": {
                "html": {
                    "href": "https://dev.azure.com/testorg/testproject/_workitems/edit/102"
                }
            }
        }
    ]


@pytest.fixture
def mock_comments():
    """
    Mock response for work item comments.
    """
    return [
        {
            "id": 1,
            "text": "Comment on work item",
            "createdBy": {
                "displayName": "Comment Author",
                "uniqueName": "comment.author@example.com"
            },
            "createdDate": "2023-01-03T12:00:00Z"
        }
    ] 