import pytest
from typing import Generator, TypeVar
from datetime import datetime

from onyx.connectors.connector_runner import CheckpointOutputWrapper
from onyx.connectors.interfaces import CheckpointOutput
from onyx.connectors.models import ConnectorCheckpoint, ConnectorFailure, Document, DocumentFailure, EntityFailure, TextSection
from onyx.configs.constants import DocumentSource


CT = TypeVar("CT", bound=ConnectorCheckpoint)


class MockConnectorCheckpoint(ConnectorCheckpoint):
    """Mock checkpoint for testing."""
    test_continuation_token: str | None = None


def test_checkpoint_output_wrapper_valid_document():
    """Test that CheckpointOutputWrapper handles valid Document objects correctly."""
    
    def mock_generator() -> CheckpointOutput[MockConnectorCheckpoint]:
        # Yield a valid document
        doc = Document(
            id="test-doc-1",
            source=DocumentSource.MOCK_CONNECTOR,
            semantic_identifier="Test Document",
            metadata={},
            sections=[TextSection(text="Test content")]
        )
        yield doc
        # Return the final checkpoint
        return MockConnectorCheckpoint(has_more=False, test_continuation_token="test-token")
    
    wrapper = CheckpointOutputWrapper[MockConnectorCheckpoint]()
    wrapped_gen = wrapper(mock_generator())
    
    # First yield should be the document
    doc, failure, checkpoint = next(wrapped_gen)
    assert doc is not None
    assert doc.id == "test-doc-1"
    assert failure is None
    assert checkpoint is None
    
    # Second yield should be the final checkpoint
    doc, failure, checkpoint = next(wrapped_gen)
    assert doc is None
    assert failure is None
    assert checkpoint is not None
    assert checkpoint.has_more is False
    assert checkpoint.test_continuation_token == "test-token"


def test_checkpoint_output_wrapper_valid_failure():
    """Test that CheckpointOutputWrapper handles valid ConnectorFailure objects correctly."""
    
    def mock_generator() -> CheckpointOutput[MockConnectorCheckpoint]:
        # Create a proper document failure
        failure = ConnectorFailure(
            failed_document=DocumentFailure(
                document_id="test-doc-id",
                document_link="https://example.com/doc"
            ),
            failure_message="Failed to process document"
        )
        yield failure
        # Return the final checkpoint
        return MockConnectorCheckpoint(has_more=False, test_continuation_token="test-token")
    
    wrapper = CheckpointOutputWrapper[MockConnectorCheckpoint]()
    wrapped_gen = wrapper(mock_generator())
    
    # First yield should be the failure
    doc, failure, checkpoint = next(wrapped_gen)
    assert doc is None
    assert failure is not None
    assert failure.failure_message == "Failed to process document"
    assert checkpoint is None
    
    # Second yield should be the final checkpoint
    doc, failure, checkpoint = next(wrapped_gen)
    assert doc is None
    assert failure is None
    assert checkpoint is not None
    assert checkpoint.has_more is False
    assert checkpoint.test_continuation_token == "test-token"


def test_checkpoint_output_wrapper_entity_failure():
    """Test that CheckpointOutputWrapper handles EntityFailure objects correctly."""
    
    def mock_generator() -> CheckpointOutput[MockConnectorCheckpoint]:
        # Create a proper entity failure
        failure = ConnectorFailure(
            failed_entity=EntityFailure(
                entity_id="test-entity"
            ),
            failure_message="Failed to process entity"
        )
        yield failure
        # Return the final checkpoint
        return MockConnectorCheckpoint(has_more=False, test_continuation_token="test-token")
    
    wrapper = CheckpointOutputWrapper[MockConnectorCheckpoint]()
    wrapped_gen = wrapper(mock_generator())
    
    # First yield should be the failure
    doc, failure, checkpoint = next(wrapped_gen)
    assert doc is None
    assert failure is not None
    assert failure.failure_message == "Failed to process entity"
    assert checkpoint is None
    
    # Second yield should be the final checkpoint
    doc, failure, checkpoint = next(wrapped_gen)
    assert doc is None
    assert failure is None
    assert checkpoint is not None
    assert checkpoint.has_more is False
    assert checkpoint.test_continuation_token == "test-token"


def test_checkpoint_output_wrapper_invalid_tuple():
    """Test that CheckpointOutputWrapper properly handles invalid tuple outputs."""
    
    def mock_generator_with_tuple() -> Generator:
        # Incorrectly yield a tuple (simulating the bug)
        yield ("test-doc-1", "test-content")
        # Return the final checkpoint
        return MockConnectorCheckpoint(has_more=False, test_continuation_token="test-token")
    
    wrapper = CheckpointOutputWrapper[MockConnectorCheckpoint]()
    wrapped_gen = wrapper(mock_generator_with_tuple())
    
    # Should raise a ValueError when encountering the tuple
    with pytest.raises(ValueError) as exc_info:
        next(wrapped_gen)
    
    assert "Invalid document_or_failure type" in str(exc_info.value)
    assert "tuple" in str(exc_info.value)


def test_checkpoint_output_wrapper_invalid_type():
    """Test that CheckpointOutputWrapper properly handles other invalid types."""
    
    def mock_generator_with_invalid_type() -> Generator:
        # Incorrectly yield a string
        yield "invalid output"
        # Return the final checkpoint
        return MockConnectorCheckpoint(has_more=False, test_continuation_token="test-token")
    
    wrapper = CheckpointOutputWrapper[MockConnectorCheckpoint]()
    wrapped_gen = wrapper(mock_generator_with_invalid_type())
    
    # Should raise a ValueError when encountering the invalid type
    with pytest.raises(ValueError) as exc_info:
        next(wrapped_gen)
    
    assert "Invalid document_or_failure type" in str(exc_info.value) 