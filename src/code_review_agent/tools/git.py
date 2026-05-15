from __future__ import annotations

from pathlib import Path

from code_review_agent.tools.base import ToolResponse


# ─── Internal cache ───────────────────────────────────────────────────────────

_diff_cache: dict[str, str] = {}


# ─── Public API ───────────────────────────────────────────────────────────────

def load_diff(repo_root: Path, base_sha: str, head_sha: str) -> None:
    """
    Pre-compute and cache the full diff between base and head.
    Called once by the orchestrator at startup — not by the Claude agent directly.
    """
    import subprocess

    result = subprocess.run(
        ["git", "diff", f"{base_sha}..{head_sha}"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    _diff_cache["full"] = result.stdout
    _diff_cache["base_sha"] = base_sha
    _diff_cache["head_sha"] = head_sha


def get_diff(
    repo_root: Path,
    file: str | None = None,
    context_lines: int = 3,
) -> ToolResponse:
    """
    Return the diff being reviewed.
    Without arguments, returns the full diff.
    With a file argument, returns only that file's diff.
    """
    if "full" not in _diff_cache:
        return ToolResponse.failure(
            "Diff not loaded. The orchestrator must call load_diff() before starting agents."
        )

    full_diff = _diff_cache["full"]

    if not full_diff.strip():
        return ToolResponse.success({
            "base_sha": _diff_cache.get("base_sha"),
            "head_sha": _diff_cache.get("head_sha"),
            "diff": "",
            "note": "No changes found between base and head.",
        })

    if file is None:
        return ToolResponse.success({
            "base_sha": _diff_cache.get("base_sha"),
            "head_sha": _diff_cache.get("head_sha"),
            "diff": full_diff,
        })

    # Filter diff to a specific file
    file_diff = _extract_file_diff(full_diff, file)

    if not file_diff:
        return ToolResponse.failure(
            f"File '{file}' not found in the diff. "
            f"It may not have been modified in this PR."
        )

    return ToolResponse.success({
        "base_sha": _diff_cache.get("base_sha"),
        "head_sha": _diff_cache.get("head_sha"),
        "file": file,
        "diff": file_diff,
    })


def get_changed_files(repo_root: Path) -> list[str]:
    """
    Return the list of files changed in the diff.
    Used by the router to decide which specialists to activate.
    """
    if "full" not in _diff_cache:
        return []

    changed = []
    for line in _diff_cache["full"].splitlines():
        if line.startswith("diff --git "):
            # Format: "diff --git a/src/foo.py b/src/foo.py"
            parts = line.split(" ")
            if len(parts) >= 4:
                # Strip the "b/" prefix
                file_path = parts[3][2:]
                changed.append(file_path)

    return changed


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _extract_file_diff(full_diff: str, target_file: str) -> str:
    """Extract the diff section for a specific file from the full diff."""
    lines = full_diff.splitlines(keepends=True)
    result = []
    inside_target = False

    for line in lines:
        if line.startswith("diff --git "):
            # Check if this section is for our target file
            inside_target = f"b/{target_file}" in line or target_file in line

        if inside_target:
            result.append(line)

    return "".join(result)