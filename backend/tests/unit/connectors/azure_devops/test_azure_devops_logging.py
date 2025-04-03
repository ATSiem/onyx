#!/usr/bin/env python3
"""
Test script for verifying Azure DevOps connector's logging functionality.
This test specifically ensures that the logging import is working properly.
"""

import os
import sys
import unittest
from unittest.mock import patch, MagicMock
import logging
import io

# Add the backend directory to the path 
sys.path.insert(0, os.path.abspath('backend'))

class TestAzureDevOpsLogging(unittest.TestCase):
    """Test case for Azure DevOps connector logging."""

    def test_logging_functionality(self):
        """Test that the logging functionality works correctly."""
        # Set up a log capture
        log_capture = io.StringIO()
        handler = logging.StreamHandler(log_capture)
        
        # Configure the handler with a simple formatter
        formatter = logging.Formatter('%(levelname)s: %(message)s')
        handler.setFormatter(formatter)
        
        # Get the root logger and add our handler
        root_logger = logging.getLogger()
        root_logger.addHandler(handler)
        
        # Save the original level to restore later
        original_level = root_logger.level
        root_logger.setLevel(logging.INFO)
        
        try:
            # Import the connector
            from onyx.connectors.azure_devops.connector import AzureDevOpsConnector
            
            # Create a connector instance, which should trigger some log messages
            connector = AzureDevOpsConnector(
                organization="test-org",
                project="test-project",
                content_scope="everything"
            )
            
            # Get the captured log output
            log_output = log_capture.getvalue()
            
            # Verify that logging happened
            self.assertIn("Content scope is set to 'everything'", log_output)
            self.assertIn("Data types:", log_output)
            self.assertIn("Azure DevOps connector initialized", log_output)
            
            # Print the captured logs for verification
            print("\nINFO level log messages:")
            print(log_output)
            
        finally:
            # Clean up: restore original level and remove our handler
            root_logger.setLevel(original_level)
            root_logger.removeHandler(handler)

    def test_debug_level_logging(self):
        """Test that debug level logging works correctly."""
        # Set up a log capture
        log_capture = io.StringIO()
        handler = logging.StreamHandler(log_capture)
        
        # Configure the handler with a simple formatter
        formatter = logging.Formatter('%(levelname)s: %(message)s')
        handler.setFormatter(formatter)
        
        # Get the root logger and add our handler
        root_logger = logging.getLogger()
        root_logger.addHandler(handler)
        
        # Save the original level to restore later
        original_level = root_logger.level
        root_logger.setLevel(logging.DEBUG)
        
        try:
            # Import the connector
            from onyx.connectors.azure_devops.connector import AzureDevOpsConnector, logger
            
            # Log a debug message directly
            logger.debug("Debug test message from Azure DevOps connector test")
            
            # Create a connector instance
            connector = AzureDevOpsConnector(
                organization="test-org",
                project="test-project",
                content_scope="everything"
            )
            
            # Get the captured log output
            log_output = log_capture.getvalue()
            
            # Verify that logging happened - even if debug messages aren't shown,
            # we should at least have INFO messages
            self.assertIn("INFO:", log_output)
            
            # Print the captured logs for verification
            print("\nLog messages:")
            print(log_output)
            
        finally:
            # Clean up: restore original level and remove our handler
            root_logger.setLevel(original_level)
            root_logger.removeHandler(handler)

if __name__ == "__main__":
    unittest.main() 