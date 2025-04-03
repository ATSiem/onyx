#!/usr/bin/env python3
"""
Test if field detection is implemented in the container.
"""

import inspect
import logging

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger()

# Import the connector
from onyx.connectors.azure_devops.connector import AzureDevOpsConnector

# Check if field detection is implemented
source = inspect.getsource(AzureDevOpsConnector._get_work_item_details)
print("\n\n===== FIELD DETECTION CHECK =====")

# Check method 1: Look for the specific string in the function constants
has_detection_in_consts = 'detecting available fields' in str(AzureDevOpsConnector._get_work_item_details.__code__.co_consts)
print(f"RESULT 1: Field detection in constants: {has_detection_in_consts}")

# Check method 2: Look for the string in the source code
has_detection_in_source = 'detecting available fields' in source
print(f"RESULT 2: Field detection in source code: {has_detection_in_source}")

# Check method 3: Look for missing fields initialization
has_missing_fields = 'missing_fields = set()' in source
print(f"RESULT 3: Missing fields initialization: {has_missing_fields}")

# Print the function constants
print(f"\nFunction constants: {AzureDevOpsConnector._get_work_item_details.__code__.co_consts}")

# Check for special case code
has_dfp10 = 'DFP_10' in source
print(f"HAS DFP_10 SPECIAL CASE: {has_dfp10}")

print("\n===== RELEVANT CODE SECTIONS =====")
# Extract and print the detecting fields section if it exists
lines = source.split('\n')
for i, line in enumerate(lines):
    if 'detecting available fields' in line:
        start = max(0, i - 5)
        end = min(len(lines), i + 15)
        print(f"\nFound 'detecting available fields' at line {i + 1}:")
        for j in range(start, end):
            print(f"{j + 1}: {lines[j]}")

# Extract and print any DFP_10 related code
for i, line in enumerate(lines):
    if 'DFP_10' in line:
        start = max(0, i - 5)
        end = min(len(lines), i + 15)
        print(f"\nFound 'DFP_10' at line {i + 1}:")
        for j in range(start, end):
            print(f"{j + 1}: {lines[j]}")

print("\n===== END OF CHECK =====") 