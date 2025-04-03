#!/usr/bin/env python3
"""
Fix for Azure DevOps connector to handle branch names correctly
This addresses the 'TF401175:The version descriptor <Branch: master> could not be resolved' error
"""

import os
import sys
import logging
import tempfile
import shutil
from datetime import datetime, timezone, timedelta
import argparse
import re

# Add the parent directory to sys.path to import modules
script_dir = os.path.dirname(os.path.abspath(__file__))
backend_dir = os.path.abspath(os.path.join(script_dir, "../../../"))
sys.path.insert(0, backend_dir)

try:
    from onyx.connectors.azure_devops.connector import AzureDevOpsConnector
except ImportError:
    print("ERROR: Cannot import AzureDevOpsConnector. Make sure you're running this from the project root.")
    sys.exit(1)

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def fix_connector_branch_issue(connector_file, backup=True):
    """
    Fix the branch name issue in the Azure DevOps connector
    
    Args:
        connector_file: Path to the connector.py file
        backup: Whether to create a backup of the original file
    
    Returns:
        bool: True if successful, False otherwise
    """
    logger.info(f"Fixing branch name issue in {connector_file}")
    
    if not os.path.exists(connector_file):
        logger.error(f"Connector file not found: {connector_file}")
        return False
    
    # Create backup if requested
    if backup:
        backup_file = f"{connector_file}.bak.{datetime.now().strftime('%Y%m%d%H%M%S')}"
        logger.info(f"Creating backup at {backup_file}")
        shutil.copy2(connector_file, backup_file)
    
    # Read the file
    with open(connector_file, 'r') as f:
        content = f.read()
    
    # Find the _get_commits method and update the branch name parameter
    pattern = r'def _get_commits\(\s*self,\s*repository_id:.*?\):\s*.*?params\s*=\s*\{.*?\'searchCriteria\.itemVersion\.version\':\s*\'master\''
    
    # Check if the pattern exists before replacing
    if not re.search(pattern, content, re.DOTALL):
        logger.error("Could not find the branch name parameter in the _get_commits method")
        fixed_content = modify_method_manually(content)
    else:
        # Replace the branch name parameter
        fixed_content = re.sub(
            pattern,
            lambda m: m.group(0).replace("'searchCriteria.itemVersion.version': 'master'", 
                                        "# Try without branch filter to get all commits\n            # 'searchCriteria.itemVersion.version': 'master',  # This was causing 404 errors when the branch doesn't exist"),
            content,
            flags=re.DOTALL
        )
    
    # Save the fixed file
    with open(connector_file, 'w') as f:
        f.write(fixed_content)
    
    logger.info(f"Fixed connector file saved to {connector_file}")
    return True

def modify_method_manually(content):
    """
    Manually modify the _get_commits method if the regex pattern didn't match
    """
    # Find the _get_commits method start
    method_start = content.find("def _get_commits")
    if method_start == -1:
        logger.error("Could not find the _get_commits method")
        return content
    
    # Find the params declaration
    params_start = content.find("params = {", method_start)
    if params_start == -1:
        logger.error("Could not find the params declaration in _get_commits method")
        return content
    
    # Find the position to insert our change
    line_end = content.find("\n", params_start)
    
    # Check if searchCriteria.itemVersion.version is there
    if "searchCriteria.itemVersion.version" in content[params_start:params_start+500]:
        # Replace the line
        version_line_start = content.find("'searchCriteria.itemVersion.version'", params_start)
        version_line_end = content.find("\n", version_line_start)
        
        before = content[:version_line_start]
        after = content[version_line_end:]
        
        return before + "# 'searchCriteria.itemVersion.version': 'master',  # Commented out to avoid branch name issues" + after
    else:
        # The parameter isn't there, so return unchanged
        logger.warning("Could not find 'searchCriteria.itemVersion.version' parameter")
        return content

def find_connector_file(directory=None):
    """Find the Azure DevOps connector file"""
    search_paths = [
        "backend/onyx/connectors/azure_devops/connector.py",
        "onyx/connectors/azure_devops/connector.py",
        "../backend/onyx/connectors/azure_devops/connector.py",
        "../onyx/connectors/azure_devops/connector.py"
    ]
    
    if directory:
        search_paths = [os.path.join(directory, p) for p in search_paths]
    
    for path in search_paths:
        if os.path.exists(path):
            return path
    
    return None

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fix Azure DevOps connector branch name issue")
    parser.add_argument("--file", help="Path to connector.py file (optional, will attempt to find it automatically)")
    parser.add_argument("--no-backup", action="store_true", help="Don't create a backup of the original file")
    args = parser.parse_args()
    
    connector_file = args.file
    if not connector_file:
        connector_file = find_connector_file()
        if not connector_file:
            logger.error("Could not find connector.py file automatically. Please specify with --file")
            sys.exit(1)
    
    success = fix_connector_branch_issue(connector_file, not args.no_backup)
    sys.exit(0 if success else 1) 