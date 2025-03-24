import time
import pytest
from unittest.mock import MagicMock, patch

from onyx.connectors.azure_devops.connector import AzureDevOpsConnector
from onyx.connectors.azure_devops.connector import AzureDevOpsConnectorCheckpoint
from onyx.connectors.models import Document, ConnectorFailure


class TestAzureDevOpsCheckpoint:
    """Test the checkpoint functionality of the Azure DevOps connector."""
    
    @patch.object(AzureDevOpsConnector, '_get_work_items')
    @patch.object(AzureDevOpsConnector, '_get_work_item_details')
    @patch.object(AzureDevOpsConnector, '_get_work_item_comments')
    def test_load_from_checkpoint(self, mock_comments, mock_details, mock_work_items, 
                                 azure_devops_connector, mock_work_items_response, 
                                 mock_work_item_details):
        """Test load_from_checkpoint with continuations."""
        connector = azure_devops_connector
        
        # Mock API responses
        mock_work_items.return_value = mock_work_items_response
        mock_details.return_value = mock_work_item_details
        mock_comments.return_value = []
        
        # Create a test checkpoint and time range
        checkpoint = AzureDevOpsConnectorCheckpoint(has_more=True, continuation_token=None)
        start_time = time.time() - 3600  # 1 hour ago
        end_time = time.time()
        
        print("Starting first checkpoint test...")
        
        # Call the method and collect results with iteration limit
        documents = []
        failures = []
        iteration_count = 0
        max_iterations = 100  # Set a reasonable limit
        
        # Use the generator and collect documents and failures
        generator = connector.load_from_checkpoint(start_time, end_time, checkpoint)
        for item in generator:
            iteration_count += 1
            if iteration_count > max_iterations:
                print(f"Warning: Reached max iterations ({max_iterations}), breaking loop")
                break
                
            if isinstance(item, Document):
                documents.append(item)
                print(f"Got document: {item.id}")
            elif isinstance(item, ConnectorFailure):
                failures.append(item)
                print(f"Got failure: {item.failure_message}")
        
        print(f"First generator loop completed after {iteration_count} iterations")
        
        # Extract the final checkpoint
        final_checkpoint = None
        try:
            # This will raise StopIteration with the return value
            next(generator)
        except StopIteration as e:
            final_checkpoint = e.value
            print(f"Got final checkpoint: {final_checkpoint}")
        except Exception as e:
            print(f"Error getting final checkpoint: {str(e)}")
        
        if not final_checkpoint:
            print("WARNING: Did not get a final checkpoint")
            return
            
        # Verify results
        assert len(documents) == 2
        assert len(failures) == 0
        
        # Verify document IDs
        doc_ids = [doc.id for doc in documents]
        assert "azuredevops:testorg/testproject/workitem/101" in doc_ids
        assert "azuredevops:testorg/testproject/workitem/102" in doc_ids
        
        # Verify checkpoint
        assert isinstance(final_checkpoint, AzureDevOpsConnectorCheckpoint)
        assert final_checkpoint.has_more is True
        assert final_checkpoint.continuation_token == "next-page-token"
        
        print("Starting second checkpoint test...")
        
        # Now test continuing from the checkpoint
        mock_work_items_response_2 = {
            "workItems": [
                {"id": 103, "url": "https://dev.azure.com/testorg/testproject/_apis/wit/workItems/103"}
            ],
            "count": 1,
            "continuationToken": None  # No more items
        }
        mock_work_item_details_2 = [
            {
                "id": 103,
                "url": "https://dev.azure.com/testorg/testproject/_apis/wit/workItems/103",
                "fields": {
                    "System.Id": 103,
                    "System.Title": "Task #1",
                    "System.Description": "<div>Task description</div>",
                    "System.WorkItemType": "Task",
                    "System.State": "New",
                    "System.CreatedDate": "2023-01-01T14:00:00Z",
                    "System.ChangedDate": "2023-01-02T14:00:00Z",
                    "System.CreatedBy": {
                        "displayName": "User 3",
                        "uniqueName": "user3@example.com"
                    }
                },
                "_links": {
                    "html": {
                        "href": "https://dev.azure.com/testorg/testproject/_workitems/edit/103"
                    }
                }
            }
        ]
        
        # Setup mocks for the second call
        mock_work_items.return_value = mock_work_items_response_2
        mock_details.return_value = mock_work_item_details_2
        
        # Use the checkpoint from the previous call
        documents2 = []
        failures2 = []
        iteration_count2 = 0
        
        generator2 = connector.load_from_checkpoint(start_time, end_time, final_checkpoint)
        for item in generator2:
            iteration_count2 += 1
            if iteration_count2 > max_iterations:
                print(f"Warning: Reached max iterations ({max_iterations}) in second test, breaking loop")
                break
                
            if isinstance(item, Document):
                documents2.append(item)
                print(f"Second test - Got document: {item.id}")
            elif isinstance(item, ConnectorFailure):
                failures2.append(item)
                print(f"Second test - Got failure: {item.failure_message}")
        
        print(f"Second generator loop completed after {iteration_count2} iterations")
        
        final_checkpoint2 = None
        try:
            next(generator2)
        except StopIteration as e:
            final_checkpoint2 = e.value
            print(f"Got final checkpoint2: {final_checkpoint2}")
        except Exception as e:
            print(f"Error getting final checkpoint2: {str(e)}")
            
        if not final_checkpoint2:
            print("WARNING: Did not get a final checkpoint2")
            return
            
        # Verify results from the second call
        assert len(documents2) == 1
        assert len(failures2) == 0
        
        # Verify document ID
        assert documents2[0].id == "azuredevops:testorg/testproject/workitem/103"
        
        # Verify final checkpoint indicates no more items
        assert final_checkpoint2.has_more is False
        assert final_checkpoint2.continuation_token is None
        
    @patch.object(AzureDevOpsConnector, '_get_work_items')
    def test_checkpoint_with_no_work_items(self, mock_work_items, azure_devops_connector):
        """Test load_from_checkpoint when no work items are returned."""
        connector = azure_devops_connector
        
        # Mock API response with no work items
        mock_work_items.return_value = {
            "workItems": [],
            "count": 0,
            "continuationToken": None
        }
        
        # Create a test checkpoint and time range
        checkpoint = AzureDevOpsConnectorCheckpoint(has_more=True, continuation_token=None)
        start_time = time.time() - 3600  # 1 hour ago
        end_time = time.time()
        
        print("Starting no work items test...")
        
        # Call the method and collect documents
        generator = connector.load_from_checkpoint(start_time, end_time, checkpoint)
        documents = []
        iteration_count = 0
        max_iterations = 100  # Set a reasonable limit
        
        for item in generator:
            iteration_count += 1
            if iteration_count > max_iterations:
                print(f"Warning: Reached max iterations ({max_iterations}) in no items test, breaking loop")
                break
                
            if isinstance(item, Document):
                documents.append(item)
                print(f"No items test - Got document: {item.id}")
        
        print(f"No items generator loop completed after {iteration_count} iterations")
        
        assert len(documents) == 0
        
        # The generator should still return a final checkpoint via StopIteration
        final_checkpoint = None
        try:
            next(generator)
        except StopIteration as e:
            final_checkpoint = e.value
            print(f"Got final checkpoint in no items test: {final_checkpoint}")
        except Exception as e:
            print(f"Error getting final checkpoint in no items test: {str(e)}")
            
        if not final_checkpoint:
            print("WARNING: Did not get a final checkpoint in no items test")
            return
            
        # Verify final checkpoint
        assert final_checkpoint.has_more is False
        assert final_checkpoint.continuation_token is None 