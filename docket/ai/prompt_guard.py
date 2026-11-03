"""Prompt injection defense and untrusted input sanitization barrier."""

from __future__ import annotations

from enum import Enum
import html
import re
from typing import List
from pydantic import BaseModel, ConfigDict, Field


class ThreatLevel(str, Enum):
    """Categorized risk level of analyzed text."""
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class SanitizedInput(BaseModel):
    """Sanitized prompt container with threat analysis metadata."""
    model_config = ConfigDict(frozen=True)

    safe_prompt_text: str
    is_suspicious: bool = False
    detected_patterns: List[str] = Field(default_factory=list)
    threat_level: ThreatLevel = ThreatLevel.LOW


class PromptInjectionGuard:
    """Detects adversarial injection attacks and encapsulates untrusted input."""

    OVERRIDE_PATTERNS = [
        (r"ignore\s+(?:all\s+)?previous\s+instructions", "SYSTEM_OVERRIDE_IGNORE_INSTRUCTIONS"),
        (r"disregard\s+(?:all\s+)?(?:prior|above|previous)", "SYSTEM_OVERRIDE_DISREGARD"),
        (r"system\s+override", "SYSTEM_OVERRIDE_TRIGGER"),
        (r"you\s+are\s+now\s+(?:a|an)?\s*(?:paypal\s+admin|dan|jailbreak)", "SYSTEM_OVERRIDE_ROLE_SWAP"),
        (r"new\s+(?:system\s+)?instructions\s*:", "SYSTEM_OVERRIDE_NEW_INSTRUCTIONS"),
    ]

    ROLE_PATTERNS = [
        (r"\[\s*system\s*\]", "ROLE_MANIPULATION_SYSTEM_BRACKET"),
        (r"<\s*system\s*>", "ROLE_MANIPULATION_SYSTEM_TAG"),
        (r"\b(?:AI|Human|Assistant|System)\s*:", "ROLE_MANIPULATION_PREFIX"),
    ]

    ACTION_PATTERNS = [
        (r"(?:call\s+function|execute|invoke)\s+[a-z0-9_]+\s*\(", "ACTION_EXECUTION_CALL"),
        (r"(?:execute_refund|refund\s+transaction|accept\s+dispute|send_money)", "ACTION_EXECUTION_FINANCIAL"),
        (r"\bPOST\s+/v[12]/", "ACTION_EXECUTION_API_PATH"),
    ]

    def sanitize(self, text: str) -> SanitizedInput:
        """Scan untrusted customer/document text and produce a safely wrapped container."""
        if not text:
            return SanitizedInput(
                safe_prompt_text="<untrusted_content></untrusted_content>",
                is_suspicious=False,
                detected_patterns=[],
                threat_level=ThreatLevel.LOW,
            )

        detected: List[str] = []

        # 1. Scan for override patterns
        for pattern, label in self.OVERRIDE_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                detected.append(label)

        # 2. Scan for role manipulation patterns
        for pattern, label in self.ROLE_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                detected.append(label)

        # 3. Scan for action execution bait
        for pattern, label in self.ACTION_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                detected.append(label)

        # Determine threat level
        is_suspicious = len(detected) > 0
        if any("SYSTEM_OVERRIDE" in p for p in detected) or any("ACTION_EXECUTION" in p for p in detected):
            threat_level = ThreatLevel.HIGH if len(detected) > 1 else ThreatLevel.MEDIUM
        elif is_suspicious:
            threat_level = ThreatLevel.MEDIUM
        else:
            threat_level = ThreatLevel.LOW

        # Neutralize XML closing tags in user content to prevent breakout
        neutralized_text = re.sub(
            r"<\s*/\s*untrusted_content\s*>",
            "&lt;/untrusted_content&gt;",
            text,
            flags=re.IGNORECASE,
        )

        safe_prompt_text = (
            f"<untrusted_content>\n"
            f"{neutralized_text.strip()}\n"
            f"</untrusted_content>"
        )

        return SanitizedInput(
            safe_prompt_text=safe_prompt_text,
            is_suspicious=is_suspicious,
            detected_patterns=detected,
            threat_level=threat_level,
        )

