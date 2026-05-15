from __future__ import annotations

import fnmatch
from dataclasses import dataclass, field
from pathlib import Path

from code_review_agent.schema.finding import Category


# ─── Activation decision ──────────────────────────────────────────────────────

@dataclass
class ActivationDecision:
    specialist: Category
    reason: str
    priority: bool = False


# ─── Rules ────────────────────────────────────────────────────────────────────

@dataclass
class SpecialistRules:
    patterns: list[str] = field(default_factory=list)
    priority_patterns: list[str] = field(default_factory=list)
    always_on: bool = False
    min_files_changed: int = 0
    min_lines_changed: int = 0


# Default rules for each specialist
DEFAULT_RULES: dict[Category, SpecialistRules] = {
    Category.QUALITY: SpecialistRules(
        always_on=True,
    ),
    Category.SECURITY: SpecialistRules(
        patterns=["**/*.py"],
        priority_patterns=[
            "**/auth/**",
            "**/security/**",
            "**/models/**",
            "**/*credential*",
            "**/*secret*",
            "**/settings*.py",
            "**/.env*",
            "**/config*.py",
        ],
    ),
    Category.ARCHITECTURE: SpecialistRules(
        patterns=["**/*.py"],
        min_files_changed=3,
        min_lines_changed=50,
    ),
    Category.TESTING: SpecialistRules(
        patterns=[
            "**/tests/**",
            "**/test_*.py",
            "**/*_test.py",
            "**/conftest.py",
        ],
    ),
}


# ─── Activator ────────────────────────────────────────────────────────────────

@dataclass
class DiffStats:
    files_changed: int
    lines_changed: int


def decide_specialists(
    changed_files: list[str],
    diff_stats: DiffStats,
    rules: dict[Category, SpecialistRules] | None = None,
) -> list[ActivationDecision]:
    """
    Decide which specialists to activate based on changed files and diff stats.
    Returns a list of ActivationDecision, one per activated specialist.
    """
    if rules is None:
        rules = DEFAULT_RULES

    decisions: list[ActivationDecision] = []
    has_src_changes = _has_src_changes(changed_files)
    has_test_changes = _has_test_changes(changed_files)

    for specialist, spec_rules in rules.items():

        # Always on
        if spec_rules.always_on:
            decisions.append(ActivationDecision(
                specialist=specialist,
                reason="always_on",
                priority=False,
            ))
            continue

        # Testing: also activate when src changed but no tests changed
        if specialist == Category.TESTING:
            if has_src_changes and not has_test_changes:
                decisions.append(ActivationDecision(
                    specialist=specialist,
                    reason="missing_tests",
                    priority=True,
                ))
                continue

        # Pattern match
        if not _matches_any(changed_files, spec_rules.patterns):
            continue

        # Threshold checks
        if spec_rules.min_files_changed and diff_stats.files_changed < spec_rules.min_files_changed:
            continue
        if spec_rules.min_lines_changed and diff_stats.lines_changed < spec_rules.min_lines_changed:
            continue

        priority = _matches_any(changed_files, spec_rules.priority_patterns)

        decisions.append(ActivationDecision(
            specialist=specialist,
            reason="pattern_match",
            priority=priority,
        ))

    return decisions


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _matches_any(files: list[str], patterns: list[str]) -> bool:
    """Return True if any file matches any pattern."""
    return any(
        fnmatch.fnmatch(f, pattern)
        for f in files
        for pattern in patterns
    )


def _has_src_changes(files: list[str]) -> bool:
    """Return True if any non-test Python file was changed."""
    return any(
        f.endswith(".py") and not _is_test_file(f)
        for f in files
    )


def _has_test_changes(files: list[str]) -> bool:
    """Return True if any test file was changed."""
    return any(_is_test_file(f) for f in files)


def _is_test_file(path: str) -> bool:
    name = Path(path).name
    parts = Path(path).parts
    return (
        name.startswith("test_")
        or name.endswith("_test.py")
        or "tests" in parts
        or "conftest" in name
    )