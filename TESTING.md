# Regression Tests for Fork-Specific Fixes

This document outlines the regression tests that verify important fixes made in this fork that differ from the upstream repository.

## Comprehensive Testing Approach

Following the best practices outlined in James Shore's article on ["The Best Product Engineering Org in the World"](https://www.jamesshore.com/v2/blog/2025/the-best-product-engineering-org-in-the-world), we've implemented a robust testing strategy focusing on internal quality:

1. **Comprehensive Test Suite** - A unified testing approach that runs:
   - Static analysis & linting
   - Unit tests
   - Regression tests
   - Integration tests
   - Docker-dependent tests

2. **Automated Test Hooks** - Git hooks that automatically run tests at critical points:
   - Pre-commit: Runs comprehensive tests before each commit
   - Pre-merge: Runs regression tests before merging from upstream
   - Post-merge: Runs comprehensive tests after merging to catch any subtle issues

To set up the test hooks:

```bash
./scripts/setup-git-hooks.sh
```

To run the comprehensive test suite manually:

```bash
./scripts/comprehensive-test-suite.sh
```

## Automated Testing

We have a pre-merge hook setup to automatically run regression tests before merging changes from upstream. This helps ensure that our custom fixes don't get broken when incorporating upstream changes.

To run the regression tests manually:

```bash
./scripts/pre-merge-check.sh
```

## Key Regression Tests

### 1. LLM Model Filtering

**Issue:** Certain LLM models with future dates in their names (e.g., "o1-2024-12-17") were appearing in the model selector but couldn't be used.

**Fix:** 
- Frontend: Added filter in `LLMSelector.tsx` to remove problematic models
- Backend: Added filter in `llm_provider_options.py` to exclude these models from options

**Tests:** 
- Backend: `backend/tests/unit/onyx/llm/test_llm_provider_options.py`

**Note:** The frontend filtering is present in the component, but frontend tests are currently disabled.

### 2. Email Invite Functionality in Single-Tenant Mode

**Issue:** Email invites weren't being sent when `MULTI_TENANT=false` in the configuration.

**Fix:** 
- Modified `backend/onyx/server/manage/users.py` to send email invites in single-tenant mode

**Tests:**
- `backend/tests/unit/test_email_invites.py`

### 3. Unstructured API Integration

**Issue:** Our fork uses the Unstructured API for document processing, which requires specialized configuration and handling.

**Fix:**
- Added API key management in `backend/onyx/file_processing/unstructured.py`
- Integrated with document extraction pipeline in `extract_file_text.py`
- Configured environment variables in docker-compose files

**Tests:**
- API Key Management: `backend/tests/unit/file_processing/test_unstructured.py`
- Text Extraction: `backend/tests/unit/file_processing/test_unstructured_text_extraction.py`
- Document Pipeline Integration: `backend/tests/unit/file_processing/test_extract_file_text.py`
- Code Integration Check: `scripts/check_unstructured_integration.sh`
- API Health Check: `scripts/test_unstructured_api_health.sh` - Verifies a running Unstructured API can process documents by uploading a test text file and confirming the response

### 4. Zulip Connector Enhancements

**Issue:** The Zulip connector needed improvements for URL handling, metadata formatting, and timestamp handling.

**Fix:**
- Added URL normalization in the connector initialization
- Ensured all metadata values are converted to strings
- Properly handled None values for last_edit_timestamp

**Tests:**
- Schema Compatibility Tests: `backend/tests/unit/connectors/zulip/test_zulip_schema.py` - Verifies:
  1. Our Zulip schemas include all required fields
  2. Our connector contains proper URL normalization and string conversion code patterns
  3. Client library version is compatible with our requirements (supports versions 0.8.0 to 1.0.0)
- Full Integration Tests: `backend/tests/unit/connectors/zulip/test_zulip_metadata.py` - Verifies:
  1. URL normalization is properly applied to different formats
  2. Metadata values are correctly converted to strings
  3. None values for last_edit_timestamp are handled correctly

**Note:** The schema compatibility tests don't require the actual Zulip library, allowing them to run in CI environments without additional dependencies.

### 5. Azure DevOps Connector Improvements

**Issue:** The Azure DevOps connector had case sensitivity issues with the content_scope parameter and was failing to retrieve git commits due to hardcoded branch names.

**Fix:**
- Modified the connector to handle different capitalization of the content_scope value (both "everything" and "Everything" work)
- Removed the hardcoded "master" branch name in the git commits query to support repositories with different default branches
- Added enhanced logging for better troubleshooting

**Tests:**
- Content Scope Tests: `backend/tests/unit/connectors/azure_devops/test_azure_devops_content_scope.py` - Verifies:
  1. The connector correctly processes both lowercase and uppercase content_scope values
  2. Git commits are properly enabled when content_scope is set to "everything" (case-insensitive)
- Git Commits Tests: `backend/tests/unit/connectors/azure_devops/test_azure_devops_git_commits.py` - Verifies:
  1. Git repositories can be fetched correctly
  2. Commits can be retrieved without requiring a specific branch name
  3. Commit data is properly processed into Documents

**Utility Scripts:**
- Diagnostic and fix scripts are maintained in `backend/tests/scripts/azure_devops/` for future reference and debugging

### 6. PostHog Analytics Integration

**Issue:** We needed to track chat usage metrics (thread creation and message sending) for internal analytics.

**Fix:**
- Added analytics utility functions in `web/src/lib/analytics.ts`
- Integrated tracking points in chat thread creation and message handling
- Added environment variable configuration for PostHog API key and host

**Tests:**
- Unit Tests: `web/src/lib/__tests__/analytics.test.ts` - Verifies:
  1. The analytics functions properly call PostHog with the correct event types and parameters
  2. Both chat thread creation and message sending events are tracked correctly
  3. Different parameter variations are handled appropriately (null descriptions, attachments, etc.)
- Integration Tests: `web/src/app/chat/__tests__/ChatAnalytics.test.tsx` - Verifies:
  1. Chat functions properly integrate with the analytics tracking
  2. Events are sent at the appropriate points in the chat workflow

## How to Add New Regression Tests

When making fork-specific fixes:

1. Create a regression test that verifies the fix
2. Add the test to the appropriate test directory
3. Add the test to both the `scripts/pre-merge-check.sh` script and `scripts/comprehensive-test-suite.sh`
4. Document the test in this file

## Git Hooks

We have three Git hooks set up to ensure our custom functionality is preserved:

1. **Pre-Commit Hook** (`.git/hooks/pre-commit`): Runs comprehensive tests before each commit. If tests fail, the commit is aborted.

2. **Pre-Merge Hook** (`.git/hooks/pre-merge-commit`): Runs regression tests before the merge is completed. If tests fail, the merge is aborted.

3. **Post-Merge Hook** (`.git/hooks/post-merge`): Runs comprehensive tests after the merge is completed. If tests fail, it warns you to fix issues or consider reverting the merge.

This approach ensures that:
- Changes meet quality standards before they're committed (pre-commit)
- Breaking changes aren't merged from upstream (pre-merge)
- You catch any subtle issues that might only appear after the merge is complete (post-merge)

## Important Notes

- Always run the regression tests before merging from upstream to ensure custom functionality is preserved.
- If adding new functionality that requires specific tests, make sure to include them in both the pre-merge checks and comprehensive test suite.
- Do not commit changes until they've been tested programmatically and/or via the UI/UX. 