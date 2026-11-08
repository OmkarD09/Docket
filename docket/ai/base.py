"""Base classes and data structures for AI semantic fact extraction."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field

from docket.models.dispute import DisputeCase
from docket.models.evidence import ExtractedClaim, SourceCitation, SourceType
from docket.models.reconciliation import ReconciledDisputeBundle


class AIProviderError(RuntimeError):
    """Raised when an external AI provider fails, times out, or returns a malformed response."""
    pass


class ParsedDocumentChunk(BaseModel):
    """A segment of unstructured source text with location coordinates."""
    model_config = ConfigDict(frozen=True)

    document_id: str
    source_type: SourceType
    text: str
    start_offset: int = 0
    end_offset: int = 0
    line_number: Optional[int] = None


class ExtractionResult(BaseModel):
    """The outcome of semantic fact extraction across bundle records."""
    model_config = ConfigDict(arbitrary_types_allowed=True)

    claims: List[ExtractedClaim] = Field(default_factory=list)
    citations: List[SourceCitation] = Field(default_factory=list)
    findings: List[str] = Field(default_factory=list)
    raw_model_response: Optional[Dict[str, Any]] = None


class BaseFactExtractor(ABC):
    """Abstract interface for AI fact extractors."""

    @abstractmethod
    def extract_from_bundle(
        self,
        dispute: DisputeCase,
        bundle: ReconciledDisputeBundle,
    ) -> ExtractionResult:
        """Extract atomic factual claims and verifiable citations from a reconciled bundle."""
        pass

    @abstractmethod
    def extract_from_text(
        self,
        text: str,
        source_id: str,
        source_type: SourceType,
    ) -> List[ExtractedClaim]:
        """Extract claims from an isolated text document."""
        pass

