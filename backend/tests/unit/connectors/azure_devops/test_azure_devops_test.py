"""Test the Test Management API functionality in the Azure DevOps connector."""
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone

import requests
from onyx.connectors.azure_devops.connector import AzureDevOpsConnector


class TestAzureDevOpsTestConnector:
    """Test the Test Management API functionality in the Azure DevOps connector."""

    @patch("requests.request")
    def test_get_test_runs(self, mock_request):
        """Test the _get_test_runs method."""
        # Setup connector
        connector = AzureDevOpsConnector(
            organization="testorg",
            project="testproject",
            data_types=["test_results", "test_stats"]
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
                    "name": "Test Run 1",
                    "state": "Completed",
                    "startedDate": "2023-01-01T10:00:00Z",
                    "completedDate": "2023-01-01T11:00:00Z",
                    "buildConfiguration": {"name": "Build 1"},
                    "releaseEnvironment": {"name": "Production"},
                    "url": "https://dev.azure.com/testorg/testproject/_apis/test/runs/1",
                    "webAccessUrl": "https://dev.azure.com/testorg/testproject/_test/runs/1"
                },
                {
                    "id": 2,
                    "name": "Test Run 2",
                    "state": "InProgress",
                    "startedDate": "2023-01-02T10:00:00Z",
                    "completedDate": None,
                    "buildConfiguration": {"name": "Build 2"},
                    "releaseEnvironment": {"name": "Staging"},
                    "url": "https://dev.azure.com/testorg/testproject/_apis/test/runs/2",
                    "webAccessUrl": "https://dev.azure.com/testorg/testproject/_test/runs/2"
                }
            ]
        }
        mock_request.return_value = mock_response
        
        # Call the method
        start_time = datetime(2023, 1, 1, tzinfo=timezone.utc)
        result = connector._get_test_runs(start_time=start_time)
        
        # Verify the API call
        assert mock_request.call_count == 1
        call_args = mock_request.call_args[1]
        assert "_apis/test/runs" in call_args["url"]
        assert call_args["params"]["minLastUpdatedDate"] == "2023-01-01T00:00:00Z"
        assert call_args["params"]["$top"] == 200
        
        # Verify the result
        assert len(result["value"]) == 2
        assert result["value"][0]["id"] == 1
        assert result["value"][0]["name"] == "Test Run 1"
        assert result["value"][1]["id"] == 2
        assert result["value"][1]["name"] == "Test Run 2"

    @patch("requests.request")
    def test_get_test_results(self, mock_request):
        """Test the _get_test_results method."""
        # Setup connector
        connector = AzureDevOpsConnector(
            organization="testorg",
            project="testproject",
            data_types=["test_results"]
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
                    "id": 101,
                    "testCase": {"name": "Test Case 1"},
                    "outcome": "Passed",
                    "startedDate": "2023-01-01T10:00:00Z",
                    "completedDate": "2023-01-01T10:05:00Z"
                },
                {
                    "id": 102,
                    "testCase": {"name": "Test Case 2"},
                    "outcome": "Failed",
                    "startedDate": "2023-01-01T10:10:00Z",
                    "completedDate": "2023-01-01T10:15:00Z"
                }
            ]
        }
        mock_request.return_value = mock_response
        
        # Call the method
        result = connector._get_test_results(1)
        
        # Verify the API call
        assert mock_request.call_count == 1
        call_args = mock_request.call_args[1]
        assert "_apis/test/runs/1/results" in call_args["url"]
        
        # Verify the result
        assert len(result["value"]) == 2
        assert result["value"][0]["id"] == 101
        assert result["value"][0]["testCase"]["name"] == "Test Case 1"
        assert result["value"][0]["outcome"] == "Passed"
        assert result["value"][1]["id"] == 102
        assert result["value"][1]["testCase"]["name"] == "Test Case 2"
        assert result["value"][1]["outcome"] == "Failed"

    @patch("requests.request")
    def test_get_test_run_statistics(self, mock_request):
        """Test the _get_test_run_statistics method."""
        # Setup connector
        connector = AzureDevOpsConnector(
            organization="testorg",
            project="testproject",
            data_types=["test_stats"]
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
            "passed": 10,
            "failed": 2,
            "skipped": 1,
            "total": 13
        }
        mock_request.return_value = mock_response
        
        # Call the method
        result = connector._get_test_run_statistics(1)
        
        # Verify the API call
        assert mock_request.call_count == 1
        call_args = mock_request.call_args[1]
        assert "_apis/test/runs/1/statistics" in call_args["url"]
        
        # Verify the result
        assert result["passed"] == 10
        assert result["failed"] == 2
        assert result["skipped"] == 1
        assert result["total"] == 13

    @patch("onyx.connectors.azure_devops.connector.AzureDevOpsConnector._get_test_run_statistics")
    @patch("onyx.connectors.azure_devops.connector.AzureDevOpsConnector._get_test_results")
    def test_process_test_run(self, mock_get_test_results, mock_get_test_run_statistics):
        """Test the _process_test_run method."""
        # Setup connector
        connector = AzureDevOpsConnector(
            organization="testorg",
            project="testproject",
            data_types=["test_results", "test_stats"]
        )
        
        connector.client_config = {
            "auth": None,
            "organization": "testorg",
            "project": "testproject",
            "base_url": "https://dev.azure.com/testorg/testproject/",
            "api_version": "7.0"
        }
        
        # Mock statistics data
        mock_get_test_run_statistics.return_value = {
            "passed": 10,
            "failed": 2,
            "skipped": 1,
            "total": 13
        }
        
        # Mock test results data
        mock_get_test_results.return_value = {
            "value": [
                {"testCase": {"name": "Test Case 1"}, "outcome": "Passed"},
                {"testCase": {"name": "Test Case 2"}, "outcome": "Failed"},
                {"testCase": {"name": "Test Case 3"}, "outcome": "Passed"}
            ]
        }
        
        # Sample test run data
        test_run = {
            "id": 1,
            "name": "Sprint 1 Regression Tests",
            "state": "Completed",
            "startedDate": "2023-01-01T10:00:00Z",
            "completedDate": "2023-01-01T11:00:00Z",
            "buildConfiguration": {"name": "Build 123"},
            "releaseEnvironment": {"name": "Production"},
            "webAccessUrl": "https://dev.azure.com/testorg/testproject/_test/runs/1"
        }
        
        # Call the method
        document = connector._process_test_run(test_run, include_results=True)
        
        # Verify the statistics were fetched
        mock_get_test_run_statistics.assert_called_once_with(1)
        
        # Verify the results were fetched
        mock_get_test_results.assert_called_once_with(1)
        
        # Verify the document
        assert document is not None
        assert document.id == "azuredevops:testorg/testproject/test/run/1"
        assert document.title == "Test Run: Sprint 1 Regression Tests"
        assert document.source.value == "azure_devops"
        assert document.semantic_identifier == "Test Run: Sprint 1 Regression Tests [Completed]"
        
        # Verify the metadata
        assert document.metadata["type"] == "test_run"
        assert document.metadata["run_id"] == "1"
        assert document.metadata["name"] == "Sprint 1 Regression Tests"
        assert document.metadata["state"] == "Completed"
        assert document.metadata["build_name"] == "Build 123"
        assert document.metadata["release_name"] == "Production"
        assert document.metadata["test_run_url"] == "https://dev.azure.com/testorg/testproject/_test/runs/1"
        assert document.metadata["stats_passed"] == "10"
        assert document.metadata["stats_failed"] == "2"
        assert document.metadata["stats_skipped"] == "1"
        assert document.metadata["stats_total"] == "13"
        
        # Verify the content
        content = document.sections[0].text
        assert "Test Run: Sprint 1 Regression Tests" in content
        assert "State: Completed" in content
        assert "Build: Build 123" in content
        assert "Release: Production" in content
        assert "Started: 2023-01-01" in content
        assert "Completed: 2023-01-01" in content
        assert "Results Summary:" in content
        assert "passed: 10" in content
        assert "failed: 2" in content
        assert "skipped: 1" in content
        assert "Detailed Test Results:" in content
        assert "- Test Case 1: Passed" in content
        assert "- Test Case 2: Failed" in content
        assert "- Test Case 3: Passed" in content

    @patch("onyx.connectors.azure_devops.connector.AzureDevOpsConnector._get_test_runs")
    @patch("onyx.connectors.azure_devops.connector.AzureDevOpsConnector._process_test_run")
    def test_load_from_checkpoint_test_results(self, mock_process_test_run, mock_get_test_runs):
        """Test the load_from_checkpoint method for test results."""
        # Setup connector
        connector = AzureDevOpsConnector(
            organization="testorg",
            project="testproject",
            data_types=["test_results", "test_stats"]
        )
        
        connector.client_config = {
            "auth": None,
            "organization": "testorg",
            "project": "testproject",
            "base_url": "https://dev.azure.com/testorg/testproject/",
            "api_version": "7.0"
        }
        connector.personal_access_token = "pat"
        
        # Mock test runs data
        mock_get_test_runs.return_value = {
            "value": [
                {
                    "id": 1,
                    "name": "Test Run 1",
                    "state": "Completed"
                },
                {
                    "id": 2,
                    "name": "Test Run 2",
                    "state": "InProgress"
                }
            ]
        }
        
        # Mock document processing
        mock_documents = [MagicMock(), MagicMock()]
        mock_process_test_run.side_effect = mock_documents
        
        # Create checkpoint
        from onyx.connectors.azure_devops.connector import AzureDevOpsConnectorCheckpoint
        checkpoint = AzureDevOpsConnectorCheckpoint(has_more=False, continuation_token=None)
        
        # Call the method
        start_time = int(datetime(2023, 1, 1, tzinfo=timezone.utc).timestamp())
        end_time = int(datetime(2023, 1, 3, tzinfo=timezone.utc).timestamp())
        
        # Exhaust the generator
        list(connector.load_from_checkpoint(start_time, end_time, checkpoint))
        
        # Verify the test runs were fetched
        mock_get_test_runs.assert_called_once()
        
        # Verify the test runs were processed
        assert mock_process_test_run.call_count == 2 