"""Factory router for fact extractors with explicit offline/live modes."""

from __future__ import annotations

import os
from typing import Optional

from docket.ai.base import BaseFactExtractor
from docket.ai.deterministic import DeterministicFactExtractor
from docket.ai.provider_openai import OpenAIFactExtractor
from docket.ai.provider_anthropic import AnthropicFactExtractor
from docket.ai.provider_gemini import GeminiFactExtractor


class AIConfigurationError(ValueError):
    """Raised when AI configuration is invalid, missing required keys, or malformed."""
    pass


def get_fact_extractor(
    mode: Optional[str] = None,
    provider: Optional[str] = None,
    model: Optional[str] = None,
    api_key: Optional[str] = None,
) -> BaseFactExtractor:
    """Return the configured AI fact extractor based on explicit configuration.

    Modes:
      - 'offline' (default): Always returns DeterministicFactExtractor. No external model calls.
      - 'live': Requires explicit provider configuration and a valid API key.

    Does NOT silently switch providers merely because an API key happens to exist in the environment.
    """
    selected_mode = (mode or os.getenv("DOCKET_AI_MODE", "")).strip().lower()

    # Legacy support: if DOCKET_AI_MODE is unset, but DOCKET_AI_PROVIDER or DOCKET_LLM_PROVIDER
    # was explicitly specified, treat as live mode.
    legacy_provider = os.getenv("DOCKET_AI_PROVIDER") or os.getenv("DOCKET_LLM_PROVIDER")
    if not selected_mode:
        if provider or legacy_provider:
            selected_mode = "live"
        else:
            selected_mode = "offline"

    if selected_mode == "offline":
        return DeterministicFactExtractor()

    if selected_mode != "live":
        raise AIConfigurationError(
            f"Invalid DOCKET_AI_MODE '{selected_mode}'. Supported modes are 'offline' and 'live'."
        )

    # Live Mode: Provider must be explicitly chosen or defaults to 'gemini'
    selected_provider = (
        provider
        or os.getenv("DOCKET_AI_PROVIDER")
        or os.getenv("DOCKET_LLM_PROVIDER")
        or "gemini"
    ).strip().lower()

    if selected_provider == "gemini":
        key = api_key or os.getenv("GEMINI_API_KEY")
        if not key:
            raise AIConfigurationError(
                "DOCKET_AI_MODE is set to 'live' with provider 'gemini', but GEMINI_API_KEY is not set."
            )
        model_name = model or os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
        return GeminiFactExtractor(api_key=key, model=model_name)

    if selected_provider == "openai":
        key = api_key or os.getenv("OPENAI_API_KEY")
        if not key:
            raise AIConfigurationError(
                "DOCKET_AI_MODE is set to 'live' with provider 'openai', but OPENAI_API_KEY is not set."
            )
        model_name = model or os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        return OpenAIFactExtractor(api_key=key, model=model_name)

    if selected_provider == "anthropic":
        key = api_key or os.getenv("ANTHROPIC_API_KEY")
        if not key:
            raise AIConfigurationError(
                "DOCKET_AI_MODE is set to 'live' with provider 'anthropic', but ANTHROPIC_API_KEY is not set."
            )
        model_name = model or os.getenv("ANTHROPIC_MODEL", "claude-3-5-sonnet-20241022")
        return AnthropicFactExtractor(api_key=key, model=model_name)

    raise AIConfigurationError(
        f"Unsupported AI provider '{selected_provider}'. Supported providers are: gemini, openai, anthropic."
    )
