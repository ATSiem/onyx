import unittest
from unittest.mock import patch

from onyx.connectors.azure_devops.connector import AzureDevOpsConnector

class TestAzureDevOpsSlimDocs(unittest.TestCase):
    @patch.object(AzureDevOpsConnector, "_get_commits")
    @patch.object(AzureDevOpsConnector, "_get_repositories")
    def test_slim_documents_for_git_commits(self, mock_get_repositories, mock_get_commits):
        """Test that slim documents are properly generated for git commits with work items."""
        # Setup connector
        connector = AzureDevOpsConnector(
            organization="testorg",
            project="testproject",
            data_types=["commits"]
        )
        
        connector.client_config = {
            "auth": None,
            "organization": "testorg",
            "project": "testproject",
            "base_url": "https://dev.azure.com/testorg/testproject/",
            "api_version": "7.0"
        }
        
        # Add credential
        connector.personal_access_token = "test-pat"
        
        # Mock repository response
        mock_get_repositories.return_value = [
            {
                "id": "repo1",
                "name": "Repository1",
                "url": "https://dev.azure.com/testorg/testproject/_apis/git/repositories/repo1",
                "remoteUrl": "https://dev.azure.com/testorg/testproject/_git/Repository1"
            }
        ]
        
        # Mock commits response with work items
        mock_get_commits.return_value = {
            "count": 2,
            "value": [
                {
                    "commitId": "1234567890abcdef",
                    "author": {
                        "name": "Mike Galante",
                        "email": "mgalante@example.com",
                        "date": "2023-01-01T12:00:00Z"
                    },
                    "comment": "Build 10.38.1337\n\nThis build includes fixes for the report generator",
                    "remoteUrl": "https://dev.azure.com/testorg/testproject/_git/Repository1/commit/1234567890abcdef",
                    "changes": [
                        {
                            "item": {
                                "path": "/src/reports/generator.py"
                            },
                            "changeType": "edit"
                        },
                        {
                            "item": {
                                "path": "/tests/test_generator.py"
                            },
                            "changeType": "add"
                        }
                    ],
                    "workItems": [
                        {
                            "id": 123,
                            "url": "https://dev.azure.com/testorg/testproject/_apis/wit/workItems/123"
                        },
                        {
                            "id": 456,
                            "url": "https://dev.azure.com/testorg/testproject/_apis/wit/workItems/456"
                        }
                    ]
                },
                {
                    "commitId": "0987654321fedcba",
                    "author": {
                        "name": "Jane Smith",
                        "email": "jane@example.com",
                        "date": "2023-01-02T12:00:00Z"
                    },
                    "comment": "Fix report generation bug",
                    "remoteUrl": "https://dev.azure.com/testorg/testproject/_git/Repository1/commit/0987654321fedcba",
                    "changes": [
                        {
                            "item": {
                                "path": "/src/reports/parser.py"
                            },
                            "changeType": "edit"
                        }
                    ]
                }
            ]
        }
        
        # Mock the work item details call
        with patch.object(AzureDevOpsConnector, "_get_work_item_details") as mock_get_work_item_details:
            mock_get_work_item_details.return_value = [
                {
                    "id": 123,
                    "fields": {
                        "System.WorkItemType": "Bug",
                        "System.Title": "Fix report generator crash",
                        "System.State": "Resolved"
                    }
                }
            ]
            
            # Call the method
            slim_docs, failures = connector.retrieve_all_slim_documents()
        
        # Verify no failures
        assert len(failures) == 0
        
        # Verify slim documents count and basic info
        assert len(slim_docs) == 2
        
        # Find Mike's commit
        mike_commit = next((doc for doc in slim_docs if doc.title.startswith("Commit 12345678")), None)
        assert mike_commit is not None
        assert mike_commit.title == "Commit 12345678: Build 10.38.1337"
        
        # Verify description includes the full commit message
        assert mike_commit.description.startswith("Build 10.38.1337")
        assert "report generator" in mike_commit.description
        
        # Verify perm_sync_data includes related work items and changed files
        assert "related_work_items" in mike_commit.perm_sync_data
        assert mike_commit.perm_sync_data["related_work_items"] == "123,456"
        
        # Verify related work item title is included (from the first work item)
        assert "related_work_item_title" in mike_commit.perm_sync_data
        assert mike_commit.perm_sync_data["related_work_item_title"] == "[Bug] #123: Fix report generator crash"
        
        # Verify changed files are included
        assert "changed_files" in mike_commit.perm_sync_data
        assert "/src/reports/generator.py" in mike_commit.perm_sync_data["changed_files"]
        assert "/tests/test_generator.py" in mike_commit.perm_sync_data["changed_files"]

    @patch.object(AzureDevOpsConnector, "_get_commits")
    @patch.object(AzureDevOpsConnector, "_get_repositories")
    def test_slim_documents_with_build_version_numbers(self, mock_get_repositories, mock_get_commits):
        """Test that slim documents properly handle build version numbers in commit messages."""
        # Setup connector
        connector = AzureDevOpsConnector(
            organization="testorg",
            project="testproject",
            data_types=["commits"]
        )
        
        connector.client_config = {
            "auth": None,
            "organization": "testorg",
            "project": "testproject",
            "base_url": "https://dev.azure.com/testorg/testproject/",
            "api_version": "7.0"
        }
        
        # Add credential
        connector.personal_access_token = "test-pat"
        
        # Mock repository response
        mock_get_repositories.return_value = [
            {
                "id": "repo1",
                "name": "Repository1",
                "url": "https://dev.azure.com/testorg/testproject/_apis/git/repositories/repo1",
                "remoteUrl": "https://dev.azure.com/testorg/testproject/_git/Repository1"
            }
        ]
        
        # Mock commits response with build version numbers
        mock_get_commits.return_value = {
            "count": 2,
            "value": [
                {
                    "commitId": "51fd8d1a1234567890abcdef",
                    "author": {
                        "name": "Mike Galante",
                        "email": "mgalante@example.com",
                        "date": "2023-01-01T12:00:00Z"
                    },
                    "comment": "Build 10.39.1371\n\nThis build includes updates to the reporting module",
                    "remoteUrl": "https://dev.azure.com/testorg/testproject/_git/Repository1/commit/51fd8d1a1234567890abcdef",
                    "changes": [
                        {
                            "item": {
                                "path": "/src/reporting/module.js"
                            },
                            "changeType": "edit"
                        }
                    ],
                    "workItems": []  # No work items directly linked
                },
                {
                    "commitId": "d6c50b4a0987654321fedcba",
                    "author": {
                        "name": "Jane Smith",
                        "email": "jane@example.com",
                        "date": "2023-01-02T12:00:00Z"
                    },
                    "comment": "Fix report generation bug AB#123",
                    "remoteUrl": "https://dev.azure.com/testorg/testproject/_git/Repository1/commit/d6c50b4a0987654321fedcba",
                    "changes": [
                        {
                            "item": {
                                "path": "/src/reports/parser.py"
                            },
                            "changeType": "edit"
                        }
                    ],
                    "workItems": [
                        {
                            "id": 123,
                            "url": "https://dev.azure.com/testorg/testproject/_apis/wit/workItems/123"
                        }
                    ]
                }
            ]
        }
        
        # Mock the work item details call
        with patch.object(AzureDevOpsConnector, "_get_work_item_details") as mock_get_work_item_details:
            mock_get_work_item_details.return_value = [
                {
                    "id": 123,
                    "fields": {
                        "System.WorkItemType": "Bug",
                        "System.Title": "Fix report generator crash",
                        "System.State": "Resolved"
                    }
                }
            ]
            
            # Call the method
            slim_docs, failures = connector.retrieve_all_slim_documents()
        
        # Verify no failures
        assert len(failures) == 0
        
        # Verify slim documents count and basic info
        assert len(slim_docs) == 2
        
        # Find build commit (51fd8d1a)
        build_commit = next((doc for doc in slim_docs if doc.title.startswith("Commit 51fd8d1a")), None)
        assert build_commit is not None
        assert build_commit.title == "Commit 51fd8d1a: Build 10.39.1371"
        
        # Verify description includes the full commit message
        assert build_commit.description.startswith("Build 10.39.1371")
        assert "reporting module" in build_commit.description
        
        # Find bug fix commit (with work item)
        bug_fix_commit = next((doc for doc in slim_docs if doc.title.startswith("Commit d6c50b4a")), None)
        assert bug_fix_commit is not None
        
        # Verify work item relationships
        assert "related_work_items" in bug_fix_commit.perm_sync_data
        assert bug_fix_commit.perm_sync_data["related_work_items"] == "123"
        
        # Verify related work item title
        assert "related_work_item_title" in bug_fix_commit.perm_sync_data
        assert bug_fix_commit.perm_sync_data["related_work_item_title"] == "[Bug] #123: Fix report generator crash" 