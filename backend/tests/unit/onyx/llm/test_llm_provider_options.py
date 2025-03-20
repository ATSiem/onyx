from unittest.mock import patch

import pytest

from onyx.llm.llm_provider_options import OPENAI_PROVIDER_NAME
from onyx.llm.llm_provider_options import fetch_models_for_provider
import onyx.llm.llm_provider_options as llm_provider_options


def test_fetch_models_for_provider(monkeypatch):
    """Test that we can retrieve a list of models for a provider, ensuring we filter out
    problematic models like "o1-2024-12-17" for the OpenAI provider.
    """
    # Mock the provider-to-models map for testing
    mock_map = {
        OPENAI_PROVIDER_NAME: ["gpt-4", "gpt-3.5-turbo", "o1-2024-12-17", "other-model"],
    }
    monkeypatch.setattr(llm_provider_options, "_PROVIDER_TO_MODELS_MAP", mock_map)

    # Test OpenAI
    models = llm_provider_options.fetch_models_for_provider(OPENAI_PROVIDER_NAME)
    assert len(models) == 3
    assert "gpt-4" in models
    assert "gpt-3.5-turbo" in models
    assert "other-model" in models
    # Verify the problematic model is filtered out
    assert "o1-2024-12-17" not in models

    # Add test where model appears in other providers too
    mock_map_with_multiple_providers = {
        OPENAI_PROVIDER_NAME: ["gpt-4", "gpt-3.5-turbo", "o1-2024-12-17"],
        "other_provider": ["model-1", "model-2", "o1-2024-12-17"],
    }
    monkeypatch.setattr(llm_provider_options, "_PROVIDER_TO_MODELS_MAP", mock_map_with_multiple_providers)

    # Test OpenAI filter
    models = llm_provider_options.fetch_models_for_provider(OPENAI_PROVIDER_NAME)
    assert "o1-2024-12-17" not in models

    # Test non-OpenAI provider - the problematic model should also be filtered
    models = llm_provider_options.fetch_models_for_provider("other_provider")
    assert "o1-2024-12-17" not in models
    assert "model-1" in models
    assert "model-2" in models


def test_fetch_models_for_provider_non_openai_also_filters():
    """
    Test that the fetch_models_for_provider function filters problematic models
    for non-OpenAI providers too.
    """
    # Mock the _PROVIDER_TO_MODELS_MAP dictionary
    with patch(
        "onyx.llm.llm_provider_options._PROVIDER_TO_MODELS_MAP",
        {"other_provider": ["model-1", "model-2", "o1-2024-12-17"]},
    ):
        # Get models for a non-OpenAI provider
        models = fetch_models_for_provider("other_provider")
        
        # Check that the problematic model is filtered out
        assert "o1-2024-12-17" not in models
        
        # Check that other models are still present
        assert "model-1" in models
        assert "model-2" in models


def test_fetch_models_for_provider_unknown_provider():
    """
    Test that the fetch_models_for_provider function returns an empty list
    for unknown providers.
    """
    # Get models for an unknown provider
    models = fetch_models_for_provider("unknown_provider")
    
    # Check that an empty list is returned
    assert models == [] 