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

## How to Add New Regression Tests

When making fork-specific fixes:

1. Create a regression test that verifies the fix
2. Add the test to the appropriate test directory
3. Add the test to the `scripts/pre-merge-check.sh` script
4. Document the test in this file

## Git Hooks

A pre-merge Git hook is installed in `.git/hooks/pre-merge-commit` to automatically run these tests before any merge operation. If tests fail, the merge will be aborted.

## Important Note

Always run the regression tests before merging from upstream to ensure custom functionality is preserved. 