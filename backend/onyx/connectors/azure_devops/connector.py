"""Azure DevOps connector for Onyx"""
import json
from collections.abc import Generator, Iterator
from datetime import datetime
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

logger = setup_logger()

# Constants
MAX_RESULTS_PER_PAGE = 100
MAX_WORK_ITEM_SIZE = 500000  # 500 KB in bytes
WORK_ITEM_TYPES = ["Bug", "Epic", "Feature", "Issue", "Task", "TestCase", "UserStory"]


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
        
        # Try to fetch a single work item to validate settings
        try:
            # Make a simple API call to verify credentials
            response = self._make_api_request(
                f"_apis/wit/wiql",
                method="POST",
                data=json.dumps({
                    "query": "SELECT [System.Id] FROM WorkItems WHERE [System.TeamProject] = @project AND [System.WorkItemType] IN ('Bug') ORDER BY [System.ChangedDate] DESC",
                    "top": 1
                })
            )
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            raise ConnectorValidationError(
                f"Failed to connect to Azure DevOps API: {str(e)}"
            )

    def _make_api_request(
        self, 
        endpoint: str, 
        method: str = "GET", 
        params: Dict[str, Any] = None,
        data: str = None
    ) -> requests.Response:
        """Make an API request to Azure DevOps.
        
        Args:
            endpoint: API endpoint relative to the organization/project
            method: HTTP method
            params: URL parameters
            data: Request body for POST requests
            
        Returns:
            Response object
            
        Raises:
            ConnectorValidationError: If the API call fails
        """
        if not self.client_config:
            raise ConnectorValidationError("Azure DevOps client not configured")
        
        base_url = self.client_config["base_url"].rstrip("/")
        url = f"{base_url}/{endpoint}"
        
        # Ensure API version is included
        api_params = params or {}
        if "api-version" not in api_params:
            api_params["api-version"] = self.client_config["api_version"]
        
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        
        try:
            response = requests.request(
                method=method,
                url=url,
                auth=self.client_config["auth"],
                params=api_params,
                headers=headers,
                data=data
            )
            return response
        except requests.exceptions.RequestException as e:
            logger.error(f"Azure DevOps API request failed: {str(e)}")
            raise ConnectorValidationError(f"API request failed: {str(e)}")

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
        # Build WIQL query
        query = "SELECT [System.Id], [System.Title], [System.WorkItemType] FROM WorkItems WHERE [System.TeamProject] = @project"
        
        # Add work item type filter
        if self.work_item_types and len(self.work_item_types) > 0:
            types_str = ", ".join([f"'{item_type}'" for item_type in self.work_item_types])
            query += f" AND [System.WorkItemType] IN ({types_str})"
        
        # Add time filter if specified
        if start_time:
            formatted_time = start_time.strftime("%Y-%m-%dT%H:%M:%SZ")
            query += f" AND [System.ChangedDate] >= '{formatted_time}'"
        
        # Order by changed date
        query += " ORDER BY [System.ChangedDate] DESC"
        
        # Make the query request
        data = {
            "query": query,
            "top": max_results
        }
        
        if continuation_token:
            data["continuationToken"] = continuation_token
            
        response = self._make_api_request(
            "_apis/wit/wiql",
            method="POST",
            data=json.dumps(data)
        )
        
        response.raise_for_status()
        return response.json()

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
        
        # Make the request
        response = self._make_api_request(
            f"_apis/wit/workitems",
            params={
                "ids": ids_str,
                "fields": fields_str,
                "$expand": "all"  # Include comments and other relations
            }
        )
        
        response.raise_for_status()
        return response.json().get("value", [])

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
            response = self._make_api_request(
                f"_apis/wit/workItems/{work_item_id}/comments"
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
        start_time = datetime.fromtimestamp(start)
        end_time = datetime.fromtimestamp(end)
        
        # Get continuation token from checkpoint
        continuation_token = checkpoint.continuation_token
        has_more = True
        
        # Safety mechanism for testing to prevent infinite loops
        iteration_count = 0
        max_iterations = 10  # Reasonable limit for testing
        
        while has_more and iteration_count < max_iterations:
            iteration_count += 1
            
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
                has_more = continuation_token is not None
                
                # Get details for each work item
                if work_item_ids:
                    work_item_details = self._get_work_item_details(work_item_ids)
                    
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
                            yield document
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
            
            except Exception as e:
                logger.error(f"Failed to fetch work items: {str(e)}")
                yield ConnectorFailure(
                    failed_entity=EntityFailure(entity_id="azure_devops_work_items"),
                    failure_message=f"Failed to fetch work items: {str(e)}"
                )
                has_more = False
        
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
        start_time = datetime.fromtimestamp(start) if start else None
        
        continuation_token = None
        has_more = True
        slim_docs_batch = []
        
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
                has_more = continuation_token is not None
                
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
            
            except Exception as e:
                logger.error(f"Failed to fetch work items for slim retrieval: {str(e)}")
                has_more = False
        
        # Yield any remaining documents
        if slim_docs_batch:
            yield slim_docs_batch
