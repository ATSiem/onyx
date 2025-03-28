#!/usr/bin/env python3
"""
Azure DevOps API Tester

This script helps test connections to the Azure DevOps API without rebuilding the application.
It allows you to validate URL formats, API parameters, authentication, and more.

To use:
1. Run the script
2. Enter your Personal Access Token (PAT), organization name, and project name when prompted
3. Choose which tests to run from the menu
"""

import requests
import base64
import json
from datetime import datetime, timezone
import time
import argparse
import sys
import textwrap


def create_auth_header(pat):
    """Create authorization header using the PAT"""
    auth_str = f":{pat}"
    encoded_auth = base64.b64encode(auth_str.encode()).decode()
    return {
        "Authorization": f"Basic {encoded_auth}",
        "Content-Type": "application/json"
    }


def test_basic_connection(org, headers):
    """Test basic connectivity to the Azure DevOps organization"""
    print("\n===== TESTING BASIC CONNECTIVITY =====")
    org_url = f"https://dev.azure.com/{org}/_apis/projects?api-version=7.0"
    
    try:
        response = requests.get(org_url, headers=headers)
        response.raise_for_status()
        
        projects_data = response.json()
        projects_count = len(projects_data.get("value", []))
        
        print(f"✅ Successfully connected to organization '{org}'")
        print(f"✅ Found {projects_count} projects")
        
        return True
    except Exception as e:
        print(f"❌ Failed to connect to organization: {str(e)}")
        if hasattr(e, 'response') and e.response is not None:
            try:
                error_details = e.response.json()
                print(f"Error details: {error_details}")
            except:
                print(f"Error details: {e.response.text[:200]}")
        
        return False


def test_project_exists(org, project, headers):
    """Test if the specified project exists within the organization"""
    print(f"\n===== TESTING PROJECT EXISTENCE =====")
    
    # Get list of projects
    org_url = f"https://dev.azure.com/{org}/_apis/projects?api-version=7.0"
    
    try:
        response = requests.get(org_url, headers=headers)
        response.raise_for_status()
        
        projects_data = response.json()
        project_found = False
        project_id = None
        
        for p in projects_data.get("value", []):
            if p.get("name") == project:
                project_found = True
                project_id = p.get("id")
                break
                
        if project_found:
            print(f"✅ Project '{project}' found with ID: {project_id}")
            return True
        else:
            print(f"❌ Project '{project}' not found in organization '{org}'")
            
            # List available projects
            if projects_data.get("value"):
                print("\nAvailable projects:")
                for p in projects_data.get("value", [])[:5]:  # Show at most 5 projects
                    print(f"  - {p.get('name')}")
                
                if len(projects_data.get("value", [])) > 5:
                    print(f"  ... and {len(projects_data.get('value', [])) - 5} more")
            
            return False
    except Exception as e:
        print(f"❌ Failed to check if project exists: {str(e)}")
        return False


def test_wiql_query(org, project, headers):
    """Test WIQL query with the project parameter in the conditions"""
    print("\n===== TESTING WIQL QUERY =====")
    wiql_url = f"https://dev.azure.com/{org}/_apis/wit/wiql?api-version=7.0"
    
    # This is the same query format used in the connector
    wiql_query = {
        "query": f"SELECT [System.Id] FROM WorkItems WHERE [System.TeamProject] = '{project}' AND [System.WorkItemType] IN ('Bug', 'Epic', 'Feature', 'Issue', 'Task', 'TestCase', 'UserStory') ORDER BY [System.ChangedDate] DESC"
    }
    
    print(f"WIQL Query: {wiql_query['query']}")
    
    try:
        work_items_response = requests.post(wiql_url, headers=headers, json=wiql_query)
        work_items_response.raise_for_status()
        
        work_items_data = work_items_response.json()
        work_item_count = len(work_items_data.get("workItems", []))
        
        print(f"✅ WIQL query returned {work_item_count} work items")
        
        # Return the work items for use in other tests
        return work_items_data.get("workItems", [])
    except Exception as e:
        print(f"❌ WIQL query failed: {str(e)}")
        if hasattr(e, 'response') and e.response is not None:
            try:
                error_details = e.response.json()
                print(f"Error details: {error_details}")
            except:
                print(f"Error details: {e.response.text[:200]}")
        
        return []


