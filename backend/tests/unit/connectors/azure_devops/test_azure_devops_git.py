"""Test the Git API functionality in the Azure DevOps connector."""
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone

import requests
from onyx.connectors.azure_devops.connector import AzureDevOpsConnector


class TestAzureDevOpsGitConnector:
    """Test the Git API functionality in the Azure DevOps connector."""

    @patch("requests.request")
    def test_get_repositories(self, mock_request):
        """Test the _get_repositories method."""
        # Setup connector
        connector = AzureDevOpsConnector(
            organization="testorg",
            project="testproject",
            data_types=["commits"]
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
                    "id": "repo1",
                    "name": "Repository1",
                    "url": "https://dev.azure.com/testorg/testproject/_apis/git/repositories/repo1",
                    "remoteUrl": "https://dev.azure.com/testorg/testproject/_git/Repository1"
                },
                {
                    "id": "repo2",
                    "name": "Repository2",
                    "url": "https://dev.azure.com/testorg/testproject/_apis/git/repositories/repo2",
                    "remoteUrl": "https://dev.azure.com/testorg/testproject/_git/Repository2"
                }
            ]
        }
        mock_request.return_value = mock_response
        
        # Call the method
        result = connector._get_repositories()
        
        # Verify the API call
        assert mock_request.call_count == 1
        call_args = mock_request.call_args[1]
        assert "_apis/git/repositories" in call_args["url"]
        assert call_args["params"] == {"includeLinks": "true", "api-version": "7.0"}
        
        # Verify the result
        assert len(result) == 2
        assert result[0]["id"] == "repo1"
        assert result[0]["name"] == "Repository1"
        assert result[1]["id"] == "repo2"
        assert result[1]["name"] == "Repository2"
        
        # Verify the cache was populated
        assert len(connector._repository_cache) == 2
        assert connector._repository_cache["repo1"]["name"] == "Repository1"
        assert connector._repository_cache["repo2"]["name"] == "Repository2"

    @patch("requests.request")
    def test_get_repositories_with_filter(self, mock_request):
        """Test the _get_repositories method with repository filter."""
        # Setup connector with repository filter
        connector = AzureDevOpsConnector(
            organization="testorg",
            project="testproject",
            data_types=["commits"],
            repositories=["Repository1"]  # Only include this repository
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
                    "id": "repo1",
                    "name": "Repository1",
                    "url": "https://dev.azure.com/testorg/testproject/_apis/git/repositories/repo1"
                },
                {
                    "id": "repo2",
                    "name": "Repository2",
                    "url": "https://dev.azure.com/testorg/testproject/_apis/git/repositories/repo2"
                }
            ]
        }
        mock_request.return_value = mock_response
        
        # Call the method
        result = connector._get_repositories()
        
        # Verify the result includes only Repository1
        assert len(result) == 1
        assert result[0]["id"] == "repo1"
        assert result[0]["name"] == "Repository1"
        
        # Verify the cache includes only Repository1
        assert len(connector._repository_cache) == 1
        assert connector._repository_cache["repo1"]["name"] == "Repository1"

    @patch("requests.request")
    def test_get_commits(self, mock_request):
        """Test the _get_commits method."""
        # Setup connector
        connector = AzureDevOpsConnector(
            organization="testorg",
            project="testproject",
            data_types=["commits"]
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
                    "commitId": "commit1",
                    "author": {
                        "name": "John Doe",
                        "email": "john@example.com",
                        "date": "2023-01-01T12:00:00Z"
                    },
                    "comment": "First commit",
                    "remoteUrl": "https://dev.azure.com/testorg/testproject/_git/Repository1/commit/commit1"
                },
                {
                    "commitId": "commit2",
                    "author": {
                        "name": "Jane Smith",
                        "email": "jane@example.com",
                        "date": "2023-01-02T12:00:00Z"
                    },
                    "comment": "Second commit",
                    "remoteUrl": "https://dev.azure.com/testorg/testproject/_git/Repository1/commit/commit2"
                }
            ]
        }
        mock_request.return_value = mock_response
        
        # Call the method
        start_time = datetime(2023, 1, 1, tzinfo=timezone.utc)
        result = connector._get_commits("repo1", start_time=start_time)
        
        # Verify the API call
        assert mock_request.call_count == 1
        
        # Verify the API endpoint and parameters
        args, kwargs = mock_request.call_args
        assert kwargs["method"] == "GET"
        assert "_apis/git/repositories/repo1/commits" in kwargs["url"]
        
        # Verify that we're requesting work items and details
        params = kwargs["params"]
        assert params["searchCriteria.includeWorkItems"] == "true"
        assert params["searchCriteria.includeDetails"] == "true"
        
        # Verify the response is properly parsed
        assert len(result["value"]) == 2
        assert result["value"][0]["commitId"] == "commit1"
        assert result["value"][1]["commitId"] == "commit2"

    @patch("requests.request")
    def test_process_commit(self, mock_request):
        """Test the _process_commit method."""
        # Setup connector
        connector = AzureDevOpsConnector(
            organization="testorg",
            project="testproject",
            data_types=["commits"]
        )
        
        connector.client_config = {
            "auth": None,
            "organization": "testorg",
            "project": "testproject",
            "base_url": "https://dev.azure.com/testorg/testproject/",
            "api_version": "7.0"
        }
        
        # Sample commit and repository data
        commit = {
            "commitId": "1234567890abcdef",
            "author": {
                "name": "John Doe",
                "email": "john@example.com",
                "date": "2023-01-01T12:00:00Z"
            },
            "comment": "Add new feature\n\nAdded a great new feature that does something awesome.",
            "remoteUrl": "https://dev.azure.com/testorg/testproject/_git/Repository1/commit/1234567890abcdef",
            "changes": [
                {
                    "item": {
                        "path": "/src/feature.py"
                    },
                    "changeType": "add"
                },
                {
                    "item": {
                        "path": "/tests/test_feature.py"
                    },
                    "changeType": "add"
                }
            ]
        }
        
        repository = {
            "id": "repo1",
            "name": "Repository1",
            "url": "https://dev.azure.com/testorg/testproject/_apis/git/repositories/repo1",
            "remoteUrl": "https://dev.azure.com/testorg/testproject/_git/Repository1"
        }
        
        # Call the method
        document = connector._process_commit(commit, repository)
        
        # Verify the document
        assert document is not None
        assert document.id == "azuredevops:testorg/testproject/git/repo1/commit/1234567890abcdef"
        assert document.title == "Commit 12345678: Add new feature"
        assert document.source.value == "azure_devops"
        assert document.semantic_identifier == "Commit 12345678: Add new feature"
        
        # Verify the metadata
        assert document.metadata["type"] == "commit"
        assert document.metadata["repository_name"] == "Repository1"
        assert document.metadata["repository_id"] == "repo1"
        assert document.metadata["commit_id"] == "1234567890abcdef"
        assert document.metadata["author_name"] == "John Doe"
        assert document.metadata["author_email"] == "john@example.com"
        assert document.metadata["commit_url"] == "https://dev.azure.com/testorg/testproject/_git/Repository1/commit/1234567890abcdef"
        assert document.metadata["commit_date"] == "2023-01-01T12:00:00+00:00"
        
        # Verify the content
        assert len(document.sections) == 1
        content = document.sections[0].text
        assert "Commit: 12345678" in content
        assert "Repository: Repository1" in content
        assert "Author: John Doe" in content
        assert "Date: 2023-01-01" in content
        assert "Commit Message:" in content
        assert "Add new feature" in content
        assert "Added a great new feature" in content
        assert "Changes:" in content
        assert "add: /src/feature.py" in content
        assert "add: /tests/test_feature.py" in content

    @patch("onyx.connectors.azure_devops.connector.AzureDevOpsConnector._get_repositories")
    @patch("onyx.connectors.azure_devops.connector.AzureDevOpsConnector._get_commits")
    @patch("onyx.connectors.azure_devops.connector.AzureDevOpsConnector._process_commit")
    def test_load_from_checkpoint_commits(self, mock_process_commit, mock_get_commits, mock_get_repositories):
        """Test the load_from_checkpoint method for commits."""
        # Setup connector
        connector = AzureDevOpsConnector(
            organization="testorg",
            project="testproject",
            data_types=["commits"]
        )
        
        connector.client_config = {
            "auth": None,
            "organization": "testorg",
            "project": "testproject",
            "base_url": "https://dev.azure.com/testorg/testproject/",
            "api_version": "7.0"
        }
        connector.personal_access_token = "pat"
        
        # Mock repository data
        mock_get_repositories.return_value = [
            {
                "id": "repo1",
                "name": "Repository1",
                "url": "https://dev.azure.com/testorg/testproject/_apis/git/repositories/repo1"
            }
        ]
        
        # Mock commit data
        mock_get_commits.return_value = {
            "value": [
                {
                    "commitId": "commit1",
                    "author": {"name": "John Doe", "date": "2023-01-01T12:00:00Z"},
                    "comment": "First commit"
                },
                {
                    "commitId": "commit2",
                    "author": {"name": "Jane Smith", "date": "2023-01-02T12:00:00Z"},
                    "comment": "Second commit"
                }
            ]
        }
        
        # Mock document processing
        mock_documents = [MagicMock(), MagicMock()]
        mock_process_commit.side_effect = mock_documents
        
        # Create checkpoint
        from onyx.connectors.azure_devops.connector import AzureDevOpsConnectorCheckpoint
        checkpoint = AzureDevOpsConnectorCheckpoint(has_more=False, continuation_token=None)
        
        # Call the method
        start_time = int(datetime(2023, 1, 1, tzinfo=timezone.utc).timestamp())
        end_time = int(datetime(2023, 1, 3, tzinfo=timezone.utc).timestamp())
        
        # Exhaust the generator (we don't actually need to collect the documents)
        list(connector.load_from_checkpoint(start_time, end_time, checkpoint))
        
        # Verify the repositories were fetched
        mock_get_repositories.assert_called_once()
        
        # Verify the commits were fetched
        mock_get_commits.assert_called_once()
        args, kwargs = mock_get_commits.call_args
        assert kwargs["repository_id"] == "repo1"  # repository_id
        assert kwargs["start_time"].date().isoformat() == "2023-01-01"
        
        # Verify the commits were processed
        assert mock_process_commit.call_count == 2

    @patch("requests.request")
    def test_process_commit_with_work_items(self, mock_request):
        """Test the _process_commit method with work items."""
        # Setup connector
        connector = AzureDevOpsConnector(
            organization="testorg",
            project="testproject",
            data_types=["commits"]
        )
        
        connector.client_config = {
            "auth": None,
            "organization": "testorg",
            "project": "testproject",
            "base_url": "https://dev.azure.com/testorg/testproject/",
            "api_version": "7.0"
        }
        
        # Mock work item details API response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "count": 1,
            "value": [
                {
                    "id": 123,
                    "rev": 1,
                    "fields": {
                        "System.WorkItemType": "User Story",
                        "System.Title": "Implement new feature",
                        "System.State": "In Progress"
                    },
                    "url": "https://dev.azure.com/testorg/testproject/_apis/wit/workItems/123"
                }
            ]
        }
        mock_request.return_value = mock_response
        
        # Sample commit with work items
        commit = {
            "commitId": "1234567890abcdef",
            "author": {
                "name": "John Doe",
                "email": "john@example.com",
                "date": "2023-01-01T12:00:00Z"
            },
            "comment": "Add new feature\n\nImplemented feature requested in US #123",
            "remoteUrl": "https://dev.azure.com/testorg/testproject/_git/Repository1/commit/1234567890abcdef",
            "changes": [
                {
                    "item": {
                        "path": "/src/feature.py"
                    },
                    "changeType": "add"
                }
            ],
            "workItems": [
                {
                    "id": 123,
                    "url": "https://dev.azure.com/testorg/testproject/_apis/wit/workItems/123"
                }
            ]
        }
        
        repository = {
            "id": "repo1",
            "name": "Repository1",
            "url": "https://dev.azure.com/testorg/testproject/_apis/git/repositories/repo1",
            "remoteUrl": "https://dev.azure.com/testorg/testproject/_git/Repository1"
        }
        
        # Call the method
        document = connector._process_commit(commit, repository)
        
        # Verify the document
        assert document is not None
        assert document.id == "azuredevops:testorg/testproject/git/repo1/commit/1234567890abcdef"
        assert document.title == "Commit 12345678: Add new feature"
        
        # Verify work items are included in metadata
        assert document.metadata["related_work_items"] == "123"
        
        # Verify the content includes work item information
        content = document.sections[0].text
        assert "Related Work Items:" in content
        assert "[User Story] #123: Implement new feature (In Progress)" in content 