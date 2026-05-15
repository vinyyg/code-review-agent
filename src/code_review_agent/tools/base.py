from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel


# ─── Response ─────────────────────────────────────────────────────────────────

class ToolResponse(BaseModel):
    ok: bool
    data: Optional[Any] = None
    error: Optional[str] = None

    def to_content(self) -> str:
        """Serialize to string for sending back to Claude as tool_result content."""
        return json.dumps(self.model_dump(exclude_none=True), indent=2)

    @classmethod
    def success(cls, data: Any) -> ToolResponse:
        return cls(ok=True, data=data)

    @classmethod
    def failure(cls, error: str) -> ToolResponse:
        return cls(ok=False, error=error)


# ─── Path safety ──────────────────────────────────────────────────────────────

class PathTraversalError(Exception):
    pass


def safe_resolve(repo_root: Path, user_path: str) -> Path:
    """
    Resolve user_path relative to repo_root, ensuring it stays inside the repo.

    Raises PathTraversalError if the resolved path escapes the repo root.
    This prevents path traversal attacks like '../../etc/passwd'.
    """
    resolved = (repo_root / user_path).resolve()

    try:
        resolved.relative_to(repo_root.resolve())
    except ValueError:
        raise PathTraversalError(
            f"Path '{user_path}' escapes the repository root. "
            f"All paths must be relative to the repo root."
        )

    return resolved