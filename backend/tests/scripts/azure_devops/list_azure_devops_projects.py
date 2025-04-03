#!/usr/bin/env python3
"""
Script to list all projects in an Azure DevOps organization
This helps identify the exact project names to use for the connector
"""

import sys
import requests
from requests.auth import HTTPBasicAuth
import json
import argparse

def list_devops_projects(organization, pat):
    """
    List all projects in an Azure DevOps organization
    """
    print(f"\n{'=' * 50}")
    print(f"LISTING PROJECTS FOR ORGANIZATION: {organization}")
    print(f"{'=' * 50}\n")
    
    # Base URL for API calls
    base_url = f"https://dev.azure.com/{organization}"
    
    # Setup basic auth with PAT
    auth = HTTPBasicAuth('', pat)
    
    # Headers for API requests
    headers = {
        'Accept': 'application/json',
        'Content-Type': 'application/json',
    }
    
    # Common parameters
    params = {
        'api-version': '7.0'  # Use latest stable API version
    }
    
    try:
        response = requests.get(
            f"{base_url}/_apis/projects",
            auth=auth,
            headers=headers,
            params=params
        )
        
        if response.status_code == 200:
            result = response.json()
            projects = result.get("value", [])
            project_count = len(projects)
            
            print(f"Found {project_count} projects in organization '{organization}':\n")
            
            # Display project information in a formatted table
            print(f"{'ID':<36} | {'Name':<30} | {'State':<10} | {'Description'}")
            print(f"{'-' * 36} | {'-' * 30} | {'-' * 10} | {'-' * 30}")
            
            for project in projects:
                project_id = project.get("id", "N/A")
                project_name = project.get("name", "N/A")
                project_state = project.get("state", "N/A")
                project_desc = project.get("description", "N/A")
                
                # Truncate description if too long
                if project_desc and len(project_desc) > 50:
                    project_desc = project_desc[:47] + "..."
                
                print(f"{project_id} | {project_name:<30} | {project_state:<10} | {project_desc}")
            
            print(f"\n{'=' * 50}")
            print("RECOMMENDATIONS:")
            print(f"{'=' * 50}")
            print("1. Copy the exact project name (case-sensitive) to use in your connector")
            print("2. Verify your PAT has access to the specific project you're trying to use")
            print("3. Ensure your PAT has 'Code (Read)' permission if you need to index Git commits")
            
            return True
        else:
            print(f"Failed to retrieve projects. Status code: {response.status_code}")
            print(f"Response: {response.text[:200]}")
            return False
            
    except Exception as e:
        print(f"Error accessing Azure DevOps API: {str(e)}")
        return False

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="List Azure DevOps projects")
    parser.add_argument("--org", default="deFactoGlobal", help="Azure DevOps organization name")
    args = parser.parse_args()
    
    # Prompt for PAT
    pat = input("Enter your Azure DevOps PAT: ")
    if not pat:
        print("No PAT provided. Exiting.")
        sys.exit(1)
    
    # List projects
    success = list_devops_projects(args.org, pat)
    
    # Exit with appropriate code
    sys.exit(0 if success else 1) 