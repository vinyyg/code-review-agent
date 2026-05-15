from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from code_review_agent.tools.base import ToolResponse


# ─── Tool definition ──────────────────────────────────────────────────────────

@dataclass
class Tool:
    name: str
    schema: dict
    handler: Callable[..., ToolResponse]


# ─── Registry ─────────────────────────────────────────────────────────────────

class ToolRegistry:
    def __init__(self, repo_root: Path):
        self._tools: dict[str, Tool] = {}
        self._repo_root = repo_root

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def schemas(self) -> list[dict]:
        """Return all tool schemas for the Claude API tools= parameter."""
        return [
            {"name": t.name, "description": t.schema["description"], "input_schema": t.schema["input_schema"]}
            for t in self._tools.values()
        ]

    def execute(self, name: str, input: dict) -> ToolResponse:
        """Execute a tool by name with the given input from Claude."""
        if name not in self._tools:
            return ToolResponse.failure(
                f"Unknown tool: '{name}'. Available tools: {list(self._tools.keys())}"
            )
        try:
            return self._tools[name].handler(**input)
        except TypeError as e:
            return ToolResponse.failure(f"Invalid arguments for tool '{name}': {e}")
        except Exception as e:
            return ToolResponse.failure(
                f"Unexpected error in tool '{name}': {type(e).__name__}: {e}"
            )

    def names(self) -> list[str]:
        return list(self._tools.keys())


# ─── Factory ──────────────────────────────────────────────────────────────────

def build_registry(repo_root: Path) -> ToolRegistry:
    """
    Build and return a ToolRegistry with all tools registered.
    Each tool handler is pre-bound to repo_root so callers
    only need to pass the arguments Claude provides.
    """
    from code_review_agent.tools.filesystem import read_file, list_files
    from code_review_agent.tools.git import get_diff
    from code_review_agent.tools.static_analysis import run_ruff, run_bandit, run_radon
    from code_review_agent.tools.schemas import (
        READ_FILE, LIST_FILES, GET_DIFF,
        RUN_RUFF, RUN_BANDIT, RUN_RADON,
    )

    registry = ToolRegistry(repo_root)

    registry.register(Tool(
        name="read_file",
        schema=READ_FILE,
        handler=lambda **kw: read_file(repo_root, **kw),
    ))
    registry.register(Tool(
        name="list_files",
        schema=LIST_FILES,
        handler=lambda **kw: list_files(repo_root, **kw),
    ))
    registry.register(Tool(
        name="get_diff",
        schema=GET_DIFF,
        handler=lambda **kw: get_diff(repo_root, **kw),
    ))
    registry.register(Tool(
        name="run_ruff",
        schema=RUN_RUFF,
        handler=lambda **kw: run_ruff(repo_root, **kw),
    ))
    registry.register(Tool(
        name="run_bandit",
        schema=RUN_BANDIT,
        handler=lambda **kw: run_bandit(repo_root, **kw),
    ))
    registry.register(Tool(
        name="run_radon",
        schema=RUN_RADON,
        handler=lambda **kw: run_radon(repo_root, **kw),
    ))

    return registry