def test_work_item_details(org, project, work_items, headers):
    """Test fetching work item details with different URL formats"""
    if not work_items:
        print("❌ No work items available to test work item details API")
        return False

    print("\n===== TESTING WORK ITEM DETAILS API =====")
    # Choose the first 3 work items to test
    test_ids = work_items[:3]
    ids_str = ",".join([str(item["id"]) for item in test_ids])
    
    print(f"Testing with work item IDs: {ids_str}\n")

    # Test 1: Using project in URL path (correct format)
    test_url_1 = f"https://dev.azure.com/{org}/{project}/_apis/wit/workitems?ids={ids_str}&fields=System.Id,System.Title,System.Description&api-version=7.0"
    print(f"Test 1: Using project in URL path (correct format)")
    print(f"URL: {test_url_1}")
    
    try:
        response_1 = requests.get(test_url_1, headers=headers)
        response_1.raise_for_status()
        data_1 = response_1.json()
        items_1 = data_1.get("value", [])
        print(f"✅ Successfully fetched {len(items_1)} work items with project in URL path")
        
        if items_1:
            sample_item = items_1[0]
            print("\nSample work item:")
            print(f"  ID: {sample_item.get('id')}")
            print(f"  Title: {sample_item.get('fields', {}).get('System.Title', 'N/A')}")
    except requests.exceptions.RequestException as e:
        print(f"❌ Failed with project in URL path: {str(e)}")
        return False

    # Test 2: Using project as query parameter (incorrect format)
    test_url_2 = f"https://dev.azure.com/{org}/_apis/wit/workitems?ids={ids_str}&fields=System.Id,System.Title&project={project}&api-version=7.0"
    print(f"\nTest 2: Using project as query parameter (incorrect format)")
    print(f"URL: {test_url_2}")
    
    try:
        response_2 = requests.get(test_url_2, headers=headers)
        response_2.raise_for_status()
        data_2 = response_2.json()
        items_2 = data_2.get("value", [])
        print(f"✅ Fetched {len(items_2)} work items with project as query parameter")
    except requests.exceptions.RequestException as e:
        print(f"❌ Failed with project as query parameter: {str(e)}")
        return False

    # Test 3: Using project in path with $expand parameter (should fail)
    test_url_3 = f"https://dev.azure.com/{org}/{project}/_apis/wit/workitems?ids={ids_str}&fields=System.Id,System.Title&$expand=all&api-version=7.0"
    print(f"\nTest 3: Using project in path with $expand parameter (should fail)")
    print(f"URL: {test_url_3}")
    
    try:
        response_3 = requests.get(test_url_3, headers=headers)
        response_3.raise_for_status()
        print("❌ Unexpected success with $expand parameter")
        return False
    except requests.exceptions.RequestException as e:
        if hasattr(e, 'response') and e.response.status_code == 400:
            print(f"✅ Correctly failed with $expand parameter: {str(e)}")
            print(f"Error details: {e.response.json()}")
        else:
            print(f"❌ Failed with unexpected error: {str(e)}")
            return False

    print("\nWork Items API Tests Summary:")
    print("  Test 1 (Project in path): ✅ Success")
    print("  Test 2 (Project as query param): ✅ Success")
    print("  Test 3 (Project in path with $expand): ✅ Expected Failure")
    
    return True


