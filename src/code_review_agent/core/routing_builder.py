from __future__ import annotations

import logging
from pathlib import Path

from code_review_agent.router.activator import DiffStats, decide_specialists
from code_review_agent.schema.finding import Category
from code_review_agent.schema.routing import SpecialistInput, SpecialistRunInput
from code_review_agent.tools import git as git_module
from code_review_agent.tools.filesystem import list_files

logger = logging.getLogger(__name__)


def build_full_scan_inputs(repo_root: Path) -> list[SpecialistRunInput]:
    """All specialists, all files, no dispatcher."""
    response = list_files(repo_root, "src", pattern="**/*.py")
    all_files = response.data.get("files", []) if response.ok else []

    return [
        SpecialistRunInput(
            specialist_input=SpecialistInput(
                specialist=specialist,
                relevant_files=all_files,
                context="Full scan mode — review the entire codebase.",
                focus=None,
            ),
            full_scan=True,
        )
        for specialist in Category
    ]


def build_dispatcher_inputs(
    routing,
) -> list[SpecialistRunInput]:
    """Convert dispatcher RoutingDecision into SpecialistRunInputs."""
    return [
        SpecialistRunInput(specialist_input=inp)
        for inp in routing.specialists
    ]


def build_fallback_inputs(changed_files: list[str]) -> list[SpecialistRunInput]:
    """Rule-based fallback when dispatcher fails."""
    full_diff = git_module._diff_cache.get("full", "")
    lines_changed = sum(
        1 for line in full_diff.splitlines()
        if (line.startswith("+") or line.startswith("-"))
        and not line.startswith("+++")
        and not line.startswith("---")
    )
    decisions = decide_specialists(
        changed_files,
        DiffStats(
            files_changed=len(changed_files),
            lines_changed=lines_changed,
        ),
    )
    return [
        SpecialistRunInput(
            specialist_input=SpecialistInput(
                specialist=d.specialist,
                relevant_files=changed_files,
                context=f"Activated by rule: {d.reason}",
                focus=None,
            ),
        )
        for d in decisions
    ]