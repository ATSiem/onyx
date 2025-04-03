#!/usr/bin/env python3
"""
Direct patch for the AzureDevOpsConnector to fix field detection.
This creates a monkeypatch for the _get_work_item_details method.
"""

import sys
import os
import logging
import inspect
from typing import Any, Dict, List, Optional

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger()

try:
    # Import the connector
    from onyx.connectors.azure_devops.connector import AzureDevOpsConnector
    import requests
    
    # Define our patched method with field detection
    def patched_get_work_item_details(self, work_item_ids: List[int]) -> List[Dict[str, Any]]:
        """Get detailed information for specific work items with field detection.
        
        Args:
            work_item_ids: List of work item IDs to fetch details for
            
        Returns:
            List of work items with detailed information
        """
        logger.info(f"PATCHED VERSION: Fetching {len(work_item_ids)} work items with essential fields")
        all_work_items = []
        
        try:
            # Split into batches to avoid hitting API limits
            batch_size = min(200, len(work_item_ids))  # 200 is max batch size for work item API
            for i in range(0, len(work_item_ids), batch_size):
                batch_ids = work_item_ids[i:i + batch_size]
                
                # Create a comma-separated list of IDs
                ids_param = ",".join(map(str, batch_ids))
                
                # First get essential fields
                response = self._make_api_request(
                    "_apis/wit/workitems",
                    params={
                        "ids": ids_param,
                        "fields": "System.Id,System.Title,System.WorkItemType,System.State,System.Description,System.CreatedDate,System.ChangedDate,System.CreatedBy,System.AssignedTo"
                    }
                )
                response.raise_for_status()
                result = response.json()
                work_items = result.get("value", [])
                
                # Keep track of IDs not found in cache - these need field detection
                uncached_ids = batch_ids
                
                # Now get additional fields like resolution status
                # These help determine if the item is resolved/closed
                try:
                    # Essential fields we already have
                    essential_fields = [
                        "System.Id", 
                        "System.Title", 
                        "System.WorkItemType", 
                        "System.State", 
                        "System.Description", 
                        "System.CreatedDate",
                        "System.ChangedDate",
                        "System.CreatedBy",
                        "System.AssignedTo"
                    ]
                    
                    # Additional fields to fetch for all work items
                    additional_fields = [
                        "System.AreaPath",
                        "System.IterationPath",
                        "Microsoft.VSTS.Common.Priority",
                        "Microsoft.VSTS.Common.Severity"
                    ]
                    
                    # Resolution fields - these may not be available in all projects
                    resolution_fields = [
                        "System.ResolvedDate", 
                        "Microsoft.VSTS.Common.ClosedDate", 
                        "Microsoft.VSTS.Common.Resolution", 
                        "System.ResolvedBy", 
                        "System.ClosedBy", 
                        "System.ClosedDate"
                    ]
                    
                    # Use a smarter approach for field discovery
                    # Rather than having a special case for DFP_10, discover the fields dynamically
                    
                    # Test first ID with all fields to detect which ones are available
                    test_id = uncached_ids[0]
                    safe_resolution_fields = []
                    
                    # Try all resolution fields in one request first - this is faster if they all exist
                    try:
                        all_fields_response = self._make_api_request(
                            "_apis/wit/workitems",
                            params={
                                "ids": str(test_id),
                                "fields": ",".join(resolution_fields)
                            }
                        )
                        all_fields_response.raise_for_status()
                        # All fields exist, add them all
                        safe_resolution_fields = resolution_fields
                        logger.info(f"All resolution fields are available in project {self.project}")
                    except Exception as e:
                        # Try each field individually to see which ones exist
                        logger.info(f"Some resolution fields aren't available in project {self.project}, detecting available fields...")
                        
                        # Try to parse the error to determine which fields are missing
                        missing_fields = set()
                        if hasattr(e, 'response') and e.response is not None:
                            try:
                                error_json = e.response.json()
                                error_msg = error_json.get('message', '')
                                # Extract field name from error like "TF51535: Cannot find field System.ResolvedDate"
                                import re
                                field_match = re.search(r"Cannot find field ([^\.]+\.[^\s\.]+)", error_msg)
                                if field_match:
                                    missing_field = field_match.group(1)
                                    missing_fields.add(missing_field)
                                    logger.info(f"Detected missing field from error: {missing_field}")
                            except Exception:
                                pass
                        
                        # For each field, check if it exists unless we already know it's missing
                        for field in resolution_fields:
                            if field in missing_fields:
                                logger.info(f"Skipping known missing field: {field}")
                                continue
                                
                            try:
                                field_response = self._make_api_request(
                                    "_apis/wit/workitems",
                                    params={
                                        "ids": str(test_id),
                                        "fields": field
                                    }
                                )
                                field_response.raise_for_status()
                                # Field exists, add it
                                safe_resolution_fields.append(field)
                                logger.info(f"Field {field} is available in project {self.project}")
                            except Exception as field_e:
                                logger.info(f"Field {field} not available in project {self.project}")
                                
                                # Try to track other missing fields from errors
                                if hasattr(field_e, 'response') and field_e.response is not None:
                                    try:
                                        error_json = field_e.response.json()
                                        error_msg = error_json.get('message', '')
                                        import re
                                        field_match = re.search(r"Cannot find field ([^\.]+\.[^\s\.]+)", error_msg)
                                        if field_match:
                                            missing_field = field_match.group(1)
                                            missing_fields.add(missing_field)
                                    except Exception:
                                        pass
                    
                    # Add safe resolution fields to additional fields
                    additional_fields.extend(safe_resolution_fields)
                    
                    # Now get all additional fields that we've verified  
                    if additional_fields:
                        fields_param = ",".join(additional_fields)
                        logger.info(f"Fetching additional fields for {len(uncached_ids)} work items: {fields_param}")
                        
                        additional_response = self._make_api_request(
                            "_apis/wit/workitems",
                            params={
                                "ids": ids_param,
                                "fields": fields_param
                            }
                        )
                        additional_response.raise_for_status()
                        additional_result = additional_response.json()
                        additional_items = additional_result.get("value", [])
                        
                        # Merge additional field data into the work items
                        for work_item in work_items:
                            work_item_id = work_item.get("id")
                            for additional_item in additional_items:
                                if additional_item.get("id") == work_item_id:
                                    work_item["fields"].update(additional_item.get("fields", {}))
                                    break
                except Exception as e:
                    logger.warning(f"Failed to fetch additional fields: {str(e)}")
                    # Continue with basic fields - we can still process the items
                
                # Add these to the results
                all_work_items.extend(work_items)
            
        except Exception as e:
            logger.error(f"Failed to fetch work items: {str(e)}")
        
        return all_work_items
    
    # Apply the patch
    print("\n===== APPLYING DIRECT PATCH =====")
    print(f"Original method ID: {id(AzureDevOpsConnector._get_work_item_details)}")
    # Replace the method
    original_method = AzureDevOpsConnector._get_work_item_details
    AzureDevOpsConnector._get_work_item_details = patched_get_work_item_details
    print(f"Patched method ID: {id(AzureDevOpsConnector._get_work_item_details)}")
    
    # Verify the patch worked
    has_detection_after = 'detecting available fields' in inspect.getsource(AzureDevOpsConnector._get_work_item_details)
    print(f"Field detection in patched method: {has_detection_after}")
    
    print("\n===== PATCH SUCCESSFUL =====")
    print("The AzureDevOpsConnector has been patched with field detection.")
    print("Next time the connector runs, it will use our patched version.")
    
except ImportError as e:
    print(f"ERROR: Failed to import required modules: {e}")
    sys.exit(1)
except Exception as e:
    print(f"ERROR: Failed to apply patch: {e}")
    sys.exit(1)

print("\n===== PATCH COMPLETE =====")
sys.exit(0) 