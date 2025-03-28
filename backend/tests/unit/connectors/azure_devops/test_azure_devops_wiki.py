"""Test the Wiki API functionality in the Azure DevOps connector."""
import pytest
from unittest.mock import MagicMock, patch, call
from datetime import datetime, timezone

import requests
from onyx.connectors.azure_devops.connector import AzureDevOpsConnector


class TestAzureDevOpsWikiConnector:
    """Test the Wiki API functionality in the Azure DevOps connector."""

    @patch("requests.request")
    def test_get_wikis(self, mock_request):
        """Test the _get_wikis method."""
        # Setup connector
        connector = AzureDevOpsConnector(
            organization="testorg",
            project="testproject",
            data_types=["wikis"]
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
                    "id": "wiki1",
                    "name": "Project Wiki",
                    "type": "projectWiki",
                    "url": "https://dev.azure.com/testorg/testproject/_apis/wiki/wikis/wiki1",
                    "remoteUrl": "https://dev.azure.com/testorg/testproject/_wiki/wikis/wiki1"
                },
                {
                    "id": "wiki2",
                    "name": "Code Wiki",
                    "type": "codeWiki",
                    "url": "https://dev.azure.com/testorg/testproject/_apis/wiki/wikis/wiki2",
                    "remoteUrl": "https://dev.azure.com/testorg/testproject/_wiki/wikis/wiki2"
                }
            ]
        }
        mock_request.return_value = mock_response
        
        # Call the method
        result = connector._get_wikis()
        
        # Verify the API call
        assert mock_request.call_count == 1
        call_args = mock_request.call_args[1]
        assert "_apis/wiki/wikis" in call_args["url"]
        
        # Verify the result
        assert len(result) == 2
        assert result[0]["id"] == "wiki1"
        assert result[0]["name"] == "Project Wiki"
        assert result[1]["id"] == "wiki2"
        assert result[1]["name"] == "Code Wiki"

    @patch("requests.request")
    def test_get_wiki_pages(self, mock_request):
        """Test the _get_wiki_pages method."""
        # Setup connector
        connector = AzureDevOpsConnector(
            organization="testorg",
            project="testproject",
            data_types=["wikis"]
        )
        
        connector.client_config = {
            "auth": None,
            "organization": "testorg",
            "project": "testproject",
            "base_url": "https://dev.azure.com/testorg/testproject/",
            "api_version": "7.0"
        }
        
        # Setup mock responses for hierarchical wiki pages
        root_response = MagicMock()
        root_response.status_code = 200
        root_response.json.return_value = {
            "id": "page1",
            "path": "/",
            "order": 0,
            "gitItemPath": "/root.md",
            "subPages": [
                {"path": "/Getting-Started"},
                {"path": "/Features"}
            ]
        }
        
        getting_started_response = MagicMock()
        getting_started_response.status_code = 200
        getting_started_response.json.return_value = {
            "id": "page2",
            "path": "/Getting-Started",
            "order": 1,
            "gitItemPath": "/Getting-Started.md",
            "subPages": [
                {"path": "/Getting-Started/Installation"}
            ]
        }
        
        features_response = MagicMock()
        features_response.status_code = 200
        features_response.json.return_value = {
            "id": "page3",
            "path": "/Features",
            "order": 2,
            "gitItemPath": "/Features.md",
            "subPages": []
        }
        
        installation_response = MagicMock()
        installation_response.status_code = 200
        installation_response.json.return_value = {
            "id": "page4",
            "path": "/Getting-Started/Installation",
            "order": 3,
            "gitItemPath": "/Getting-Started/Installation.md",
            "subPages": []
        }
        
        # Set side_effect to return different responses for different calls
        mock_request.side_effect = [
            root_response,
            getting_started_response,
            features_response,
            installation_response
        ]
        
        # Call the method
        result = connector._get_wiki_pages("wiki1")
        
        # Verify all API calls
        assert mock_request.call_count == 4
        
        # First call should be for the root page
        root_call = mock_request.call_args_list[0]
        assert "_apis/wiki/wikis/wiki1/pages" in root_call[1]["url"]
        assert "path" not in root_call[1]["params"]
        
        # Check that the remaining calls are for the expected paths,
        # but don't assume a specific order since it might depend on implementation
        expected_paths = {"/Getting-Started", "/Features", "/Getting-Started/Installation"}
        actual_paths = set()
        
        for i in range(1, 4):
            call = mock_request.call_args_list[i]
            assert "_apis/wiki/wikis/wiki1/pages" in call[1]["url"]
            actual_paths.add(call[1]["params"]["path"])
        
        assert actual_paths == expected_paths
        
        # Verify the result
        assert len(result) == 4
        assert result[0]["id"] == "page1"
        assert result[0]["path"] == "/"
        assert result[1]["id"] == "page2"
        assert result[1]["path"] == "/Getting-Started"
        assert result[2]["id"] == "page3"
        assert result[2]["path"] == "/Features"
        assert result[3]["id"] == "page4"
        assert result[3]["path"] == "/Getting-Started/Installation"

    @patch("requests.request")
    def test_get_wiki_page_content(self, mock_request):
        """Test the _get_wiki_page_content method."""
        # Setup connector
        connector = AzureDevOpsConnector(
            organization="testorg",
            project="testproject",
            data_types=["wikis"]
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
            "id": "page1",
            "path": "/Getting-Started",
            "order": 1,
            "gitItemPath": "/Getting-Started.md",
            "content": "# Getting Started\n\nThis page explains how to get started with the project.\n\n## Prerequisites\n\n- Node.js 14 or higher\n- npm or yarn"
        }
        mock_request.return_value = mock_response
        
        # Call the method
        result = connector._get_wiki_page_content("wiki1", "/Getting-Started")
        
        # Verify the API call
        assert mock_request.call_count == 1
        call_args = mock_request.call_args[1]
        assert "_apis/wiki/wikis/wiki1/pages" in call_args["url"]
        assert call_args["params"]["path"] == "/Getting-Started"
        assert call_args["params"]["includeContent"] == "true"
        
        # Verify the result
        assert result == "# Getting Started\n\nThis page explains how to get started with the project.\n\n## Prerequisites\n\n- Node.js 14 or higher\n- npm or yarn"

    @patch("onyx.connectors.azure_devops.connector.AzureDevOpsConnector._get_wiki_page_content")
    def test_process_wiki_page(self, mock_get_wiki_page_content):
        """Test the _process_wiki_page method."""
        # Setup connector
        connector = AzureDevOpsConnector(
            organization="testorg",
            project="testproject",
            data_types=["wikis"]
        )
        
        connector.client_config = {
            "auth": None,
            "organization": "testorg",
            "project": "testproject",
            "base_url": "https://dev.azure.com/testorg/testproject/",
            "api_version": "7.0"
        }
        
        # Mock page content
        mock_get_wiki_page_content.return_value = "# Getting Started\n\nThis page explains how to get started with the project.\n\n## Prerequisites\n\n- Node.js 14 or higher\n- npm or yarn"
        
        # Sample wiki and page data
        wiki = {
            "id": "wiki1",
            "name": "Project Wiki",
            "type": "projectWiki",
            "url": "https://dev.azure.com/testorg/testproject/_apis/wiki/wikis/wiki1",
            "remoteUrl": "https://dev.azure.com/testorg/testproject/_wiki/wikis/wiki1"
        }
        
        page = {
            "id": "page2",
            "path": "/Getting-Started",
            "order": 1,
            "gitItemPath": "/Getting-Started.md",
            "lastModifiedDate": "2023-01-01T10:00:00Z",
            "url": "https://dev.azure.com/testorg/testproject/_wiki/wikis/wiki1/2/Getting-Started"
        }
        
        # Call the method
        document = connector._process_wiki_page(wiki, page)
        
        # Verify the page content was fetched
        mock_get_wiki_page_content.assert_called_once_with("wiki1", "/Getting-Started")
        
        # Verify the document
        assert document is not None
        assert document.id == "azuredevops:testorg/testproject/wiki/wiki1/page/Getting-Started"
        assert document.title == "Wiki: Project Wiki - Getting-Started"
        assert document.source.value == "azure_devops"
        assert document.semantic_identifier == "Wiki: Project Wiki - Getting-Started"
        
        # Verify the metadata
        assert document.metadata["type"] == "wiki_page"
        assert document.metadata["wiki_id"] == "wiki1"
        assert document.metadata["wiki_name"] == "Project Wiki"
        assert document.metadata["page_id"] == "page2"
        assert document.metadata["page_path"] == "/Getting-Started"
        assert "https://dev.azure.com/testorg/testproject/_wiki/wikis/wiki1" in document.metadata["page_url"]
        assert "Getting-Started" in document.metadata["page_url"]
        
        # Verify the content
        content = document.sections[0].text
        assert "Wiki: Project Wiki" in content
        assert "Page: Getting-Started" in content
        assert "Git Path: /Getting-Started.md" in content
        assert "Content:" in content
        assert "# Getting Started" in content
        assert "This page explains how to get started with the project." in content
        assert "## Prerequisites" in content
        assert "- Node.js 14 or higher" in content
        assert "- npm or yarn" in content

    @patch("onyx.connectors.azure_devops.connector.AzureDevOpsConnector._get_wikis")
    @patch("onyx.connectors.azure_devops.connector.AzureDevOpsConnector._get_wiki_pages")
    @patch("onyx.connectors.azure_devops.connector.AzureDevOpsConnector._process_wiki_page")
    def test_load_from_checkpoint_wikis(self, mock_process_wiki_page, mock_get_wiki_pages, mock_get_wikis):
        """Test the load_from_checkpoint method for wikis."""
        # Setup connector
        connector = AzureDevOpsConnector(
            organization="testorg",
            project="testproject",
            data_types=["wikis"]
        )
        
        connector.client_config = {
            "auth": None,
            "organization": "testorg",
            "project": "testproject",
            "base_url": "https://dev.azure.com/testorg/testproject/",
            "api_version": "7.0"
        }
        connector.personal_access_token = "pat"
        
        # Mock wikis data
        mock_get_wikis.return_value = [
            {
                "id": "wiki1",
                "name": "Project Wiki",
                "type": "projectWiki"
            }
        ]
        
        # Mock wiki pages data
        mock_get_wiki_pages.return_value = [
            {
                "id": "page1",
                "path": "/"
            },
            {
                "id": "page2",
                "path": "/Getting-Started"
            }
        ]
        
        # Mock document processing
        mock_documents = [MagicMock(), MagicMock()]
        mock_process_wiki_page.side_effect = mock_documents
        
        # Create checkpoint
        from onyx.connectors.azure_devops.connector import AzureDevOpsConnectorCheckpoint
        checkpoint = AzureDevOpsConnectorCheckpoint(has_more=False, continuation_token=None)
        
        # Call the method
        start_time = int(datetime(2023, 1, 1, tzinfo=timezone.utc).timestamp())
        end_time = int(datetime(2023, 1, 3, tzinfo=timezone.utc).timestamp())
        
        # Exhaust the generator
        list(connector.load_from_checkpoint(start_time, end_time, checkpoint))
        
        # Verify the wikis were fetched
        mock_get_wikis.assert_called_once()
        
        # Verify the wiki pages were fetched
        mock_get_wiki_pages.assert_called_once()
        
        # Verify the wiki pages were processed
        assert mock_process_wiki_page.call_count == 2 