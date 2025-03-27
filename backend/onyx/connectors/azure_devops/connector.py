"""Azure DevOps connector for Onyx"""
import json
import time
from collections.abc import Generator, Iterator
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, cast

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

    def __init__(
        self,
        organization: str,
        project: str,
        work_item_types: Optional[List[str]] = None,
        include_comments: bool = True,
        include_attachments: bool = False,
    ) -> None:
        """Initialize the Azure DevOps connector.
        
        Args:
            organization: Azure DevOps organization name
            project: Azure DevOps project name
            work_item_types: List of work item types to index (defaults to all common types)
            include_comments: Whether to include work item comments
            include_attachments: Whether to include work item attachments (as links)
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

    @rate_limit_builder(max_calls=60, period=60)  # More conservative rate limiting
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

                # Build the URL for the batch request
                endpoint = f"_apis/wit/workitems"
                params = {
                    "ids": batch_ids_str,
                    "fields": ",".join([
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
                        "System.AssignedTo",
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
                    ])
                }

                response = self._make_api_request(endpoint, method="GET", params=params)
                response.raise_for_status()

                # Process the response
                batch_data = response.json()
                if "value" in batch_data:
                    all_work_items.extend(batch_data["value"])

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
            checkpoint: Previous checkpoint
            
        Yields:
            Documents or failures
            
        Returns:
            Updated checkpoint
        """
        if not self.client_config:
            raise ConnectorMissingCredentialError("Azure DevOps")
        
        # Convert epoch seconds to datetime
        # Using timezone.utc to create timezone-aware datetimes for proper comparison
        start_time = datetime.fromtimestamp(start, tz=timezone.utc)
        end_time = datetime.fromtimestamp(end, tz=timezone.utc)
        
        # Get continuation token from checkpoint
        continuation_token = checkpoint.continuation_token
        has_more = True
        
        # Initialize document batch
        doc_batch: List[Document] = []
        
        while has_more:
            try:
                # Get work items
                result = self._get_work_items(
                    start_time=start_time,
                    continuation_token=continuation_token,
                    max_results=MAX_RESULTS_PER_PAGE
                )
                
                # Extract work item IDs
                work_items = result.get("workItems", [])
                work_item_ids = [item["id"] for item in work_items if "id" in item]
                
                # Update continuation token
                continuation_token = result.get("continuationToken")
                has_more = continuation_token is not None and len(work_item_ids) > 0
                
                # Get details for each work item
                if work_item_ids:
                    # Process work items in batches of 200 (API limit)
                    for i in range(0, len(work_item_ids), 200):
                        batch = work_item_ids[i:i+200]
                        work_item_details = self._get_work_item_details(batch)
                        
                        # Process each work item
                        for work_item in work_item_details:
                            try:
                                # Check if work item was updated within our time range
                                changed_date = get_item_field_value(work_item, "System.ChangedDate")
                                if changed_date:
                                    changed_datetime = format_date(changed_date)
                                    if changed_datetime and (changed_datetime < start_time or changed_datetime > end_time):
                                        continue
                                
                                document = self._process_work_item(work_item)
                                doc_batch.append(document)
                                
                                # Yield in batches
                                if len(doc_batch) >= INDEX_BATCH_SIZE:
                                    for doc in doc_batch:
                                        yield doc
                                    doc_batch = []
                            except Exception as e:
                                logger.error(f"Failed to process work item: {str(e)}")
                                work_item_id = get_item_field_value(work_item, "System.Id", "unknown")
                                item_url = build_azure_devops_url(
                                    self.client_config["base_url"], 
                                    str(work_item_id), 
                                    "workitems"
                                )
                                yield ConnectorFailure(
                                    failed_document=DocumentFailure(
                                        document_id=item_url,
                                        document_link=item_url
                                    ),
                                    failure_message=f"Failed to process work item: {str(e)}"
                                )
                else:
                    # No more work items, break out of the loop
                    has_more = False
            
            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 429:  # Too Many Requests
                    retry_after = int(e.response.headers.get('Retry-After', 30))
                    logger.warning(f"Rate limited by Azure DevOps API. Waiting for {retry_after} seconds.")
                    time.sleep(retry_after)
                    # Continue with the next iteration
                    continue
                else:
                    logger.error(f"HTTP error fetching work items: {str(e)}")
                    yield ConnectorFailure(
                        failed_entity=EntityFailure(entity_id="azure_devops_work_items"),
                        failure_message=f"Failed to fetch work items: {str(e)}"
                    )
                    has_more = False
            except Exception as e:
                logger.error(f"Failed to fetch work items: {str(e)}")
                yield ConnectorFailure(
                    failed_entity=EntityFailure(entity_id="azure_devops_work_items"),
                    failure_message=f"Failed to fetch work items: {str(e)}"
                )
                has_more = False
        
        # Yield any remaining documents
        for doc in doc_batch:
            yield doc
        
        # Return updated checkpoint
        return AzureDevOpsConnectorCheckpoint(
            has_more=has_more,
            continuation_token=continuation_token
        )

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
        """Retrieve all slim documents (just IDs) for pruning.
        
        Args:
            start: Optional start time
            end: Optional end time
            callback: Optional callback for progress updates
            
        Yields:
            Batches of slim documents
        """
        if not self.client_config:
            raise ConnectorMissingCredentialError("Azure DevOps")
        
        # Convert epoch seconds to datetime if provided
        start_time = datetime.fromtimestamp(start, tz=timezone.utc) if start else None
        
        continuation_token = None
        has_more = True
        slim_docs_batch: List[SlimDocument] = []
        
        while has_more:
            try:
                # Get work items
                result = self._get_work_items(
                    start_time=start_time,
                    continuation_token=continuation_token,
                    max_results=MAX_RESULTS_PER_PAGE
                )
                
                # Extract work item IDs
                work_items = result.get("workItems", [])
                
                # Update continuation token
                continuation_token = result.get("continuationToken")
                has_more = continuation_token is not None and len(work_items) > 0
                
                # Process each work item ID into a slim document
                for item in work_items:
                    if "id" in item:
                        work_item_id = str(item["id"])
                        item_url = build_azure_devops_url(
                            self.client_config["base_url"], 
                            work_item_id, 
                            "workitems"
                        )
                        
                        slim_docs_batch.append(SlimDocument(id=item_url))
                        
                        # Yield in batches
                        if len(slim_docs_batch) >= INDEX_BATCH_SIZE:
                            yield slim_docs_batch
                            slim_docs_batch = []
                            
                            # Update progress if callback provided
                            if callback:
                                callback.heartbeat()
            
            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 429:  # Too Many Requests
                    retry_after = int(e.response.headers.get('Retry-After', 30))
                    logger.warning(f"Rate limited by Azure DevOps API. Waiting for {retry_after} seconds.")
                    time.sleep(retry_after)
                    # Continue with the next iteration
                    continue
                else:
                    logger.error(f"HTTP error fetching work items for slim retrieval: {str(e)}")
                    has_more = False
            except Exception as e:
                logger.error(f"Failed to fetch work items for slim retrieval: {str(e)}")
                has_more = False
        
        # Yield any remaining documents
        if slim_docs_batch:
            yield slim_docs_batch

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
