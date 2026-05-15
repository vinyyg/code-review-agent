from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from pydantic import BaseModel, Field

from code_review_agent.schema.finding import Category


# ─── Input pra cada specialist ────────────────────────────────────────────────

class SpecialistInput(BaseModel):
    specialist: Category
    relevant_files: list[str] = Field(
        ...,
        description="Files the specialist should focus on.",
    )
    context: str = Field(
        ...,
        description="What the dispatcher observed about these files.",
    )
    focus: Optional[str] = Field(
        default=None,
        description="Specific question or concern for the specialist to answer.",
    )


# ─── Decisão de roteamento do dispatcher ──────────────────────────────────────

class RoutingDecision(BaseModel):
    specialists: list[SpecialistInput] = Field(
        ...,
        description="List of specialists to activate with their focused inputs.",
    )
    dispatcher_summary: str = Field(
        ...,
        max_length=500,
        description="Brief summary of what the dispatcher found in the diff.",
    )


# ─── Estado do comentário existente ───────────────────────────────────────────

@dataclass
class ExistingComment:
    comment_id: int
    specialist: Category
    last_commit_sha: str
    body: str


# ─── Input completo pro specialist (dispatcher + estado do PR) ────────────────

@dataclass
class SpecialistRunInput:
    specialist_input: SpecialistInput
    existing_comment: Optional[ExistingComment] = None
    full_scan: bool = False

    @property
    def specialist(self) -> Category:
        return self.specialist_input.specialist

    @property
    def is_update(self) -> bool:
        return self.existing_comment is not None