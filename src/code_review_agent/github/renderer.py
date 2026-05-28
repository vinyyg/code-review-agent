from __future__ import annotations

import json
from datetime import datetime, timezone

from code_review_agent.schema.finding import Severity
from code_review_agent.schema.report import SpecialistReport

# ── Markers ───────────────────────────────────────────────────────────────────

def make_marker(specialist: str) -> str:
    return f"<!-- review-agent:specialist={specialist}:v=1 -->"

def make_end_marker(specialist: str) -> str:
    return f"<!-- /review-agent:specialist={specialist} -->"

def extract_specialist_from_marker(body: str) -> str | None:
    """Extract specialist name from a comment marker."""
    import re
    match = re.search(r"review-agent:specialist=(\w+):", body)
    return match.group(1) if match else None

# ── Status ────────────────────────────────────────────────────────────────────

def _status_line(report: SpecialistReport) -> str:
    if not report.findings:
        return "**Status:** ✅ No issues found"

    critical_high = [
        f for f in report.findings
        if f.severity in (Severity.CRITICAL, Severity.HIGH)
    ]
    if critical_high:
        return f"**Status:** 🔴 {len(critical_high)} critical/high issue(s) found"

    return f"**Status:** ⚠️ {len(report.findings)} issue(s) found"

# ── Severity emoji ────────────────────────────────────────────────────────────

SEVERITY_EMOJI = {
    Severity.CRITICAL: "🔴",
    Severity.HIGH:     "🔴",
    Severity.MEDIUM:   "🟡",
    Severity.LOW:      "🔵",
    Severity.INFO:     "⚪",
}

# ── Renderer ──────────────────────────────────────────────────────────────────

SPECIALIST_EMOJI = {
    "quality":      "🔍",
    "security":     "🔒",
    "architecture": "🏗️",
    "testing":      "🧪",
}

def render_report(
    report: SpecialistReport,
    commit_sha: str,
) -> str:
    specialist = report.specialist.value
    emoji = SPECIALIST_EMOJI.get(specialist, "🤖")
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    marker = make_marker(specialist)
    end_marker = make_end_marker(specialist)

    # Header
    lines = [
        marker,
        "",
        f"## {emoji} {specialist.title()} Review",
        "",
        _status_line(report),
        f"**Commit reviewed:** `{commit_sha[:7]}`",
        f"**Last updated:** {timestamp}",
        "",
    ]

    # Summary
    if report.summary:
        lines += [report.summary, ""]

    # Findings
    if report.findings:
        lines.append("### Findings")
        lines.append("")

        for finding in report.findings:
            sev_emoji = SEVERITY_EMOJI.get(finding.severity, "⚪")
            lines.append(
                f"#### {sev_emoji} {finding.severity.value.title()} — {finding.title}"
            )
            lines.append(f"**File:** `{finding.file}:{finding.line_start}`")
            lines.append("")
            lines.append(finding.description)
            lines.append("")

            if finding.evidence:
                lines.append("```python")
                lines.append(finding.evidence)
                lines.append("```")
                lines.append("")

            if finding.suggestion:
                s = finding.suggestion
                if s.type.value != "manual" and s.old and s.new:
                    lines.append("**Suggested fix:**")
                    lines.append("```python")
                    lines.append(f"# Before")
                    lines.append(s.old)
                    lines.append(f"# After")
                    lines.append(s.new)
                    lines.append("```")
                    lines.append("")

                if s.observation:
                    lines.append(f"> 💡 {s.observation}")
                    lines.append("")

            if finding.references:
                refs = " · ".join(f"`{r}`" for r in finding.references)
                lines.append(f"**References:** {refs}")
                lines.append("")

            lines.append("---")
            lines.append("")
    else:
        lines.append("No issues found in this diff.")
        lines.append("")

    # Machine-readable JSON block
    lines += [
        "<details>",
        "<summary>🤖 Machine-readable data (for automated tools)</summary>",
        "",
        "```json",
        json.dumps(report.model_dump(), indent=2),
        "```",
        "",
        "</details>",
        "",
        end_marker,
    ]

    return "\n".join(lines)