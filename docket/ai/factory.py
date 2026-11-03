"""Factory router for fact extractors with deterministic fallback."""

from __future__ import annotations

import os
from typing import Optional

from docket.ai.base import BaseFactExtractor
from docket.ai.deterministic import DeterministicFactExtractor
from docket.ai.provider_openai import OpenAIFactExtractor
from docket.ai.provider_anthropic import AnthropicFactExtractor
from docket.ai.provider_gemini import GeminiFactExtractor


def get_fact_extractor(provider: Optional[str] = None) -> BaseFactExtractor:
    """Return the configured AI fact extractor or fall back safely to DeterministicFactExtractor."""
    selected_provider = (provider or os.getenv("DOCKET_LLM_PROVIDER", "")).strip().lower()

    openai_key = os.getenv("OPENAI_API_KEY")
    anthropic_key = os.getenv("ANTHROPIC_API_KEY")
    gemini_key = os.getenv("GEMINI_API_KEY")

    if selected_provider == "openai" and openai_key:
        return OpenAIFactExtractor(api_key=openai_key)
    if selected_provider == "anthropic" and anthropic_key:
        return AnthropicFactExtractor(api_key=anthropic_key)
    if selected_provider == "gemini" and gemini_key:
        return GeminiFactExtractor(api_key=gemini_key)

    # Automatic fallback based on available environment credentials
    if openai_key and not selected_provider:
        return OpenAIFactExtractor(api_key=openai_key)
    if anthropic_key and not selected_provider:
        return AnthropicFactExtractor(api_key=anthropic_key)
    if gemini_key and not selected_provider:
        return GeminiFactExtractor(api_key=gemini_key)

    # Safe deterministic offline extractor (0 network or API key dependency)
    return DeterministicFactExtractor()

