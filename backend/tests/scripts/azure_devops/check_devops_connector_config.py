#!/usr/bin/env python3
"""
Script to check the local connector configuration database for Azure DevOps connector settings
This helps verify if the connector is properly configured for Git commits
"""

import os
import sys
import json
import argparse
import sqlite3
from pathlib import Path

def find_sqlite_db():
    """Find the SQLite database file in common locations"""
    # Common locations for the SQLite database
    possible_locations = [
        # Local dev environment
        "./data/onyx.db",
        "./onyx.db",
        "./backend/data/onyx.db",
        # Docker volume mounts
        "/data/onyx.db",
        # Home directory
        os.path.expanduser("~/.onyx/data/onyx.db"),
    ]
    
    for location in possible_locations:
        if os.path.exists(location):
            return location
    
    return None

def check_connector_configs(db_path, connector_name=None):
    """
    Check the connector configurations in the database
    """
    print(f"\n{'=' * 50}")
    print(f"CHECKING AZURE DEVOPS CONNECTOR CONFIGURATIONS")
    print(f"{'=' * 50}\n")
    
    print(f"Using database: {db_path}")
    
    try:
        # Connect to the database
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Get all Azure DevOps connectors
        query = """
        SELECT 
            c.id, 
            c.name, 
            c.source, 
            c.connector_specific_config,
            c.credential_id
        FROM 
            connector c 
        WHERE 
            c.source = 'azure_devops'
        """
        
        if connector_name:
            query += " AND c.name LIKE ?"
            cursor.execute(query, (f"%{connector_name}%",))
        else:
            cursor.execute(query)
            
        connectors = cursor.fetchall()
        
        if not connectors:
            print("❌ No Azure DevOps connectors found in the database.")
            return
        
        print(f"Found {len(connectors)} Azure DevOps connector(s):")
        
        for i, connector in enumerate(connectors):
            connector_id, name, source, config_json, credential_id = connector
            config = json.loads(config_json)
            
            print(f"\n{i+1}. Connector: {name} (ID: {connector_id})")
            print(f"   Organization: {config.get('organization', 'Not set')}")
            print(f"   Project: {config.get('project', 'Not set')}")
            
            # Check if content_scope is set to "everything"
            content_scope = config.get('content_scope', 'Not set')
            if content_scope == 'everything':
                print(f"   ✅ Content Scope: {content_scope} (Git commits should be included)")
            else:
                print(f"   ❌ Content Scope: {content_scope} (Git commits will NOT be included)")
                print(f"       To fix: Edit the connector and set Content Scope to 'everything'")
            
            # Check if data_types includes commits
            data_types = config.get('data_types', [])
            if 'commits' in data_types:
                print(f"   ✅ Data Types: 'commits' is included in {data_types}")
            else:
                print(f"   ❌ Data Types: 'commits' is NOT included in {data_types}")
                print(f"       This should be set automatically when content_scope is 'everything'")
            
            # Get credential info
            cursor.execute("SELECT id, name FROM credential WHERE id = ?", (credential_id,))
            credential = cursor.fetchone()
            if credential:
                cred_id, cred_name = credential
                print(f"   Credential: {cred_name} (ID: {cred_id})")
                print(f"   NOTE: Cannot verify PAT permissions from database (PAT is encrypted)")
            else:
                print(f"   ❌ Credential not found (ID: {credential_id})")
            
            # Check indexing status
            cursor.execute("""
                SELECT 
                    status,
                    timestamp,
                    num_docs_indexed
                FROM 
                    connector_indexing_status 
                WHERE 
                    connector_id = ?
                ORDER BY 
                    timestamp DESC
                LIMIT 3
            """, (connector_id,))
            
            indexing_statuses = cursor.fetchall()
            if indexing_statuses:
                print("\n   Recent indexing attempts:")
                for status, timestamp, num_docs in indexing_statuses:
                    print(f"   - {timestamp}: Status: {status}, Documents indexed: {num_docs}")
            else:
                print("\n   No recent indexing attempts found.")
        
        # Summary
        print(f"\n{'=' * 50}")
        print("RECOMMENDATIONS:")
        print(f"{'=' * 50}")
        print("If your Azure DevOps connector is not retrieving Git commits:")
        print("1. Ensure 'content_scope' is set to 'everything' in the connector configuration")
        print("2. Verify the PAT has 'Code (Read)' permission using verify_azure_pat_permissions.py")
        print("3. Check server logs for errors during indexing")
        print("4. Verify that repositories actually contain commits")
        print("5. Try running a complete re-indexing after fixing any issues")
        
    except sqlite3.Error as e:
        print(f"Database error: {e}")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Check Azure DevOps connector configurations")
    parser.add_argument("--db", help="Path to the SQLite database file")
    parser.add_argument("--name", help="Filter connectors by name (partial match)")
    args = parser.parse_args()
    
    # Find database
    db_path = args.db
    if not db_path:
        db_path = find_sqlite_db()
    
    if not db_path or not os.path.exists(db_path):
        print("❌ SQLite database not found. Please specify the path with --db.")
        sys.exit(1)
    
    # Check connector configurations
    check_connector_configs(db_path, args.name) 