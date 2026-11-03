"""Verbatim citation verification and character offset mapping."""

from __future__ import annotations

import re
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field

from docket.models.evidence import SourceCitation, SourceType, VerificationStatus


class CitationVerificationResult(BaseModel):
    """The result of verifying an extracted citation against its source document."""
    model_config = ConfigDict(frozen=True)

    is_verified: bool
    start_offset: Optional[int] = None
    end_offset: Optional[int] = None
    citation: SourceCitation
    flags: List[str] = Field(default_factory=list)


class VerbatimCitationVerifier:
    """Verifies that an extracted quote exists in the source text without hallucination."""

    def verify_citation(
        self,
        document_text: str,
        cited_excerpt: str,
        document_id: str,
        source_type: SourceType,
        field_path: str = "text",
    ) -> CitationVerificationResult:
        """Check if cited_excerpt exists in document_text, computing coordinates."""
        clean_excerpt = cited_excerpt.strip()

        # 1. Exact match
        exact_idx = document_text.find(clean_excerpt)
        if exact_idx != -1:
            end_idx = exact_idx + len(clean_excerpt)
            citation = SourceCitation(
                source_type=source_type,
                source_identifier=document_id,
                field_path=field_path,
                extracted_value=clean_excerpt,
                verification_status=VerificationStatus.VERIFIED,
            )
            return CitationVerificationResult(
                is_verified=True,
                start_offset=exact_idx,
                end_offset=end_idx,
                citation=citation,
                flags=[],
            )

        # 2. Normalized whitespace match
        # Construct a regex that matches the words with flexible whitespace
        words = [re.escape(w) for w in re.split(r"\s+", clean_excerpt) if w]
        if words:
            pattern = r"\s+".join(words)
            match = re.search(pattern, document_text, flags=re.IGNORECASE)
            if match:
                start_idx, end_idx = match.span()
                matched_text = document_text[start_idx:end_idx]
                citation = SourceCitation(
                    source_type=source_type,
                    source_identifier=document_id,
                    field_path=field_path,
                    extracted_value=matched_text,
                    verification_status=VerificationStatus.VERIFIED,
                )
                return CitationVerificationResult(
                    is_verified=True,
                    start_offset=start_idx,
                    end_offset=end_idx,
                    citation=citation,
                    flags=["WHITESPACE_NORMALIZED_MATCH"],
                )

        # 3. Not found — Hallucination / Fabricated citation
        citation = SourceCitation(
            source_type=source_type,
            source_identifier=document_id,
            field_path=field_path,
            extracted_value=clean_excerpt,
            verification_status=VerificationStatus.UNVERIFIED,
        )
        return CitationVerificationResult(
            is_verified=False,
            start_offset=None,
            end_offset=None,
            citation=citation,
            flags=["CITATION_NOT_FOUND"],
        )

