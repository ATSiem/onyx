"""Test the Release Management API functionality in the Azure DevOps connector."""
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone

import requests
from onyx.connectors.azure_devops.connector import AzureDevOpsConnector


class TestAzureDevOpsReleaseConnector:
    """Test the Release Management API functionality in the Azure DevOps connector."""

    @patch("requests.request")
    def test_get_releases(self, mock_request):
        """Test the _get_releases method."""
        # Setup connector
        connector = AzureDevOpsConnector(
            organization="testorg",
            project="testproject",
            data_types=["releases", "release_details"]
        )
        
        connector.client_config = {
            "auth": None,
            "organization": "testorg",
            "project": "testproject",
            "base_url": "https://dev.azure.com/testorg/testproject/",
            "api_version": "7.0"
        }
        
        # Mock API response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "count": 2,
            "value": [
                {
                    "id": 1,
                    "name": "Release 1.0",
                    "status": "succeeded",
                    "createdBy": {"displayName": "John Doe"},
                    "createdOn": "2023-01-01T10:00:00Z",
                    "modifiedOn": "2023-01-01T11:00:00Z",
                    "releaseDefinition": {"name": "Website Deployment"},
                    "environments": [
                        {"name": "Dev", "status": "succeeded"},
                        {"name": "Staging", "status": "succeeded"},
                        {"name": "Production", "status": "succeeded"}
                    ],
                    "_links": {"web": {"href": "https://dev.azure.com/testorg/testproject/_release/1"}}
                },
                {
                    "id": 2,
                    "name": "Release 1.1",
                    "status": "inProgress",
                    "createdBy": {"displayName": "Jane Smith"},
                    "createdOn": "2023-01-02T10:00:00Z",
                    "modifiedOn": "2023-01-02T11:00:00Z",
                    "releaseDefinition": {"name": "Website Deployment"},
                    "environments": [
                        {"name": "Dev", "status": "succeeded"},
                        {"name": "Staging", "status": "inProgress"},
                        {"name": "Production", "status": "notStarted"}
                    ],
                    "_links": {"web": {"href": "https://dev.azure.com/testorg/testproject/_release/2"}}
                }
            ]
        }
        mock_request.return_value = mock_response
        
        # Call the method
        start_time = datetime(2023, 1, 1, tzinfo=timezone.utc)
        result = connector._get_releases(start_time=start_time)
        
        # Verify the API call
        assert mock_request.call_count == 1
        call_args = mock_request.call_args[1]
        assert "_apis/release/releases" in call_args["url"]
        assert call_args["params"]["minCreatedTime"] == "2023-01-01T00:00:00Z"
        assert call_args["params"]["$top"] == 200
        
        # Verify the result
        assert len(result["value"]) == 2
        assert result["value"][0]["id"] == 1
        assert result["value"][0]["name"] == "Release 1.0"
        assert result["value"][1]["id"] == 2
        assert result["value"][1]["name"] == "Release 1.1"

    @patch("requests.request")
    def test_get_release_details(self, mock_request):
        """Test the _get_release_details method."""
        # Setup connector
        connector = AzureDevOpsConnector(
            organization="testorg",
            project="testproject",
            data_types=["release_details"]
        )
        
        connector.client_config = {
            "auth": None,
            "organization": "testorg",
            "project": "testproject",
            "base_url": "https://dev.azure.com/testorg/testproject/",
            "api_version": "7.0"
        }
        
        # Mock API response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "id": 1,
            "name": "Release 1.0",
            "status": "succeeded",
            "releaseDefinition": {
                "id": 100,
                "name": "Website Deployment",
                "releaseNotes": "Bug fixes and performance improvements"
            },
            "environments": [
                {
                    "name": "Dev",
                    "status": "succeeded",
                    "preDeployApprovals": [
                        {"status": "approved", "approvedBy": {"displayName": "John Doe"}, "approvedOn": "2023-01-01T09:00:00Z"}
                    ],
                    "postDeployApprovals": []
                },
                {
                    "name": "Production",
                    "status": "succeeded",
                    "preDeployApprovals": [
                        {"status": "approved", "approvedBy": {"displayName": "Jane Smith"}, "approvedOn": "2023-01-01T11:00:00Z"}
                    ],
                    "postDeployApprovals": [
                        {"status": "approved", "approvedBy": {"displayName": "Bob Johnson"}, "approvedOn": "2023-01-01T12:00:00Z"}
                    ]
                }
            ]
        }
        mock_request.return_value = mock_response
        
        # Call the method
        result = connector._get_release_details(1)
        
        # Verify the API call
        assert mock_request.call_count == 1
        call_args = mock_request.call_args[1]
        assert "_apis/release/releases/1" in call_args["url"]
        
        # Verify the result
        assert result["id"] == 1
        assert result["name"] == "Release 1.0"
        assert result["releaseDefinition"]["releaseNotes"] == "Bug fixes and performance improvements"
        assert len(result["environments"]) == 2
        assert result["environments"][0]["name"] == "Dev"
        assert result["environments"][1]["name"] == "Production"
        assert result["environments"][1]["preDeployApprovals"][0]["approvedBy"]["displayName"] == "Jane Smith"

    @patch("onyx.connectors.azure_devops.connector.AzureDevOpsConnector._get_release_details")
    def test_process_release(self, mock_get_release_details):
        """Test the _process_release method."""
        # Setup connector
        connector = AzureDevOpsConnector(
            organization="testorg",
            project="testproject",
            data_types=["releases", "release_details"]
        )
        
        connector.client_config = {
            "auth": None,
            "organization": "testorg",
            "project": "testproject",
            "base_url": "https://dev.azure.com/testorg/testproject/",
            "api_version": "7.0"
        }
        
        # Mock release details
        mock_get_release_details.return_value = {
            "id": 1,
            "name": "Release 1.0",
            "status": "succeeded",
            "releaseDefinition": {
                "id": 100,
                "name": "Website Deployment",
                "releaseNotes": "Bug fixes and performance improvements"
            },
            "environments": [
                {
                    "name": "Dev",
                    "status": "succeeded",
                    "preDeployApprovals": [
                        {"status": "approved", "approvedBy": {"displayName": "John Doe"}, "approvedOn": "2023-01-01T09:00:00Z"}
                    ],
                    "postDeployApprovals": []
                },
                {
                    "name": "Production",
                    "status": "succeeded",
                    "preDeployApprovals": [
                        {"status": "approved", "approvedBy": {"displayName": "Jane Smith"}, "approvedOn": "2023-01-01T11:00:00Z"}
                    ],
                    "postDeployApprovals": [
                        {"status": "approved", "approvedBy": {"displayName": "Bob Johnson"}, "approvedOn": "2023-01-01T12:00:00Z"}
                    ]
                }
            ]
        }
        
        # Sample release data
        release = {
            "id": 1,
            "name": "Release 1.0",
            "status": "succeeded",
            "createdBy": {"displayName": "John Doe"},
            "createdOn": "2023-01-01T10:00:00Z",
            "modifiedOn": "2023-01-01T12:00:00Z",
            "releaseDefinition": {"name": "Website Deployment"},
            "environments": [
                {"name": "Dev", "status": "succeeded"},
                {"name": "Staging", "status": "succeeded"},
                {"name": "Production", "status": "succeeded"}
            ],
            "artifacts": [
                {
                    "type": "Build",
                    "definitionReference": {
                        "name": {"name": "WebsiteRepo"},
                        "version": {"name": "1.0.42"}
                    }
                }
            ],
            "_links": {"web": {"href": "https://dev.azure.com/testorg/testproject/_release/1"}}
        }
        
        # Call the method
        document = connector._process_release(release, include_details=True)
        
        # Verify the release details were fetched
        mock_get_release_details.assert_called_once_with(1)
        
        # Verify the document
        assert document is not None
        assert document.id == "azuredevops:testorg/testproject/release/1"
        assert document.title == "Release: Release 1.0"
        assert document.source.value == "azure_devops"
        assert document.semantic_identifier == "Release: Release 1.0 [succeeded]"
        
        # Verify the metadata
        assert document.metadata["type"] == "release"
        assert document.metadata["release_id"] == "1"
        assert document.metadata["name"] == "Release 1.0"
        assert document.metadata["status"] == "succeeded"
        assert document.metadata["created_by"] == "John Doe"
        assert document.metadata["definition_name"] == "Website Deployment"
        assert document.metadata["release_url"] == "https://dev.azure.com/testorg/testproject/_release/1"
        assert document.metadata["environment_0_name"] == "Dev"
        assert document.metadata["environment_0_status"] == "succeeded"
        assert document.metadata["environment_1_name"] == "Staging"
        assert document.metadata["environment_1_status"] == "succeeded"
        assert document.metadata["environment_2_name"] == "Production"
        assert document.metadata["environment_2_status"] == "succeeded"
        
        # Verify the content
        content = document.sections[0].text
        assert "Release: Release 1.0" in content
        assert "Status: succeeded" in content
        assert "Created By: John Doe" in content
        assert "Created: 2023-01-01" in content
        assert "Definition: Website Deployment" in content
        assert "Environments:" in content
        assert "- Dev: succeeded" in content
        assert "- Staging: succeeded" in content
        assert "- Production: succeeded" in content
        assert "Artifacts:" in content
        assert "- WebsiteRepo (1.0.42)" in content
        assert "Release Notes:" in content
        assert "Bug fixes and performance improvements" in content
        assert "Approvals:" in content
        assert "Pre-deploy approved by Jane Smith" in content
        assert "Post-deploy approved by Bob Johnson" in content

    @patch("onyx.connectors.azure_devops.connector.AzureDevOpsConnector._get_releases")
    @patch("onyx.connectors.azure_devops.connector.AzureDevOpsConnector._process_release")
    def test_load_from_checkpoint_releases(self, mock_process_release, mock_get_releases):
        """Test the load_from_checkpoint method for releases."""
        # Setup connector
        connector = AzureDevOpsConnector(
            organization="testorg",
            project="testproject",
            data_types=["releases", "release_details"]
        )
        
        connector.client_config = {
            "auth": None,
            "organization": "testorg",
            "project": "testproject",
            "base_url": "https://dev.azure.com/testorg/testproject/",
            "api_version": "7.0"
        }
        connector.personal_access_token = "pat"
        
        # Mock releases data
        mock_get_releases.return_value = {
            "value": [
                {
                    "id": 1,
                    "name": "Release 1.0",
                    "status": "succeeded"
                },
                {
                    "id": 2,
                    "name": "Release 1.1",
                    "status": "inProgress"
                }
            ]
        }
        
        # Mock document processing
        mock_documents = [MagicMock(), MagicMock()]
        mock_process_release.side_effect = mock_documents
        
        # Create checkpoint
        from onyx.connectors.azure_devops.connector import AzureDevOpsConnectorCheckpoint
        checkpoint = AzureDevOpsConnectorCheckpoint(has_more=False, continuation_token=None)
        
        # Call the method
        start_time = int(datetime(2023, 1, 1, tzinfo=timezone.utc).timestamp())
        end_time = int(datetime(2023, 1, 3, tzinfo=timezone.utc).timestamp())
        
        # Exhaust the generator
        list(connector.load_from_checkpoint(start_time, end_time, checkpoint))
        
        # Verify the releases were fetched
        mock_get_releases.assert_called_once()
        
        # Verify the releases were processed
        assert mock_process_release.call_count == 2 