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
6. For scopes, select "Custom defined" and ensure the following permissions:
   - "Work Items (Read)" - Required for work items
   - "Code (Read)" - Required if you want to index Git commits
   - "Test Management (Read)" - Required if you want to index test results
   - "Release (Read)" - Required if you want to index releases
7. Set an expiration date (note: you'll need to update the token in Onyx when it expires)
8. Click "Create"
9. Copy the token value (you won't be able to see it again)

### Configuring the Connector in Onyx

The setup is a two-step process:

#### Step 1: Create a Credential

1. In the Onyx admin interface, go to "Connectors" and click "Create Credential"
2. Select "Azure DevOps" from the list
3. Enter a name for your credential (optional)
4. Paste your Personal Access Token in the field
5. Click "Create"

#### Step 2: Add the Connector

1. After creating the credential, go to "Add Connector"
2. Select "Azure DevOps" from the list
3. Select the credential you just created
4. Fill in the required information:
   - **Organization**: Your Azure DevOps organization name
   - **Project**: Your Azure DevOps project name
   - **Work Item Types**: (Optional) Types of work items to index (e.g., Bug, UserStory, Task)
   - **Include Comments**: Toggle to include work item comments
   - **Include Attachments**: Toggle to include links to work item attachments
   - **Content Scope**: Choose between "Work Items Only" (default) or "Everything". Select "Everything" if you want to index Git commits, test results, releases, and wikis in addition to work items. Note that selecting "Everything" requires additional PAT permissions as specified above.
     - Note: The content_scope value is case-insensitive, so both "everything" and "Everything" will work.
5. Click "Save" to add the connector

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

## Troubleshooting

### Common Setup Issues

1. **"Unable to authenticate" error**: 
   - Verify your Personal Access Token is correct and not expired
   - Ensure the PAT has "Read" permissions for work items
   - Check that you've entered the organization and project names correctly

2. **No work items appearing after indexing**:
   - Confirm your project has work items of the selected types
   - Check that the work items have been updated recently (if using changed date filtering)
   - Verify the connector configuration is correct (organization, project names)

3. **Credential Creation vs Connector Configuration**:
   - Remember that creating a credential is separate from configuring the connector
   - First create the credential with your PAT, then configure the connector with organization and project details
   - If you see only a PAT field during setup, you're likely in the credential creation step - after creating the credential, you'll need to complete the connector configuration

4. **URL Configuration**:
   - You don't need to manually enter the Azure DevOps URL
   - The connector automatically builds the URL using your organization and project names
   - Just enter the organization name (the part after `https://dev.azure.com/`) and project name

5. **Git Commits Not Appearing**:
   - Ensure your PAT has "Code (Read)" permission
   - Check that "Content Scope" is set to "Everything" in the connector configuration
   - Verify your project actually has Git repositories with commits
   - If using a repository filter, confirm the repository names are correct
   - Note: If you're configuring via the API or scripts, the content_scope value is case-insensitive - both "everything" and "Everything" will work.

### Testing the Connection

After setup, you can verify the connection is working by:

1. Saving the connector configuration
2. Starting an indexing job
3. Checking the logs for any errors
4. Verifying that work items appear in search results 