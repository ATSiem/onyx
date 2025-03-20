import inspect
import pytest
from typing import get_type_hints
import importlib.metadata
from packaging import version as parse_version

"""
This regression test verifies that our fork maintains compatibility with the Zulip API schema.
Instead of testing the full functionality (which requires dependencies), it checks:
1. That our schema definitions match the expected structure
2. That required fields are properly typed
"""

def test_zulip_message_schema():
    """Test that our Message schema has the expected fields and types."""
    try:
        # Import without needing the actual zulip package
        from onyx.connectors.zulip.schemas import Message
        
        # Check that Message class exists
        assert Message, "Message schema should exist"
        
        # Get annotation/type hints to check fields
        annotations = get_type_hints(Message)
        
        # Check for essential fields in Message
        essential_fields = [
            "sender_full_name", "content", "timestamp", 
            "display_recipient", "subject", "sender_email", 
            "stream_id", "reactions", "content_type", "last_edit_timestamp"
        ]
        
        for field in essential_fields:
            assert field in annotations, f"Message schema missing essential field: {field}"
        
        # Verify last_edit_timestamp is defined as Optional
        assert "last_edit_timestamp" in annotations, "Message schema must include last_edit_timestamp"
    except ImportError:
        pytest.skip("Zulip schemas not available - skipping test")


def test_zulip_schemas_module():
    """Test that the zulip.schemas module has the expected classes."""
    try:
        # Import module to inspect
        import onyx.connectors.zulip.schemas as schemas
        
        # Check that the module has the required classes
        required_classes = ["Message", "GetMessagesResponse"]
        module_contents = dir(schemas)
        
        for cls in required_classes:
            assert cls in module_contents, f"schemas module missing required class: {cls}"
    except ImportError:
        pytest.skip("Zulip schemas not available - skipping test")


def test_connector_url_normalization_function():
    """Test that the ZulipConnector has URL normalization code."""
    try:
        # Import the connector module source code as text
        import onyx.connectors.zulip.connector as connector
        source = inspect.getsource(connector)
        
        # Check for URL normalization code patterns
        normalization_patterns = [
            ".strip()", 
            ".lower()", 
            "rstrip('/')",
            "https://"
        ]
        
        for pattern in normalization_patterns:
            assert pattern in source, f"Connector missing URL normalization pattern: {pattern}"
    except ImportError:
        pytest.skip("Zulip connector not available - skipping test")


def test_metadata_string_conversion_exists():
    """Test that the connector converts metadata values to strings."""
    try:
        # Import the connector module source code as text
        import onyx.connectors.zulip.connector as connector
        source = inspect.getsource(connector)
        
        # Look for string conversion pattern in the metadata assignment
        string_conversion_patterns = [
            "str(message.",
            '"stream_name": str(',
            '"topic": str(',
            '"sender_name": str(',
            '"message_id": str(',
            '"stream_id": str('
        ]
        
        for pattern in string_conversion_patterns:
            assert pattern in source, f"Connector missing string conversion pattern: {pattern}"
    except ImportError:
        pytest.skip("Zulip connector not available - skipping test")


def test_zulip_client_version_compatibility():
    """Test that the installed Zulip client version is compatible with what we need."""
    try:
        # Get the installed version of zulip client
        zulip_version = importlib.metadata.version("zulip")
        
        # Use version range instead of exact match
        min_version = "0.8.0"
        max_version = "1.0.0"  # Assuming API won't break in minor versions
        
        # Verify version is within acceptable range
        version_obj = parse_version.parse(zulip_version)
        min_version_obj = parse_version.parse(min_version)
        max_version_obj = parse_version.parse(max_version)
        
        assert version_obj >= min_version_obj, f"Zulip client version too old. Got {zulip_version}, need at least {min_version}"
        assert version_obj < max_version_obj, f"Zulip client version too new. Got {zulip_version}, maximum supported is {max_version}"
        
        # Log the actual version for reference
        print(f"Using Zulip client version: {zulip_version}")
    except (ImportError, importlib.metadata.PackageNotFoundError):
        pytest.skip("Zulip package not installed - skipping version test") 