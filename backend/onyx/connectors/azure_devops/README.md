# Azure DevOps Connector for Onyx

This connector allows Onyx to index and search work items from Microsoft Azure DevOps. It supports indexing various types of work items like bugs, user stories, tasks, and more.

## Features

- Index work items from Azure DevOps projects
- Filter by work item types
- Include work item comments
- Support for work item metadata (priority, severity, state, etc.)
- Proper attribution to work item creators and assignees

## Requirements

To use this connector, you'll need:

1. An Azure DevOps organization
2. A project within that organization
3. A Personal Access Token (PAT) with read access to work items

## Setup Instructions

### Creating a Personal Access Token (PAT)

1. Sign in to your Azure DevOps organization: `https://dev.azure.com/[organization]`
2. Click on your profile icon in the top-right corner and select "Personal access tokens"
3. Click "New Token"
4. Give your token a name (e.g., "Onyx Integration")
5. Set the organization to your organization
6. For scopes, select "Custom defined" and ensure "Work Items (Read)" is checked
7. Set an expiration date (note: you'll need to update the token in Onyx when it expires)
8. Click "Create"
9. Copy the token value (you won't be able to see it again)

### Configuring the Connector in Onyx

1. In the Onyx admin interface, go to "Connectors" and click "Add Connector"
2. Select "Azure DevOps" from the list
3. Fill in the required information:
   - **Organization**: Your Azure DevOps organization name
   - **Project**: Your Azure DevOps project name
   - **Work Item Types**: (Optional) Types of work items to index (e.g., Bug, UserStory, Task)
   - **Include Comments**: Toggle to include work item comments
   - **Include Attachments**: Toggle to include links to work item attachments
   - **Personal Access Token**: The PAT you created earlier
4. Click "Save" to add the connector

## How It Works

The connector uses the Azure DevOps REST API to:

1. Query for work items using Work Item Query Language (WIQL)
2. Fetch detailed information for each work item
3. Convert each work item into a Document object for indexing in Onyx
4. Retrieve comments if enabled

## Known Limitations

- The connector does not index the content of attachments, only their links
- Due to API limitations, some work item history details might not be included
- The connector currently only supports a single project per connector instance 