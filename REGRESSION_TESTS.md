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
- Frontend: `web/src/components/llm/LLMSelector.test.tsx`
- Backend: `backend/tests/unit/onyx/llm/test_llm_provider_options.py`

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