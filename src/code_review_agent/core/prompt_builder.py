from __future__ import annotations

from code_review_agent.core.prompts import get_specialist_prompt
from code_review_agent.schema.routing import SpecialistRunInput


def build_system_prompt(run_input: SpecialistRunInput) -> str:
    """Build the full system prompt for a specialist run."""
    base = get_specialist_prompt(run_input.specialist.value)

    blocks: list[str] = []

    if run_input.specialist_input.context:
        blocks.append(
            f"## Dispatcher context\n{run_input.specialist_input.context}"
        )

    if run_input.specialist_input.focus:
        blocks.append(
            f"## Specific focus\n{run_input.specialist_input.focus}"
        )

    if run_input.specialist_input.relevant_files:
        files = "\n".join(
            f"- {f}" for f in run_input.specialist_input.relevant_files
        )
        blocks.append(f"## Relevant files\n{files}")

    if run_input.is_update and run_input.existing_comment:
        sha = run_input.existing_comment.last_commit_sha[:7]
        blocks.append(
            f"## Update context\n"
            f"This is an UPDATE. Previous review was on commit {sha}. "
            f"Focus on what changed since then."
        )

    if run_input.full_scan:
        blocks.append(
            "## Mode\nFULL SCAN — review the entire codebase, not just the diff."
        )

    return base + "\n\n" + "\n\n".join(blocks) if blocks else base


def build_user_message(run_input: SpecialistRunInput) -> str:
    """Build the user message for a specialist run."""
    if run_input.full_scan:
        return f"Perform a full {run_input.specialist.value} review of the codebase."

    files = (
        ", ".join(run_input.specialist_input.relevant_files)
        if run_input.specialist_input.relevant_files
        else "the changed files"
    )
    return f"Review the recent changes. Focus on: {files}."