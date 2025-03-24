"""Azure DevOps connector for Onyx"""
import json
import time
from collections.abc import Generator, Iterator
from datetime import datetime, timezone
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

logger = setup_logger()

# Constants
MAX_RESULTS_PER_PAGE = 100
MAX_WORK_ITEM_SIZE = 500000  # 500 KB in bytes
WORK_ITEM_TYPES = ["Bug", "Epic", "Feature", "Issue", "Task", "TestCase", "UserStory"]

# Rate limit settings based on Azure DevOps documentation
# Azure DevOps recommends responding to Retry-After headers and has a global consumption limit
# of 200 Azure DevOps throughput units (TSTUs) within a sliding 5-minute window
MAX_API_CALLS_PER_MINUTE = 60  # Conservative limit to avoid hitting rate limits


class AzureDevOpsConnectorCheckpoint(ConnectorCheckpoint):
    """Checkpoint for the Azure DevOps connector to keep track of pagination."""
    continuation_token: Optional[str] = None


class AzureDevOpsConnector(CheckpointConnector[AzureDevOpsConnectorCheckpoint], SlimConnector):
    """Connector for Microsoft Azure DevOps."""

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
        self.organization = organization
        self.project = project
        self.work_item_types = work_item_types or WORK_ITEM_TYPES
        self.include_comments = include_comments
        self.include_attachments = include_attachments
        self.client_config: Dict[str, Any] = {}
        self.personal_access_token: Optional[str] = None

    @override
    def load_credentials(self, credentials: dict[str, Any]) -> dict[str, Any] | None:
        """Load credentials for the Azure DevOps connector.
        
        Args:
            credentials: Dictionary containing the personal access token
            
        Returns:
            None, as credentials are stored in the connector instance
            
        Raises:
            ConnectorMissingCredentialError: If credentials are missing
        """
        if not credentials:
            raise ConnectorMissingCredentialError("Azure DevOps")
        
        if "personal_access_token" not in credentials:
            raise ConnectorMissingCredentialError("Azure DevOps - Personal Access Token required")
        
        self.personal_access_token = credentials["personal_access_token"]
        self.client_config = build_azure_devops_client(
            credentials, self.organization, self.project
        )
        
        return None

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
                            # Check common variants
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
        """Make an API request to Azure DevOps with rate limiting and retry logic.
        
        Args:
            endpoint: API endpoint relative to the organization/project
            method: HTTP method
            params: URL parameters
            data: Request body for POST requests
            organization_level: Whether this is an organization-level API call
                               (no project in path)
            
        Returns:
            Response object
            
        Raises:
            ConnectorValidationError: If the API call fails
        """
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

    def _get_work_item_details(self, work_item_ids: List[int]) -> List[Dict[str, Any]]:
        """Get detailed information for work items.
        
        Args:
            work_item_ids: List of work item IDs
            
        Returns:
            List of work item details
        """
        if not work_item_ids:
            return []
        
        # Build comma-separated list of IDs
        ids_str = ",".join([str(wid) for wid in work_item_ids])
        
        # Build fields list to retrieve
        fields = [
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
            "System.History"  # For changelog
        ]
        
        fields_str = ",".join(fields)
        
        # Detailed logging to debug API issues
        logger.info(f"Fetching details for work items: {ids_str}")
        
        try:
            # Make the request
            # NOTE: Using the project in the URL path (not as a query parameter)
            # Also removing $expand parameter as it conflicts with fields parameter
            response = self._make_api_request(
                f"{self.project}/_apis/wit/workitems",
                params={
                    "ids": ids_str,
                    "fields": fields_str
                },
                organization_level=True  # Use organization-level URL
            )
            
            response.raise_for_status()
            result = response.json()
            logger.info(f"Successfully fetched {len(result.get('value', []))} work items")
            return result.get("value", [])
            
        except requests.exceptions.RequestException as e:
            # Get more details about the error
            error_detail = ""
            if hasattr(e, 'response') and e.response is not None:
                try:
                    error_detail = e.response.json()
                except:
                    error_detail = e.response.text
                
            logger.error(f"HTTP error fetching work items: {str(e)}")
            logger.error(f"Error details: {error_detail}")
            
            # For Azure DevOps, let's be explicit about certain error types
            if hasattr(e, 'response'):
                if e.response.status_code == 401:
                    logger.error("Authentication failed. Check your Personal Access Token.")
                elif e.response.status_code == 403:
                    logger.error("Authorization failed. Verify your PAT has 'Read' permissions for Work Items.")
                elif e.response.status_code == 404:
                    logger.error(f"Work items not found. Verify the work item IDs exist: {ids_str}")
                elif e.response.status_code == 400:
                    logger.error("Bad request. The request may be malformed or invalid work items were specified.")
            
            # Re-raise as ConnectorValidationError for the indexing process to handle
            raise ConnectorValidationError(f"Failed to fetch work items: {str(e)}")

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

    def _process_work_item(self, work_item: Dict[str, Any]) -> Document:
        """Process a work item into a Document.
        
        Args:
            work_item: Work item data
            
        Returns:
            Document object
        """
        work_item_id = str(get_item_field_value(work_item, "System.Id"))
        title = get_item_field_value(work_item, "System.Title", "")
        description = get_item_field_value(work_item, "System.Description", "")
        work_item_type = get_item_field_value(work_item, "System.WorkItemType", "")
        state = get_item_field_value(work_item, "System.State", "")
        
        # Create content sections
        content = f"Title: {title}\n\n"
        
        if description:
            content += f"Description:\n{description}\n\n"
        
        # Get comments if enabled
        if self.include_comments and "id" in work_item:
            comments = self._get_work_item_comments(work_item["id"])
            if comments:
                content += "Comments:\n"
                for comment in comments:
                    content += f"- {comment.get('createdBy', {}).get('displayName', 'Unknown')}: {comment.get('text', '')}\n"
                content += "\n"
        
        # Build URL for the work item
        item_url = build_azure_devops_url(
            self.client_config["base_url"], 
            work_item_id, 
            "workitems"
        )
        
        # Create document ID in the format "azuredevops:org/project/workitem/id"
        document_id = f"azuredevops:{self.organization}/{self.project}/workitem/{work_item_id}"
        
        # Process owners
        primary_owners = []
        
        # Creator
        creator_info = get_user_info_from_item(work_item, "System.CreatedBy")
        if creator_info:
            primary_owners.append(creator_info)
        
        # Assigned To
        assignee_info = get_user_info_from_item(work_item, "System.AssignedTo")
        if assignee_info and assignee_info not in primary_owners:
            primary_owners.append(assignee_info)
        
        # Build metadata
        metadata = {
            "type": work_item_type,
            "state": state,
        }
        
        # Add priority if available
        priority = get_item_field_value(work_item, "Microsoft.VSTS.Common.Priority")
        if priority:
            metadata["priority"] = str(priority)
        
        # Add severity if available (usually for bugs)
        severity = get_item_field_value(work_item, "Microsoft.VSTS.Common.Severity")
        if severity:
            metadata["severity"] = str(severity)
        
        # Add tags if available
        tags = get_item_field_value(work_item, "System.Tags")
        if tags:
            metadata["tags"] = [tag.strip() for tag in tags.split(';') if tag.strip()]
        
        # Add area path
        area_path = get_item_field_value(work_item, "System.AreaPath")
        if area_path:
            metadata["area_path"] = area_path
        
        # Add iteration path
        iteration_path = get_item_field_value(work_item, "System.IterationPath")
        if iteration_path:
            metadata["iteration_path"] = iteration_path
        
        # Create the document
        return Document(
            id=document_id,
            sections=[TextSection(link=item_url, text=content)],
            source=DocumentSource.AZURE_DEVOPS,
            semantic_identifier=f"{work_item_type} {work_item_id}: {title}",
            title=f"{work_item_type} {work_item_id}: {title}",
            url=item_url,
            doc_updated_at=format_date(get_item_field_value(work_item, "System.ChangedDate")),
            primary_owners=primary_owners if primary_owners else None,
            metadata=metadata,
        )

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
