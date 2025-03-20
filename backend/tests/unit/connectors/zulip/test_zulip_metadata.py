import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone

from onyx.connectors.zulip.connector import ZulipConnector
from onyx.connectors.zulip.schemas import Message

"""
This is a regression test for Zulip connector enhancements in the fork.
It verifies the following key features:
1. URL normalization in the connector initialization
2. Proper handling of metadata value conversion to strings
3. Proper handling of None values for last_edit_timestamp
"""

def test_zulip_url_normalization():
    """Test that the ZulipConnector correctly normalizes URLs."""
    # Test with trailing slashes
    connector = ZulipConnector(realm_name="test", realm_url="https://zulip.example.com/")
    assert connector.realm_url == "https://zulip.example.com"
    
    # Test with uppercase
    connector = ZulipConnector(realm_name="test", realm_url="HTTPS://ZULIP.EXAMPLE.COM")
    assert connector.realm_url == "https://zulip.example.com"
    
    # Test with whitespace
    connector = ZulipConnector(realm_name="test", realm_url="  https://zulip.example.com  ")
    assert connector.realm_url == "https://zulip.example.com"
    
    # Test without scheme - should add https://
    connector = ZulipConnector(realm_name="test", realm_url="zulip.example.com")
    assert connector.realm_url == "https://zulip.example.com"


def test_metadata_string_conversion():
    """Test that all metadata values are properly converted to strings."""
    connector = ZulipConnector(realm_name="test", realm_url="https://zulip.example.com")
    
    # Create a mock message with various data types in fields
    mock_message = MagicMock(spec=Message)
    mock_message.id = 12345
    mock_message.stream_id = 67890
    mock_message.sender_full_name = "Test User"
    mock_message.content = "Test message"
    mock_message.display_recipient = "test-stream"
    mock_message.subject = "Test Topic"
    mock_message.sender_email = "test@example.com"
    mock_message.timestamp = 1613492400  # Feb 16, 2021
    mock_message.content_type = "text/markdown"
    mock_message.reactions = []
    
    # Set up the message_to_narrow_link method to return a dummy link
    with patch.object(connector, '_message_to_narrow_link', return_value="https://example.com/link"):
        document = connector._message_to_doc(mock_message)
    
    # Verify all metadata values are strings
    for key, value in document.metadata.items():
        assert isinstance(value, str), f"Metadata {key} should be a string, got {type(value)}"
    
    # Verify specific conversions
    assert document.metadata["message_id"] == "12345"
    assert document.metadata["stream_id"] == "67890"
    assert document.metadata["has_reactions"] == "False"


def test_none_timestamp_handling():
    """Test that None values for last_edit_timestamp are handled correctly."""
    connector = ZulipConnector(realm_name="test", realm_url="https://zulip.example.com")
    
    # Create a mock message with None for last_edit_timestamp
    mock_message = MagicMock(spec=Message)
    mock_message.id = 12345
    mock_message.stream_id = 67890
    mock_message.sender_full_name = "Test User"
    mock_message.content = "Test message"
    mock_message.display_recipient = "test-stream"
    mock_message.subject = "Test Topic"
    mock_message.sender_email = "test@example.com"
    mock_message.timestamp = 1613492400  # Feb 16, 2021
    mock_message.last_edit_timestamp = None
    mock_message.content_type = "text/markdown"
    mock_message.reactions = []
    
    # Set up the message_to_narrow_link method to return a dummy link
    with patch.object(connector, '_message_to_narrow_link', return_value="https://example.com/link"):
        document = connector._message_to_doc(mock_message)
    
    # Verify that edit_timestamp is not in metadata
    assert "edit_timestamp" not in document.metadata
    
    # Now test with a valid edit timestamp
    mock_message.last_edit_timestamp = 1613492500  # 100 seconds later
    
    with patch.object(connector, '_message_to_narrow_link', return_value="https://example.com/link"):
        document = connector._message_to_doc(mock_message)
    
    # Verify that edit_timestamp is in metadata and is a string
    assert "edit_timestamp" in document.metadata
    assert document.metadata["edit_timestamp"] == "1613492500"
    assert isinstance(document.metadata["edit_timestamp"], str) 