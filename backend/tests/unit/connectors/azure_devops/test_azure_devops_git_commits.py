#!/usr/bin/env python3
"""
Tests for Azure DevOps connector git commits functionality.
"""

import pytest
import requests
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone, timedelta

from onyx.connectors.azure_devops.connector import AzureDevOpsConnector

# Sample repository data for testing
SAMPLE_REPO = {
    "id": "test-repo-id",
    "name": "test-repository",
    "project": {"id": "test-project-id"},
    "defaultBranch": "refs/heads/main",
    "webUrl": "https://dev.azure.com/test-org/test-project/_git/test-repository"
}

# Sample commit data for testing
SAMPLE_COMMIT = {
    "commitId": "1234567890abcdef1234567890abcdef12345678",
    "comment": "Test commit message",
    "author": {
        "name": "Test Author",
        "email": "test@example.com",
        "date": "2023-04-01T12:00:00Z"
    },
    "committer": {
        "name": "Test Committer",
        "email": "committer@example.com",
        "date": "2023-04-01T12:30:00Z"
    },
    "url": "https://dev.azure.com/test-org/test-project/_git/test-repository/commit/1234567890abcdef1234567890abcdef12345678"
}

@pytest.fixture
def mock_connector():
    """Create a connector with mocked API calls for testing"""
    with patch("onyx.connectors.azure_devops.connector.AzureDevOpsConnector._make_api_request") as mock_api:
        connector = AzureDevOpsConnector(
            organization="test-org",
            project="test-project",
            content_scope="everything"
        )
        connector.load_credentials({"personal_access_token": "fake-pat"})
        
        # Create a mock response
        def create_mock_response(status_code, data):
            mock_response = MagicMock(spec=requests.Response)
            mock_response.status_code = status_code
            mock_response.json.return_value = data
            mock_response.raise_for_status.return_value = None
            return mock_response
        
        # Configure the mock to return different values based on the endpoint
        def side_effect(endpoint, *args, **kwargs):
            if "_apis/git/repositories" in endpoint and "commits" not in endpoint:
                return create_mock_response(200, {"value": [SAMPLE_REPO]})
            elif "commits" in endpoint:
                return create_mock_response(200, {"value": [SAMPLE_COMMIT]})
            return create_mock_response(200, {"value": []})
        
        mock_api.side_effect = side_effect
        yield connector

def test_get_repositories(mock_connector):
    """Test that repositories can be fetched correctly"""
    repos = mock_connector._get_repositories()
    
    assert len(repos) == 1
    assert repos[0]["id"] == "test-repo-id"
    assert repos[0]["name"] == "test-repository"

def test_get_commits(mock_connector):
    """Test that commits can be fetched correctly"""
    # Create a start time 1 year ago
    start_time = datetime.now(timezone.utc) - timedelta(days=365)
    
    commits_response = mock_connector._get_commits(
        repository_id=SAMPLE_REPO["id"],
        start_time=start_time
    )
    
    assert "value" in commits_response
    commits = commits_response["value"]
    assert len(commits) == 1
    assert commits[0]["commitId"] == SAMPLE_COMMIT["commitId"]
    assert commits[0]["comment"] == SAMPLE_COMMIT["comment"]

def test_process_commit(mock_connector):
    """Test that a commit can be processed into a Document"""
    # Add repository to cache so _process_commit can access it
    mock_connector._repository_cache = {SAMPLE_REPO["id"]: SAMPLE_REPO}
    
    doc = mock_connector._process_commit(SAMPLE_COMMIT, SAMPLE_REPO)
    
    assert doc is not None
    assert "test-repo-id" in doc.id
    assert SAMPLE_COMMIT["commitId"] in doc.id
    assert "commit" in doc.id
    assert doc.title.startswith("Commit 12345678")
    assert "Test commit message" in doc.title
    assert len(doc.sections) > 0
    
    # Check that repository name is in metadata
    assert doc.metadata.get("repository_name") == "test-repository" 