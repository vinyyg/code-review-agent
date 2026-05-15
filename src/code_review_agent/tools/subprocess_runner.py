from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Optional

from code_review_agent.tools.base import ToolResponse


def run_command(
    cmd: list[str],
    cwd: Path,
    timeout: int = 30,
    input_data: Optional[str] = None,
) -> ToolResponse:
    """
    Run a subprocess command safely with timeout.

    Always use this instead of subprocess.run directly.
    Handles timeouts, missing executables, and unexpected errors
    returning structured ToolResponse instead of raising exceptions.
    """
    try:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
            input=input_data,
            check=False,
        )
        return ToolResponse.success({
            "stdout": result.stdout,
            "stderr": result.stderr,
            "exit_code": result.returncode,
        })

    except subprocess.TimeoutExpired:
        return ToolResponse.failure(
            f"Command timed out after {timeout}s: {' '.join(cmd)}"
        )

    except FileNotFoundError:
        return ToolResponse.failure(
            f"Executable not found: '{cmd[0]}'. "
            f"Make sure it is installed and available in PATH."
        )

    except Exception as e:
        return ToolResponse.failure(
            f"Unexpected error running '{cmd[0]}': {type(e).__name__}: {e}"
        )