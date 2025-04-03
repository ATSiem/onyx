#!/usr/bin/env python3
"""
Test script to check if field detection is working correctly in the Azure DevOps connector.
"""

import sys
import os
import logging
import inspect

# Configure logging
logging.basicConfig(level=logging.DEBUG, 
                    format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("test_field_detection")

# Add the parent directory to sys.path to import modules
sys.path.insert(0, os.path.abspath("."))

try:
    # Try to import the connector
    logger.info("Importing AzureDevOpsConnector...")
    from backend.onyx.connectors.azure_devops.connector import AzureDevOpsConnector

    # Check if field detection is implemented
    logger.info("Checking if field detection is implemented...")
    
    # Method 1: Check if the specific string is in the function constants
    field_detection_in_consts = 'detecting available fields' in str(AzureDevOpsConnector._get_work_item_details.__code__.co_consts)
    logger.info(f"Field detection in constants: {field_detection_in_consts}")
    
    # Method 2: Look at the function source
    source_lines = inspect.getsourcelines(AzureDevOpsConnector._get_work_item_details)[0]
    field_detection_in_source = any('detecting available fields' in line for line in source_lines)
    logger.info(f"Field detection in source: {field_detection_in_source}")
    
    # Print the function constants to see what's there
    logger.info(f"Function constants: {AzureDevOpsConnector._get_work_item_details.__code__.co_consts}")
    
    # Method 3: Specifically look for missing field detection code
    missing_fields_check = any('missing_fields = set()' in line for line in source_lines)
    logger.info(f"Missing fields initialization found: {missing_fields_check}")
    
    # Print the relevant portion of the source
    for i, line in enumerate(source_lines):
        if 'detecting available fields' in line:
            logger.info(f"Line {i}: {line.strip()}")
            # Print the next few lines
            for j in range(1, 5):
                if i + j < len(source_lines):
                    logger.info(f"Line {i+j}: {source_lines[i+j].strip()}")
    
    logger.info("Field detection check complete.")
except ImportError as e:
    logger.error(f"Failed to import AzureDevOpsConnector: {str(e)}")
    sys.exit(1)
except Exception as e:
    logger.error(f"Error while checking field detection: {str(e)}")
    sys.exit(1)

# Exit with success
sys.exit(0) 