#!/usr/bin/env python3
"""
Script to verify Azure DevOps PAT permissions for accessing Git repositories and commits
This helps diagnose permission-related issues with the Azure DevOps connector
"""

import sys
import requests
from requests.auth import HTTPBasicAuth
import json
import argparse
from urllib.parse import quote

def verify_pat_permissions(organization, project, pat):
    """
    Verify that the provided PAT has the necessary permissions
    to access git repositories and commits
    """
    print(f"\n{'=' * 50}")
    print(f"VERIFYING PAT PERMISSIONS FOR: {organization}/{project}")
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
    
    # Test 1: Organization access
    print("1. Testing organization access...")
    try:
        response = requests.get(
            f"{base_url}/_apis/projects",
            auth=auth,
            headers=headers,
            params=params
        )
        if response.status_code == 200:
            result = response.json()
            project_count = result.get('count', 0)
            print(f"   ✅ Successfully accessed organization API. Found {project_count} projects.")
        else:
            print(f"   ❌ Failed to access organization API. Status code: {response.status_code}")
            print(f"   Response: {response.text[:200]}")
            print("   This indicates basic authentication issues with the PAT.")
            return False
    except Exception as e:
        print(f"   ❌ Error accessing organization API: {str(e)}")
        return False
    
    # Test 2: Project access
    print(f"\n2. Testing project access for '{project}'...")
    try:
        # URL encode project name to handle spaces
        encoded_project = quote(project)
        response = requests.get(
            f"{base_url}/{encoded_project}/_apis/project",
            auth=auth,
            headers=headers,
            params=params
        )
        if response.status_code == 200:
            project_info = response.json()
            project_name = project_info.get('name', 'Unknown')
            print(f"   ✅ Successfully accessed project '{project_name}'")
        else:
            print(f"   ❌ Failed to access project '{project}'. Status code: {response.status_code}")
            print(f"   Response: {response.text[:200]}")
            print("   This indicates the project may not exist or the PAT doesn't have access to it.")
            return False
    except Exception as e:
        print(f"   ❌ Error accessing project API: {str(e)}")
        return False
    
    # Test 3: Git repository access
    print(f"\n3. Testing Git repositories access...")
    try:
        response = requests.get(
            f"{base_url}/{encoded_project}/_apis/git/repositories",
            auth=auth,
            headers=headers,
            params=params
        )
        if response.status_code == 200:
            repos = response.json()
            repo_count = repos.get('count', 0)
            if repo_count > 0:
                print(f"   ✅ Successfully accessed Git repositories. Found {repo_count} repositories.")
                repositories = repos.get('value', [])
                for i, repo in enumerate(repositories[:5]):  # Show first 5 repos
                    repo_name = repo.get('name', 'unnamed')
                    repo_id = repo.get('id', 'no-id')
                    print(f"     {i+1}. {repo_name} (ID: {repo_id})")
                
                if repo_count > 5:
                    print(f"     ... and {repo_count - 5} more")
                
                # Save first repo for next test
                first_repo = repositories[0]
            else:
                print(f"   ⚠️ No Git repositories found in project '{project}'")
                print("   This could be a legitimate project configuration or a permission issue.")
                return True  # This is not a failure, just may be no repos
        else:
            print(f"   ❌ Failed to access Git repositories. Status code: {response.status_code}")
            print(f"   Response: {response.text[:200]}")
            print("   This indicates the PAT doesn't have 'Code (Read)' permission.")
            return False
    except Exception as e:
        print(f"   ❌ Error accessing Git repositories API: {str(e)}")
        return False
    
    # Early return if no repositories
    if repo_count == 0:
        print("\n4. Cannot test Git commits access as no repositories were found.")
        return True
    
    # Test 4: Git commits access
    print(f"\n4. Testing Git commits access for '{first_repo.get('name')}'...")
    try:
        repo_id = first_repo.get('id')
        response = requests.get(
            f"{base_url}/{encoded_project}/_apis/git/repositories/{repo_id}/commits",
            auth=auth,
            headers=headers,
            params={**params, 'top': 10}  # Limit to 10 commits
        )
        if response.status_code == 200:
            commits = response.json()
            commit_count = commits.get('count', 0)
            if commit_count > 0:
                print(f"   ✅ Successfully accessed Git commits. Found {commit_count} commits.")
                commit_list = commits.get('value', [])
                for i, commit in enumerate(commit_list[:3]):  # Show first 3 commits
                    commit_id = commit.get('commitId', '')[:8]
                    author = commit.get('author', {}).get('name', 'unknown')
                    comment = commit.get('comment', '')
                    if comment and len(comment) > 50:
                        comment = comment[:47] + "..."
                    print(f"     {i+1}. Commit {commit_id} by {author}: {comment}")
            else:
                print(f"   ⚠️ No commits found in repository '{first_repo.get('name')}'")
                print("   This could be an empty repository or a permission issue.")
        else:
            print(f"   ❌ Failed to access Git commits. Status code: {response.status_code}")
            print(f"   Response: {response.text[:200]}")
            print("   This indicates the PAT doesn't have 'Code (Read)' permission for commits.")
            return False
    except Exception as e:
        print(f"   ❌ Error accessing Git commits API: {str(e)}")
        return False
    
    # Summary
    print(f"\n{'=' * 50}")
    print("SUMMARY:")
    print(f"{'=' * 50}")
    print("✅ The PAT appears to have the necessary permissions for Azure DevOps integration.")
    print("It can access:")
    print("  - Organization and projects")
    print("  - Git repositories")
    print("  - Git commits")
    print("\nIf your connector is still not working, verify:")
    print("1. The connector configuration in Onyx has 'content_scope' set to 'everything'")
    print("2. The correct PAT is being used in the connector")
    print("3. The indexing time window includes dates when commits were made")
    print("4. Check server logs for other potential issues during indexing")
    
    return True

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Verify Azure DevOps PAT permissions")
    parser.add_argument("--org", default="deFactoGlobal", help="Azure DevOps organization name")
    parser.add_argument("--project", default="DFP_10", help="Azure DevOps project name")
    args = parser.parse_args()
    
    # Prompt for PAT
    pat = input("Enter your Azure DevOps PAT to verify permissions: ")
    if not pat:
        print("No PAT provided. Exiting.")
        sys.exit(1)
    
    # Run verification
    success = verify_pat_permissions(args.org, args.project, pat)
    
    # Exit with appropriate code
    sys.exit(0 if success else 1) 