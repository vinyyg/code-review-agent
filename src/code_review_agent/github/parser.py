from __future__ import annotations

import json
import logging
import re
from typing import Optional

from code_review_agent.schema.report import SpecialistReport

logger = logging.getLogger(__name__)


def parse_report_from_comment(body: str) -> Optional[SpecialistReport]:
    """
    Extract and parse the machine-readable SpecialistReport
    from an existing PR comment body.

    The JSON is stored inside a <details> block like:
    <details>
    <summary>🤖 Machine-readable data...</summary>

```json
    { ... }
```

    </details>
    """
    json_str = _extract_json_block(body)
    if not json_str:
        logger.debug("No JSON block found in comment body.")
        return None

    try:
        data = json.loads(json_str)
        return SpecialistReport.model_validate(data)
    except (json.JSONDecodeError, Exception) as e:
        logger.warning(f"Failed to parse SpecialistReport from comment: {e}")
        return None


def extract_commit_sha(body: str) -> Optional[str]:
    """
    Extract the commit SHA from a review-agent comment.
    Looks for: **Commit reviewed:** `abc1234`
    """
    match = re.search(r"\*\*Commit reviewed:\*\*\s+`([a-f0-9]+)`", body)
    return match.group(1) if match else None


def extract_last_updated(body: str) -> Optional[str]:
    """
    Extract the last updated timestamp from a review-agent comment.
    Looks for: **Last updated:** 2026-05-27 20:00 UTC
    """
    match = re.search(r"\*\*Last updated:\*\*\s+(.+)", body)
    return match.group(1).strip() if match else None


# ── Helpers ───────────────────────────────────────────────────────────────────

def _extract_json_block(body: str) -> Optional[str]:
    """Extract JSON content from inside a ```json ... ``` block in <details>."""
    pattern = re.compile(
        r"<details>.*?```json\s*(.*?)\s*```.*?</details>",
        re.DOTALL,
    )
    match = pattern.search(body)
    if not match:
        return None
    return match.group(1).strip()