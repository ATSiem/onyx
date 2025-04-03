#!/usr/bin/env python3
"""
Diagnostic script for Azure DevOps connector to help troubleshoot issues with Git commits
This specifically targets the DFP_10 project connector that isn't retrieving commits
"""

import os
import sys
import logging
from datetime import datetime, timezone, timedelta
import json
import argparse

# Setup path to import onyx modules
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

try:
    from onyx.connectors.azure_devops.connector import AzureDevOpsConnector
except ImportError:
    # Try backend directory if in the main project directory
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), 'backend')))
    try:
        from onyx.connectors.azure_devops.connector import AzureDevOpsConnector
    except ImportError:
        print("ERROR: Cannot import AzureDevOpsConnector. Make sure you're running this from the project root.")
        sys.exit(1)

# Set up logging with more detail
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("azure_devops_debug")

def debug_connector(organization, project, pat, verbose=False):
    """
    Run diagnostics on the Azure DevOps connector for the specific project
    """
    print(f"\n{'=' * 50}")
    print(f"DIAGNOSTICS FOR AZURE DEVOPS CONNECTOR: {organization}/{project}")
    print(f"{'=' * 50}\n")

    # Step 1: Create connector instance with proper settings
    print("1. Creating connector instance with 'everything' content scope...")
    connector = AzureDevOpsConnector(
        organization=organization,
        project=project,
        content_scope="everything"  # This should include Git commits
    )
    
    # Step 2: Load credentials
    print("2. Loading credentials...")
    connector.load_credentials({"personal_access_token": pat})
    
    # Step 3: Check data types configuration
    print("\n3. Checking data types configuration...")
    print(f"   Data types: {connector.data_types}")
    if "commits" in connector.data_types:
        print("   ✅ 'commits' data type is properly configured")
    else:
        print("   ❌ 'commits' data type is NOT enabled")
        print("   This is a configuration issue - content_scope isn't properly setting data types")
        return
    
    # Step 4: Validate connector settings
    print("\n4. Validating connector settings...")
    try:
        connector.validate_connector_settings()
        print("   ✅ Connector settings validated successfully")
    except Exception as e:
        print(f"   ❌ Connector validation failed: {str(e)}")
        print("   This could indicate permission or project access issues")
        return
    
    # Step 5: Attempt to fetch repositories
    print("\n5. Fetching repositories...")
    repositories = connector._get_repositories()
    if not repositories:
        print("   ❌ No repositories found. This could be due to:")
        print("     - No repositories exist in the project")
        print("     - Permission issues with the PAT (needs 'Code (Read)' permission)")
        print("     - Project configuration issue")
        return
    
    print(f"   ✅ Found {len(repositories)} repositories")
    for i, repo in enumerate(repositories[:5]):  # Show first 5 repos
        repo_name = repo.get("name", "unnamed")
        repo_id = repo.get("id", "no-id")
        print(f"     {i+1}. {repo_name} (ID: {repo_id})")
    
    if len(repositories) > 5:
        print(f"     ... and {len(repositories) - 5} more")
    
    # Step 6: Check for commits in each repository
    print("\n6. Checking for commits in repositories...")
    found_commits = False
    
    # Try different time ranges to ensure we find commits if they exist
    time_ranges = [
        ("Past day", timedelta(days=1)),
        ("Past week", timedelta(days=7)),
        ("Past month", timedelta(days=30)),
        ("Past year", timedelta(days=365)),
        ("All time", timedelta(days=3650))  # ~10 years
    ]
    
    for repo in repositories:
        repo_name = repo.get("name", "unnamed")
        repo_id = repo.get("id", "no-id")
        print(f"\n   Repository: {repo_name}")
        
        commit_found_in_repo = False
        
        for time_label, delta in time_ranges:
            start_time = datetime.now(timezone.utc) - delta
            print(f"     Checking {time_label} (since {start_time.isoformat()})...")
            
            try:
                commits_response = connector._get_commits(repository_id=repo_id, start_time=start_time)
                commits = commits_response.get("value", [])
                
                if commits:
                    print(f"     ✅ Found {len(commits)} commits in {time_label}")
                    commit_found_in_repo = True
                    found_commits = True
                    
                    # Show sample commits
                    if verbose:
                        for i, commit in enumerate(commits[:3]):  # Show first 3 commits
                            commit_id = commit.get("commitId", "")[:8]
                            author = commit.get("author", {}).get("name", "unknown")
                            date = commit.get("author", {}).get("date", "unknown")
                            message = commit.get("comment", "")
                            if message and len(message) > 50:
                                message = message[:47] + "..."
                            print(f"       {i+1}. Commit {commit_id} by {author} on {date}: {message}")
                    
                    # Test document creation for one commit
                    if commits:
                        test_commit = commits[0]
                        doc = connector._process_commit(test_commit, repo)
                        if doc:
                            print(f"     ✅ Successfully created document from commit {test_commit.get('commitId', '')[:8]}")
                            print(f"       Document ID: {doc.id}")
                        else:
                            print(f"     ❌ Failed to create document from commit")
                    
                    # No need to check other time ranges if we found commits
                    break
                else:
                    print(f"     No commits found in {time_label}")
            except Exception as e:
                print(f"     ❌ Error fetching commits for {time_label}: {str(e)}")
        
        if not commit_found_in_repo:
            print(f"     ❌ No commits found in any time range for repository {repo_name}")
    
    # Step 7: Summarize findings
    print("\n7. Summary:")
    if found_commits:
        print("   ✅ Found commits in at least one repository")
        print("   If your connector is still not indexing commits during a complete re-indexing:")
        print("     - Check logs for errors during the indexing process")
        print("     - Ensure the connector configuration has 'content_scope' set to 'everything'")
        print("     - Verify the indexing time range includes the dates of your commits")
    else:
        print("   ❌ No commits found in any repository")
        print("   This could be due to:")
        print("     - Repositories are empty or have no commits")
        print("     - API permissions issues with the PAT")
        print("     - Issues with the Git repositories in Azure DevOps")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Debug Azure DevOps connector issues")
    parser.add_argument("--org", default="deFactoGlobal", help="Azure DevOps organization name")
    parser.add_argument("--project", default="DFP_10", help="Azure DevOps project name")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show more detailed output")
    args = parser.parse_args()
    
    # Prompt for PAT
    pat = input("Enter your Azure DevOps PAT: ")
    if not pat:
        print("No PAT provided. Exiting.")
        sys.exit(1)
    
    debug_connector(args.org, args.project, pat, args.verbose) 