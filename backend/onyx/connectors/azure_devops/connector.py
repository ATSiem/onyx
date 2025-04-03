"""Azure DevOps connector for Onyx"""
import json
import logging
import time
from collections.abc import Generator, Iterator
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, cast
import re
import os

import requests
from pydantic import BaseModel
from typing_extensions import override

from onyx.configs.app_configs import INDEX_BATCH_SIZE
from onyx.configs.constants import DocumentSource
from onyx.connectors.azure_devops.utils import build_azure_devops_client
from onyx.connectors.azure_devops.utils import build_azure_devops_url
from onyx.connectors.azure_devops.utils import format_date
from onyx.connectors.azure_devops.utils import get_item_field_value
from onyx.connectors.azure_devops.utils import get_user_info_from_item
from onyx.connectors.cross_connector_utils.miscellaneous_utils import time_str_to_utc
from onyx.connectors.cross_connector_utils.rate_limit_wrapper import rate_limit_builder
from onyx.connectors.exceptions import ConnectorMissingCredentialError
from onyx.connectors.exceptions import ConnectorValidationError
from onyx.connectors.interfaces import CheckpointConnector
from onyx.connectors.interfaces import CheckpointOutput
from onyx.connectors.interfaces import GenerateSlimDocumentOutput
from onyx.connectors.interfaces import SecondsSinceUnixEpoch
from onyx.connectors.interfaces import SlimConnector
from onyx.connectors.models import BasicExpertInfo
from onyx.connectors.models import ConnectorCheckpoint
from onyx.connectors.models import ConnectorFailure
from onyx.connectors.models import Document
from onyx.connectors.models import DocumentFailure
from onyx.connectors.models import EntityFailure
from onyx.connectors.models import SlimDocument
from onyx.connectors.models import TextSection
from onyx.indexing.indexing_heartbeat import IndexingHeartbeatInterface
from onyx.utils.logger import setup_logger
from onyx.utils.retry_wrapper import retry_builder
from functools import lru_cache
from concurrent.futures import ThreadPoolExecutor

logger = setup_logger()

# Constants
MAX_RESULTS_PER_PAGE = 200  # Azure DevOps API can handle larger page sizes
MAX_WORK_ITEM_SIZE = 1000000  # 1MB - Azure DevOps API can handle larger responses
MAX_BATCH_SIZE = 200  # Maximum number of work items to fetch in a single batch
WORK_ITEM_TYPES = ["Bug", "Epic", "Feature", "Issue", "Task", "TestCase", "UserStory"]
AZURE_DEVOPS_BASE_URL = "https://dev.azure.com"

# Rate limit settings based on Azure DevOps documentation
# Azure DevOps recommends responding to Retry-After headers and has a global consumption limit
# of 200 Azure DevOps throughput units (TSTUs) within a sliding 5-minute window
MAX_API_CALLS_PER_MINUTE = 60  # Back to original value since we're handling rate limits properly

# Constants for Azure DevOps API
API_VERSION = "7.0"
BASE_URL_TEMPLATE = "https://dev.azure.com/{organization}/{project}/"  # Note the trailing slash


class AzureDevOpsConnectorCheckpoint(ConnectorCheckpoint):
    """Checkpoint for the Azure DevOps connector to keep track of pagination."""
    continuation_token: Optional[str] = None


