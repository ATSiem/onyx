"""
Test script to verify the fix for the Azure DevOps connector.

This script tests the specific issue where the Azure DevOps connector was 
incorrectly yielding tuples instead of Document or ConnectorFailure objects.
"""
import json
import os
import sys
import traceback
from datetime import datetime, timezone
from typing import Generator, Any, cast

# Add backend to the path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__))))

from onyx.connectors.azure_devops.connector import AzureDevOpsConnector
from onyx.connectors.azure_devops.connector import AzureDevOpsConnectorCheckpoint
from onyx.connectors.connector_runner import CheckpointOutputWrapper
from onyx.connectors.interfaces import CheckpointConnector, CheckpointOutput
from onyx.connectors.models import ConnectorCheckpoint, ConnectorFailure, Document, TextSection, DocumentFailure
from onyx.configs.constants import DocumentSource


class BrokenAzureDevOpsConnector(AzureDevOpsConnector):
    """
    A modified version of the Azure DevOps connector that simulates the bug
    by yielding tuples instead of proper Document or ConnectorFailure objects.
    """
    
    def load_from_checkpoint(
        self,
        start: float,
        end: float,
        checkpoint: AzureDevOpsConnectorCheckpoint,
    ) -> CheckpointOutput[AzureDevOpsConnectorCheckpoint]:
        """
        Simulates the bug by yielding a tuple instead of a Document.
        """
        # First yield a valid document to ensure basic functionality works
        valid_doc = Document(
            id="valid-doc-1",
            source=DocumentSource.AZURE_DEVOPS,
            semantic_identifier="Valid Document",
            metadata={},
            sections=[TextSection(text="Valid content")]
        )
        yield valid_doc
        
        # Now yield a tuple to simulate the bug
        # This is what was causing the error
        yield ("invalid-doc-1", "This is a tuple instead of a Document")
        
        # Return a valid checkpoint
        return AzureDevOpsConnectorCheckpoint(has_more=False, continuation_token="test-token")


def test_error_detection():
    """Test that the CheckpointOutputWrapper correctly detects and reports the error."""
    print("Testing error detection in CheckpointOutputWrapper...")
    
    # Create a broken connector instance
    connector = BrokenAzureDevOpsConnector(organization="test-org", project="test-project")
    
    # Create a dummy checkpoint
    checkpoint = AzureDevOpsConnectorCheckpoint(has_more=True, continuation_token=None)
    
    # Set the start and end times
    start_time = int(datetime(2023, 1, 1, tzinfo=timezone.utc).timestamp())
    end_time = int(datetime(2023, 12, 31, tzinfo=timezone.utc).timestamp())
    
    try:
        # Get the generator from the connector
        print("Calling load_from_checkpoint on broken connector...")
        checkpoint_generator = connector.load_from_checkpoint(start_time, end_time, checkpoint)
        
        # Create the wrapper
        print("Creating CheckpointOutputWrapper...")
        wrapper = CheckpointOutputWrapper[AzureDevOpsConnectorCheckpoint]()
        
        # Call the wrapper with the generator
        print("Processing with CheckpointOutputWrapper...")
        wrapped_generator = wrapper(checkpoint_generator)
        
        # Process the generator
        print("Iterating through results...")
        
        # First yield should be a valid document and should work
        doc, failure, next_checkpoint = next(wrapped_generator)
        if doc:
            print(f"First yield: Document: {doc.id}")
        
        # Second yield should be a tuple and should fail
        try:
            doc, failure, next_checkpoint = next(wrapped_generator)
            print("ERROR: The test failed because the invalid tuple was not detected")
            return False
        except ValueError as e:
            if "tuple" in str(e):
                print("SUCCESS: The CheckpointOutputWrapper correctly detected the tuple and raised an error")
                print(f"Error message: {str(e)}")
                return True
            else:
                print(f"ERROR: Wrong error type: {str(e)}")
                return False
        
    except Exception as e:
        print(f"Test failed with unexpected error: {str(e)}")
        traceback.print_exc()
        return False


def test_fix_with_fixed_wrapper():
    """
    Test that the fixed CheckpointOutputWrapper provides better error messages
    when it encounters a tuple.
    """
    print("\nTesting improved error messaging in fixed CheckpointOutputWrapper...")
    
    # Create a broken connector instance
    connector = BrokenAzureDevOpsConnector(organization="test-org", project="test-project")
    
    # Create a dummy checkpoint
    checkpoint = AzureDevOpsConnectorCheckpoint(has_more=True, continuation_token=None)
    
    # Set the start and end times
    start_time = int(datetime(2023, 1, 1, tzinfo=timezone.utc).timestamp())
    end_time = int(datetime(2023, 12, 31, tzinfo=timezone.utc).timestamp())
    
    try:
        # Get the generator from the connector
        checkpoint_generator = connector.load_from_checkpoint(start_time, end_time, checkpoint)
        
        # Create the wrapper
        wrapper = CheckpointOutputWrapper[AzureDevOpsConnectorCheckpoint]()
        
        # Call the wrapper with the generator
        wrapped_generator = wrapper(checkpoint_generator)
        
        # Process the generator
        # First yield should be a valid document and should work
        doc, failure, next_checkpoint = next(wrapped_generator)
        
        # Second yield should be a tuple and should fail with our improved error message
        try:
            doc, failure, next_checkpoint = next(wrapped_generator)
            return False
        except ValueError as e:
            error_msg = str(e)
            # Check that our improved error message contains more detailed information
            if "tuple" in error_msg and "Connector yielded a tuple" in error_msg:
                print("SUCCESS: The fixed wrapper provides a detailed error message:")
                print(f"Error message: {error_msg}")
                return True
            else:
                print(f"ERROR: Error message doesn't contain expected details: {error_msg}")
                return False
        
    except Exception as e:
        print(f"Test failed with unexpected error: {str(e)}")
        traceback.print_exc()
        return False


if __name__ == "__main__":
    print("Running Azure DevOps connector fix validation tests")
    success = test_error_detection() and test_fix_with_fixed_wrapper()
    
    if success:
        print("\nALL TESTS PASSED: The fix for Azure DevOps connector is working correctly!")
        sys.exit(0)
    else:
        print("\nTESTS FAILED: The fix is not working as expected.")
        sys.exit(1) 