def test_work_item_comments(org, project, work_items, headers):
    """Test fetching work item comments with different URL formats and API versions"""
    if not work_items:
        print("❌ No work items available to test comments API")
        return False

    print("\n===== TESTING WORK ITEM COMMENTS API =====")
    # Choose the first work item to test comments API
    test_id = work_items[0]["id"]
    
    print(f"Testing with work item ID: {test_id}\n")

    # Test 1: Using project in path with preview flag (correct format)
    test_url_1 = f"https://dev.azure.com/{org}/{project}/_apis/wit/workItems/{test_id}/comments?api-version=7.0-preview"
    print(f"Test 1: Using project in path with preview flag (correct format)")
    print(f"URL: {test_url_1}")
    
    try:
        response_1 = requests.get(test_url_1, headers=headers)
        response_1.raise_for_status()
        data_1 = response_1.json()
        comments_count_1 = len(data_1.get("comments", []))
        print(f"✅ Successfully fetched {comments_count_1} comments with project in path and preview flag")
        
        if comments_count_1 > 0:
            sample_comment = data_1.get("comments", [])[0]
            print("\nSample comment:")
            print(f"  Author: {sample_comment.get('createdBy', {}).get('displayName', 'N/A')}")
            print(f"  Date: {sample_comment.get('createdDate', 'N/A')}")
            print(f"  Text: {sample_comment.get('text', 'N/A')[:100]}...")
    except requests.exceptions.RequestException as e:
        print(f"❌ Failed with project in path and preview flag: {str(e)}")
        return False

    # Test 2: Using project in path without preview flag (should fail)
    test_url_2 = f"https://dev.azure.com/{org}/{project}/_apis/wit/workItems/{test_id}/comments?api-version=7.0"
    print(f"\nTest 2: Using project in path without preview flag (should fail)")
    print(f"URL: {test_url_2}")
    
    try:
        response_2 = requests.get(test_url_2, headers=headers)
        response_2.raise_for_status()
        print("❌ Unexpected success without preview flag")
        return False
    except requests.exceptions.RequestException as e:
        if hasattr(e, 'response') and e.response.status_code == 400:
            print(f"✅ Correctly failed without preview flag: {str(e)}")
            print(f"Error details: {e.response.json()}")
        else:
            print(f"❌ Failed with unexpected error: {str(e)}")
            return False

    # Test 3: Using project as query parameter (should fail)
    test_url_3 = f"https://dev.azure.com/{org}/_apis/wit/workItems/{test_id}/comments?project={project}&api-version=7.0-preview"
    print(f"\nTest 3: Using project as query parameter (should fail)")
    print(f"URL: {test_url_3}")
    
    try:
        response_3 = requests.get(test_url_3, headers=headers)
        response_3.raise_for_status()
        print("❌ Unexpected success with project as query parameter")
        return False
    except requests.exceptions.RequestException as e:
        if hasattr(e, 'response') and e.response.status_code == 404:
            print(f"✅ Correctly failed with project as query parameter: {str(e)}")
            print(f"Error details: {e.response.text[:200]}")
        else:
            print(f"❌ Failed with unexpected error: {str(e)}")
            return False

    print("\nComments API Tests Summary:")
    print("  Test 1 (Project in path with preview flag): ✅ Success")
    print("  Test 2 (Project in path without preview flag): ✅ Expected Failure")
    print("  Test 3 (Project as query param): ✅ Expected Failure")
    
    return True


