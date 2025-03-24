# Regression Tests for Fork-Specific Fixes

This document outlines the regression tests that verify important fixes made in this fork that differ from the upstream repository.

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
- Added helper script to ensure Unstructured API is running

**Tests:**
- API Key Management: `backend/tests/unit/file_processing/test_unstructured.py`
- Text Extraction: `backend/tests/unit/file_processing/test_unstructured_text_extraction.py`
- Document Pipeline Integration: `backend/tests/unit/file_processing/test_extract_file_text.py`
- Code Integration Check: `scripts/check_unstructured_integration.sh`
- API Health Check: `scripts/test_unstructured_api_health.sh` - Verifies a running Unstructured API can process documents by uploading a test text file and confirming the response
- Container Management: `scripts/ensure_unstructured_api.sh` - Checks if the Unstructured API container is running and starts it if needed, preventing test failures due to missing API service

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

## How to Add New Regression Tests

When making fork-specific fixes:

1. Create a regression test that verifies the fix
2. Add the test to the appropriate test directory
3. Add the test to the `scripts/pre-merge-check.sh` script
4. Document the test in this file

## Git Hooks

We have two Git hooks set up to ensure our custom functionality is preserved when merging from upstream:

1. **Pre-Merge Hook** (`.git/hooks/pre-merge-commit`): Runs tests before the merge is completed. If tests fail, the merge is aborted.

2. **Post-Merge Hook** (`.git/hooks/post-merge`): Runs tests after the merge is completed. If tests fail, it warns you to fix issues or consider reverting the merge.

This dual approach ensures that:
- Breaking changes aren't merged (pre-merge)
- You catch any subtle issues that might only appear after the merge is complete (post-merge)

## Important Note

Always run the regression tests before merging from upstream to ensure custom functionality is preserved. 