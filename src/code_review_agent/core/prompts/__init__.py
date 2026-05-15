from __future__ import annotations

from pathlib import Path

_PROMPTS_DIR = Path(__file__).parent
_OUTPUT_FORMAT = (_PROMPTS_DIR / "output_format.md").read_text(encoding="utf-8")


def get_specialist_prompt(specialist_name: str) -> str:
    valid = ["quality", "security", "architecture", "testing"]
    if specialist_name not in valid:
        raise ValueError(f"Unknown specialist: '{specialist_name}'. Valid: {valid}")
    base = (_PROMPTS_DIR / f"{specialist_name}.md").read_text(encoding="utf-8")
    return base + "\n" + _OUTPUT_FORMAT


def get_dispatcher_prompt() -> str:
    return (_PROMPTS_DIR / "dispatcher.md").read_text(encoding="utf-8")


def list_specialists() -> list[str]:
    return ["quality", "security", "architecture", "testing"]