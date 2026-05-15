from __future__ import annotations

import json
from pathlib import Path

from code_review_agent.tools.base import ToolResponse, safe_resolve, PathTraversalError
from code_review_agent.tools.subprocess_runner import run_command


# ─── run_ruff ─────────────────────────────────────────────────────────────────

def run_ruff(
    repo_root: Path,
    paths: list[str],
    select: list[str] | None = None,
) -> ToolResponse:
    """
    Run ruff linter on the given files.
    Returns structured violations filtered to the provided paths.
    """
    validated = _validate_paths(repo_root, paths)
    if isinstance(validated, ToolResponse):
        return validated

    cmd = ["ruff", "check", "--output-format", "json"] + paths
    if select:
        cmd += ["--select", ",".join(select)]

    result = run_command(cmd, cwd=repo_root)
    if not result.ok:
        return result

    stdout = result.data["stdout"]
    if not stdout.strip():
        return ToolResponse.success({"violations": [], "total": 0})

    try:
        raw = json.loads(stdout)
    except json.JSONDecodeError:
        return ToolResponse.failure(
            f"Could not parse ruff output as JSON. Raw output: {stdout[:300]}"
        )

    violations = [
        {
            "file": item["filename"],
            "line": item["location"]["row"],
            "column": item["location"]["column"],
            "code": item["code"],
            "message": item["message"],
            "fixable": item.get("fix") is not None,
        }
        for item in raw
    ]

    return ToolResponse.success({"violations": violations, "total": len(violations)})


# ─── run_bandit ───────────────────────────────────────────────────────────────

def run_bandit(
    repo_root: Path,
    paths: list[str],
    severity_threshold: str = "low",
) -> ToolResponse:
    """
    Run bandit security scanner on the given files.
    Returns structured findings above the severity threshold.
    """
    validated = _validate_paths(repo_root, paths)
    if isinstance(validated, ToolResponse):
        return validated

    severity_map = {"low": "l", "medium": "m", "high": "h"}
    level = severity_map.get(severity_threshold, "l")

    cmd = [
        "bandit",
        "--format", "json",
        "--severity-level", level,
        "--quiet",
        "-r",
    ] + paths

    result = run_command(cmd, cwd=repo_root)
    if not result.ok:
        return result

    stdout = result.data["stdout"]
    if not stdout.strip():
        return ToolResponse.success({"findings": [], "total": 0})

    try:
        raw = json.loads(stdout)
    except json.JSONDecodeError:
        return ToolResponse.failure(
            f"Could not parse bandit output as JSON. Raw output: {stdout[:300]}"
        )

    findings = [
        {
            "file": item["filename"],
            "line": item["line_number"],
            "severity": item["issue_severity"].lower(),
            "confidence": item["issue_confidence"].lower(),
            "code": item["test_id"],
            "message": item["issue_text"],
            "cwe": item.get("issue_cwe", {}).get("id"),
        }
        for item in raw.get("results", [])
    ]

    return ToolResponse.success({"findings": findings, "total": len(findings)})


# ─── run_radon ────────────────────────────────────────────────────────────────

def run_radon(
    repo_root: Path,
    paths: list[str],
    min_complexity: int = 10,
) -> ToolResponse:
    """
    Compute cyclomatic complexity (CC) per function and
    maintainability index (MI) per file using radon.
    Only reports functions with CC >= min_complexity.
    """
    validated = _validate_paths(repo_root, paths)
    if isinstance(validated, ToolResponse):
        return validated

    # Cyclomatic complexity
    cc_result = run_command(
        ["radon", "cc", "--json", "--min", "A"] + paths,
        cwd=repo_root,
    )
    if not cc_result.ok:
        return cc_result

    # Maintainability index
    mi_result = run_command(
        ["radon", "mi", "--json"] + paths,
        cwd=repo_root,
    )
    if not mi_result.ok:
        return mi_result

    try:
        cc_raw = json.loads(cc_result.data["stdout"] or "{}")
        mi_raw = json.loads(mi_result.data["stdout"] or "{}")
    except json.JSONDecodeError as e:
        return ToolResponse.failure(f"Could not parse radon output: {e}")

    # Filter functions above min_complexity threshold
    complex_functions = []
    for file_path, functions in cc_raw.items():
        for fn in functions:
            if fn.get("complexity", 0) >= min_complexity:
                complex_functions.append({
                    "file": file_path,
                    "name": fn["name"],
                    "type": fn["type"],
                    "line": fn["lineno"],
                    "complexity": fn["complexity"],
                    "rank": fn["rank"],
                })

    # Maintainability index per file
    mi_scores = [
        {
            "file": file_path,
            "mi_score": round(data.get("mi", 0), 1),
            "rank": data.get("rank", "?"),
        }
        for file_path, data in mi_raw.items()
    ]

    return ToolResponse.success({
        "complex_functions": complex_functions,
        "complex_functions_total": len(complex_functions),
        "maintainability": mi_scores,
        "min_complexity_threshold": min_complexity,
    })


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _validate_paths(repo_root: Path, paths: list[str]) -> ToolResponse | None:
    """Validate all paths are inside the repo. Returns ToolResponse on error, None if ok."""
    if not paths:
        return ToolResponse.failure("At least one path must be provided.")

    for path in paths:
        try:
            safe_resolve(repo_root, path)
        except PathTraversalError as e:
            return ToolResponse.failure(str(e))

    return None