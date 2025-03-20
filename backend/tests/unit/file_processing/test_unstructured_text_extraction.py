import pytest
import inspect

"""
Regression test for Unstructured API text extraction functionality.

This test file verifies that the text extraction functionality using the Unstructured API
is properly included in the codebase, which is a fork-specific customization.
"""

def test_unstructured_to_text_function_exists():
    """Test that the unstructured_to_text function exists and has the expected properties."""
    from onyx.file_processing import unstructured
    
    assert hasattr(unstructured, "unstructured_to_text"), "unstructured_to_text function should exist"
    
    sig = inspect.signature(unstructured.unstructured_to_text)
    params = list(sig.parameters.keys())
    
    # Check for required parameters
    assert "file" in params, "unstructured_to_text should have a 'file' parameter"
    assert "file_name" in params, "unstructured_to_text should have a 'file_name' parameter" 