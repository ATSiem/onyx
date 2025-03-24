"""Module with Azure DevOps connector utility functions"""
import base64
from datetime import datetime
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import requests
from requests.auth import HTTPBasicAuth

from onyx.connectors.models import BasicExpertInfo
from onyx.utils.logger import setup_logger

logger = setup_logger()


def build_azure_devops_client(
    credentials: dict[str, Any], organization: str, project: str
) -> dict[str, Any]:
    """
    Build and return Azure DevOps client configuration.
    """
    personal_access_token = credentials["personal_access_token"]

    return {
        "auth": HTTPBasicAuth("", personal_access_token),
        "organization": organization,
        "project": project,
        "base_url": f"https://dev.azure.com/{organization}/{project}/",
        "api_version": "7.0",  # Using the latest stable version as of 2023
    }


def build_azure_devops_url(base_url: str, item_id: str, item_type: str) -> str:
    """
    Build the URL for a specific Azure DevOps item.
    
    Args:
        base_url: Base URL for the Azure DevOps project
        item_id: ID of the item
        item_type: Type of the item (e.g., 'workitems', 'git/repositories')
        
    Returns:
        URL for the specific item
    """
    # Remove trailing slash if present
    base_url = base_url.rstrip("/")
    
    if item_type == "workitems":
        return f"{base_url}/_workitems/edit/{item_id}"
    elif item_type == "pullrequests":
        return f"{base_url}/_git/pullrequest/{item_id}"
    # Add more item types as needed
    
    return f"{base_url}/{item_id}"


def extract_organization_project(url: str) -> tuple[str, str]:
    """
    Extract organization and project name from an Azure DevOps URL.
    
    Args:
        url: Azure DevOps URL
        
    Returns:
        Tuple of (organization, project)
        
    Raises:
        ValueError: If the URL does not contain organization and project
    """
    parsed_url = urlparse(url)
    path_parts = parsed_url.path.strip("/").split("/")
    
    if len(path_parts) < 2:
        raise ValueError("URL does not contain organization and project")
    
    return path_parts[0], path_parts[1]


def get_item_field_value(
    item: Dict[str, Any], field_name: str, default: Any = None
) -> Any:
    """
    Safely extract a field value from an Azure DevOps work item.
    
    Args:
        item: Work item dictionary
        field_name: Name of the field to extract
        default: Default value if field is not found
        
    Returns:
        Field value or default
    """
    if "fields" not in item:
        return default
    
    fields = item["fields"]
    # Handle System.* fields
    if field_name.startswith("System."):
        return fields.get(field_name, default)
    
    # Try different ways the field might be stored
    field_variants = [
        field_name,
        f"System.{field_name}",
        f"Microsoft.VSTS.Common.{field_name}"
    ]
    
    for variant in field_variants:
        if variant in fields:
            return fields[variant]
    
    return default


def get_user_info_from_item(
    item: Dict[str, Any], field_name: str
) -> Optional[BasicExpertInfo]:
    """
    Extract user information from a work item field.
    
    Args:
        item: Work item dictionary
        field_name: Name of the field containing user information
        
    Returns:
        BasicExpertInfo object or None if not found
    """
    user_info = get_item_field_value(item, field_name)
    if not user_info:
        return None
    
    # Different Azure DevOps API versions might return different formats
    display_name = None
    email = None
    
    if isinstance(user_info, dict):
        display_name = user_info.get("displayName")
        email = user_info.get("uniqueName") or user_info.get("emailAddress")
    
    if not display_name and not email:
        return None
    
    return BasicExpertInfo(display_name=display_name, email=email)


def format_date(date_str: Optional[str]) -> Optional[datetime]:
    """
    Format an Azure DevOps date string to a datetime object.
    
    Args:
        date_str: Date string from Azure DevOps API
        
    Returns:
        datetime object or None if date_str is None
    """
    if not date_str:
        return None
    
    try:
        return datetime.fromisoformat(date_str.replace('Z', '+00:00'))
    except (ValueError, TypeError):
        logger.warning(f"Failed to parse date: {date_str}")
        return None
