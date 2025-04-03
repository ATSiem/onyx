#!/usr/bin/env python3
"""
Tests for Azure DevOps connector initialization.
"""

import pytest
from unittest.mock import patch, MagicMock
from onyx.connectors.azure_devops.connector import AzureDevOpsConnector

def test_connector_initialization():
    """Test that the connector initializes correctly with default settings."""
    # Create connector instance with default settings
    connector = AzureDevOpsConnector(
        organization="test-org",
        project="test-project",
        content_scope="everything"
    )
    
    # Verify basic properties
    assert connector.organization == "test-org"
    assert connector.project == "test-project"
    assert connector.content_scope == "everything"
    assert connector.DATA_TYPE_COMMITS in connector.data_types
    assert connector.DATA_TYPE_WORK_ITEMS in connector.data_types

@pytest.mark.parametrize("content_scope,expect_commits", [
    ("everything", True),
    ("Everything", True),  # Test case sensitivity
    ("work_items_only", False),
])
def test_content_scope_affects_data_types(content_scope, expect_commits):
    """Test that content_scope properly affects available data types."""
    connector = AzureDevOpsConnector(
        organization="test-org",
        project="test-project",
        content_scope=content_scope
    )
    
    if expect_commits:
        assert connector.DATA_TYPE_COMMITS in connector.data_types, f"Content scope '{content_scope}' should enable commits"
    else:
        assert connector.DATA_TYPE_COMMITS not in connector.data_types, f"Content scope '{content_scope}' should not enable commits"

@patch('onyx.connectors.azure_devops.connector.AzureDevOpsConnector._get_repositories')
def test_repository_fetch(mock_get_repos):
    """Test that repositories are fetched correctly."""
    # Setup mock
    mock_get_repos.return_value = [
        {"id": "repo1", "name": "Repository 1"},
        {"id": "repo2", "name": "Repository 2"}
    ]
    
    # Create connector
    connector = AzureDevOpsConnector(
        organization="test-org",
        project="test-project"
    )
    connector.load_credentials({"personal_access_token": "fake-pat"})
    
    # Get repositories
    repos = connector._get_repositories()
    
    # Verify results
    assert len(repos) == 2
    assert repos[0]["name"] == "Repository 1"
    assert repos[1]["id"] == "repo2"
    
    # Verify mock was called
    mock_get_repos.assert_called_once() 