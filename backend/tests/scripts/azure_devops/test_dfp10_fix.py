#!/usr/bin/env python3
"""
Test script to verify the DFP_10 Azure DevOps connector fix.
This script simulates multiple runs of the connector and checks that 
documents aren't incorrectly marked as "new" on each run.
"""

import os
import sys
import logging
import time
import argparse
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Set

# Setup path to import onyx modules
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

try:
    from onyx.connectors.azure_devops.connector import AzureDevOpsConnector, AzureDevOpsConnectorCheckpoint
except ImportError:
    # Try backend directory if in the main project directory
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), 'backend')))
    try:
        from onyx.connectors.azure_devops.connector import AzureDevOpsConnector, AzureDevOpsConnectorCheckpoint
    except ImportError:
        print("ERROR: Cannot import AzureDevOpsConnector. Make sure you're running this from the project root.")
        sys.exit(1)

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("test_dfp10_fix")

class DocumentCollector:
    """Collects and tracks documents across multiple connector runs."""
    
    def __init__(self):
        self.all_runs = []  # List of document sets from each run
        self.all_documents = {}  # Map of document ID to document
        self.run_count = 0
    
    def collect_run(self, documents: List[dict]) -> Set[str]:
        """
        Collect documents from a run and return any that are "new".
        
        Args:
            documents: List of documents from a connector run
            
        Returns:
            Set of document IDs that are new in this run
        """
        self.run_count += 1
        
        # Track document IDs for this run
        run_doc_ids = set()
        new_doc_ids = set()
        
        for doc in documents:
            doc_id = doc.id
            run_doc_ids.add(doc_id)
            
            # Check if this document is new
            if doc_id not in self.all_documents:
                new_doc_ids.add(doc_id)
                self.all_documents[doc_id] = doc
                logger.info(f"New document found: {doc_id}")
        
        # Store this run's results
        self.all_runs.append(run_doc_ids)
        
        return new_doc_ids

def test_dfp10_connector(pat: str, num_runs: int = 3):
    """
    Test the DFP_10 connector fix by simulating multiple runs.
    
    Args:
        pat: Personal Access Token for Azure DevOps
        num_runs: Number of connector runs to simulate
    """
    print(f"\n{'=' * 80}")
    print(f"TESTING DFP_10 CONNECTOR FIX")
    print(f"{'=' * 80}\n")
    
    # Create connector instance
    print("Creating connector instance...")
    connector = AzureDevOpsConnector(
        organization="deFactoGlobal",
        project="DFP_10",
        content_scope="everything"  # Ensure we retrieve commits
    )
    
    # Load credentials
    print("Loading credentials...")
    connector.load_credentials({"personal_access_token": pat})
    
    # Create document collector
    collector = DocumentCollector()
    
    # Run connector multiple times, simulating normal operation
    print(f"\nRunning connector {num_runs} times to test for duplicate documents...")
    
    # Set up time window - go back 30 days to ensure we find documents
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=30)
    
    # Create initial dummy checkpoint
    checkpoint = connector.build_dummy_checkpoint()
    
    # Run the connector multiple times
    for i in range(num_runs):
        print(f"\nRun {i+1}/{num_runs}:")
        
        # Convert times to seconds since epoch
        start_epoch = int(start.timestamp())
        end_epoch = int(end.timestamp())
        
        # Collect documents from this run
        documents = []
        try:
            # Run the connector with checkpoint
            for item in connector.load_from_checkpoint(start_epoch, end_epoch, checkpoint):
                if hasattr(item, 'id'):  # It's a document, not a failure
                    documents.append(item)
                    
            # The returned value after the generator stops is the new checkpoint
        except StopIteration as e:
            # Get the new checkpoint from the StopIteration exception
            checkpoint = e.value
            
        # Record and analyze the documents
        new_doc_ids = collector.collect_run(documents)
        
        print(f"  - Found {len(documents)} total documents")
        print(f"  - {len(new_doc_ids)} new documents in this run")
        
        if i > 0 and new_doc_ids:
            # After the first run, we shouldn't find any new documents
            print(f"  - WARNING: Found new documents in run {i+1}! This indicates the fix might not be working.")
            for doc_id in new_doc_ids:
                print(f"    - New document: {doc_id}")
        
        # Small delay to ensure timestamps are different
        time.sleep(1)
    
    # Print summary
    print(f"\n{'=' * 80}")
    print("TEST SUMMARY:")
    print(f"{'=' * 80}")
    print(f"Total connector runs: {collector.run_count}")
    print(f"Total unique documents found: {len(collector.all_documents)}")
    
    # Calculate test result
    success = all(len(collector.collect_run([])) == 0 for i in range(1, collector.run_count))
    
    if success:
        print("\nTEST PASSED: No duplicate documents found in subsequent runs.")
        print("The DFP_10 connector fix appears to be working correctly.")
    else:
        print("\nTEST FAILED: Duplicate documents were incorrectly identified as new.")
        print("The fix may not be completely effective. Review the logs for more details.")
    
    print(f"{'=' * 80}\n")

def main():
    parser = argparse.ArgumentParser(description="Test the DFP_10 Azure DevOps connector fix")
    parser.add_argument("--runs", type=int, default=3, help="Number of simulated connector runs")
    args = parser.parse_args()
    
    # Get PAT from environment or prompt
    pat = os.environ.get("AZURE_DEVOPS_PAT")
    if not pat:
        pat = input("Enter your Azure DevOps PAT: ")
        if not pat:
            print("No PAT provided. Exiting.")
            sys.exit(1)
    
    # Run test
    test_dfp10_connector(pat, args.runs)

if __name__ == "__main__":
    main() 