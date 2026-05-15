from __future__ import annotations

from pathlib import Path

from code_review_agent.tools.base import PathTraversalError, ToolResponse, safe_resolve

# ─── Constants ────────────────────────────────────────────────────────────────

MAX_LINES_DEFAULT = 500
MAX_RESULTS_DEFAULT = 100

# Directories to skip when listing files
IGNORED_DIRS = {
    ".git", ".venv", "venv", "__pycache__", ".mypy_cache",
    ".ruff_cache", "node_modules", "dist", "build", ".eggs",
}


# ─── read_file ────────────────────────────────────────────────────────────────

def read_file(
    repo_root: Path,
    path: str,
    start_line: int | None = None,
    end_line: int | None = None,
) -> ToolResponse:
    """
    Read a file from the repository with optional line range.
    Lines are 1-indexed. Returns numbered lines for precise referencing.
    """
    try:
        resolved = safe_resolve(repo_root, path)
    except PathTraversalError as e:
        return ToolResponse.failure(str(e))

    if not resolved.exists():
        return ToolResponse.failure(f"File not found: '{path}'")

    if not resolved.is_file():
        return ToolResponse.failure(f"Path is not a file: '{path}'")

    try:
        lines = resolved.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as e:
        return ToolResponse.failure(f"Could not read file '{path}': {e}")

    total_lines = len(lines)

    # Normalize range (convert to 0-indexed for slicing)
    start = (start_line - 1) if start_line else 0
    end = end_line if end_line else total_lines

    # Clamp to valid range
    start = max(0, min(start, total_lines))
    end = max(start, min(end, total_lines))

    selected = lines[start:end]
    truncated = False

    # Protect against huge files flooding the context
    if len(selected) > MAX_LINES_DEFAULT:
        selected = selected[:MAX_LINES_DEFAULT]
        truncated = True

    # Prefix each line with its 1-indexed number
    numbered = "\n".join(
        f"{start + i + 1:>4}\t{line}"
        for i, line in enumerate(selected)
    )

    return ToolResponse.success({
        "path": path,
        "total_lines": total_lines,
        "range": [start + 1, start + len(selected)],
        "content": numbered,
        "truncated": truncated,
        **({"truncation_note": f"Showing first {MAX_LINES_DEFAULT} of {end - start} requested lines."} if truncated else {}),
    })


# ─── list_files ───────────────────────────────────────────────────────────────

def list_files(
    repo_root: Path,
    path: str,
    pattern: str = "**/*",
    max_results: int = MAX_RESULTS_DEFAULT,
) -> ToolResponse:
    """
    List files in a directory, filtered by glob pattern.
    Skips common non-source directories (.git, .venv, __pycache__, etc).
    """
    try:
        resolved = safe_resolve(repo_root, path)
    except PathTraversalError as e:
        return ToolResponse.failure(str(e))

    if not resolved.exists():
        return ToolResponse.failure(f"Directory not found: '{path}'")

    if not resolved.is_dir():
        return ToolResponse.failure(f"Path is not a directory: '{path}'")

    try:
        all_files = [
            p for p in resolved.glob(pattern)
            if p.is_file()
            and not any(part in IGNORED_DIRS for part in p.parts)
        ]
    except OSError as e:
        return ToolResponse.failure(f"Could not list files in '{path}': {e}")

    # Sort for deterministic output
    all_files.sort()

    truncated = len(all_files) > max_results
    shown = all_files[:max_results]

    # Return paths relative to repo root for portability
    relative_paths = [p.relative_to(repo_root).as_posix() for p in shown]

    return ToolResponse.success({
        "path": path,
        "pattern": pattern,
        "files": relative_paths,
        "total_found": len(all_files),
        "shown": len(shown),
        "truncated": truncated,
    })