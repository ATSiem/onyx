import pytest
import sys

"""
Regression test for Unstructured API integration.

This test file exists to verify that the Unstructured API integration modules 
are properly included in the codebase, which is a fork-specific customization.
"""

def test_unstructured_module_exists():
    """Test that the unstructured.py module exists in the file_processing package."""
    import onyx.file_processing
    assert hasattr(onyx.file_processing, "unstructured"), "The unstructured.py module should exist"
    

def test_unstructured_api_functions_exist():
    """Test that the key Unstructured API functions exist."""
    from onyx.file_processing import unstructured
    
    # Check for API key management functions
    assert hasattr(unstructured, "get_unstructured_api_key"), "get_unstructured_api_key function should exist"
    assert hasattr(unstructured, "update_unstructured_api_key"), "update_unstructured_api_key function should exist"
    assert hasattr(unstructured, "delete_unstructured_api_key"), "delete_unstructured_api_key function should exist"
    
    # Check for text extraction function
    assert hasattr(unstructured, "unstructured_to_text"), "unstructured_to_text function should exist" 