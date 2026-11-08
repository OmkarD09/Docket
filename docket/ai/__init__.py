"""Docket AI semantic fact extraction, citation verification, and workflow engine."""

from docket.ai.base import (
    AIProviderError,
    BaseFactExtractor,
    ExtractionResult,
    ParsedDocumentChunk,
)
from docket.ai.citation_verifier import (
    CitationVerificationResult,
    VerbatimCitationVerifier,
)
from docket.ai.contradiction import (
    ContradictionDetector,
    ContradictionFinding,
)
from docket.ai.deterministic import DeterministicFactExtractor
from docket.ai.factory import AIConfigurationError, get_fact_extractor
from docket.ai.prompt_guard import (
    PromptInjectionGuard,
    SanitizedInput,
    ThreatLevel,
)
from docket.ai.provider_openai import OpenAIFactExtractor
from docket.ai.provider_anthropic import AnthropicFactExtractor
from docket.ai.provider_gemini import GeminiFactExtractor
from docket.ai.workflow import (
    SemanticExtractionWorkflow,
    SemanticWorkflowResult,
)

__all__ = [
    "AIConfigurationError",
    "AIProviderError",
    "BaseFactExtractor",
    "ExtractionResult",
    "ParsedDocumentChunk",
    "CitationVerificationResult",
    "VerbatimCitationVerifier",
    "ContradictionDetector",
    "ContradictionFinding",
    "DeterministicFactExtractor",
    "get_fact_extractor",
    "PromptInjectionGuard",
    "SanitizedInput",
    "ThreatLevel",
    "OpenAIFactExtractor",
    "AnthropicFactExtractor",
    "GeminiFactExtractor",
    "SemanticExtractionWorkflow",
    "SemanticWorkflowResult",
]
