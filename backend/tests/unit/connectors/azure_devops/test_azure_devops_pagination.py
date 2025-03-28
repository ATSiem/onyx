import pytest
from unittest.mock import MagicMock, patch
import requests
import time
from datetime import datetime

from onyx.connectors.azure_devops.connector import AzureDevOpsConnector
from onyx.connectors.azure_devops.connector import AzureDevOpsConnectorCheckpoint
from onyx.connectors.exceptions import ConnectorValidationError


class TestAzureDevOpsConnectorPagination:
    """Test pagination and rate limiting in the Azure DevOps connector."""

    def test_pagination_with_continuation_token(self):
        """Test that the connector correctly handles continuation tokens for pagination."""
        # Initialize the connector
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
        connector.personal_access_token = "test_token"  # Set test token to avoid credential errors

        # Mock the API response for WIQL query
        with patch.object(connector, '_make_api_request') as mock_request:
            # First response with continuation token
            mock_response1 = MagicMock()
            mock_response1.json.return_value = {
                "workItems": [{"id": 1}, {"id": 2}],
                "continuationToken": "token123"
            }
            # Ensure all responses have raise_for_status method
            mock_response1.raise_for_status = MagicMock()
            
            # Second response without continuation token
            mock_response2 = MagicMock()
            mock_response2.json.return_value = {
                "workItems": [{"id": 3}, {"id": 4}],
                "continuationToken": None
            }
            mock_response2.raise_for_status = MagicMock()
            
            # Mock work item details responses
            mock_details_response1 = MagicMock()
            mock_details_response1.json.return_value = {
                "value": [
                    {
                        "id": 1,
                        "fields": {
                            "System.Id": 1,
                            "System.Title": "Test Item 1",
                            "System.WorkItemType": "Bug",
                            "System.State": "Active",
                            "System.ChangedDate": "2023-01-01T12:00:00Z"
                        }
                    },
                    {
                        "id": 2,
                        "fields": {
                            "System.Id": 2,
                            "System.Title": "Test Item 2",
                            "System.WorkItemType": "Bug",
                            "System.State": "Active",
                            "System.ChangedDate": "2023-01-01T12:00:00Z"
                        }
                    }
                ]
            }
            mock_details_response1.raise_for_status = MagicMock()
            
            mock_details_response2 = MagicMock()
            mock_details_response2.json.return_value = {
                "value": [
                    {
                        "id": 3,
                        "fields": {
                            "System.Id": 3,
                            "System.Title": "Test Item 3",
                            "System.WorkItemType": "Bug",
                            "System.State": "Active",
                            "System.ChangedDate": "2023-01-01T12:00:00Z"
                        }
                    },
                    {
                        "id": 4,
                        "fields": {
                            "System.Id": 4,
                            "System.Title": "Test Item 4",
                            "System.WorkItemType": "Bug",
                            "System.State": "Active",
                            "System.ChangedDate": "2023-01-01T12:00:00Z"
                        }
                    }
                ]
            }
            mock_details_response2.raise_for_status = MagicMock()
            
            # Also patch _get_work_item_comments to return an empty list
            with patch.object(connector, '_get_work_item_comments', return_value=[]):
                # Set up mock to return different responses in sequence
                mock_request.side_effect = [
                    mock_response1,  # First WIQL query
                    mock_details_response1,  # Details for items 1-2
                    mock_response2,  # Second WIQL query with continuation token
                    mock_details_response2,  # Details for items 3-4
                ]
                
                # Create a checkpoint and call load_from_checkpoint
                checkpoint = AzureDevOpsConnectorCheckpoint(has_more=True, continuation_token=None)
                start_time = int(datetime(2023, 1, 1).timestamp())
                end_time = int(datetime(2023, 1, 31).timestamp())
                
                # Collect documents from the connector
                documents = list(connector.load_from_checkpoint(start_time, end_time, checkpoint))
                
                # Should have 4 documents (one for each work item)
                assert len(documents) == 4
                
                # Check that correct API calls were made
                assert mock_request.call_count == 4
                
                # Check the continuation token was used
                # The second call to _get_work_items should include the token
                args, kwargs = mock_request.call_args_list[2]
                assert 'continuationToken' in kwargs.get('data', '')

    def test_rate_limit_handling(self):
        """Test that the connector correctly handles rate limiting responses."""
        # Initialize the connector
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
        
        # Create a rate limit response
        rate_limit_response = MagicMock()
        rate_limit_response.status_code = 429
        rate_limit_response.headers = {'Retry-After': '2'}
        
        # Create a success response for the retry
        success_response = MagicMock()
        success_response.status_code = 200
        success_response.json.return_value = {
            "workItems": [{"id": 1}],
            "continuationToken": None
        }
        
        # Mock work item details response
        details_response = MagicMock()
        details_response.json.return_value = {
            "value": [
                {
                    "id": 1,
                    "fields": {
                        "System.Id": 1,
                        "System.Title": "Test Item 1",
                        "System.WorkItemType": "Bug",
                        "System.State": "Active",
                        "System.ChangedDate": "2023-01-01T12:00:00Z"
                    }
                }
            ]
        }
        
        # Testing the _make_api_request method directly since that's where rate limiting is handled
        with patch('time.sleep') as mock_sleep:
            with patch('requests.request') as mock_request:
                # First return rate limited response, then success
                mock_request.side_effect = [rate_limit_response, success_response]
                
                # Call the method directly - should handle rate limiting internally
                response = connector._make_api_request('_apis/wit/wiql')
                
                # Verify sleep was called with correct duration
                mock_sleep.assert_called_with(2)
                
                # Verify request was called twice (initial + retry)
                assert mock_request.call_count == 2
                
                # Verify the method returned the success response
                assert response == success_response

    def test_empty_response_handling(self):
        """Test that the connector correctly handles empty responses."""
        # Initialize the connector
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
        connector.personal_access_token = "test_token"  # Set test token to avoid credential errors

        # Create an empty response
        empty_response = MagicMock()
        empty_response.json.return_value = {
            "workItems": [],
            "continuationToken": None
        }
        
        with patch.object(connector, '_make_api_request') as mock_request:
            # Set up mock to return empty response
            mock_request.return_value = empty_response
            
            # Create a checkpoint and call load_from_checkpoint
            checkpoint = AzureDevOpsConnectorCheckpoint(has_more=True, continuation_token=None)
            start_time = int(datetime(2023, 1, 1).timestamp())
            end_time = int(datetime(2023, 1, 31).timestamp())
            
            # Collect documents from the connector
            documents = list(connector.load_from_checkpoint(start_time, end_time, checkpoint))
            
            # Should have 0 documents
            assert len(documents) == 0
            
            # We can't check has_more from documents since there are no documents
            # Instead, let's verify that mock_request was called
            mock_request.assert_called_once()

    def test_network_error_handling(self):
        """Test that the connector correctly handles network errors."""
        # Initialize the connector
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
        connector.personal_access_token = "test_token"  # Set test token to avoid credential errors

        with patch.object(connector, '_make_api_request') as mock_request:
            # Set up mock to raise a network error
            mock_request.side_effect = requests.exceptions.ConnectionError("Network error")
            
            # Create a checkpoint and call load_from_checkpoint
            checkpoint = AzureDevOpsConnectorCheckpoint(has_more=True, continuation_token=None)
            start_time = int(datetime(2023, 1, 1).timestamp())
            end_time = int(datetime(2023, 1, 31).timestamp())
            
            # Collect documents from the connector
            documents = list(connector.load_from_checkpoint(start_time, end_time, checkpoint))
            
            # Should have 1 document which is a ConnectorFailure
            assert len(documents) == 1
            assert hasattr(documents[0], 'failure_message')
            assert "Network error" in documents[0].failure_message

    def test_batch_processing(self):
        """Test that the connector correctly processes items in batches."""
        # Initialize the connector
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
        connector.personal_access_token = "test_token"  # Set test token to avoid credential errors

        # Create a list of 300 work item IDs (exceeds the 200 item batch limit)
        work_item_ids = list(range(1, 301))

        # For each batch of 200 work items, create a response
        first_batch = work_item_ids[:200]
        second_batch = work_item_ids[200:]

        # Create the test responses
        wiql_response = MagicMock()
        wiql_response.json.return_value = {
            "workItems": [{"id": id} for id in work_item_ids],
            "continuationToken": None
        }
        wiql_response.raise_for_status.return_value = None

        first_batch_response = MagicMock()
        first_batch_response.json.return_value = {
            "value": [
                {
                    "id": id,
                    "fields": {
                        "System.Id": id,
                        "System.Title": f"Test Item {id}",
                        "System.WorkItemType": "Bug",
                        "System.State": "Active",
                        "System.ChangedDate": "2023-01-01T12:00:00Z"
                    }
                } for id in first_batch
            ]
        }
        first_batch_response.raise_for_status.return_value = None

        second_batch_response = MagicMock()
        second_batch_response.json.return_value = {
            "value": [
                {
                    "id": id,
                    "fields": {
                        "System.Id": id,
                        "System.Title": f"Test Item {id}",
                        "System.WorkItemType": "Bug",
                        "System.State": "Active",
                        "System.ChangedDate": "2023-01-01T12:00:00Z"
                    }
                } for id in second_batch
            ]
        }
        second_batch_response.raise_for_status.return_value = None

        with patch.object(connector, '_make_api_request') as mock_request:
            # Set up mock to return our pre-defined responses
            mock_request.side_effect = [
                wiql_response,
                first_batch_response,
                second_batch_response
            ]

            # Patch the _get_work_item_comments method to return empty list to simplify test
            with patch.object(connector, '_get_work_item_comments', return_value=[]):
                # Create a checkpoint and call load_from_checkpoint
                checkpoint = AzureDevOpsConnectorCheckpoint(has_more=True, continuation_token=None)
                start_time = int(datetime(2023, 1, 1).timestamp())
                end_time = int(datetime(2023, 1, 31).timestamp())

                # Collect documents from the connector
                documents = list(connector.load_from_checkpoint(start_time, end_time, checkpoint))
                
                # Should have 300 documents (one for each work item)
                assert len(documents) == 300

                # Check that we made 3 API calls:
                # 1. The WIQL query
                # 2-3. Two batches of work item details (at most 200 items each)
                assert mock_request.call_count == 3

                # Verify that IDs in documents match our work_item_ids
                # Extract work_item_id from the semantic_identifier instead of title
                doc_ids = []
                for doc in documents:
                    semantic_id = doc.semantic_identifier
                    # Extract ID from format like "Bug 123: Test Item 123 [Not Resolved]"
                    id_part = semantic_id.split(':', 1)[0].split(' ')[1]
                    doc_ids.append(int(id_part))
                
                # Sort and compare IDs
                assert sorted(doc_ids) == sorted(work_item_ids) 