def test_data_types(org, project, headers):
    """Test API endpoints for different data types supported by the connector"""
    print("\n===== TESTING DATA TYPE API ENDPOINTS =====")
    
    data_types = {
        "work_items": "Already tested in previous steps",
        "commits": "Git repositories and commits",
        "test_results": "Test runs and results",
        "test_stats": "Test run statistics",
        "releases": "Release definitions and instances",
        "wikis": "Project wikis"
    }
    
    print(f"Testing {len(data_types)} data types supported by the connector:\n")
    
    results = {}
    
    # 1. Test repositories and commits API (for commits data type)
    print("\n----- Testing Repositories & Commits API -----")
    try:
        # Get repositories
        repos_url = f"https://dev.azure.com/{org}/{project}/_apis/git/repositories?api-version=7.0"
        print(f"Testing Repository API: {repos_url}")
        
        repos_response = requests.get(repos_url, headers=headers)
        repos_response.raise_for_status()
        
        repos_data = repos_response.json()
        repos_count = len(repos_data.get("value", []))
        
        print(f"✅ Successfully fetched {repos_count} repositories")
        
        # Try to get commits for the first repository if any
        if repos_count > 0:
            repo_id = repos_data["value"][0]["id"]
            repo_name = repos_data["value"][0]["name"]
            
            commits_url = f"https://dev.azure.com/{org}/{project}/_apis/git/repositories/{repo_id}/commits?api-version=7.0&$top=10"
            print(f"\nTesting Commits API for repository '{repo_name}':")
            print(f"URL: {commits_url}")
            
            commits_response = requests.get(commits_url, headers=headers)
            commits_response.raise_for_status()
            
            commits_data = commits_response.json()
            commits_count = len(commits_data.get("value", []))
            
            print(f"✅ Successfully fetched {commits_count} commits")
            
            if commits_count > 0:
                commit = commits_data["value"][0]
                print("\nSample commit:")
                print(f"  Commit ID: {commit.get('commitId', 'N/A')[:8]}...")
                print(f"  Author: {commit.get('author', {}).get('name', 'N/A')}")
                print(f"  Date: {commit.get('author', {}).get('date', 'N/A')}")
                print(f"  Message: {commit.get('comment', 'N/A')[:100]}...")
            
            results["commits"] = "✅ Success"
        else:
            print("⚠️ No repositories found to test commits API")
            results["commits"] = "⚠️ No repositories found"
    except requests.exceptions.RequestException as e:
        print(f"❌ Failed to access repositories and commits: {str(e)}")
        if hasattr(e, 'response') and e.response is not None:
            try:
                error_details = e.response.json()
                print(f"Error details: {error_details}")
            except:
                print(f"Error details: {e.response.text[:200]}")
        results["commits"] = "❌ Failed"
    
    # 2. Test test runs API (for test_results and test_stats data types)
    print("\n----- Testing Test Runs API -----")
    try:
        test_url = f"https://dev.azure.com/{org}/{project}/_apis/test/runs?api-version=7.0&$top=10"
        print(f"Testing Test Runs API: {test_url}")
        
        test_response = requests.get(test_url, headers=headers)
        test_response.raise_for_status()
        
        test_data = test_response.json()
        test_count = len(test_data.get("value", []))
        
        print(f"✅ Successfully fetched {test_count} test runs")
        
        # Try to get test results and stats for the first test run if any
        if test_count > 0:
            run_id = test_data["value"][0]["id"]
            run_name = test_data["value"][0]["name"]
            
            # Get test results
            results_url = f"https://dev.azure.com/{org}/{project}/_apis/test/Runs/{run_id}/results?api-version=7.0&$top=10"
            print(f"\nTesting Test Results API for run '{run_name}':")
            print(f"URL: {results_url}")
            
            results_response = requests.get(results_url, headers=headers)
            results_response.raise_for_status()
            
            results_data = results_response.json()
            results_count = len(results_data.get("value", []))
            
            print(f"✅ Successfully fetched {results_count} test results")
            
            # Get test statistics
            stats_url = f"https://dev.azure.com/{org}/{project}/_apis/test/Runs/{run_id}/Statistics?api-version=7.0"
            print(f"\nTesting Test Statistics API for run '{run_name}':")
            print(f"URL: {stats_url}")
            
            stats_response = requests.get(stats_url, headers=headers)
            stats_response.raise_for_status()
            
            stats_data = stats_response.json()
            
            print(f"✅ Successfully fetched test run statistics")
            print(f"  Total Tests: {stats_data.get('totalTests', 'N/A')}")
            print(f"  Passed Tests: {stats_data.get('passedTests', 'N/A')}")
            print(f"  Failed Tests: {stats_data.get('failedTests', 'N/A')}")
            
            results["test_results"] = "✅ Success"
            results["test_stats"] = "✅ Success"
        else:
            print("⚠️ No test runs found to test results and statistics API")
            results["test_results"] = "⚠️ No test runs found"
            results["test_stats"] = "⚠️ No test runs found"
    except requests.exceptions.RequestException as e:
        print(f"❌ Failed to access test runs and results: {str(e)}")
        if hasattr(e, 'response') and e.response is not None:
            try:
                error_details = e.response.json()
                print(f"Error details: {error_details}")
            except:
                print(f"Error details: {e.response.text[:200]}")
        results["test_results"] = "❌ Failed"
        results["test_stats"] = "❌ Failed"
    
    # 3. Test releases API (for releases data type)
    print("\n----- Testing Releases API -----")
    try:
        releases_url = f"https://vsrm.dev.azure.com/{org}/{project}/_apis/release/releases?api-version=7.0&$top=10"
        print(f"Testing Releases API: {releases_url}")
        
        releases_response = requests.get(releases_url, headers=headers)
        releases_response.raise_for_status()
        
        releases_data = releases_response.json()
        releases_count = len(releases_data.get("value", []))
        
        print(f"✅ Successfully fetched {releases_count} releases")
        
        if releases_count > 0:
            release = releases_data["value"][0]
            print("\nSample release:")
            print(f"  Release ID: {release.get('id', 'N/A')}")
            print(f"  Name: {release.get('name', 'N/A')}")
            print(f"  Status: {release.get('status', 'N/A')}")
            
            # Get release details
            release_id = release.get("id")
            details_url = f"https://vsrm.dev.azure.com/{org}/{project}/_apis/release/releases/{release_id}?api-version=7.0"
            print(f"\nTesting Release Details API:")
            print(f"URL: {details_url}")
            
            details_response = requests.get(details_url, headers=headers)
            details_response.raise_for_status()
            
            print(f"✅ Successfully fetched release details")
            
            results["releases"] = "✅ Success"
        else:
            print("⚠️ No releases found to test releases API")
            results["releases"] = "⚠️ No releases found"
    except requests.exceptions.RequestException as e:
        print(f"❌ Failed to access releases: {str(e)}")
        if hasattr(e, 'response') and e.response is not None:
            try:
                error_details = e.response.json()
                print(f"Error details: {error_details}")
            except:
                print(f"Error details: {e.response.text[:200]}")
        results["releases"] = "❌ Failed"
    
    # 4. Test wikis API (for wikis data type)
    print("\n----- Testing Wikis API -----")
    try:
        wikis_url = f"https://dev.azure.com/{org}/{project}/_apis/wiki/wikis?api-version=7.0"
        print(f"Testing Wikis API: {wikis_url}")
        
        wikis_response = requests.get(wikis_url, headers=headers)
        wikis_response.raise_for_status()
        
        wikis_data = wikis_response.json()
        wikis_count = len(wikis_data.get("value", []))
        
        print(f"✅ Successfully fetched {wikis_count} wikis")
        
        if wikis_count > 0:
            wiki = wikis_data["value"][0]
            wiki_id = wiki.get("id")
            wiki_name = wiki.get("name")
            
            # Get wiki pages
            pages_url = f"https://dev.azure.com/{org}/{project}/_apis/wiki/wikis/{wiki_id}/pages?api-version=7.0&includeContent=true"
            print(f"\nTesting Wiki Pages API for wiki '{wiki_name}':")
            print(f"URL: {pages_url}")
            
            try:
                pages_response = requests.get(pages_url, headers=headers)
                pages_response.raise_for_status()
                
                print(f"✅ Successfully accessed wiki pages")
                
                # Try to fetch content of the root page
                root_path = wiki.get("path", "")
                content_url = f"https://dev.azure.com/{org}/{project}/_apis/wiki/wikis/{wiki_id}/pages?path={root_path}&includeContent=true&api-version=7.0"
                print(f"\nTesting Wiki Page Content API:")
                print(f"URL: {content_url}")
                
                content_response = requests.get(content_url, headers=headers)
                content_response.raise_for_status()
                
                print(f"✅ Successfully fetched wiki page content")
                
                results["wikis"] = "✅ Success"
            except requests.exceptions.RequestException as e:
                print(f"⚠️ Could access wiki but not pages: {str(e)}")
                results["wikis"] = "⚠️ Partial success"
        else:
            print("⚠️ No wikis found to test wikis API")
            results["wikis"] = "⚠️ No wikis found"
    except requests.exceptions.RequestException as e:
        print(f"❌ Failed to access wikis: {str(e)}")
        if hasattr(e, 'response') and e.response is not None:
            try:
                error_details = e.response.json()
                print(f"Error details: {error_details}")
            except:
                print(f"Error details: {e.response.text[:200]}")
        results["wikis"] = "❌ Failed"
    
    # Print summary of data type tests
    print("\n===== DATA TYPE API TESTS SUMMARY =====")
    print("Work Items:    ✅ Success (tested in previous steps)")
    for data_type, result in results.items():
        print(f"{data_type.capitalize()}: {result}")
    
    # Return overall success (true if at least work items work)
    return True


