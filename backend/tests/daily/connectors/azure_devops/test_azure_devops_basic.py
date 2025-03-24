import json
import os
from datetime import datetime
from typing import Dict, List
from unittest.mock import MagicMock, patch

import pytest
from requests.models import Response

from onyx.configs.constants import DocumentSource
from onyx.connectors.azure_devops.connector import AzureDevOpsConnector
from onyx.connectors.models import Document


# Mock response for WIQL query
MOCK_WIQL_RESPONSE = {
    "workItems": [
        {"id": 1, "url": "https://dev.azure.com/org/project/_apis/wit/workItems/1"},
        {"id": 2, "url": "https://dev.azure.com/org/project/_apis/wit/workItems/2"},
    ]
}

# Mock response for work item details
MOCK_WORK_ITEM_DETAILS = {
    "value": [
        {
            "id": 1,
            "fields": {
                "System.Id": 1,
                "System.Title": "Bug Title",
                "System.Description": "This is a bug description",
                "System.WorkItemType": "Bug",
                "System.State": "Active",
                "System.CreatedBy": {
                    "displayName": "Test User",
                    "uniqueName": "test@example.com",
                },
                "System.CreatedDate": "2023-01-01T00:00:00Z",
                "System.ChangedBy": {
                    "displayName": "Test User",
                    "uniqueName": "test@example.com",
                },
                "System.ChangedDate": "2023-01-02T00:00:00Z",
                "System.Tags": "tag1; tag2",
                "System.AssignedTo": {
                    "displayName": "Assigned User",
                    "uniqueName": "assigned@example.com",
                },
                "System.AreaPath": "Project\\Area",
                "System.IterationPath": "Project\\Iteration",
                "Microsoft.VSTS.Common.Priority": 1,
                "Microsoft.VSTS.Common.Severity": "2 - High",
            },
        },
        {
            "id": 2,
            "fields": {
                "System.Id": 2,
                "System.Title": "Feature Title",
                "System.Description": "This is a feature description",
                "System.WorkItemType": "Feature",
                "System.State": "New",
                "System.CreatedBy": {
                    "displayName": "Test User",
                    "uniqueName": "test@example.com",
                },
                "System.CreatedDate": "2023-01-01T00:00:00Z",
                "System.ChangedBy": {
                    "displayName": "Test User",
                    "uniqueName": "test@example.com",
                },
                "System.ChangedDate": "2023-01-02T00:00:00Z",
                "System.Tags": "feature; important",
                "System.AssignedTo": {
                    "displayName": "Assigned User",
                    "uniqueName": "assigned@example.com",
                },
                "System.AreaPath": "Project\\Area",
                "System.IterationPath": "Project\\Iteration",
                "Microsoft.VSTS.Common.Priority": 2,
            },
        },
    ]
}

# Mock response for comments
MOCK_COMMENTS = {
    "comments": [
        {
            "id": 1,
            "text": "This is a comment",
            "createdBy": {"displayName": "Commenter", "uniqueName": "commenter@example.com"},
            "createdDate": "2023-01-03T00:00:00Z",
        }
    ]
}


def create_mock_response(status_code: int, json_data: Dict) -> Response:
    mock_response = MagicMock(spec=Response)
    mock_response.status_code = status_code
    mock_response.json.return_value = json_data
    mock_response.raise_for_status.return_value = None
    return mock_response


class TestAzureDevOpsConnector:
    @pytest.fixture
    def mock_connector(self):
        connector = AzureDevOpsConnector(
            organization="testorg",
            project="testproject",
            work_item_types=["Bug", "Feature"],
            include_comments=True,
        )
        
        # Mock credentials
        connector.load_credentials({"personal_access_token": "test_token"})
        
        return connector

    @patch("onyx.connectors.azure_devops.connector.requests.request")
    def test_load_from_checkpoint(self, mock_request, mock_connector):
        # Mock API responses
        mock_request.side_effect = [
            create_mock_response(200, MOCK_WIQL_RESPONSE),
            create_mock_response(200, MOCK_WORK_ITEM_DETAILS),
            create_mock_response(200, MOCK_COMMENTS),
            create_mock_response(200, MOCK_COMMENTS),
        ]
        
        # Call load_from_checkpoint
        start_time = int(datetime(2023, 1, 1).timestamp())
        end_time = int(datetime(2023, 1, 10).timestamp())
        
        checkpoint = mock_connector.build_dummy_checkpoint()
        
        # Get documents
        documents = []
        for item in mock_connector.load_from_checkpoint(start_time, end_time, checkpoint):
            if isinstance(item, Document):
                documents.append(item)
                
        # Verify documents
        assert len(documents) == 2
        
        # Check first document
        assert documents[0].source == DocumentSource.AZURE_DEVOPS
        assert documents[0].semantic_identifier == "Bug 1: Bug Title"
        assert "Bug Title" in documents[0].sections[0].text
        assert "This is a bug description" in documents[0].sections[0].text
        assert documents[0].metadata["type"] == "Bug"
        assert documents[0].metadata["state"] == "Active"
        assert documents[0].metadata["priority"] == "1"
        assert documents[0].metadata["severity"] == "2 - High"
        assert set(documents[0].metadata["tags"]) == {"tag1", "tag2"}
        
        # Check second document
        assert documents[1].source == DocumentSource.AZURE_DEVOPS
        assert documents[1].semantic_identifier == "Feature 2: Feature Title"
        assert "Feature Title" in documents[1].sections[0].text
        assert "This is a feature description" in documents[1].sections[0].text
        assert documents[1].metadata["type"] == "Feature"
        assert documents[1].metadata["state"] == "New"
        assert documents[1].metadata["priority"] == "2"
        assert set(documents[1].metadata["tags"]) == {"feature", "important"}

    @patch("onyx.connectors.azure_devops.connector.requests.request")
    def test_slim_retrieval(self, mock_request, mock_connector):
        # Mock API responses
        mock_request.side_effect = [
            create_mock_response(200, MOCK_WIQL_RESPONSE),
        ]
        
        # Call retrieve_all_slim_documents
        start_time = int(datetime(2023, 1, 1).timestamp())
        
        # Get slim documents
        slim_docs = []
        for batch in mock_connector.retrieve_all_slim_documents(start=start_time):
            slim_docs.extend(batch)
                
        # Verify slim documents
        assert len(slim_docs) == 2
        assert all(doc.id.startswith("https://dev.azure.com/testorg/testproject/_workitems/edit/") for doc in slim_docs)
        assert "1" in slim_docs[0].id
        assert "2" in slim_docs[1].id 