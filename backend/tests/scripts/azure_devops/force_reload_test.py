#!/usr/bin/env python3
"""
Test script to force reload the module and check for field detection.
"""

import importlib
import sys
import inspect

# First check without reloading
print("\n===== BEFORE RELOAD =====")
from onyx.connectors.azure_devops.connector import AzureDevOpsConnector
source_before = inspect.getsource(AzureDevOpsConnector._get_work_item_details)
has_detection_before = 'detecting available fields' in source_before
print(f"Field detection in source: {has_detection_before}")

# Now try to force reload everything
print("\n===== FORCING RELOAD =====")
# Remove module from cache
for module_name in list(sys.modules.keys()):
    if 'onyx.connectors.azure_devops' in module_name:
        print(f"Removing module from cache: {module_name}")
        del sys.modules[module_name]

# Force Python to clear bytecode cache if possible
try:
    import importlib.util.cache_from_source as cache_from_source
    print("Clearing bytecode cache if possible")
except ImportError:
    print("Cannot access bytecode cache directly")

# Reimport
print("Reimporting module...")
import onyx.connectors.azure_devops.connector
importlib.reload(onyx.connectors.azure_devops.connector)
from onyx.connectors.azure_devops.connector import AzureDevOpsConnector as ReloadedConnector

# Check again
source_after = inspect.getsource(ReloadedConnector._get_work_item_details)
has_detection_after = 'detecting available fields' in source_after
print(f"Field detection in source after reload: {has_detection_after}")

# Print actual file content
print("\n===== FILE CONTENT CHECK =====")
with open('/app/onyx/connectors/azure_devops/connector.py', 'r') as f:
    content = f.read()
    has_detection_in_file = 'detecting available fields' in content
    print(f"Field detection in file content: {has_detection_in_file}")

# Compare module vs file
print("\n===== MODULE VS FILE COMPARISON =====")
print(f"Module location: {onyx.connectors.azure_devops.connector.__file__}")
print(f"Module matches file: {has_detection_after == has_detection_in_file}")

if not has_detection_after and has_detection_in_file:
    print("\nWARNING: Module doesn't match file content!")
    print("This suggests there might be a cached bytecode (.pyc) file that's not being updated.")
    
    # Look for any .pyc files
    import os
    module_dir = os.path.dirname(onyx.connectors.azure_devops.connector.__file__)
    print(f"\nChecking for .pyc files in {module_dir}:")
    for filename in os.listdir(module_dir):
        if filename.endswith('.pyc'):
            pyc_path = os.path.join(module_dir, filename)
            print(f"Found: {pyc_path} (Modified: {os.path.getmtime(pyc_path)})")

print("\n===== END OF TEST =====") 