class AzureDevOpsConnector(CheckpointConnector[AzureDevOpsConnectorCheckpoint], SlimConnector):
    """Connector for Microsoft Azure DevOps."""

    # Class-level constants
    MAX_BATCH_SIZE = 200  # Maximum number of work items to fetch in a single batch
    MAX_RESULTS_PER_PAGE = 200  # Azure DevOps API can handle larger page sizes
    MAX_WORK_ITEM_SIZE = 1000000  # 1MB - Azure DevOps API can handle larger responses
    WORK_ITEM_TYPES = ["Bug", "Epic", "Feature", "Issue", "Task", "TestCase", "UserStory"]
    MAX_API_CALLS_PER_MINUTE = 60  # Back to original value since we're handling rate limits properly
    
    # Data type constants for tracking what types of data to fetch
    DATA_TYPE_WORK_ITEMS = "work_items"
    DATA_TYPE_COMMITS = "commits"
    DATA_TYPE_TEST_RESULTS = "test_results"
    DATA_TYPE_TEST_STATS = "test_stats"
    DATA_TYPE_RELEASES = "releases"
    DATA_TYPE_RELEASE_DETAILS = "release_details"
    DATA_TYPE_WIKIS = "wikis"
    
    # Default data types to fetch
    DEFAULT_DATA_TYPES = [DATA_TYPE_WORK_ITEMS]

    def __init__(
        self,
        organization: str,
        project: str,
        work_item_types: Optional[List[str]] = None,
        include_comments: bool = True,
        include_attachments: bool = False,
        data_types: Optional[List[str]] = None,
        repositories: Optional[List[str]] = None,
        content_scope: Optional[str] = None,
    ) -> None:
        """Initialize the Azure DevOps connector.
        
        Args:
            organization: Azure DevOps organization name
            project: Azure DevOps project name
            work_item_types: List of work item types to index (defaults to all common types)
            include_comments: Whether to include work item comments
            include_attachments: Whether to include work item attachments (as links)
            data_types: Types of data to fetch (defaults to work items only)
            repositories: List of repository names to fetch commits from (defaults to all)
            content_scope: UI selection for content scope (work_items_only or everything)
        """
        super().__init__()
        self.organization = organization
        self.project = project
        self.work_item_types = work_item_types or self.WORK_ITEM_TYPES
        self.include_comments = include_comments
        self.include_attachments = include_attachments
        self.base_url = BASE_URL_TEMPLATE.format(organization=organization, project=project)
        self.client_config = {}  # Initialize as empty dict, will be populated when credentials are loaded
        self.personal_access_token: Optional[str] = None
        self._context_cache = {}
        self._cache_ttl = timedelta(minutes=5)
        
        # Handle content_scope from the UI - if "everything" is selected, 
        # set data_types to include all available data types.
        # This value comes from a select dropdown in the UI with two options:
        # "work_items_only" and "everything"
        if content_scope and content_scope.lower() == "everything":
            logger.info(f"Content scope is set to '{content_scope}', setting all data types")
            self.data_types = [
                self.DATA_TYPE_WORK_ITEMS,
                self.DATA_TYPE_COMMITS,
                self.DATA_TYPE_TEST_RESULTS,
                self.DATA_TYPE_TEST_STATS,
                self.DATA_TYPE_RELEASES,
                self.DATA_TYPE_RELEASE_DETAILS,
                self.DATA_TYPE_WIKIS
            ]
        else:
            # If data_types is explicitly provided, use it, otherwise default to work_items only
            self.data_types = data_types or self.DEFAULT_DATA_TYPES
            
        # Store the content scope for logging purposes
        self.content_scope = content_scope
        
        # Log the configuration for debugging
        logger.info(f"Azure DevOps connector initialized with content_scope: {content_scope}")
        logger.info(f"Data types: {self.data_types}")
            
        self.repositories = repositories  # None means all repositories
        
        # Initialize repository cache
        self._repository_cache = {}

    @override
    def load_credentials(self, credentials: Dict[str, Any]) -> None:
        """Load Azure DevOps credentials from the provided dictionary.

        Args:
            credentials: Dictionary containing Azure DevOps credentials
                Expected format:
                {
                    "personal_access_token": "your-pat-token"
                }

        Raises:
            ConnectorMissingCredentialError: If credentials are missing or invalid
        """
        if not credentials:
            raise ConnectorMissingCredentialError("Azure DevOps")

        if "personal_access_token" not in credentials:
            raise ConnectorMissingCredentialError("Azure DevOps - Personal Access Token required")

        self.personal_access_token = credentials["personal_access_token"]
        
        # Set up client config with credentials using the utility function
        self.client_config = build_azure_devops_client(credentials, self.organization, self.project)

    def validate_connector_settings(self) -> None:
        """Validate the connector settings by making a test API call.
        
        Raises:
            ConnectorValidationError: If the settings are invalid
        """
        if not self.client_config:
            raise ConnectorValidationError("Azure DevOps client not configured")
        
        # Log connector configuration for debugging
        logger.info(f"Validating Azure DevOps connector with content_scope: {getattr(self, 'content_scope', None)}")
        logger.info(f"Data types to index: {self.data_types}")
        
        # Try to fetch project info as a simpler validation step
        try:
            # First, get the list of projects at organization level
            logger.info(f"Validating connection to Azure DevOps organization: {self.organization}")
            
            # Check if PAT is present but masked for privacy in logs
            if self.personal_access_token:
                pat_length = len(self.personal_access_token)
                logger.info(f"Using PAT (length: {pat_length}, first chars: {self.personal_access_token[:4]}...)")
            else:
                logger.warning("No Personal Access Token provided")
            
            # Start with organization-level API call which we know works with the PAT
            org_response = self._make_api_request(
                endpoint="_apis/projects",
                method="GET",
                organization_level=True  # Mark this as an organization-level call
            )
            
            logger.info(f"Organization API response status code: {org_response.status_code}")
            org_response.raise_for_status()
            
            # Extract all projects to find our project by name
            org_data = org_response.json()
            projects = org_data.get("value", [])
            logger.info(f"Found {len(projects)} projects in organization")
            
            # Find our project
            project_found = False
            project_id = None
            
            for project in projects:
                if project.get("name") == self.project:
                    project_found = True
                    project_id = project.get("id")
                    logger.info(f"Found project '{self.project}' with ID: {project_id}")
                    break
            
            if not project_found:
                logger.error(f"Project '{self.project}' not found in organization '{self.organization}'")
                raise ConnectorValidationError(f"Project '{self.project}' not found in organization '{self.organization}'. Please verify the project name.")
            
            # Now that we know the project exists, try to get work item types using project ID
            # This ensures we have proper permissions for work items
            logger.info(f"Validating work item access for project: {self.project}")
            
            # Use organization-level API with project in query rather than path
            types_response = self._make_api_request(
                "_apis/wit/workitemtypes",
                method="GET",
                params={"project": self.project},
                organization_level=True  # Use organization-level URL
            )
            
            if types_response.status_code == 200:
                types_data = types_response.json()
                available_types = [t.get('name') for t in types_data.get('value', [])]
                logger.info(f"Available work item types in this project: {', '.join(available_types)}")
                
                # Update work item types to only include actually available types
                if self.work_item_types:
                    original_types = set(self.work_item_types)
                    available_type_set = set(available_types)
                    
                    # Check which types are actually available
                    found_types = original_types.intersection(available_type_set)
                    
                    # Try with variant spellings (UserStory vs User Story)
                    for original_type in original_types:
                        if original_type not in found_types:
                            # Check common variations
                            if original_type == "User Story" and "UserStory" in available_type_set:
                                found_types.add("UserStory")
                            elif original_type == "UserStory" and "User Story" in available_type_set:
                                found_types.add("User Story")
                    
                    if found_types != original_types:
                        logger.info(f"Some specified work item types are not available. Using available types: {found_types}")
                        self.work_item_types = list(found_types) or ["Bug", "Task"]  # Default to Bug and Task if none found
            
        except requests.exceptions.HTTPError as e:
            error_message = str(e)
            status_code = e.response.status_code if hasattr(e, 'response') and hasattr(e.response, 'status_code') else 'unknown'
            logger.error(f"HTTP Error during validation: {error_message} (status code: {status_code})")
            
            # Try to get more details from the response
            error_details = None
            if hasattr(e, 'response') and hasattr(e.response, 'content'):
                try:
                    error_details = e.response.json() if e.response.content else None
                except:
                    error_details = e.response.content.decode('utf-8', errors='ignore')[:200] if e.response.content else None
            
            if error_details:
                logger.error(f"Error details: {error_details}")
            
            # Provide more user-friendly error messages
            if status_code == 401:
                error_message = "Authentication failed. Please check your Personal Access Token. Make sure it has not expired and has sufficient scopes (read access to the project)."
            elif status_code == 403:
                error_message = "Authorization failed. Your PAT doesn't have sufficient permissions for this project."
            elif status_code == 404:
                error_message = f"Project '{self.project}' not found in organization '{self.organization}'. Please verify the project and organization names."
            
            raise ConnectorValidationError(
                f"Failed to connect to Azure DevOps API: {error_message}"
            )
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Request exception during validation: {str(e)}")
            error_message = str(e)
            
            # Provide more specific error messages for common issues
            if "SSLError" in error_message:
                error_message = "SSL Error occurred. This might be due to network or proxy issues."
            elif "ConnectionError" in error_message:
                error_message = "Connection Error. Could not connect to Azure DevOps. Please check your network connection."
            elif "Timeout" in error_message:
                error_message = "Connection timed out. Azure DevOps API did not respond in time."
                
            raise ConnectorValidationError(
                f"Failed to connect to Azure DevOps API: {error_message}"
            )

    @retry_builder(tries=5, backoff=1.5)
    @rate_limit_builder(max_calls=MAX_API_CALLS_PER_MINUTE, period=60)
    def _make_api_request(
        self, 
        endpoint: str, 
        method: str = "GET", 
        params: Dict[str, Any] = None,
        data: str = None,
        organization_level: bool = False
    ) -> requests.Response:
        """Make an API request to Azure DevOps with rate limiting and retry logic."""
        if not self.client_config:
            raise ConnectorValidationError("Azure DevOps client not configured")
        
        # For organization-level APIs, use just the organization part of the URL
        if organization_level:
            # Extract just the organization part from the base URL
            org_url_parts = self.client_config["base_url"].split('/')
            # Typical URL format: https://dev.azure.com/org/project/
            if 'dev.azure.com' in self.client_config["base_url"].lower():
                # For dev.azure.com URLs
                org_base_url = f"https://dev.azure.com/{self.organization}"
            else:
                # For visualstudio.com URLs
                org_base_url = f"https://{self.organization}.visualstudio.com"
            
            url = f"{org_base_url}/{endpoint}"
            logger.info(f"Using organization-level API URL: {url}")
        else:
            # Use the full project URL for project-level APIs
            base_url = self.client_config["base_url"].rstrip("/")
            url = f"{base_url}/{endpoint}"
        
        # Ensure API version is included, but don't override if explicitly provided
        api_params = params or {}
        if "api-version" not in api_params:
            api_params["api-version"] = self.client_config["api_version"]
        
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        
        # Keep track of errors to provide better debugging info
        errors = []
        urls_tried = []
        
        # First try with the primary URL
        try:
            logger.debug(f"Making {method} request to {url} with params {api_params}")
            response = requests.request(
                method=method,
                url=url,
                auth=self.client_config["auth"],
                params=api_params,
                headers=headers,
                data=data
            )
            urls_tried.append(url)
            
            # Handle rate limiting explicitly
            if response.status_code == 429:
                retry_after = int(response.headers.get('Retry-After', 30))
                logger.warning(f"Rate limited by Azure DevOps API. Waiting for {retry_after} seconds.")
                time.sleep(retry_after)
                # Recursive call after waiting
                return self._make_api_request(endpoint, method, params, data, organization_level)
            
            # Check for X-RateLimit headers to adjust our rate limiting if needed
            remaining = response.headers.get('X-RateLimit-Remaining')
            if remaining and int(remaining) < 10:
                logger.warning(f"Approaching Azure DevOps API rate limit. Only {remaining} requests remaining.")
            
            # Log bad request errors with more detail
            if response.status_code == 400:
                try:
                    error_content = response.json()
                    logger.error(f"Bad request (400) error: {error_content}")
                except:
                    logger.error(f"Bad request (400) error: {response.text[:500]}")
            
            # If we got a 404 or 401, we might want to try alternate URL formats
            if response.status_code in (404, 401) and "alt_base_url" in self.client_config and not organization_level:
                errors.append(f"Primary URL {url} failed with status code {response.status_code}")
                
                # Try with the alternate URL format (only for project-level APIs)
                alt_base_url = self.client_config["alt_base_url"].rstrip("/")
                alt_url = f"{alt_base_url}/{endpoint}"
                
                if alt_url not in urls_tried:  # Avoid infinite recursion
                    logger.info(f"Primary URL failed, trying alternate URL: {alt_url}")
                    
                    alt_response = requests.request(
                        method=method,
                        url=alt_url,
                        auth=self.client_config["auth"],
                        params=api_params,
                        headers=headers,
                        data=data
                    )
                    urls_tried.append(alt_url)
                    
                    # If alternate URL works better, update the client config
                    if alt_response.status_code < response.status_code:
                        logger.info(f"Alternate URL format worked better, updating client config")
                        self.client_config["base_url"] = alt_base_url
                        return alt_response
            
            return response
        except requests.exceptions.RequestException as e:
            error_str = str(e)
            errors.append(f"Request to {url} failed: {error_str}")
            
            # Try alternate URL if primary fails due to connection issue (only for project-level APIs)
            if "alt_base_url" in self.client_config and not organization_level:
                alt_base_url = self.client_config["alt_base_url"].rstrip("/")
                alt_url = f"{alt_base_url}/{endpoint}"
                
                if alt_url not in urls_tried:  # Avoid infinite recursion
                    logger.info(f"Primary URL failed with exception, trying alternate URL: {alt_url}")
                    try:
                        alt_response = requests.request(
                            method=method,
                            url=alt_url,
                            auth=self.client_config["auth"],
                            params=api_params,
                            headers=headers,
                            data=data
                        )
                        urls_tried.append(alt_url)
                        
                        # If we get here, the alternate URL worked; update the client config
                        logger.info(f"Alternate URL format worked, updating client config")
                        self.client_config["base_url"] = alt_base_url
                        return alt_response
                    except requests.exceptions.RequestException as alt_e:
                        errors.append(f"Request to alternate URL {alt_url} also failed: {str(alt_e)}")
            
            # Both attempts failed or we only had one URL to try
            error_detail = "; ".join(errors)
            logger.error(f"All Azure DevOps API requests failed: {error_detail}")
            raise ConnectorValidationError(f"API request failed: {error_str}. URLs tried: {', '.join(urls_tried)}")

    def _get_work_items(
        self, 
        start_time: Optional[datetime] = None,
        continuation_token: Optional[str] = None,
        max_results: int = MAX_RESULTS_PER_PAGE
    ) -> Dict[str, Any]:
        """Get work items from Azure DevOps.
        
        Args:
            start_time: Only return work items modified after this time
            continuation_token: Token for pagination
            max_results: Maximum number of results to return
            
        Returns:
            API response containing work items
        """
        # Build a WIQL query that explicitly uses the project name instead of @project parameter
        # This makes the filtering more explicit and reliable
        query = f"SELECT [System.Id] FROM WorkItems WHERE [System.TeamProject] = '{self.project}'"
        
        # Add work item type filter if specified
        if self.work_item_types and len(self.work_item_types) > 0:
            # Convert user-friendly names to exact Azure DevOps system names if needed
            # e.g., "User Story" might be stored as "UserStory" in some projects
            sanitized_types = []
            for item_type in self.work_item_types:
                sanitized_types.append(item_type)
                # Add common variations
                if item_type == "User Story":
                    sanitized_types.append("UserStory")
                elif item_type == "UserStory":
                    sanitized_types.append("User Story")
            
            types_str = ", ".join([f"'{item_type}'" for item_type in sanitized_types])
            query += f" AND [System.WorkItemType] IN ({types_str})"
        
        # Add time filter if specified
        if start_time:
            # Format with only date part, without time component to avoid WIQL precision error
            formatted_date = start_time.strftime("%Y-%m-%d")
            query += f" AND [System.ChangedDate] >= '{formatted_date}'"
        
        # Order by changed date
        query += " ORDER BY [System.ChangedDate] DESC"
        
        # Make the query request
        data = {
            "query": query,
            "top": max_results
        }
        
        if continuation_token:
            data["continuationToken"] = continuation_token
            
        # Log the WIQL query to help debug issues
        logger.info(f"Executing WIQL query: {query}")
        logger.info(f"Organization: {self.organization}, Project: {self.project}")
            
        try:
            response = self._make_api_request(
                "_apis/wit/wiql",
                method="POST",
                data=json.dumps(data),
                organization_level=True  # Use organization-level URL
            )
            
            response.raise_for_status()
            result = response.json()
            
            # Log the number of work items found
            work_item_count = len(result.get("workItems", []))
            logger.info(f"WIQL query returned {work_item_count} work items")
            
            return result
        except requests.exceptions.RequestException as e:
            # Get more details about the error
            error_detail = ""
            if hasattr(e, 'response') and e.response is not None:
                try:
                    error_detail = e.response.json()
                except:
                    error_detail = e.response.text
                
            logger.error(f"Error executing WIQL query: {str(e)}")
            logger.error(f"Error details: {error_detail}")
            raise ConnectorValidationError(f"Failed to execute WIQL query: {str(e)}")

    @retry_builder(tries=3, backoff=2)  # Add retry mechanism
    def _get_work_item_details(self, work_item_ids: List[int]) -> List[Dict[str, Any]]:
        """Get detailed information for work items with improved rate limiting."""
        if not work_item_ids:
            return []

        # First check cache for all work items
        all_work_items = []
        uncached_ids = []

        for work_item_id in work_item_ids:
            cached_doc = self._get_cached_context(work_item_id)
            if cached_doc:
                # Extract the work item details from the cached document
                work_item = {
                    "id": work_item_id,
                    "fields": {
                        "System.Id": work_item_id,
                        "System.Title": cached_doc.title.split(": ", 1)[1] if ": " in cached_doc.title else cached_doc.title,
                        "System.Description": cached_doc.sections[0].text if cached_doc.sections else "",
                        "System.WorkItemType": cached_doc.metadata.get("type", ""),
                        "System.State": cached_doc.metadata.get("state", ""),
                        "System.CreatedDate": cached_doc.doc_updated_at.isoformat() if cached_doc.doc_updated_at else None,
                        "System.ChangedDate": cached_doc.doc_updated_at.isoformat() if cached_doc.doc_updated_at else None,
                        "System.Tags": "; ".join(cached_doc.metadata.get("tags", [])),
                        "System.AreaPath": cached_doc.metadata.get("area_path", ""),
                        "System.IterationPath": cached_doc.metadata.get("iteration_path", ""),
                        "Microsoft.VSTS.Common.Priority": cached_doc.metadata.get("priority", ""),
                        "Microsoft.VSTS.Common.Severity": cached_doc.metadata.get("severity", ""),
                        "System.ResolvedDate": cached_doc.metadata.get("resolved_date", ""),
                        "Microsoft.VSTS.Common.ClosedDate": cached_doc.metadata.get("closed_date", ""),
                        "Microsoft.VSTS.Common.Resolution": cached_doc.metadata.get("resolution", ""),
                        "System.ResolvedBy": cached_doc.metadata.get("resolved_by", ""),
                        "System.ClosedBy": cached_doc.metadata.get("closed_by", ""),
                        "System.ClosedDate": cached_doc.metadata.get("closed_date", ""),
                    }
                }
                all_work_items.append(work_item)
            else:
                uncached_ids.append(work_item_id)

        # If we have uncached IDs, fetch them in batches
        if uncached_ids:
            for i in range(0, len(uncached_ids), self.MAX_BATCH_SIZE):
                batch_ids = uncached_ids[i:i + self.MAX_BATCH_SIZE]
                batch_ids_str = ",".join(map(str, batch_ids))

                # Define essential and optional fields to reduce request complexity
                # Essential fields are always fetched
                essential_fields = [
                    "System.Id",
                    "System.Title",
                    "System.Description",
                    "System.WorkItemType",
                    "System.State",
                    "System.CreatedBy",
                    "System.CreatedDate",
                    "System.ChangedBy",
                    "System.ChangedDate",
                    "System.Tags",
                    "System.AssignedTo"
                ]
                
                # Try with essential fields first
                try:
                    logger.info(f"Fetching {len(batch_ids)} work items with essential fields")
                    endpoint = f"_apis/wit/workitems"
                    params = {
                        "ids": batch_ids_str,
                        "fields": ",".join(essential_fields)
                    }

                    response = self._make_api_request(endpoint, method="GET", params=params)
                    response.raise_for_status()

                    # Process the response
                    batch_data = response.json()
                    if "value" in batch_data:
                        all_work_items.extend(batch_data["value"])

                    # Now try to get additional fields in a separate request if needed
                    try:
                        additional_fields = [
                            "System.AreaPath",
                            "System.IterationPath",
                            "Microsoft.VSTS.Common.Priority",
                            "Microsoft.VSTS.Common.Severity",
                            "System.ResolvedDate",
                            "Microsoft.VSTS.Common.ClosedDate",
                            "Microsoft.VSTS.Common.Resolution",
                            "System.ResolvedBy",
                            "System.ClosedBy",
                            "System.ClosedDate"
                        ]
                        
                        # Only fetch additional fields if we have items
                        if "value" in batch_data and batch_data["value"]:
                            logger.info(f"Fetching additional fields for {len(batch_ids)} work items")
                            additional_params = {
                                "ids": batch_ids_str,
                                "fields": ",".join(additional_fields)
                            }
                            
                            additional_response = self._make_api_request(endpoint, method="GET", params=additional_params)
                            additional_response.raise_for_status()
                            
                            additional_data = additional_response.json()
                            if "value" in additional_data:
                                # Merge the additional fields into the existing work items
                                for additional_item in additional_data["value"]:
                                    for existing_item in all_work_items:
                                        if existing_item["id"] == additional_item["id"]:
                                            # Merge fields
                                            existing_item["fields"].update(additional_item.get("fields", {}))
                                            break
                    except requests.exceptions.RequestException as additional_e:
                        # Log the error but continue with the essential fields we already have
                        logger.warning(f"Failed to fetch additional fields: {str(additional_e)}")
                        # Don't re-raise, we can continue with essential fields
                except requests.exceptions.RequestException as e:
                    logger.error(f"Failed to fetch work items: {str(e)}")
                    if hasattr(e, 'response') and e.response is not None:
                        try:
                            error_details = e.response.json()
                            logger.error(f"Error details: {error_details}")
                        except:
                            logger.error(f"Error details: {e.response.text[:500]}")
                    raise ConnectorValidationError(f"Failed to fetch work items: {str(e)}")

        return all_work_items

    def _get_work_item_comments(self, work_item_id: int) -> List[Dict[str, Any]]:
        """Get comments for a work item.
        
        Args:
            work_item_id: Work item ID
            
        Returns:
            List of comments
        """
        if not self.include_comments:
            return []
        
        try:
            # Note: Comments API requires api-version with -preview flag
            response = self._make_api_request(
                f"{self.project}/_apis/wit/workItems/{work_item_id}/comments",
                params={"api-version": "7.0-preview"},  # Override the default API version to use preview
                organization_level=True  # Use organization-level URL
            )
            response.raise_for_status()
            return response.json().get("comments", [])
        except requests.exceptions.RequestException as e:
            logger.warning(f"Failed to get comments for work item {work_item_id}: {str(e)}")
            return []

    def _process_work_item(self, work_item: Dict[str, Any], comments: Optional[List[Dict[str, Any]]] = None) -> Optional[Document]:
        """Process a work item into a Document object.

        Args:
            work_item: The work item data from Azure DevOps
            comments: Optional list of comments for the work item

        Returns:
            Document object if successful, None otherwise
        """
        try:
            fields = work_item.get("fields", {})
            work_item_id = str(work_item.get("id"))
            
            # Extract basic fields
            title = fields.get("System.Title", "")
            description = fields.get("System.Description", "")
            work_item_type = fields.get("System.WorkItemType", "")
            state = fields.get("System.State", "")
            
            # Get the work item URL from _links if available
            item_url = work_item.get("_links", {}).get("html", {}).get("href")
            if not item_url:
                # Build URL for the work item as fallback
                base_url = self.client_config.get("base_url", "")
                if not base_url:
                    base_url = f"https://dev.azure.com/{self.organization}/{self.project}"
                item_url = build_azure_devops_url(
                    base_url, 
                    work_item_id, 
                    "workitems"
                )
            
            # Create sections
            sections = []
            
            # Determine resolution status early so we can use it in the semantic identifier
            resolution_status = self._determine_resolution_status(fields)
            
            # Build main content section with improved structure
            content_parts = []
            # Add resolution status in the title for better visibility in citations
            content_parts.append(f"Title: {title} [{resolution_status}]")
            if description:
                content_parts.append(f"\nDescription:\n{description}")
            
            # Add status information with improved detail and structure
            status_parts = []
            if state:
                status_parts.append(f"Status: {state}")
            
            # Add resolution information with clarity about which fields are used
            resolved_date = fields.get("System.ResolvedDate")
            if resolved_date:
                status_parts.append(f"Resolved Date: {format_date(resolved_date)}")
            
            closed_date = fields.get("Microsoft.VSTS.Common.ClosedDate")
            if closed_date:
                status_parts.append(f"Closed Date: {format_date(closed_date)}")
            
            resolution = fields.get("Microsoft.VSTS.Common.Resolution")
            if resolution:
                status_parts.append(f"Resolution: {resolution}")
            else:
                # Be explicit when resolution is not set
                status_parts.append("Resolution: Not Set")
            
            # Add explicit resolution status with confidence information
            status_parts.append(f"Resolution Status: {resolution_status}")
            
            # Add URL information
            status_parts.append(f"Original URL: {item_url}")
            
            if status_parts:
                content_parts.append(f"\nStatus Information:\n" + "\n".join(status_parts))
            
            # Add comments if present and enabled
            if comments:
                content_parts.append("\nComments:")
                for comment in comments:
                    author = comment.get("createdBy", {}).get("displayName", "Unknown")
                    text = comment.get("text", "")
                    date = comment.get("createdDate", "")
                    content_parts.append(f"- {author} ({date}): {text}")
            
            sections.append(TextSection(
                text="\n".join(content_parts),
                link=item_url
            ))
            
            # Extract metadata with improved resolution status handling
            metadata = {
                "type": work_item_type or "",
                "state": state or "",
                "area_path": fields.get("System.AreaPath", ""),
                "iteration_path": fields.get("System.IterationPath", ""),
                "priority": str(fields.get("Microsoft.VSTS.Common.Priority", "")),
                "severity": str(fields.get("Microsoft.VSTS.Common.Severity", "")),
                "tags": fields.get("System.Tags", "").split("; ") if fields.get("System.Tags") else [],
                "resolution_status": resolution_status,
                "original_url": item_url  # Always include the URL in metadata
            }
            
            # Include explicit boolean fields for resolved status
            has_resolved_date = resolved_date is not None
            has_closed_date = closed_date is not None
            has_resolution = resolution is not None
            
            metadata["has_resolution_field"] = "true" if has_resolution else "false"
            metadata["has_resolved_date"] = "true" if has_resolved_date else "false"
            metadata["has_closed_date"] = "true" if has_closed_date else "false"
            metadata["is_resolved"] = "true" if (has_resolved_date or has_closed_date or has_resolution) else "false"

            # Add resolution-related fields only if they are set
            if resolution:
                metadata["resolution"] = resolution
            if resolved_date:
                # Ensure we store a string, not a datetime object, with Z format
                resolved_date_str = format_date(resolved_date)
                if isinstance(resolved_date_str, datetime):
                    resolved_date_str = resolved_date_str.strftime("%Y-%m-%dT%H:%M:%SZ")
                elif isinstance(resolved_date_str, str) and "+00:00" in resolved_date_str:
                    resolved_date_str = resolved_date_str.replace("+00:00", "Z")
                metadata["resolved_date"] = resolved_date_str
            if closed_date:
                # Ensure we store a string, not a datetime object, with Z format
                closed_date_str = format_date(closed_date)
                if isinstance(closed_date_str, datetime):
                    closed_date_str = closed_date_str.strftime("%Y-%m-%dT%H:%M:%SZ")
                elif isinstance(closed_date_str, str) and "+00:00" in closed_date_str:
                    closed_date_str = closed_date_str.replace("+00:00", "Z")
                metadata["closed_date"] = closed_date_str
            if resolved_by := fields.get("System.ResolvedBy"):
                if isinstance(resolved_by, dict):
                    metadata["resolved_by"] = resolved_by.get("displayName", "")
                else:
                    metadata["resolved_by"] = str(resolved_by)
            if closed_by := fields.get("System.ClosedBy"):
                if isinstance(closed_by, dict):
                    metadata["closed_by"] = closed_by.get("displayName", "")
                else:
                    metadata["closed_by"] = str(closed_by)
            
            # Extract dates
            created_date = fields.get("System.CreatedDate")
            if created_date:
                doc_created_at = format_date(created_date)
                # Ensure we have a datetime, not a string
                if isinstance(doc_created_at, str):
                    doc_created_at = datetime.fromisoformat(doc_created_at.replace("Z", "+00:00"))
            else:
                doc_created_at = None
                
            changed_date = fields.get("System.ChangedDate")
            if changed_date:
                doc_updated_at = format_date(changed_date)
                # Ensure we have a datetime, not a string
                if isinstance(doc_updated_at, str):
                    doc_updated_at = datetime.fromisoformat(doc_updated_at.replace("Z", "+00:00"))
            else:
                doc_updated_at = None
            
            # Build semantic identifier
            # Include resolution status in the semantic identifier for better visibility in citation displays
            semantic_identifier = f"{work_item_type} {work_item_id}: {title} [{resolution_status}]"
            
            # Extract primary owners
            primary_owners = []
            
            # Add creator if available
            creator = fields.get("System.CreatedBy")
            if creator:
                creator_info = {
                    "display_name": creator.get("displayName", ""),
                    "email": creator.get("uniqueName", "")
                }
                primary_owners.append(creator_info)
            
            # Add assignee if available and different from creator
            assignee = fields.get("System.AssignedTo")
            if assignee:
                assignee_email = assignee.get("uniqueName", "")
                if not any(owner.get("email") == assignee_email for owner in primary_owners):
                    assignee_info = {
                        "display_name": assignee.get("displayName", ""),
                        "email": assignee_email
                    }
                    primary_owners.append(assignee_info)
            
            # Create document
            return Document(
                id=f"azuredevops:{self.organization}/{self.project}/workitem/{work_item_id}",
                title=f"[{resolution_status}] {semantic_identifier}",
                semantic_identifier=semantic_identifier,
                sections=sections,
                metadata=metadata,
                source=DocumentSource.AZURE_DEVOPS,
                doc_created_at=doc_created_at,
                doc_updated_at=doc_updated_at,
                link=item_url,
                primary_owners=primary_owners if primary_owners else None
            )
            
        except Exception as e:
            logger.error(f"Failed to process work item {work_item.get('id')}: {str(e)}")
            return None

    def _determine_resolution_status(self, fields: Dict[str, Any]) -> str:
        """Determine the resolution status of a work item with confidence indicators.
        
        Args:
            fields: Dictionary of work item fields
            
        Returns:
            String indicating resolution status with confidence level when appropriate
        """
        state = fields.get("System.State", "").lower()
        resolution = fields.get("Microsoft.VSTS.Common.Resolution", "")
        resolved_date = fields.get("System.ResolvedDate")
        closed_date = fields.get("Microsoft.VSTS.Common.ClosedDate") or fields.get("System.ClosedDate")
        
        # Build a clear resolution status with a deterministic process
        
        # 1. Explicit resolution field has highest priority
        if resolution:
            return "Resolved"
        
        # 2. Explicit date fields have high priority
        if resolved_date:
            return "Resolved"
        elif closed_date:
            return "Closed"
        
        # 3. State-based determination
        resolved_states = ["resolved", "closed", "done", "completed", "fixed"]
        active_states = ["new", "active", "in progress", "to do", "open"]
        
        if state in resolved_states:
            return "Resolved"
        elif state in active_states:
            return "Not Resolved"
        
        # 4. If we can't determine status, be explicit about it
        return "Unknown"

    @override
    def load_from_checkpoint(
        self,
        start: SecondsSinceUnixEpoch,
        end: SecondsSinceUnixEpoch,
        checkpoint: AzureDevOpsConnectorCheckpoint,
    ) -> CheckpointOutput[AzureDevOpsConnectorCheckpoint]:
        """Load documents from Azure DevOps since the last checkpoint.
        
        Args:
            start: Start time as seconds since Unix epoch
            end: End time as seconds since Unix epoch
            checkpoint: Last checkpoint with continuation token
            
        Returns:
            Generator yielding Documents or ConnectorFailures and returning the new checkpoint
        """
        # Convert epoch seconds to datetime
        start_time = datetime.fromtimestamp(start, tz=timezone.utc)
        end_time = datetime.fromtimestamp(end, tz=timezone.utc)
        
        logger.info(f"Loading documents from {start_time.isoformat()} to {end_time.isoformat()}")
        logger.info(f"Checkpoint continuation token: {checkpoint.continuation_token}")
        logger.info(f"Content scope: {getattr(self, 'content_scope', 'Not set')}")
        logger.info(f"Configured data types: {self.data_types}")
        
        # Check if git commits are enabled
        if self.DATA_TYPE_COMMITS in self.data_types:
            logger.info("Git commits indexing is enabled")
        else:
            logger.warning("Git commits indexing is NOT enabled. If you want to index commits, set content_scope to 'everything' (or 'Everything') in the connector configuration.")
        
        # Make sure we have credentials
        if not self.personal_access_token:
            error_message = "Azure DevOps connector requires credentials to be loaded first"
            logger.error(error_message)
            raise ConnectorMissingCredentialError("Azure DevOps")
        
        # Track if we have a new continuation token
        new_continuation_token = None
        has_more = False
        
        # Process each data type
        for data_type in self.data_types:
            if data_type == self.DATA_TYPE_WORK_ITEMS:
                # Existing work items logic
                try:
                    # Get work items since the last checkpoint
                    work_items_response = self._get_work_items(
                        start_time=start_time,
                        continuation_token=checkpoint.continuation_token
                    )
                    
                    # Extract work item references from the response
                    work_item_refs = work_items_response.get("workItems", [])
                    logger.info(f"Found {len(work_item_refs)} work items")
                    
                    # Extract the continuation token for the next page
                    new_continuation_token = work_items_response.get("continuationToken")
                    
                    # Check if there are more results
                    has_more = bool(new_continuation_token and len(work_item_refs) == self.MAX_RESULTS_PER_PAGE)
                    
                    # Get detailed information for each work item in batches
                    for i in range(0, len(work_item_refs), self.MAX_BATCH_SIZE):
                        batch = work_item_refs[i:i + self.MAX_BATCH_SIZE]
                        batch_ids = [int(item["id"]) for item in batch]
                        
                        # Get detailed work item information
                        work_items = self._get_work_item_details(batch_ids)
                        
                        # Process each work item
                        for work_item in work_items:
                            work_item_id = work_item.get("id")
                            if not work_item_id:
                                continue
                            
                            try:
                                # Get comments if enabled
                                comments = None
                                if self.include_comments:
                                    comments = self._get_work_item_comments(work_item_id)
                                
                                # Process the work item into a Document
                                work_item_url = build_azure_devops_url(
                                    self.client_config.get("base_url", ""),
                                    str(work_item_id),
                                    "workitems"
                                )
                                logger.debug(f"Processing work item {work_item_id}: {work_item_url}")
                                
                                doc = self._process_work_item(work_item, comments)
                                if doc:
                                    # Yield the document instead of adding to a list
                                    yield doc
                                    
                                    # Cache the document for future use
                                    self._store_in_cache(work_item_id, doc)
                            except Exception as e:
                                logger.error(f"Failed to process work item {work_item_id}: {str(e)}")
                                # Yield the failure instead of adding to a list
                                yield DocumentFailure(
                                    document_id=f"azuredevops:{self.organization}/{self.project}/workitem/{work_item_id}",
                                    error=str(e)
                                )
                except requests.exceptions.RequestException as e:
                    # Handle API errors
                    error_detail = str(e)
                    retry_after = 0
                    
                    # Extract retry-after header if available
                    if hasattr(e, 'response') and e.response and 'Retry-After' in e.response.headers:
                        retry_after = int(e.response.headers['Retry-After'])
                        logger.warning(f"Rate limited by Azure DevOps API. Waiting for {retry_after} seconds.")
                    
                    logger.error(f"Failed to fetch work items: {error_detail}")
                    yield EntityFailure(entity_id="azure_devops_work_items")
                    
                    # Create a new checkpoint with the same continuation token
                    new_checkpoint = AzureDevOpsConnectorCheckpoint(
                        has_more=True,
                        continuation_token=checkpoint.continuation_token
                    )
                    # Must return the checkpoint, not yield it
                    return new_checkpoint
                    
                except Exception as e:
                    # Handle other errors
                    logger.error(f"Error fetching work items: {str(e)}")
                    yield EntityFailure(entity_id="azure_devops_work_items")
                    
                    # Create a new checkpoint with the same continuation token
                    new_checkpoint = AzureDevOpsConnectorCheckpoint(
                        has_more=True,
                        continuation_token=checkpoint.continuation_token
                    )
                    # Must return the checkpoint, not yield it
                    return new_checkpoint
                
            elif data_type == self.DATA_TYPE_COMMITS:
                # Process Git commits
                try:
                    # Get all repositories for the project
                    repositories = self._get_repositories()
                    
                    for repo in repositories:
                        repo_id = repo.get("id")
                        if not repo_id:
                            continue
                        
                        # Get commits for this repository
                        commits_response = self._get_commits(
                            repository_id=repo_id,
                            start_time=start_time
                        )
                        
                        # Process each commit
                        for commit in commits_response.get("value", []):
                            try:
                                doc = self._process_commit(commit, repo)
                                if doc:
                                    # Yield the document instead of adding to a list
                                    yield doc
                            except Exception as e:
                                commit_id = commit.get("commitId", "unknown")
                                logger.error(f"Failed to process commit {commit_id}: {str(e)}")
                                # Yield the failure instead of adding to a list
                                yield DocumentFailure(
                                    document_id=f"azuredevops:{self.organization}/{self.project}/git/{repo_id}/commit/{commit_id}",
                                    error=str(e)
                                )
                except Exception as e:
                    logger.error(f"Error fetching commits: {str(e)}")
                    yield DocumentFailure(
                        document_id=f"azuredevops:{self.organization}/{self.project}/git/commits",
                        error=str(e)
                    )
                    
            elif data_type == self.DATA_TYPE_TEST_RESULTS or data_type == self.DATA_TYPE_TEST_STATS:
                # Process test runs and results
                try:
                    # Get test runs
                    test_runs_response = self._get_test_runs(start_time=start_time)
                    
                    # Process each test run
                    for test_run in test_runs_response.get("value", []):
                        try:
                            # Include details only if TEST_RESULTS is requested
                            include_results = self.DATA_TYPE_TEST_RESULTS in self.data_types
                            doc = self._process_test_run(test_run, include_results=include_results)
                            if doc:
                                # Yield the document instead of adding to a list
                                yield doc
                        except Exception as e:
                            run_id = test_run.get("id", "unknown")
                            logger.error(f"Failed to process test run {run_id}: {str(e)}")
                            # Yield the failure instead of adding to a list
                            yield DocumentFailure(
                                document_id=f"azuredevops:{self.organization}/{self.project}/test/run/{run_id}",
                                error=str(e)
                            )
                except Exception as e:
                    logger.error(f"Error fetching test runs: {str(e)}")
                    yield DocumentFailure(
                        document_id=f"azuredevops:{self.organization}/{self.project}/test/runs",
                        error=str(e)
                    )
                    
            elif data_type == self.DATA_TYPE_RELEASES or data_type == self.DATA_TYPE_RELEASE_DETAILS:
                # Process releases
                try:
                    # Get releases
                    releases_response = self._get_releases(start_time=start_time)
                    
                    # Process each release
                    for release in releases_response.get("value", []):
                        try:
                            # Include details only if RELEASE_DETAILS is requested
                            include_details = self.DATA_TYPE_RELEASE_DETAILS in self.data_types
                            doc = self._process_release(release, include_details=include_details)
                            if doc:
                                # Yield the document instead of adding to a list
                                yield doc
                        except Exception as e:
                            release_id = release.get("id", "unknown")
                            logger.error(f"Failed to process release {release_id}: {str(e)}")
                            # Yield the failure instead of adding to a list
                            yield DocumentFailure(
                                document_id=f"azuredevops:{self.organization}/{self.project}/release/{release_id}",
                                error=str(e)
                            )
                except Exception as e:
                    logger.error(f"Error fetching releases: {str(e)}")
                    yield DocumentFailure(
                        document_id=f"azuredevops:{self.organization}/{self.project}/releases",
                        error=str(e)
                    )
                    
            elif data_type == self.DATA_TYPE_WIKIS:
                # Process wikis
                try:
                    # Get all wikis for the project
                    wikis = self._get_wikis()
                    
                    for wiki in wikis:
                        wiki_id = wiki.get("id")
                        if not wiki_id:
                            continue
                        
                        # Get all pages for this wiki
                        pages = self._get_wiki_pages(wiki_id)
                        
                        # Process each page
                        for page in pages:
                            try:
                                doc = self._process_wiki_page(wiki, page)
                                if doc:
                                    # Yield the document instead of adding to a list
                                    yield doc
                            except Exception as e:
                                page_path = page.get("path", "unknown")
                                logger.error(f"Failed to process wiki page {page_path}: {str(e)}")
                                # Yield the failure instead of adding to a list
                                yield DocumentFailure(
                                    document_id=f"azuredevops:{self.organization}/{self.project}/wiki/{wiki_id}/page{page_path}",
                                    error=str(e)
                                )
                except Exception as e:
                    logger.error(f"Error fetching wikis: {str(e)}")
                    yield DocumentFailure(
                        document_id=f"azuredevops:{self.organization}/{self.project}/wikis",
                        error=str(e)
                    )
        
        # Use continuation token only for work items, as other data types don't support pagination the same way
        has_more = bool(new_continuation_token) if new_continuation_token is not None else bool(checkpoint.continuation_token)
        
        logger.info(f"Finished processing documents with continuationToken: {new_continuation_token}")
        
        # Create new checkpoint with the updated continuation token
        new_checkpoint = AzureDevOpsConnectorCheckpoint(
            has_more=has_more,
            continuation_token=new_continuation_token if new_continuation_token is not None else checkpoint.continuation_token
        )
        
        # Return the final checkpoint (do not yield it)
        # CheckpointOutputWrapper will grab this returned value
        logger.info(f"Returning final checkpoint: has_more={has_more}, token={new_continuation_token}")
        return new_checkpoint

    @override
    def build_dummy_checkpoint(self) -> AzureDevOpsConnectorCheckpoint:
        """Build a dummy checkpoint for initial indexing.
        
        Returns:
            Dummy checkpoint
        """
        return AzureDevOpsConnectorCheckpoint(has_more=True, continuation_token=None)

    @override
    def validate_checkpoint_json(self, checkpoint_json: str) -> AzureDevOpsConnectorCheckpoint:
        """Validate and parse a checkpoint from JSON.
        
        Args:
            checkpoint_json: JSON string representing the checkpoint
            
        Returns:
            Checkpoint object
        """
        checkpoint_dict = json.loads(checkpoint_json)
        return AzureDevOpsConnectorCheckpoint(**checkpoint_dict)

    @override
    def retrieve_all_slim_documents(
        self,
        start: SecondsSinceUnixEpoch | None = None,
        end: SecondsSinceUnixEpoch | None = None,
        callback: IndexingHeartbeatInterface | None = None,
    ) -> GenerateSlimDocumentOutput:
        """Retrieve all slim documents from Azure DevOps.
        
        This implementation bypasses the checkpoint mechanism to process all documents in a single batch.
        It's primarily used for slim documents where we don't need to process full content.
        
        Args:
            start: Start time (epoch seconds), ignored as Azure DevOps has no time-based filtering for slim docs
            end: End time (epoch seconds), ignored as Azure DevOps has no time-based filtering for slim docs
            callback: Optional callback to report progress, ignored in this implementation
            
        Returns:
            Tuple of (slim documents, entity failures)
        """
        # Convert epoch seconds to datetime if provided
        start_time = datetime.fromtimestamp(start, tz=timezone.utc) if start else None
        end_time = datetime.fromtimestamp(end, tz=timezone.utc) if end else None
        
        # Make sure we have credentials
        if not self.personal_access_token:
            error_message = "Azure DevOps connector requires credentials to be loaded first"
            logger.error(error_message)
            raise ConnectorMissingCredentialError("Azure DevOps")
        
        slim_documents = []
        
        try:
            # Process each data type
            for data_type in self.data_types:
                if data_type == self.DATA_TYPE_WORK_ITEMS:
                    # Process work items (existing functionality)
                    work_items_response = self._get_work_items(
                        start_time=start_time,
                        max_results=MAX_RESULTS_PER_PAGE
                    )
                    
                    work_item_refs = work_items_response.get("workItems", [])
                    logger.info(f"Found {len(work_item_refs)} work items for slim documents")
                    
                    # Process work items in batches
                    for i in range(0, len(work_item_refs), MAX_BATCH_SIZE):
                        batch = work_item_refs[i:i + MAX_BATCH_SIZE]
                        batch_ids = [int(item["id"]) for item in batch]
                        
                        # Get detailed work item information
                        work_items = self._get_work_item_details(batch_ids)
                        
                        # Convert each work item to a slim document
                        for work_item in work_items:
                            work_item_id = work_item.get("id")
                            if not work_item_id:
                                continue
                            
                            fields = work_item.get("fields", {})
                            title = fields.get("System.Title", "")
                            work_item_type = fields.get("System.WorkItemType", "")
                            state = fields.get("System.State", "")
                            
                            # Build the URL for the work item
                            item_url = build_azure_devops_url(
                                self.client_config.get("base_url", ""),
                                str(work_item_id),
                                "workitems"
                            )
                            
                            # Determine updated time
                            updated_at = fields.get("System.ChangedDate")
                            updated_time = format_date(updated_at) if updated_at else None
                            
                            # Create slim document
                            slim_doc = SlimDocument(
                                id=f"azuredevops:{self.organization}/{self.project}/workitem/{work_item_id}",
                                title=f"{work_item_type}: {title}",
                                updated_at=updated_time,
                                link=item_url,
                                source=DocumentSource.AZURE_DEVOPS,
                            )
                            
                            slim_documents.append(slim_doc)
                
                elif data_type == self.DATA_TYPE_COMMITS:
                    # Process commits
                    repositories = self._get_repositories()
                    
                    for repo in repositories:
                        repo_id = repo.get("id")
                        repo_name = repo.get("name", "")
                        
                        if not repo_id:
                            continue
                        
                        # Get commits for this repository
                        commits_response = self._get_commits(
                            repository_id=repo_id,
                            start_time=start_time
                        )
                        
                        # Process each commit
                        for commit in commits_response.get("value", []):
                            commit_id = commit.get("commitId", "")
                            if not commit_id:
                                continue
                                
                            # Extract basic info
                            comment = commit.get("comment", "")
                            commit_time = commit.get("author", {}).get("date", "")
                            
                            # Get the commit URL
                            commit_url = commit.get("remoteUrl", "")
                            if not commit_url:
                                # Build fallback URL
                                commit_url = build_azure_devops_url(
                                    self.client_config.get("base_url", ""),
                                    commit_id,
                                    "git/commit"
                                )
                            
                            # Create slim document
                            first_line = comment.split('\n')[0][:50] if comment else ""
                            
                            # Special handling for build version numbers to prevent truncation
                            build_version_match = re.search(r'Build\s+(\d+\.\d+\.\d+)', first_line)
                            if build_version_match:
                                version_num = build_version_match.group(1)
                                # Ensure the version number isn't truncated
                                first_line = first_line.replace(version_num, f"{version_num}")
                                
                            slim_doc = SlimDocument(
                                id=f"azuredevops:{self.organization}/{self.project}/git/{repo_id}/commit/{commit_id}",
                                title=f"Commit {commit_id[:8]}: {first_line}",
                                updated_at=format_date(commit_time),
                                link=commit_url,
                                source=DocumentSource.AZURE_DEVOPS,
                                description=comment[:500] if comment else None,
                                perm_sync_data={
                                    "type": "commit",
                                    "repository_name": repo_name,
                                    "repository_id": repo_id,
                                    "commit_id": commit_id,
                                    "author_name": commit.get("author", {}).get("name", ""),
                                    "author_email": commit.get("author", {}).get("email", ""),
                                }
                            )
                            
                            # Add related work items to perm_sync_data if available
                            work_items = commit.get("workItems", [])
                            if work_items:
                                logger.info(f"Found {len(work_items)} related work items for commit {commit_id[:8]}")
                                work_item_ids = []
                                
                                for work_item in work_items:
                                    work_item_id = work_item.get("id")
                                    work_item_url = work_item.get("url", "")
                                    
                                    # Parse work item ID from URL if not provided directly
                                    if not work_item_id and work_item_url:
                                        # Extract ID from URL pattern like .../workitems/123?...
                                        match = re.search(r"/workitems/(\d+)", work_item_url, re.IGNORECASE)
                                        if match:
                                            work_item_id = match.group(1)
                                    
                                    if work_item_id:
                                        work_item_ids.append(str(work_item_id))
                                        logger.debug(f"Added work item ID: {work_item_id} to commit {commit_id[:8]}")
                                    else:
                                        logger.warning(f"Could not extract work item ID from URL: {work_item_url}")
                                
                                if work_item_ids:
                                    slim_doc.perm_sync_data["related_work_items"] = ",".join(work_item_ids)
                                    
                                    # Try to get first work item details for title enrichment
                                    try:
                                        first_work_item_id = int(work_item_ids[0])
                                        details = self._get_work_item_details([first_work_item_id])
                                        if details and details[0]:
                                            work_item_detail = details[0]
                                            work_item_type = work_item_detail.get("fields", {}).get("System.WorkItemType", "")
                                            work_item_title = work_item_detail.get("fields", {}).get("System.Title", "")
                                            
                                            if work_item_type and work_item_title:
                                                slim_doc.perm_sync_data["related_work_item_title"] = f"[{work_item_type}] #{first_work_item_id}: {work_item_title}"
                                                logger.info(f"Added work item details to commit {commit_id[:8]}: {work_item_type} #{first_work_item_id}: {work_item_title}")
                                    except Exception as e:
                                        logger.warning(f"Error enriching slim document with work item details: {str(e)}")
                            else:
                                # Try to extract work item references from commit message
                                # Look for patterns like "#123" or "AB#123" in commit messages
                                if comment:
                                    # Match common work item reference patterns
                                    wi_refs = re.findall(r'(?:AB)?#(\d+)', comment)
                                    if wi_refs:
                                        logger.info(f"Found {len(wi_refs)} work item references in commit message for {commit_id[:8]}")
                                        slim_doc.perm_sync_data["possible_work_items"] = ",".join(wi_refs)
                                        
                                        # Try to verify and use the work item references
                                        verified_refs = []
                                        for wi_ref in wi_refs[:3]:  # Limit to first 3 references to avoid excessive API calls
                                            try:
                                                ref_id = int(wi_ref)
                                                details = self._get_work_item_details([ref_id])
                                                if details and details[0]:
                                                    work_item_detail = details[0]
                                                    work_item_type = work_item_detail.get("fields", {}).get("System.WorkItemType", "")
                                                    work_item_title = work_item_detail.get("fields", {}).get("System.Title", "")
                                                    
                                                    if work_item_type and work_item_title:
                                                        verified_refs.append(str(ref_id))
                                                        # Use the first verified reference for the title enrichment
                                                        if not slim_doc.perm_sync_data.get("related_work_item_title"):
                                                            slim_doc.perm_sync_data["related_work_item_title"] = f"[{work_item_type}] #{ref_id}: {work_item_title}"
                                                            logger.info(f"Added work item from message reference to commit {commit_id[:8]}: {work_item_type} #{ref_id}")
                                            except Exception as e:
                                                logger.warning(f"Error verifying work item {wi_ref} from commit message: {str(e)}")
                                        
                                        if verified_refs:
                                            slim_doc.perm_sync_data["related_work_items"] = ",".join(verified_refs)
                                            logger.info(f"Added {len(verified_refs)} verified work items from message references to commit {commit_id[:8]}")
                            
                            # Add file changes data if available
                            changes = commit.get("changes", [])
                            if changes:
                                changed_files = []
                                for change in changes:
                                    item = change.get("item", {})
                                    path = item.get("path", "")
                                    if path:
                                        changed_files.append(path)
                                
                                if changed_files:
                                    # Add up to 5 files to perm_sync_data
                                    slim_doc.perm_sync_data["changed_files"] = "; ".join(changed_files[:5])
                                    if len(changed_files) > 5:
                                        slim_doc.perm_sync_data["changed_files"] += f"; +{len(changed_files) - 5} more"

                            slim_documents.append(slim_doc)
                
                elif data_type == self.DATA_TYPE_TEST_RESULTS or data_type == self.DATA_TYPE_TEST_STATS:
                    # Process test runs
                    test_runs_response = self._get_test_runs(start_time=start_time)
                    
                    # Process each test run
                    for test_run in test_runs_response.get("value", []):
                        run_id = test_run.get("id")
                        if not run_id:
                            continue
                            
                        # Extract basic info
                        name = test_run.get("name", "")
                        state = test_run.get("state", "")
                        completed_date = test_run.get("completedDate")
                        started_date = test_run.get("startedDate")
                        
                        # Get the test run URL
                        test_run_url = test_run.get("url", "")
                        if not test_run_url:
                            # Try web access URL
                            test_run_url = test_run.get("webAccessUrl", "")
                            if not test_run_url:
                                # Build fallback URL
                                test_run_url = build_azure_devops_url(
                                    self.client_config.get("base_url", ""),
                                    str(run_id),
                                    "test/runs"
                                )
                        
                        # Create slim document
                        slim_doc = SlimDocument(
                            id=f"azuredevops:{self.organization}/{self.project}/test/run/{run_id}",
                            title=f"Test Run: {name} ({state})",
                            updated_at=format_date(completed_date or started_date),
                            link=test_run_url,
                            source=DocumentSource.AZURE_DEVOPS,
                        )
                        
                        slim_documents.append(slim_doc)
                
                elif data_type == self.DATA_TYPE_RELEASES or data_type == self.DATA_TYPE_RELEASE_DETAILS:
                    # Process releases
                    releases_response = self._get_releases(start_time=start_time)
                    
                    # Process each release
                    for release in releases_response.get("value", []):
                        release_id = release.get("id")
                        if not release_id:
                            continue
                            
                        # Extract basic info
                        name = release.get("name", "")
                        status = release.get("status", "")
                        modified_date = release.get("modifiedOn")
                        
                        # Get the release URL
                        release_url = release.get("_links", {}).get("web", {}).get("href", "")
                        if not release_url:
                            # Build fallback URL
                            release_url = build_azure_devops_url(
                                self.client_config.get("base_url", ""),
                                str(release_id),
                                "release"
                            )
                        
                        # Create slim document
                        slim_doc = SlimDocument(
                            id=f"azuredevops:{self.organization}/{self.project}/release/{release_id}",
                            title=f"Release: {name} ({status})",
                            updated_at=format_date(modified_date),
                            link=release_url,
                            source=DocumentSource.AZURE_DEVOPS,
                        )
                        
                        slim_documents.append(slim_doc)
                
                elif data_type == self.DATA_TYPE_WIKIS:
                    # Process wikis
                    wikis = self._get_wikis()
                    
                    for wiki in wikis:
                        wiki_id = wiki.get("id")
                        wiki_name = wiki.get("name", "")
                        
                        if not wiki_id:
                            continue
                        
                        # Get all pages for this wiki
                        pages = self._get_wiki_pages(wiki_id)
                        
                        # Process each page
                        for page in pages:
                            page_path = page.get("path", "")
                            if not page_path:
                                continue
                                
                            # Get display name from path
                            page_display_name = page_path.split("/")[-1] if "/" in page_path else page_path
                            
                            # Get the page URL
                            page_url = page.get("remoteUrl", "")
                            if not page_url:
                                # Use wiki URL as base
                                page_url = wiki.get("remoteUrl", "")
                                if page_url and page_path:
                                    # Try to construct the URL for the specific page
                                    page_url = f"{page_url.rstrip('/')}/{page_path.lstrip('/')}"
                            
                            # Extract updated time
                            updated_at = page.get("lastModifiedDate") or page.get("lastUpdatedDate")
                            
                            # Create slim document
                            slim_doc = SlimDocument(
                                id=f"azuredevops:{self.organization}/{self.project}/wiki/{wiki_id}/page{page_path}",
                                title=f"Wiki: {wiki_name} - {page_display_name}",
                                updated_at=format_date(updated_at),
                                link=page_url,
                                source=DocumentSource.AZURE_DEVOPS,
                            )
                            
                            slim_documents.append(slim_doc)
            
            logger.info(f"Retrieved {len(slim_documents)} slim documents from Azure DevOps")
            return slim_documents, []
            
        except Exception as e:
            logger.error(f"Error retrieving slim documents from Azure DevOps: {str(e)}")
            return [], [EntityFailure(entity_id="azure_devops_connector", error=str(e))]

    def _get_cached_context(self, work_item_id: int) -> Optional[Document]:
        """Get cached context if available and not expired."""
        if work_item_id in self._context_cache:
            doc, timestamp = self._context_cache[work_item_id]
            if datetime.now() - timestamp < self._cache_ttl:
                # Ensure the doc has complete information
                if doc and doc.metadata and "resolution_status" in doc.metadata:
                    return doc
        return None

    def _store_in_cache(self, work_item_id: int, document: Document) -> None:
        """Store a document in the cache.
        
        Args:
            work_item_id: The ID of the work item
            document: The document to store in the cache
        """
        if document and document.metadata:
            # Verify document has all necessary metadata before caching
            self._context_cache[work_item_id] = (document, datetime.now())

    def fetch_additional_context(self, work_item_id: int, force_refresh: bool = False) -> Optional[Document]:
        """Fetch additional context for a work item.

        Args:
            work_item_id: The ID of the work item to fetch context for.
            force_refresh: If True, bypass cache and fetch fresh data.

        Returns:
            Document object if successful, None otherwise.
        """
        try:
            # Check cache unless force refresh is requested
            if not force_refresh:
                cached_doc = self._get_cached_context(work_item_id)
                if cached_doc:
                    logger.info(f"Using cached context for work item {work_item_id}")
                    return cached_doc

            # Fetch work item details with all necessary fields
            logger.info(f"Fetching fresh context for work item {work_item_id}")
            work_items = self._get_work_item_details([work_item_id])
            if not work_items:
                logger.warning(f"No work item found for ID {work_item_id}")
                return None

            work_item = work_items[0]  # We only requested one item
            
            # Ensure work item has _links or a fallback URL
            if not work_item.get("_links", {}).get("html", {}).get("href"):
                # Build URL for the work item as fallback
                base_url = self.client_config.get("base_url", "")
                item_url = build_azure_devops_url(
                    base_url, 
                    str(work_item_id), 
                    "workitems"
                )
                # Add the URL to the work item data
                if "_links" not in work_item:
                    work_item["_links"] = {}
                if "html" not in work_item["_links"]:
                    work_item["_links"]["html"] = {}
                work_item["_links"]["html"]["href"] = item_url
            
            # Fetch comments if enabled
            comments = []
            if self.include_comments:
                comments = self._get_work_item_comments(work_item_id)

            # Create document from work item
            document = self._process_work_item(work_item, comments)
            
            if document:
                # Only cache if not force refresh
                if not force_refresh:
                    self._store_in_cache(work_item_id, document)
                
                logger.info(f"Successfully fetched context for work item {work_item_id}")
                return document
            else:
                logger.warning(f"Failed to process work item {work_item_id} into Document")

        except Exception as e:
            logger.error(f"Failed to fetch fresh context for work item {work_item_id}: {str(e)}")
            # Add additional error details
            logger.error(f"Error details: {type(e).__name__} - {str(e)}")
            return None

        return None

    def fetch_additional_context_batch(self, work_item_ids: List[int]) -> List[Document]:
        """Fetch additional context for multiple work items in parallel.

        Args:
            work_item_ids: List of work item IDs to fetch context for.

        Returns:
            List of Document objects.
        """
        try:
            # First check cache for all work items
            documents = []
            uncached_ids = []

            for work_item_id in work_item_ids:
                cached_doc = self._get_cached_context(work_item_id)
                if cached_doc:
                    documents.append(cached_doc)
                else:
                    uncached_ids.append(work_item_id)

            if uncached_ids:
                logger.info(f"Fetching fresh context for {len(uncached_ids)} work items")
                # Fetch work item details
                work_items = self._get_work_item_details(uncached_ids)
                
                # Create a mapping from work item ID to work item for easier lookup
                work_item_map = {item.get("id"): item for item in work_items}
                
                # Ensure all work items have _links or fallback URLs
                for work_item_id, work_item in work_item_map.items():
                    if not work_item.get("_links", {}).get("html", {}).get("href"):
                        # Build URL for the work item as fallback
                        base_url = self.client_config.get("base_url", f"https://dev.azure.com/{self.organization}/{self.project}")
                        item_url = build_azure_devops_url(
                            base_url, 
                            str(work_item_id), 
                            "workitems"
                        )
                        # Add the URL to the work item data
                        if "_links" not in work_item:
                            work_item["_links"] = {}
                        if "html" not in work_item["_links"]:
                            work_item["_links"]["html"] = {}
                        work_item["_links"]["html"]["href"] = item_url
                
                # Fetch comments in parallel if enabled
                comments_map = {}
                if self.include_comments:
                    with ThreadPoolExecutor() as executor:
                        comment_futures = {
                            executor.submit(self._get_work_item_comments, wid): wid 
                            for wid in uncached_ids
                        }
                        for future in comment_futures:
                            work_item_id = comment_futures[future]
                            try:
                                comments_map[work_item_id] = future.result()
                            except Exception as e:
                                logger.error(f"Failed to fetch comments for work item {work_item_id}: {str(e)}")
                                comments_map[work_item_id] = []

                # Process work items
                for work_item_id in uncached_ids:
                    if work_item_id in work_item_map:
                        work_item = work_item_map[work_item_id]
                        comments = comments_map.get(work_item_id, []) if self.include_comments else None
                        document = self._process_work_item(work_item, comments)
                        
                        if document:
                            self._store_in_cache(work_item_id, document)
                            documents.append(document)
                        else:
                            logger.warning(f"Failed to process work item {work_item_id} into Document")
                    else:
                        logger.warning(f"Work item {work_item_id} not found in API response")

            logger.info(f"Returned {len(documents)} documents from fetch_additional_context_batch")
            return documents

        except Exception as e:
            logger.error(f"Failed to fetch fresh context for work items {work_item_ids}: {str(e)}")
            # Add additional error details for better debugging
            logger.error(f"Error details: {type(e).__name__} - {str(e)}")
            return []

    def _get_repositories(self) -> List[Dict[str, Any]]:
        """Get all repositories for the project.
        
        Returns:
            List of repository dictionaries
        """
        # Check cache first
        if self._repository_cache:
            logger.debug("Using cached repositories")
            return list(self._repository_cache.values())
        
        logger.info(f"Fetching Git repositories for organization: {self.organization}, project: {self.project}")
        
        try:
            response = self._make_api_request(
                "_apis/git/repositories",
                params={"includeLinks": "true"}
            )
            
            # Log the response status
            status_code = response.status_code
            logger.debug(f"Repository API response status code: {status_code}")
            
            if status_code != 200:
                logger.warning(f"Non-200 response from repository API: {status_code}")
                # Try to extract error message if possible
                try:
                    error_msg = response.json()
                    logger.warning(f"API Error response: {error_msg}")
                except Exception:
                    logger.warning(f"Raw error response: {response.text[:200]}")
            
            response.raise_for_status()
            
            repositories = response.json().get("value", [])
            
            # Log repository info for debugging
            for repo in repositories:
                repo_name = repo.get("name", "unnamed")
                repo_id = repo.get("id", "no-id")
                logger.debug(f"Found repository: {repo_name} (ID: {repo_id})")
            
            # Filter repositories if specific ones were requested
            if self.repositories:
                filtered_repositories = []
                for repo in repositories:
                    if repo.get("name") in self.repositories:
                        filtered_repositories.append(repo)
                repositories = filtered_repositories
                logger.info(f"Filtered to {len(repositories)} repositories based on configuration")
            
            # Cache the repositories by ID for later use
            for repo in repositories:
                self._repository_cache[repo.get("id")] = repo
            
            if not repositories:
                logger.warning("No repositories found. This could be due to insufficient permissions (PAT needs 'Code (Read)') or there are no repositories in the project.")
            else:
                logger.info(f"Found {len(repositories)} Git repositories in project")
            
            return repositories
        except requests.exceptions.RequestException as e:
            error_detail = str(e)
            if hasattr(e, 'response') and e.response:
                status_code = e.response.status_code
                logger.error(f"Repository API failed with status code: {status_code}")
                
                if status_code == 401 or status_code == 403:
                    logger.error("Permission denied when accessing Git repositories. Ensure your PAT has 'Code (Read)' permission.")
                elif status_code == 404:
                    logger.error(f"Project {self.project} not found or has no Git repositories.")
                
                # Try to extract error details
                try:
                    error_content = e.response.json()
                    logger.error(f"Error details: {error_content}")
                except Exception:
                    if e.response.content:
                        logger.error(f"Error response: {e.response.content.decode('utf-8', errors='ignore')[:200]}")
            
            logger.warning(f"Failed to get repositories: {error_detail}")
            return []

    def _get_commits(
        self, 
        repository_id: str,
        start_time: Optional[datetime] = None,
        continuation_token: Optional[str] = None,
        max_results: int = MAX_RESULTS_PER_PAGE
    ) -> Dict[str, Any]:
        """Get commits from a repository.
        
        Args:
            repository_id: ID of the repository
            start_time: Only return commits after this time
            continuation_token: Token for pagination
            max_results: Maximum number of results to return
            
        Returns:
            API response containing commits
        """
        # Get repository name for better logging
        repo_name = "unknown"
        if repository_id in self._repository_cache:
            repo_name = self._repository_cache[repository_id].get("name", "unknown")
        
        logger.debug(f"Fetching commits for repository: {repo_name} (ID: {repository_id})")
        
        params = {
            # Removed hardcoded master branch filter to work with all branches
            # "searchCriteria.itemVersion.version": "master",  # This was causing 404 errors when the branch doesn't exist
            "$top": max_results,
            # Include changes and work items in the response - explicitly set these to true
            "searchCriteria.includeWorkItems": "true",
            "searchCriteria.includeDetails": "true",
            "$orderby": "author/date desc"  # Sort by newest first
        }
        
        # Add time filter if specified
        if start_time:
            # Format date for API
            formatted_date = start_time.strftime("%Y-%m-%dT%H:%M:%SZ")
            params["searchCriteria.fromDate"] = formatted_date
            logger.debug(f"Using time filter: {formatted_date}")
        
        # Add continuation token if specified
        if continuation_token:
            params["continuationToken"] = continuation_token
        
        logger.debug(f"Commit API parameters: {params}")
        
        # Try to fetch commits
        try:
            response = self._make_api_request(
                f"_apis/git/repositories/{repository_id}/commits",
                params=params
            )
            response.raise_for_status()
            
            result = response.json()
            
            # Get commit count
            commits_count = len(result.get("value", []))
            
            if commits_count == 0:
                logger.info(f"No commits found in repository {repo_name} (ID: {repository_id}). This could be due to an empty repository or the time filter.")
            else:
                logger.info(f"Found {commits_count} commits in repository {repo_name} (ID: {repository_id})")
                
                # Log commit details for debugging
                if logger.isEnabledFor(logging.DEBUG):
                    commits = result.get("value", [])
                    for i, commit in enumerate(commits[:5]):  # Log first 5 commits
                        commit_id = commit.get("commitId", "")[:8]
                        author = commit.get("author", {}).get("name", "unknown")
                        date = commit.get("author", {}).get("date", "")
                        message = commit.get("comment", "")
                        if message and len(message) > 50:
                            message = message[:47] + "..."
                        work_items = commit.get("workItems", [])
                        work_item_count = len(work_items)
                        logger.debug(f"Commit {i+1}: ID={commit_id}, Author={author}, Date={date}, Message={message}, Work Items={work_item_count}")
                        
                        # Log work item details if any
                        if work_item_count > 0 and logger.isEnabledFor(logging.DEBUG):
                            for j, work_item in enumerate(work_items[:3]):  # Log first 3 work items
                                wi_id = work_item.get("id")
                                wi_url = work_item.get("url", "")
                                logger.debug(f"  - Work Item {j+1}: ID={wi_id}, URL={wi_url}")
            
            return result
        except requests.exceptions.RequestException as e:
            error_detail = str(e)
            if hasattr(e, 'response') and e.response:
                status_code = e.response.status_code
                logger.error(f"Commits API failed with status code: {status_code}")
                
                if status_code == 401 or status_code == 403:
                    logger.error("Permission denied when accessing Git commits. Ensure your PAT has 'Code (Read)' permission.")
                elif status_code == 404:
                    logger.error(f"Repository {repo_name} (ID: {repository_id}) not found or API endpoint has changed.")
                
                # Try to extract error details
                try:
                    error_content = e.response.json()
                    logger.error(f"Error details: {error_content}")
                except Exception:
                    if e.response.content:
                        logger.error(f"Error response: {e.response.content.decode('utf-8', errors='ignore')[:200]}")
            
            logger.warning(f"Failed to get commits for repository {repo_name} (ID: {repository_id}): {error_detail}")
            return {"value": []}

    def _process_commit(self, commit: Dict[str, Any], repository: Dict[str, Any]) -> Optional[Document]:
        """Process a commit into a Document object.
        
        Args:
            commit: Commit data from Azure DevOps
            repository: Repository data
            
        Returns:
            Document object if successful, None otherwise
        """
        try:
            commit_id = commit.get("commitId", "")
            if not commit_id:
                return None
                
            repo_name = repository.get("name", "")
            repo_id = repository.get("id", "")
            
            # Extract basic fields
            author_name = commit.get("author", {}).get("name", "")
            author_email = commit.get("author", {}).get("email", "")
            comment = commit.get("comment", "")
            commit_time = commit.get("author", {}).get("date", "")
            
            # Get the commit URL
            commit_url = commit.get("remoteUrl", "")
            if not commit_url:
                # Build fallback URL
                commit_url = build_azure_devops_url(
                    self.client_config.get("base_url", ""),
                    commit_id,
                    "git/commit"
                )
            
            # Create sections
            sections = []
            
            # Build content with structured information
            content_parts = []
            content_parts.append(f"Commit: {commit_id[:8]}")
            content_parts.append(f"Repository: {repo_name}")
            
            if author_name:
                content_parts.append(f"Author: {author_name} <{author_email}>")
            
            if commit_time:
                formatted_date = format_date(commit_time)
                if formatted_date:
                    content_parts.append(f"Date: {formatted_date.isoformat()}")
            
            if comment:
                content_parts.append(f"\nCommit Message:\n{comment}")
            
            # Add changes if available
            changes = commit.get("changes", [])
            if changes:
                changes_text = []
                for change in changes:
                    item = change.get("item", {})
                    path = item.get("path", "")
                    change_type = change.get("changeType", "")
                    if path and change_type:
                        changes_text.append(f"{change_type}: {path}")
                
                if changes_text:
                    content_parts.append(f"\nChanges:\n" + "\n".join(changes_text))
            
            # Add work items if available
            work_items = commit.get("workItems", [])
            if work_items:
                work_items_text = []
                work_items_ids = []
                
                for work_item in work_items:
                    work_item_id = work_item.get("id")
                    work_item_url = work_item.get("url", "")
                    
                    # Parse work item ID from URL if not provided directly
                    if not work_item_id and work_item_url:
                        # Extract ID from URL pattern like .../workitems/123?...
                        match = re.search(r"/workitems/(\d+)", work_item_url, re.IGNORECASE)
                        if match:
                            work_item_id = match.group(1)
                    
                    if work_item_id:
                        work_items_ids.append(str(work_item_id))
                        
                        # Try to get work item details for richer information
                        try:
                            details = self._get_work_item_details([int(work_item_id)])
                            if details and details[0]:
                                work_item_detail = details[0]
                                work_item_type = work_item_detail.get("fields", {}).get("System.WorkItemType", "")
                                work_item_title = work_item_detail.get("fields", {}).get("System.Title", "")
                                work_item_state = work_item_detail.get("fields", {}).get("System.State", "")
                                
                                if work_item_type and work_item_title:
                                    work_items_text.append(f"[{work_item_type}] #{work_item_id}: {work_item_title} ({work_item_state})")
                                else:
                                    work_items_text.append(f"Work Item #{work_item_id}")
                            else:
                                work_items_text.append(f"Work Item #{work_item_id}")
                        except Exception as e:
                            logger.warning(f"Error fetching work item {work_item_id} details: {str(e)}")
                            work_items_text.append(f"Work Item #{work_item_id}")
                
                if work_items_text:
                    content_parts.append(f"\nRelated Work Items:\n" + "\n".join(work_items_text))
            
            sections.append(TextSection(
                text="\n".join(content_parts),
                link=commit_url
            ))
            
            # Create metadata
            metadata = {
                "type": "commit",
                "repository_name": repo_name,
                "repository_id": repo_id,
                "commit_id": commit_id,
                "author_name": author_name,
                "author_email": author_email,
                "commit_url": commit_url,
            }
            
            # Add work item IDs to metadata
            if work_items:
                work_item_ids = []
                for work_item in work_items:
                    work_item_id = work_item.get("id")
                    if not work_item_id and "url" in work_item:
                        # Extract ID from URL pattern
                        match = re.search(r"/workitems/(\d+)", work_item.get("url", ""), re.IGNORECASE)
                        if match:
                            work_item_id = match.group(1)
                    
                    if work_item_id:
                        work_item_ids.append(str(work_item_id))
                
                if work_item_ids:
                    metadata["related_work_items"] = ",".join(work_item_ids)
            
            # Add detailed changes metadata
            if changes:
                changed_files = []
                for change in changes:
                    item = change.get("item", {})
                    path = item.get("path", "")
                    if path:
                        changed_files.append(path)
                
                if changed_files:
                    # Add up to 5 files to metadata
                    metadata["changed_files"] = "; ".join(changed_files[:5])
                    if len(changed_files) > 5:
                        metadata["changed_files"] += f"; +{len(changed_files) - 5} more"
                    
                    # Count files by extension
                    extensions = {}
                    for file in changed_files:
                        ext = os.path.splitext(file)[1].lower()
                        if ext:
                            extensions[ext] = extensions.get(ext, 0) + 1
                        else:
                            extensions["no_extension"] = extensions.get("no_extension", 0) + 1
                    
                    if extensions:
                        metadata["file_extensions"] = "; ".join([f"{ext}: {count}" for ext, count in extensions.items()])
            
            # Extract dates
            if commit_time:
                commit_date = format_date(commit_time)
                if commit_date:
                    metadata["commit_date"] = commit_date.isoformat()
            
            # Create semantic identifier for the commit
            semantic_id = f"Commit {commit_id[:8]}"
            if comment:
                # Add the first line of the commit message to the semantic identifier
                first_line = comment.split('\n')[0].strip()
                if first_line:
                    semantic_id = f"{semantic_id}: {first_line}"
            
            # Build document
            first_line_title = comment.split('\n')[0][:50] if comment else ""
            
            # Special handling for build version numbers to prevent truncation
            build_version_match = re.search(r'Build\s+(\d+\.\d+\.\d+)', first_line_title)
            if build_version_match:
                version_num = build_version_match.group(1)
                # Ensure the version number isn't truncated in the title
                first_line_title = first_line_title.replace(version_num, f"{version_num}")
            
            # If we have work items from the API, also check commit message for additional references
            if work_items and comment:
                # Check if we already have work_items_ids defined
                if 'work_items_ids' in locals() and work_items_ids:
                    # Extract work item references from commit message to add to existing ones
                    wi_refs = re.findall(r'(?:AB)?#(\d+)', comment)
                    for wi_ref in wi_refs:
                        if wi_ref not in work_items_ids:
                            try:
                                # Try to verify the work item exists
                                ref_id = int(wi_ref)
                                details = self._get_work_item_details([ref_id])
                                if details and details[0]:
                                    work_item_detail = details[0]
                                    work_item_type = work_item_detail.get("fields", {}).get("System.WorkItemType", "")
                                    work_item_title = work_item_detail.get("fields", {}).get("System.Title", "")
                                    work_item_state = work_item_detail.get("fields", {}).get("System.State", "")
                                    
                                    if work_item_type and work_item_title:
                                        work_items_text.append(f"[{work_item_type}] #{ref_id}: {work_item_title} ({work_item_state})")
                                        work_items_ids.append(str(ref_id))
                                        logger.info(f"Added work item from commit message reference: {work_item_type} #{ref_id}")
                            except Exception as e:
                                logger.warning(f"Error verifying work item from commit message reference: {str(e)}")
            # No work items from API, try to extract from commit message 
            elif not work_items and comment:
                # Extract work item references from commit message when no API work items are provided
                wi_refs = re.findall(r'(?:AB)?#(\d+)', comment)
                if wi_refs:
                    logger.info(f"No linked work items for commit {commit_id[:8]}, but found {len(wi_refs)} references in commit message")
                    
                    # Store these as potential work items in metadata for visibility
                    metadata["possible_work_items"] = ",".join(wi_refs)
                    
                    # Check first reference to see if it's valid
                    try:
                        message_work_items_text = []
                        message_work_items_ids = []
                        
                        for wi_ref in wi_refs[:3]:  # Limit to first 3 references to avoid excessive API calls
                            ref_id = int(wi_ref)
                            details = self._get_work_item_details([ref_id])
                            if details and details[0]:
                                work_item_detail = details[0]
                                work_item_type = work_item_detail.get("fields", {}).get("System.WorkItemType", "")
                                work_item_title = work_item_detail.get("fields", {}).get("System.Title", "")
                                work_item_state = work_item_detail.get("fields", {}).get("System.State", "")
                                
                                if work_item_type and work_item_title:
                                    message_work_items_text.append(f"[{work_item_type}] #{ref_id}: {work_item_title} ({work_item_state})")
                                    message_work_items_ids.append(str(ref_id))
                                    logger.info(f"Verified work item from commit message: {work_item_type} #{ref_id}")
                        
                        if message_work_items_text:
                            content_parts.append(f"\nPossible Related Work Items (from commit message):\n" + "\n".join(message_work_items_text))
                            metadata["related_work_items"] = ",".join(message_work_items_ids)
                    except Exception as e:
                        logger.warning(f"Error verifying work item from commit message: {str(e)}")
            
            return Document(
                id=f"azuredevops:{self.organization}/{self.project}/git/{repo_id}/commit/{commit_id}",
                title=f"Commit {commit_id[:8]}: {first_line_title}",
                semantic_identifier=semantic_id,
                doc_updated_at=format_date(commit_time) if commit_time else None,
                created_at=format_date(commit_time) if commit_time else None,
                updated_at=format_date(commit_time) if commit_time else None,
                sections=sections,
                source=DocumentSource.AZURE_DEVOPS,
                metadata=metadata,
                resolved=True  # Commits are always considered "resolved"
            )
        except Exception as e:
            logger.error(f"Error processing commit {commit.get('commitId', 'unknown')}: {str(e)}")
            return None

    def _get_test_runs(
        self,
        start_time: Optional[datetime] = None,
        max_results: int = MAX_RESULTS_PER_PAGE
    ) -> Dict[str, Any]:
        """Get test runs from Azure DevOps.
        
        Args:
            start_time: Only return test runs after this time
            max_results: Maximum number of results to return
            
        Returns:
            API response containing test runs
        """
        params = {
            "$top": max_results
        }
        
        # Add time filter if specified
        if start_time:
            # Format date for API
            formatted_date = start_time.strftime("%Y-%m-%dT%H:%M:%SZ")
            params["minLastUpdatedDate"] = formatted_date
        
        try:
            response = self._make_api_request("_apis/test/runs", params=params)
            response.raise_for_status()
            
            result = response.json()
            run_count = len(result.get("value", []))
            logger.info(f"Found {run_count} test runs in project")
            return result
        except requests.exceptions.RequestException as e:
            logger.warning(f"Failed to get test runs: {str(e)}")
            return {"value": []}
    
    def _get_test_results(self, run_id: int) -> Dict[str, Any]:
        """Get test results for a specific test run.
        
        Args:
            run_id: ID of the test run
            
        Returns:
            API response containing test results
        """
        try:
            response = self._make_api_request(f"_apis/test/runs/{run_id}/results")
            response.raise_for_status()
            
            result = response.json()
            result_count = len(result.get("value", []))
            logger.info(f"Found {result_count} test results for run {run_id}")
            return result
        except requests.exceptions.RequestException as e:
            logger.warning(f"Failed to get test results for run {run_id}: {str(e)}")
            return {"value": []}
    
    def _get_test_run_statistics(self, run_id: int) -> Dict[str, Any]:
        """Get statistics for a specific test run.
        
        Args:
            run_id: ID of the test run
            
        Returns:
            API response containing test run statistics
        """
        try:
            response = self._make_api_request(f"_apis/test/runs/{run_id}/statistics")
            response.raise_for_status()
            
            result = response.json()
            logger.info(f"Retrieved test run statistics for run {run_id}")
            return result
        except requests.exceptions.RequestException as e:
            logger.warning(f"Failed to get test run statistics for run {run_id}: {str(e)}")
            return {}
    
    def _process_test_run(self, test_run: Dict[str, Any], include_results: bool = True) -> Optional[Document]:
        """Process a test run into a Document object.
        
        Args:
            test_run: Test run data from Azure DevOps
            include_results: Whether to include detailed test results
            
        Returns:
            Document object if successful, None otherwise
        """
        try:
            run_id = test_run.get("id")
            if not run_id:
                return None
            
            # Extract basic fields
            name = test_run.get("name", "")
            state = test_run.get("state", "")
            started_date = test_run.get("startedDate")
            completed_date = test_run.get("completedDate")
            build_name = test_run.get("buildConfiguration", {}).get("name", "")
            release_name = test_run.get("releaseEnvironment", {}).get("name", "")
            
            # Get the test run URL
            test_run_url = test_run.get("url", "")
            if not test_run_url:
                # Build fallback URL
                web_url = test_run.get("webAccessUrl", "")
                if web_url:
                    test_run_url = web_url
                else:
                    test_run_url = build_azure_devops_url(
                        self.client_config.get("base_url", ""),
                        str(run_id),
                        "test/runs"
                    )
            
            # Get statistics for the test run
            statistics = self._get_test_run_statistics(run_id)
            
            # Format statistics for display
            stats_summary = []
            if statistics:
                for result_state, count in statistics.items():
                    if isinstance(count, int) and count > 0 and not result_state.startswith("@"):
                        stats_summary.append(f"{result_state}: {count}")
            
            # Create sections
            sections = []
            
            # Build content with structured information
            content_parts = []
            content_parts.append(f"Test Run: {name}")
            content_parts.append(f"State: {state}")
            
            if build_name:
                content_parts.append(f"Build: {build_name}")
            
            if release_name:
                content_parts.append(f"Release: {release_name}")
            
            if started_date:
                formatted_start = format_date(started_date)
                if formatted_start:
                    content_parts.append(f"Started: {formatted_start.isoformat()}")
            
            if completed_date:
                formatted_end = format_date(completed_date)
                if formatted_end:
                    content_parts.append(f"Completed: {formatted_end.isoformat()}")
            
            if stats_summary:
                content_parts.append(f"\nResults Summary:\n" + "\n".join(stats_summary))
            
            # Include detailed test results if requested
            if include_results:
                results = self._get_test_results(run_id).get("value", [])
                if results:
                    content_parts.append("\nDetailed Test Results:")
                    for result in results[:50]:  # Limit to first 50 results to avoid too much data
                        test_name = result.get("testCase", {}).get("name", "") or result.get("testCaseTitle", "")
                        test_outcome = result.get("outcome", "")
                        content_parts.append(f"- {test_name}: {test_outcome}")
                    
                    if len(results) > 50:
                        content_parts.append(f"... and {len(results) - 50} more tests")
            
            sections.append(TextSection(
                text="\n".join(content_parts),
                link=test_run_url
            ))
            
            # Create metadata
            metadata = {
                "type": "test_run",
                "run_id": str(run_id),
                "name": name,
                "state": state,
                "build_name": build_name,
                "release_name": release_name,
                "test_run_url": test_run_url,
            }
            
            # Add statistics to metadata
            if statistics:
                for key, value in statistics.items():
                    if not key.startswith("@") and isinstance(value, (int, str, bool)):
                        metadata[f"stats_{key}"] = str(value)
            
            # Extract dates
            if started_date:
                start_date = format_date(started_date)
                if start_date:
                    metadata["started_date"] = start_date.isoformat()
            
            if completed_date:
                end_date = format_date(completed_date)
                if end_date:
                    metadata["completed_date"] = end_date.isoformat()
            
            # Create semantic identifier
            semantic_id = f"Test Run: {name}"
            if state:
                semantic_id += f" [{state}]"
            
            # Build document
            return Document(
                id=f"azuredevops:{self.organization}/{self.project}/test/run/{run_id}",
                title=f"Test Run: {name}",
                semantic_identifier=semantic_id,
                doc_updated_at=format_date(completed_date or started_date),
                created_at=format_date(started_date),
                updated_at=format_date(completed_date),
                sections=sections,
                source=DocumentSource.AZURE_DEVOPS,
                metadata=metadata,
                resolved=state.lower() in ("completed", "done", "finished", "closed")
            )
        except Exception as e:
            logger.error(f"Error processing test run {test_run.get('id', 'unknown')}: {str(e)}")
            return None

    def _get_releases(
        self,
        start_time: Optional[datetime] = None,
        max_results: int = MAX_RESULTS_PER_PAGE
    ) -> Dict[str, Any]:
        """Get releases from Azure DevOps.
        
        Args:
            start_time: Only return releases after this time
            max_results: Maximum number of results to return
            
        Returns:
            API response containing releases
        """
        params = {
            "$top": max_results
        }
        
        # Add time filter if specified
        if start_time:
            # Format date for API
            formatted_date = start_time.strftime("%Y-%m-%dT%H:%M:%SZ")
            params["minCreatedTime"] = formatted_date
        
        try:
            response = self._make_api_request("_apis/release/releases", params=params)
            response.raise_for_status()
            
            result = response.json()
            release_count = len(result.get("value", []))
            logger.info(f"Found {release_count} releases in project")
            return result
        except requests.exceptions.RequestException as e:
            logger.warning(f"Failed to get releases: {str(e)}")
            return {"value": []}
    
    def _get_release_details(self, release_id: int) -> Dict[str, Any]:
        """Get detailed information for a specific release.
        
        Args:
            release_id: ID of the release
            
        Returns:
            API response containing release details
        """
        try:
            response = self._make_api_request(f"_apis/release/releases/{release_id}")
            response.raise_for_status()
            
            result = response.json()
            logger.info(f"Retrieved release details for release {release_id}")
            return result
        except requests.exceptions.RequestException as e:
            logger.warning(f"Failed to get release details for release {release_id}: {str(e)}")
            return {}
    
    def _process_release(self, release: Dict[str, Any], include_details: bool = True) -> Optional[Document]:
        """Process a release into a Document object.
        
        Args:
            release: Release data from Azure DevOps
            include_details: Whether to include detailed release information
            
        Returns:
            Document object if successful, None otherwise
        """
        try:
            release_id = release.get("id")
            if not release_id:
                return None
            
            # Extract basic fields
            name = release.get("name", "")
            status = release.get("status", "")
            created_by_name = release.get("createdBy", {}).get("displayName", "")
            created_date = release.get("createdOn")
            modified_date = release.get("modifiedOn")
            
            # Get the release URL
            release_url = release.get("_links", {}).get("web", {}).get("href", "")
            if not release_url:
                release_url = build_azure_devops_url(
                    self.client_config.get("base_url", ""),
                    str(release_id),
                    "release"
                )
            
            # Get detailed release information if requested
            release_details = {}
            if include_details:
                release_details = self._get_release_details(release_id)
            
            # Create sections
            sections = []
            
            # Build content with structured information
            content_parts = []
            content_parts.append(f"Release: {name}")
            content_parts.append(f"Status: {status}")
            
            if created_by_name:
                content_parts.append(f"Created By: {created_by_name}")
            
            if created_date:
                formatted_date = format_date(created_date)
                if formatted_date:
                    content_parts.append(f"Created: {formatted_date.isoformat()}")
            
            # Include release definition information if available
            definition_name = release.get("releaseDefinition", {}).get("name", "")
            if definition_name:
                content_parts.append(f"Definition: {definition_name}")
            
            # Include environments information
            environments = release.get("environments", [])
            if environments:
                content_parts.append("\nEnvironments:")
                
                for env in environments:
                    env_name = env.get("name", "")
                    env_status = env.get("status", "")
                    env_deployed_date = env.get("deploySteps", [{}])[-1].get("deploymentJob", {}).get("finishTime", "")
                    
                    env_line = f"- {env_name}: {env_status}"
                    if env_deployed_date:
                        formatted_env_date = format_date(env_deployed_date)
                        if formatted_env_date:
                            env_line += f" (Deployed: {formatted_env_date.isoformat()})"
                    
                    content_parts.append(env_line)
            
            # Include artifacts information if available
            artifacts = release.get("artifacts", [])
            if artifacts:
                content_parts.append("\nArtifacts:")
                
                for artifact in artifacts:
                    artifact_type = artifact.get("type", "")
                    artifact_name = artifact.get("definitionReference", {}).get("name", {}).get("name", "")
                    artifact_version = artifact.get("definitionReference", {}).get("version", {}).get("name", "")
                    
                    if artifact_name:
                        artifact_line = f"- {artifact_name}"
                        if artifact_version:
                            artifact_line += f" ({artifact_version})"
                        if artifact_type:
                            artifact_line += f" [{artifact_type}]"
                        
                        content_parts.append(artifact_line)
            
            # Include additional details if available
            if release_details and isinstance(release_details, dict):
                # Include release notes if available
                release_notes = release_details.get("releaseDefinition", {}).get("releaseNotes", "")
                if release_notes:
                    content_parts.append(f"\nRelease Notes:\n{release_notes}")
                
                # Include approval information
                approvals = []
                for env in release_details.get("environments", []):
                    for pre_approval in env.get("preDeployApprovals", []):
                        if pre_approval.get("status") == "approved":
                            approver = pre_approval.get("approvedBy", {}).get("displayName", "")
                            approval_date = pre_approval.get("approvedOn", "")
                            if approver and approval_date:
                                formatted_approval_date = format_date(approval_date)
                                approval_str = f"Pre-deploy approved by {approver}"
                                if formatted_approval_date:
                                    approval_str += f" on {formatted_approval_date.isoformat()}"
                                approvals.append(approval_str)
                    
                    for post_approval in env.get("postDeployApprovals", []):
                        if post_approval.get("status") == "approved":
                            approver = post_approval.get("approvedBy", {}).get("displayName", "")
                            approval_date = post_approval.get("approvedOn", "")
                            if approver and approval_date:
                                formatted_approval_date = format_date(approval_date)
                                approval_str = f"Post-deploy approved by {approver}"
                                if formatted_approval_date:
                                    approval_str += f" on {formatted_approval_date.isoformat()}"
                                approvals.append(approval_str)
                
                if approvals:
                    content_parts.append("\nApprovals:")
                    for approval in approvals:
                        content_parts.append(f"- {approval}")
            
            sections.append(TextSection(
                text="\n".join(content_parts),
                link=release_url
            ))
            
            # Create metadata
            metadata = {
                "type": "release",
                "release_id": str(release_id),
                "name": name,
                "status": status,
                "created_by": created_by_name,
                "definition_name": definition_name,
                "release_url": release_url,
            }
            
            # Extract environment statuses
            if environments:
                for i, env in enumerate(environments[:5]):  # Limit to first 5 environments
                    env_name = env.get("name", "")
                    env_status = env.get("status", "")
                    if env_name and env_status:
                        metadata[f"environment_{i}_name"] = env_name
                        metadata[f"environment_{i}_status"] = env_status
            
            # Extract dates
            if created_date:
                created = format_date(created_date)
                if created:
                    metadata["created_date"] = created.isoformat()
            
            if modified_date:
                modified = format_date(modified_date)
                if modified:
                    metadata["modified_date"] = modified.isoformat()
            
            # Create semantic identifier
            semantic_id = f"Release: {name}"
            if status:
                semantic_id += f" [{status}]"
                
            # Build document
            return Document(
                id=f"azuredevops:{self.organization}/{self.project}/release/{release_id}",
                title=f"Release: {name}",
                semantic_identifier=semantic_id,
                doc_updated_at=format_date(modified_date or created_date),
                created_at=format_date(created_date),
                updated_at=format_date(modified_date),
                sections=sections,
                source=DocumentSource.AZURE_DEVOPS,
                metadata=metadata,
                resolved=status.lower() in ("succeeded", "partiallysuccessful", "complete", "completed")
            )
        except Exception as e:
            logger.error(f"Error processing release {release.get('id', 'unknown')}: {str(e)}")
            return None

    def _get_wikis(self) -> List[Dict[str, Any]]:
        """Get all wikis for the project.
        
        Returns:
            List of wiki dictionaries
        """
        try:
            response = self._make_api_request("_apis/wiki/wikis")
            response.raise_for_status()
            
            wikis = response.json().get("value", [])
            logger.info(f"Found {len(wikis)} wikis in project")
            return wikis
        except requests.exceptions.RequestException as e:
            logger.warning(f"Failed to get wikis: {str(e)}")
            return []
    
    def _get_wiki_pages(self, wiki_id: str) -> List[Dict[str, Any]]:
        """Get all pages for a specific wiki.
        
        Args:
            wiki_id: ID of the wiki
            
        Returns:
            List of wiki page dictionaries
        """
        pages = []
        
        try:
            # Get the root pages first
            response = self._make_api_request(f"_apis/wiki/wikis/{wiki_id}/pages")
            response.raise_for_status()
            
            # Process the root page
            root_page = response.json()
            if root_page:
                pages.append(root_page)
                
                # Now get all sub-pages recursively
                if root_page.get("subPages"):
                    self._get_wiki_subpages_recursive(wiki_id, root_page["subPages"], pages)
            
            logger.info(f"Found {len(pages)} wiki pages for wiki {wiki_id}")
            return pages
        except requests.exceptions.RequestException as e:
            logger.warning(f"Failed to get wiki pages for wiki {wiki_id}: {str(e)}")
            return []
    
    def _get_wiki_subpages_recursive(self, wiki_id: str, sub_pages: List[Dict[str, Any]], result_pages: List[Dict[str, Any]]) -> None:
        """Recursively get all sub-pages for a wiki.
        
        Args:
            wiki_id: ID of the wiki
            sub_pages: List of sub-page references
            result_pages: List to store the results
        """
        for sub_page_ref in sub_pages:
            page_path = sub_page_ref.get("path", "")
            if not page_path:
                continue
                
            try:
                # Use requests.utils.quote directly in the params
                response = self._make_api_request(f"_apis/wiki/wikis/{wiki_id}/pages", params={"path": page_path})
                response.raise_for_status()
                
                page = response.json()
                result_pages.append(page)
                
                # Process sub-pages recursively
                if page.get("subPages"):
                    self._get_wiki_subpages_recursive(wiki_id, page["subPages"], result_pages)
            except requests.exceptions.RequestException as e:
                logger.warning(f"Failed to get wiki sub-page {page_path}: {str(e)}")
    
    def _get_wiki_page_content(self, wiki_id: str, page_path: str) -> Optional[str]:
        """Get the content of a wiki page.
        
        Args:
            wiki_id: ID of the wiki
            page_path: Path of the page
            
        Returns:
            Content of the page as string, or None if failed
        """
        try:
            # Add includeContent=true to get the actual content, don't encode the path here
            response = self._make_api_request(
                f"_apis/wiki/wikis/{wiki_id}/pages", 
                params={"path": page_path, "includeContent": "true"}
            )
            response.raise_for_status()
            
            page = response.json()
            return page.get("content", "")
        except requests.exceptions.RequestException as e:
            logger.warning(f"Failed to get wiki page content for {page_path}: {str(e)}")
            return None
    
    def _process_wiki_page(self, wiki: Dict[str, Any], page: Dict[str, Any]) -> Optional[Document]:
        """Process a wiki page into a Document object.
        
        Args:
            wiki: Wiki data
            page: Wiki page data
            
        Returns:
            Document object if successful, None otherwise
        """
        try:
            wiki_id = wiki.get("id", "")
            wiki_name = wiki.get("name", "")
            
            page_id = page.get("id", "")
            page_path = page.get("path", "")
            page_display_name = page.get("path", "").split("/")[-1] if page.get("path") else ""
            
            if not wiki_id or not page_path:
                return None
            
            # Get the page URL
            page_url = page.get("remoteUrl", "")
            if not page_url:
                page_url = wiki.get("remoteUrl", "")
                if page_url and page_path:
                    # Try to construct the URL for the specific page
                    page_url = f"{page_url.rstrip('/')}/{page_path.lstrip('/')}"
            
            # Get the page content
            content = self._get_wiki_page_content(wiki_id, page_path)
            
            # Create sections
            sections = []
            
            # Build content with structured information
            content_parts = []
            content_parts.append(f"Wiki: {wiki_name}")
            content_parts.append(f"Page: {page_display_name}")
            
            if page.get("gitItemPath"):
                content_parts.append(f"Git Path: {page.get('gitItemPath')}")
            
            # Include the actual content if available
            if content:
                content_parts.append(f"\nContent:\n{content}")
            
            sections.append(TextSection(
                text="\n".join(content_parts),
                link=page_url
            ))
            
            # Create metadata
            metadata = {
                "type": "wiki_page",
                "wiki_id": wiki_id,
                "wiki_name": wiki_name,
                "page_id": page_id,
                "page_path": page_path,
                "page_url": page_url,
            }
            
            # Extract dates
            updated_at = page.get("lastModifiedDate") or page.get("lastUpdatedDate")
            created_at = page.get("createdDate")
            
            # Create semantic identifier
            semantic_id = f"Wiki: {wiki_name} - {page_display_name}"
            
            # Build document
            return Document(
                id=f"azuredevops:{self.organization}/{self.project}/wiki/{wiki_id}/page{page_path}",
                title=f"Wiki: {wiki_name} - {page_display_name}",
                semantic_identifier=semantic_id,
                doc_updated_at=format_date(updated_at),
                created_at=format_date(created_at),
                updated_at=format_date(updated_at),
                sections=sections,
                source=DocumentSource.AZURE_DEVOPS,
                metadata=metadata,
                resolved=True  # Wiki pages are always considered "resolved"
            )
        except Exception as e:
            wiki_name = wiki.get("name", "unknown")
            page_path = page.get("path", "unknown")
            logger.error(f"Error processing wiki page {wiki_name}/{page_path}: {str(e)}")
            return None# 'searchCriteria.itemVersion.version': 'master',  # Commented out to avoid branch name issues
