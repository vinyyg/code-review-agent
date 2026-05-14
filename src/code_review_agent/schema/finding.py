from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


# ─── Enums ────────────────────────────────────────────────────────────────────

class Severity(str, Enum):
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class Category(str, Enum):
    QUALITY = "quality"
    SECURITY = "security"
    ARCHITECTURE = "architecture"
    TESTING = "testing"


class SuggestionType(str, Enum):
    REPLACE = "replace"
    INSERT_BEFORE = "insert_before"
    INSERT_AFTER = "insert_after"
    DELETE = "delete"
    MANUAL = "manual"


# ─── Suggestion ───────────────────────────────────────────────────────────────

class Suggestion(BaseModel):
    type: SuggestionType

    old: Optional[str] = Field(
        default=None,
        description="Original code to be replaced or removed. Required for replace and delete.",
    )
    new: Optional[str] = Field(
        default=None,
        description="New code. Required for replace, insert_before, insert_after.",
    )
    anchor_line: Optional[int] = Field(
        default=None,
        description="Reference line for insertions. Falls back to Finding.line_start if omitted.",
    )
    observation: Optional[str] = Field(
        default=None,
        max_length=500,
        description="Free-text agent note: trade-offs, side-effects, reasoning, or why no patch was proposed.",
    )
    confidence: float = Field(..., ge=0.0, le=1.0)
    auto_applicable: bool = Field(
        ...,
        description="If True, a fix agent can apply this without human review.",
    )


# ─── Finding ──────────────────────────────────────────────────────────────────

class Finding(BaseModel):
    id: str = Field(
        ...,
        description="Specialist-prefixed sequence ID, e.g. 'sec-001', 'qual-003'.",
    )
    severity: Severity
    category: Category
    subcategory: str = Field(
        ...,
        description="Free-form tag within the category, e.g. 'sql-injection', 'dead-code', 'missing-test'.",
    )
    file: str = Field(..., description="Path relative to repo root.")
    line_start: int = Field(..., ge=1)
    line_end: int = Field(..., ge=1)
    title: str = Field(..., max_length=120)
    description: str = Field(..., max_length=1000)
    evidence: Optional[str] = Field(
        default=None,
        description="Short code snippet showing the problem.",
    )
    suggestion: Suggestion
    references: list[str] = Field(
        default_factory=list,
        description="Standards this finding relates to, e.g. ['CWE-89', 'OWASP-A03', 'PEP-8'].",
    )