#!/usr/bin/env python3
"""
Script to detect the correct branch name for Azure DevOps git repositories
This helps fix the "TF401175:The version descriptor <Branch: master> could not be resolved" error
"""

import sys
import requests
from requests.auth import HTTPBasicAuth
import json
import argparse
from urllib.parse import quote

def detect_branch_names(organization, project, pat):
    """
    Detect branch names for repositories in an Azure DevOps project
    """
    print(f"\n{'=' * 50}")
    print(f"DETECTING BRANCH NAMES FOR: {organization}/{project}")
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
    
    # Step 1: Get repositories
    try:
        print("1. Fetching git repositories...")
        encoded_project = quote(project)
        response = requests.get(
            f"{base_url}/{encoded_project}/_apis/git/repositories",
            auth=auth,
            headers=headers,
            params=params
        )
        
        if response.status_code != 200:
            print(f"Failed to fetch repositories: Status code {response.status_code}")
            print(f"Response: {response.text[:200]}")
            return False
        
        repos = response.json().get('value', [])
        print(f"   Found {len(repos)} repositories")
        
        # Step 2: For each repository, get branches
        print("\n2. Checking branches for each repository...\n")
        
        for repo in repos:
            repo_id = repo.get('id')
            repo_name = repo.get('name')
            
            print(f"   Repository: {repo_name} (ID: {repo_id})")
            
            # Get branches
            branch_response = requests.get(
                f"{base_url}/{encoded_project}/_apis/git/repositories/{repo_id}/refs",
                auth=auth,
                headers=headers,
                params=params
            )
            
            if branch_response.status_code != 200:
                print(f"      ❌ Failed to fetch branches: {branch_response.status_code}")
                print(f"         Error: {branch_response.text[:200]}")
                continue
            
            branches = branch_response.json().get('value', [])
            branch_count = len(branches)
            
            if branch_count == 0:
                print(f"      ❌ No branches found")
                continue
            
            print(f"      ✅ Found {branch_count} branches:")
            
            for branch in branches:
                branch_name = branch.get('name', '')
                if branch_name.startswith('refs/heads/'):
                    branch_name = branch_name[11:]  # Remove the 'refs/heads/' prefix
                
                # Get the last commit on this branch
                try:
                    # Try to get a single commit from this branch to verify access
                    commit_params = params.copy()
                    commit_params['searchCriteria.itemVersion.version'] = branch_name
                    commit_params['$top'] = 1
                    
                    commit_response = requests.get(
                        f"{base_url}/{encoded_project}/_apis/git/repositories/{repo_id}/commits",
                        auth=auth,
                        headers=headers,
                        params=commit_params
                    )
                    
                    if commit_response.status_code == 200:
                        commits = commit_response.json().get('value', [])
                        commit_count = len(commits)
                        
                        if commit_count > 0:
                            commit = commits[0]
                            commit_id = commit.get('commitId', '')[:8]
                            commit_msg = commit.get('comment', '')
                            if commit_msg and len(commit_msg) > 40:
                                commit_msg = commit_msg[:37] + "..."
                            
                            print(f"         ✅ Branch: {branch_name} - Latest commit: {commit_id} {commit_msg}")
                        else:
                            print(f"         ⚠️ Branch: {branch_name} - No commits found")
                    else:
                        print(f"         ❌ Branch: {branch_name} - Error accessing commits: {commit_response.status_code}")
                except Exception as e:
                    print(f"         ❌ Branch: {branch_name} - Error: {str(e)}")
        
        # Step 3: Recommendations
        print(f"\n{'=' * 50}")
        print("RECOMMENDATIONS:")
        print(f"{'=' * 50}")
        print("1. Open the connector.py file and find the _get_commits method")
        print("2. Update the 'searchCriteria.itemVersion.version' parameter in the params variable")
        print("3. Change it from 'master' to the correct branch name for each repository")
        print("4. Either:")
        print("   a. Edit line ~1775 to use a different default branch name (like 'main')")
        print("   b. Add branch name detection code before making the commits API request")
        print("   c. Remove the branch filter entirely if you want to get commits from all branches")
        return True
        
    except Exception as e:
        print(f"Error: {str(e)}")
        return False

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Detect branch names for Azure DevOps git repositories")
    parser.add_argument("--org", default="deFactoGlobal", help="Azure DevOps organization name")
    parser.add_argument("--project", default="DFP_10", help="Azure DevOps project name")
    args = parser.parse_args()
    
    # Prompt for PAT
    pat = input("Enter your Azure DevOps PAT: ")
    if not pat:
        print("No PAT provided. Exiting.")
        sys.exit(1)
    
    # Detect branch names
    success = detect_branch_names(args.org, args.project, pat)
    
    # Exit with appropriate code
    sys.exit(0 if success else 1) 