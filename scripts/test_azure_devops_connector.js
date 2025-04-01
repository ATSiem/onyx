#!/usr/bin/env node
/**
 * This script tests the Azure DevOps connector configuration to verify
 * that the data_types parameter is being set correctly based on the UI selection.
 * 
 * Usage:
 * 1. Run the script with a connector ID as an argument:
 *    node test_azure_devops_connector.js <connector_id>
 * 2. The script will fetch the connector configuration and verify that data_types
 *    includes all expected data types when "content_scope" is set to "everything".
 */

const fetch = require('node-fetch');
const API_URL = process.env.API_URL || 'http://localhost:3000';

// Expected data types for "everything" content scope
const EXPECTED_DATA_TYPES = [
  'work_items',
  'commits',
  'test_results',
  'test_stats',
  'releases',
  'release_details',
  'wikis'
];

async function testAzureDevOpsConnector(connectorId) {
  try {
    console.log(`Fetching connector configuration for ID: ${connectorId}`);
    
    // Fetch the connector configuration
    const response = await fetch(`${API_URL}/api/manage/admin/connector/${connectorId}`);
    if (!response.ok) {
      throw new Error(`Failed to fetch connector: ${response.status} ${response.statusText}`);
    }
    
    const connector = await response.json();
    console.log(`\nConnector Name: ${connector.name}`);
    
    // Check if this is an Azure DevOps connector
    if (connector.source !== 'azure_devops') {
      console.error('This is not an Azure DevOps connector!');
      process.exit(1);
    }
    
    // Get the connector specific config
    const config = connector.connector_specific_config;
    console.log('\nConnector Configuration:');
    console.log(JSON.stringify(config, null, 2));
    
    // Check if data_types is set
    if (!config.data_types) {
      console.error('\nERROR: data_types parameter is not set!');
      console.log('The UI change to set data_types based on content_scope selection is not working.');
      process.exit(1);
    }
    
    // If content_scope is set to "everything", verify data_types includes all expected types
    if (config.content_scope === 'everything') {
      const missingTypes = EXPECTED_DATA_TYPES.filter(type => !config.data_types.includes(type));
      
      if (missingTypes.length > 0) {
        console.error('\nERROR: Some expected data types are missing!');
        console.log('Missing types:', missingTypes);
        process.exit(1);
      } else {
        console.log('\nSUCCESS: All expected data types are present!');
        console.log('data_types:', config.data_types);
      }
    } else {
      console.log('\nContent scope is not set to "everything". data_types:', config.data_types);
    }
    
  } catch (error) {
    console.error('Error testing connector:', error.message);
    process.exit(1);
  }
}

// Get connector ID from command line arguments
const connectorId = process.argv[2];
if (!connectorId) {
  console.error('Please provide a connector ID as an argument.');
  console.log('Usage: node test_azure_devops_connector.js <connector_id>');
  process.exit(1);
}

testAzureDevOpsConnector(connectorId); 