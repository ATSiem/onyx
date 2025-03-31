import pytest
from datetime import datetime

from onyx.connectors.azure_devops.utils import build_azure_devops_client
from onyx.connectors.azure_devops.utils import build_azure_devops_url
from onyx.connectors.azure_devops.utils import extract_organization_project
from onyx.connectors.azure_devops.utils import get_item_field_value
from onyx.connectors.azure_devops.utils import get_user_info_from_item
from onyx.connectors.azure_devops.utils import format_date
from onyx.connectors.models import BasicExpertInfo


class TestAzureDevOpsUtils:
    """Test the utility functions for the Azure DevOps connector."""

    def test_build_azure_devops_client(self):
        """Test building the Azure DevOps client configuration."""
        credentials = {"personal_access_token": "test_token"}
        organization = "testorg"
        project = "testproject"
        
        config = build_azure_devops_client(credentials, organization, project)
        
        assert config["organization"] == organization
        assert config["project"] == project
        assert config["base_url"] == f"https://dev.azure.com/{organization}/{project}/"
        assert config["api_version"] == "7.0"
        assert config["auth"] is not None

    def test_build_azure_devops_url(self):
        """Test building Azure DevOps item URLs."""
        base_url = "https://dev.azure.com/testorg/testproject/"
        
        # Test work item URL
        work_item_url = build_azure_devops_url(base_url, "123", "workitems")
        assert work_item_url == "https://dev.azure.com/testorg/testproject/_workitems/edit/123"
        
        # Test pull request URL
        pr_url = build_azure_devops_url(base_url, "456", "pullrequests")
        assert pr_url == "https://dev.azure.com/testorg/testproject/_git/pullrequest/456"
        
        # Test generic URL
        generic_url = build_azure_devops_url(base_url, "789", "other")
        assert generic_url == "https://dev.azure.com/testorg/testproject/789"
        
        # Test with trailing slash
        url_with_slash = build_azure_devops_url(base_url + "/", "123", "workitems")
        assert url_with_slash == "https://dev.azure.com/testorg/testproject/_workitems/edit/123"

    def test_extract_organization_project(self):
        """Test extracting organization and project from URLs."""
        # Standard URL
        url = "https://dev.azure.com/testorg/testproject/path"
        org, proj = extract_organization_project(url)
        assert org == "testorg"
        assert proj == "testproject"
        
        # URL with trailing slash
        url = "https://dev.azure.com/testorg/testproject/"
        org, proj = extract_organization_project(url)
        assert org == "testorg"
        assert proj == "testproject"
        
        # Invalid URL
        url = "https://dev.azure.com/testorg"
        with pytest.raises(ValueError):
            extract_organization_project(url)

    def test_get_item_field_value(self):
        """Test extracting field values from work items."""
        # Test with System field
        item = {"fields": {"System.Title": "Test Title"}}
        title = get_item_field_value(item, "System.Title")
        assert title == "Test Title"
        
        # Test with simple field
        item = {"fields": {"Title": "Test Title"}}
        title = get_item_field_value(item, "Title")
        assert title == "Test Title"
        
        # Test with Microsoft field
        item = {"fields": {"Microsoft.VSTS.Common.Priority": "1"}}
        priority = get_item_field_value(item, "Priority")
        assert priority == "1"
        
        # Test with default value
        item = {"fields": {}}
        priority = get_item_field_value(item, "Priority", "2")
        assert priority == "2"
        
        # Test with missing fields
        item = {}
        priority = get_item_field_value(item, "Priority", "2")
        assert priority == "2"

    def test_get_user_info_from_item(self):
        """Test extracting user information from work items."""
        # Test with display name and email
        item = {
            "fields": {
                "System.CreatedBy": {
                    "displayName": "Test User",
                    "uniqueName": "test@example.com"
                }
            }
        }
        user_info = get_user_info_from_item(item, "System.CreatedBy")
        assert isinstance(user_info, BasicExpertInfo)
        assert user_info.display_name == "Test User"
        assert user_info.email == "test@example.com"
        
        # Test with display name and email in alternate field
        item = {
            "fields": {
                "System.CreatedBy": {
                    "displayName": "Test User",
                    "emailAddress": "test@example.com"
                }
            }
        }
        user_info = get_user_info_from_item(item, "System.CreatedBy")
        assert user_info.email == "test@example.com"
        
        # Test with missing user info
        item = {"fields": {}}
        user_info = get_user_info_from_item(item, "System.CreatedBy")
        assert user_info is None
        
        # Test with incomplete user info
        item = {
            "fields": {
                "System.CreatedBy": {}
            }
        }
        user_info = get_user_info_from_item(item, "System.CreatedBy")
        assert user_info is None

    def test_format_date(self):
        """Test date formatting function."""
        # Test with valid date
        date_str = "2023-01-01T12:00:00Z"
        date = format_date(date_str)
        assert isinstance(date, datetime)
        assert date.year == 2023
        assert date.month == 1
        assert date.day == 1
        assert date.hour == 12
        
        # Test with invalid date
        date_str = "invalid-date"
        date = format_date(date_str)
        assert date is None
        
        # Test with None
        date = format_date(None)
        assert date is None 