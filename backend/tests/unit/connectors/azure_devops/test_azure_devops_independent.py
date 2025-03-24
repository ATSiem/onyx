import unittest
import sys
import os

# Add the project root to the Python path so we can import the modules directly
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../../')))

# We'll just test the utils module which doesn't have as many dependencies
from onyx.connectors.azure_devops.utils import (
    build_azure_devops_url,
    extract_organization_project,
    format_date
)


class TestAzureDevOpsUtilsIndependent(unittest.TestCase):
    """Test Azure DevOps utility functions independently without framework dependencies."""

    def test_build_azure_devops_url(self):
        """Test building Azure DevOps item URLs."""
        base_url = "https://dev.azure.com/testorg/testproject/"
        
        # Test work item URL
        work_item_url = build_azure_devops_url(base_url, "123", "workitems")
        self.assertEqual(work_item_url, "https://dev.azure.com/testorg/testproject/_workitems/edit/123")
        
        # Test pull request URL
        pr_url = build_azure_devops_url(base_url, "456", "pullrequests")
        self.assertEqual(pr_url, "https://dev.azure.com/testorg/testproject/_git/pullrequest/456")
        
        # Test generic URL
        generic_url = build_azure_devops_url(base_url, "789", "other")
        self.assertEqual(generic_url, "https://dev.azure.com/testorg/testproject/789")
        
        # Test with trailing slash
        url_with_slash = build_azure_devops_url(base_url + "/", "123", "workitems")
        self.assertEqual(url_with_slash, "https://dev.azure.com/testorg/testproject/_workitems/edit/123")

    def test_extract_organization_project(self):
        """Test extracting organization and project from URLs."""
        # Standard URL
        url = "https://dev.azure.com/testorg/testproject/path"
        org, proj = extract_organization_project(url)
        self.assertEqual(org, "testorg")
        self.assertEqual(proj, "testproject")
        
        # URL with trailing slash
        url = "https://dev.azure.com/testorg/testproject/"
        org, proj = extract_organization_project(url)
        self.assertEqual(org, "testorg")
        self.assertEqual(proj, "testproject")
        
        # Invalid URL
        url = "https://dev.azure.com/testorg"
        with self.assertRaises(ValueError):
            extract_organization_project(url)

    def test_format_date(self):
        """Test date formatting function."""
        # Test with valid date
        date_str = "2023-01-01T12:00:00Z"
        date = format_date(date_str)
        self.assertEqual(date.year, 2023)
        self.assertEqual(date.month, 1)
        self.assertEqual(date.day, 1)
        self.assertEqual(date.hour, 12)
        
        # Test with invalid date
        date_str = "invalid-date"
        date = format_date(date_str)
        self.assertIsNone(date)
        
        # Test with None
        date = format_date(None)
        self.assertIsNone(date)


if __name__ == '__main__':
    unittest.main() 