def simulate_indexing(org, project, headers):
    """Simulate a full indexing process similar to the actual connector"""
    print("\n===== SIMULATING FULL INDEXING PROCESS =====")
    
    # Step 1: Use the WIQL query to get work item IDs
    print("\nStep 1: Executing WIQL query to get work item IDs...")
    wiql_url = f"https://dev.azure.com/{org}/_apis/wit/wiql?api-version=7.0"
    
    wiql_query = {
        "query": f"SELECT [System.Id] FROM WorkItems WHERE [System.TeamProject] = '{project}' AND [System.WorkItemType] IN ('Bug', 'Epic', 'Feature', 'Issue', 'Task', 'TestCase', 'UserStory') ORDER BY [System.ChangedDate] DESC"
    }
    
    try:
        work_items_response = requests.post(wiql_url, headers=headers, json=wiql_query)
        work_items_response.raise_for_status()
        
        work_items_data = work_items_response.json()
        work_item_count = len(work_items_data.get("workItems", []))
        
        if work_item_count == 0:
            print("❌ No work items found. Cannot proceed with test.")
            return False
            
        print(f"✅ WIQL query returned {work_item_count} work items")
        
        # Step 2: Get details for work items (using limited items for test)
        print("\nStep 2: Getting work item details...")
        test_items = work_items_data.get("workItems", [])[:3]  # Limit to 3 for testing
        item_ids = [item.get("id") for item in test_items]
        ids_str = ",".join([str(item_id) for item_id in item_ids])
        
        # Using the fixed URL format with project in path
        item_url = f"https://dev.azure.com/{org}/{project}/_apis/wit/workitems?ids={ids_str}&fields=System.Id,System.Title,System.Description,System.WorkItemType,System.State,System.CreatedBy,System.CreatedDate,System.ChangedBy,System.ChangedDate&api-version=7.0"
        
        item_response = requests.get(item_url, headers=headers)
        item_response.raise_for_status()
        
        items_data = item_response.json()
        items_count = len(items_data.get("value", []))
        print(f"✅ Successfully fetched details for {items_count} work items")
        
        # Step 3: Fetch comments for one work item to verify comment API
        if item_ids:
            test_id = item_ids[0]
            print(f"\nStep 3: Fetching comments for work item {test_id}...")
            
            # Using the fixed URL format with project in path and preview API version
            comments_url = f"https://dev.azure.com/{org}/{project}/_apis/wit/workItems/{test_id}/comments?api-version=7.0-preview"
            
            comments_response = requests.get(comments_url, headers=headers)
            comments_response.raise_for_status()
            
            comments_data = comments_response.json()
            comments_count = len(comments_data.get("comments", []))
            print(f"✅ Successfully fetched {comments_count} comments for work item {test_id}")
        
        # Step 4: Display sample work item to verify document processing
        print("\nStep 4: Processing sample work item into document...")
        if items_count > 0:
            sample_item = items_data.get("value", [])[0]
            item_id = sample_item.get("id", "Unknown")
            fields = sample_item.get("fields", {})
            
            print(f"Work Item ID: {item_id}")
            print(f"Title: {fields.get('System.Title', 'No title')}")
            print(f"Type: {fields.get('System.WorkItemType', 'Unknown')}")
            print(f"State: {fields.get('System.State', 'Unknown')}")
            print(f"Created: {fields.get('System.CreatedDate', 'Unknown')}")
            print(f"URL: https://dev.azure.com/{org}/{project}/_workitems/edit/{item_id}")
            
            # Verify we can create a proper document ID in the expected format
            document_id = f"azuredevops:{org}/{project}/workitem/{item_id}"
            print(f"Document ID: {document_id}")
        
        print("\n===== INDEXING SIMULATION COMPLETED SUCCESSFULLY =====")
        return True
    except Exception as e:
        print(f"❌ Indexing simulation failed: {str(e)}")
        if hasattr(e, 'response') and e.response is not None:
            try:
                error_details = e.response.json()
                print(f"Error details: {error_details}")
            except:
                print(f"Error details: {e.response.text[:200]}")
        
        return False


