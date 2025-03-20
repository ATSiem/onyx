import pytest

"""
Regression test for Unstructured API integration with file extraction.

This test verifies that the file extraction functionality properly integrates with 
the Unstructured API, which is a fork-specific customization.
"""

def test_extract_file_text_imports_unstructured_api():
    """Test that extract_file_text imports Unstructured API functions."""
    import inspect
    from onyx.file_processing import extract_file_text
    
    # Get the source code of the extract_file_text module
    source = inspect.getsource(extract_file_text)
    
    # Check for imports of unstructured API functions
    assert "from onyx.file_processing.unstructured import get_unstructured_api_key" in source, \
        "extract_file_text should import get_unstructured_api_key"
    assert "from onyx.file_processing.unstructured import unstructured_to_text" in source, \
        "extract_file_text should import unstructured_to_text"


def test_extract_file_text_function_uses_unstructured_api():
    """Test that the extract_file_text function uses the Unstructured API when available."""
    import inspect
    from onyx.file_processing.extract_file_text import extract_file_text
    
    # Get the source code of the extract_file_text function
    source = inspect.getsource(extract_file_text)
    
    # Check that it uses the Unstructured API
    assert "get_unstructured_api_key()" in source, \
        "extract_file_text should call get_unstructured_api_key()"
    assert "unstructured_to_text" in source, \
        "extract_file_text should use unstructured_to_text" 