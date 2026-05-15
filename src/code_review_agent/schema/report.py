from pydantic import BaseModel, Field
from code_review_agent.schema.finding import Category, Finding


class SpecialistReport(BaseModel):
    schema_version: str = Field(
        default="1.0",
        description="Version of this schema. Increment on breaking changes.",
    )
    specialist: Category
    findings: list[Finding] = Field(default_factory=list)
    summary: str = Field(
        ...,
        max_length=300,
        description="One-paragraph overview of the review for humans.",
    )
    tools_used: list[str] = Field(
        default_factory=list,
        description="Names of tools called during investigation.",
    )
    files_examined: list[str] = Field(
        default_factory=list,
        description="Files the specialist read or analyzed.",
    )