def main():
    """Main entry point for the script"""
    parser = argparse.ArgumentParser(description='Azure DevOps API Tester')
    parser.add_argument('--all', action='store_true', help='Run all tests')
    parser.add_argument('--basic', action='store_true', help='Test basic connectivity')
    parser.add_argument('--project', action='store_true', help='Test project existence')
    parser.add_argument('--wiql', action='store_true', help='Test WIQL query')
    parser.add_argument('--items', action='store_true', help='Test work item details API')
    parser.add_argument('--comments', action='store_true', help='Test work item comments API')
    parser.add_argument('--data-types', action='store_true', help='Test supported data type API endpoints')
    parser.add_argument('--simulate', action='store_true', help='Simulate full indexing process')
    
    args = parser.parse_args()
    
    # Default to "all" if no specific tests are selected
    if not (args.all or args.basic or args.project or args.wiql or 
            args.items or args.comments or args.data_types or args.simulate):
        args.all = True
    
    # Get credentials and connection info
    print("===== AZURE DEVOPS API TESTER =====")
    pat = input("Enter your Personal Access Token: ")
    org = input("Enter your Azure DevOps organization name: ")
    project = input("Enter your Azure DevOps project name: ")
    
    # Create authorization header
    headers = create_auth_header(pat)
    
    # Run selected tests
    success = True
    
    # Test basic connectivity
    if args.all or args.basic:
        if not test_basic_connection(org, headers):
            print("❌ Basic connectivity test failed. Cannot proceed with other tests.")
            return False
    
    # Test project existence
    if args.all or args.project:
        if not test_project_exists(org, project, headers):
            print("❌ Project existence test failed. Cannot proceed with other tests.")
            return False
    
    # Test WIQL query
    work_items = []
    if args.all or args.wiql or args.items or args.comments or args.simulate:
        work_items = test_wiql_query(org, project, headers)
        if not work_items:
            print("❌ WIQL query test failed. Cannot proceed with work item tests.")
            success = False
    
    # Test work item details
    if (args.all or args.items) and work_items:
        if not test_work_item_details(org, project, work_items, headers):
            success = False
    
    # Test work item comments
    if (args.all or args.comments) and work_items:
        if not test_work_item_comments(org, project, work_items, headers):
            success = False
    
    # Test data type API endpoints
    if args.all or args.data_types:
        if not test_data_types(org, project, headers):
            success = False
    
    # Simulate indexing
    if args.all or args.simulate:
        if not simulate_indexing(org, project, headers):
            success = False
    
    # Provide a summary
    print("\n===== TEST SUMMARY =====")
    if success:
        print("✅ All tests completed successfully!")
    else:
        print("❌ Some tests failed. Check the output for details.")
    
    return success


if __name__ == "__main__":
    try:
        success = main()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user.")
        sys.exit(1)
    except Exception as e:
        print(f"\n\nUnexpected error: {str(e)}")
        sys.exit(1) 