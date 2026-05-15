from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from pathlib import Path

from code_review_agent.core.agent_loop import AgentConfig, AgentResult, run_agent_async
from code_review_agent.core.dispatcher import run_dispatcher
from code_review_agent.router.activator import (
    ActivationDecision,
    DiffStats,
    decide_specialists,
)
from code_review_agent.schema.finding import Category
from code_review_agent.schema.report import SpecialistReport
from code_review_agent.schema.routing import (
    RoutingDecision,
    SpecialistInput,
    SpecialistRunInput,
)
from code_review_agent.tools import git as git_module
from code_review_agent.tools.registry import ToolRegistry, build_registry

logger = logging.getLogger(__name__)


# ─── Tool kits per specialist ─────────────────────────────────────────────────

SPECIALIST_TOOLS: dict[Category, list[str]] = {
    Category.QUALITY:      ["get_diff", "read_file", "list_files", "run_ruff", "run_radon", "submit_findings"],
    Category.SECURITY:     ["get_diff", "read_file", "list_files", "run_bandit", "submit_findings"],
    Category.ARCHITECTURE: ["get_diff", "read_file", "list_files", "run_radon", "submit_findings"],
    Category.TESTING:      ["get_diff", "read_file", "list_files", "submit_findings"],
}


# ─── System prompts ───────────────────────────────────────────────────────────

def _build_system_prompt(run_input: SpecialistRunInput) -> str:
    specialist = run_input.specialist
    inp = run_input.specialist_input

    context_block = f"\nContext from dispatcher:\n{inp.context}" if inp.context else ""
    focus_block = f"\nSpecific focus: {inp.focus}" if inp.focus else ""
    files_block = f"\nRelevant files: {', '.join(inp.relevant_files)}" if inp.relevant_files else ""

    update_block = ""
    if run_input.is_update and run_input.existing_comment:
        update_block = (
            f"\nThis is an UPDATE review. The previous review was on commit "
            f"{run_input.existing_comment.last_commit_sha[:7]}. "
            f"Focus on what changed since then."
        )

    full_scan_block = ""
    if run_input.full_scan:
        full_scan_block = "\nFULL SCAN MODE: Review the entire codebase, not just the diff."

    specialist_focus = {
        Category.QUALITY: """
Focus areas:
- Code smells (long functions, deep nesting, magic numbers)
- Unused variables, imports, dead code
- Readability and naming conventions
- PEP-8 violations beyond what ruff catches""",

        Category.SECURITY: """
Focus areas:
- Injection vulnerabilities (SQL, command, path traversal)
- Hardcoded secrets, credentials, API keys
- Missing authentication or authorization checks
- Insecure deserialization or use of eval/exec
- Weak cryptography or random number generation""",

        Category.ARCHITECTURE: """
Focus areas:
- High cyclomatic complexity (use run_radon)
- Tight coupling between modules
- Single responsibility principle violations
- Circular imports or dependency issues
- Structural changes that affect maintainability""",

        Category.TESTING: """
Focus areas:
- Missing tests for changed functionality
- Tests without meaningful assertions
- Missing edge cases (None, empty, boundary values)
- Over-mocking that makes tests fragile
- Test names that don't describe the scenario""",
    }

    return f"""You are a senior Python engineer performing a focused {specialist.value} review.

Your workflow:
1. Call get_diff to understand what changed
2. Investigate further using available tools — focus on relevant files only
3. Call submit_findings exactly once when done

Rules:
- Only report issues in the CHANGED code (lines in the diff)
- Be specific: include file, line numbers, and evidence
- Each suggestion must have a concrete old/new patch when possible
- Use the observation field for trade-offs, side-effects, or reasoning
- If you find nothing, submit with empty findings list and explain why
- Aim to finish in 5-10 tool calls
{context_block}{focus_block}{files_block}{update_block}{full_scan_block}
{specialist_focus[specialist]}"""


# ─── Orchestrator result ──────────────────────────────────────────────────────

@dataclass
class OrchestratorResult:
    reports: list[SpecialistReport] = field(default_factory=list)
    agent_results: list[AgentResult] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    routing: RoutingDecision | None = None
    used_fallback_router: bool = False

    @property
    def total_tokens(self) -> int:
        return sum(r.total_tokens for r in self.agent_results)

    @property
    def total_cost_usd(self) -> float:
        return sum(r.estimated_cost_usd for r in self.agent_results)

    @property
    def success(self) -> bool:
        return len(self.reports) > 0


# ─── Main entry point ─────────────────────────────────────────────────────────

def run_review(
    repo_root: Path,
    base_sha: str,
    head_sha: str,
    full_scan: bool = False,
    agent_config: AgentConfig | None = None,
) -> OrchestratorResult:
    """
    Main entry point for a code review run.

    Flow:
    1. Load diff
    2. Run dispatcher (or fallback to rules)
    3. Run specialists in parallel
    4. Return all reports
    """
    result = OrchestratorResult()

    # ── Load diff ─────────────────────────────────────────────────────────────
    logger.info(f"Loading diff {base_sha[:7]}..{head_sha[:7]}")
    git_module.load_diff(repo_root, base_sha, head_sha)
    changed_files = git_module.get_changed_files(repo_root)

    if not changed_files and not full_scan:
        logger.warning("No changed files found in diff.")
        return result

    logger.info(f"Changed files: {changed_files}")

    # ── Build routing ─────────────────────────────────────────────────────────
    run_inputs: list[SpecialistRunInput] = []

    if full_scan:
        logger.info("Full scan mode — activating all specialists.")
        run_inputs = _build_full_scan_inputs(repo_root)

    else:
        # Try dispatcher first
        logger.info("Running dispatcher...")
        routing = run_dispatcher(repo_root, base_sha, head_sha)

        if routing is not None:
            result.routing = routing
            run_inputs = [
                SpecialistRunInput(specialist_input=inp)
                for inp in routing.specialists
            ]
            logger.info(
                f"Dispatcher routed to: "
                f"{[i.specialist.value for i in run_inputs]}"
            )
        else:
            # Fallback to rule-based router
            logger.warning("Dispatcher failed — falling back to rule-based router.")
            result.used_fallback_router = True
            run_inputs = _build_fallback_inputs(changed_files, repo_root)
            logger.info(
                f"Fallback router activated: "
                f"{[i.specialist.value for i in run_inputs]}"
            )

    if not run_inputs:
        logger.warning("No specialists activated.")
        return result

    # ── Run specialists in parallel ───────────────────────────────────────────
    full_registry = build_registry(repo_root)
    reports, agent_results, errors = asyncio.run(
        _run_specialists_parallel(run_inputs, full_registry, agent_config)
    )

    result.reports = reports
    result.agent_results = agent_results
    result.errors = errors

    logger.info(
        f"Review complete — {len(reports)} reports, "
        f"{result.total_tokens} tokens, "
        f"~${result.total_cost_usd:.4f}"
    )

    return result


# ─── Parallel execution ───────────────────────────────────────────────────────

async def _run_specialists_parallel(
    run_inputs: list[SpecialistRunInput],
    full_registry: ToolRegistry,
    agent_config: AgentConfig | None,
) -> tuple[list[SpecialistReport], list[AgentResult], list[str]]:

    tasks = [
        _run_single_specialist(inp, full_registry, agent_config)
        for inp in run_inputs
    ]

    results = await asyncio.gather(*tasks, return_exceptions=True)

    reports = []
    agent_results = []
    errors = []

    for inp, result in zip(run_inputs, results):
        if isinstance(result, Exception):
            msg = f"{inp.specialist.value} raised exception: {result}"
            logger.error(msg)
            errors.append(msg)
            continue

        report, agent_result = result
        agent_results.append(agent_result)

        if report is not None:
            reports.append(report)
        elif agent_result.error:
            errors.append(f"{inp.specialist.value}: {agent_result.error}")

    return reports, agent_results, errors


async def _run_single_specialist(
    run_input: SpecialistRunInput,
    full_registry: ToolRegistry,
    agent_config: AgentConfig | None,
) -> tuple[SpecialistReport | None, AgentResult]:

    specialist = run_input.specialist
    logger.info(f"Starting {specialist.value} specialist...")

    scoped_registry = _scope_registry(full_registry, specialist)
    system_prompt = _build_system_prompt(run_input)
    user_message = _build_user_message(run_input)

    agent_result = await run_agent_async(
        system_prompt=system_prompt,
        user_message=user_message,
        registry=scoped_registry,
        config=agent_config,
    )

    if not agent_result.success:
        logger.error(f"{specialist.value} failed: {agent_result.error}")
        return None, agent_result

    try:
        report = SpecialistReport.model_validate(agent_result.output)
        logger.info(
            f"{specialist.value} done — "
            f"{len(report.findings)} findings, "
            f"{agent_result.total_tokens} tokens"
        )
        return report, agent_result
    except Exception as e:
        logger.error(f"{specialist.value} output validation failed: {e}")
        agent_result.error = f"Output validation failed: {e}"
        return None, agent_result


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _build_full_scan_inputs(repo_root: Path) -> list[SpecialistRunInput]:
    """Full scan: all specialists, all files, no dispatcher."""
    from code_review_agent.tools.filesystem import list_files
    all_files_response = list_files(repo_root, "src", pattern="**/*.py")
    all_files = (
        all_files_response.data.get("files", [])
        if all_files_response.ok else []
    )

    return [
        SpecialistRunInput(
            specialist_input=SpecialistInput(
                specialist=specialist,
                relevant_files=all_files,
                context="Full scan mode — review the entire codebase.",
                focus=None,
            ),
            full_scan=True,
        )
        for specialist in Category
    ]


def _build_fallback_inputs(
    changed_files: list[str],
    repo_root: Path,
) -> list[SpecialistRunInput]:
    """Fallback: use rule-based router when dispatcher fails."""
    full_diff = git_module._diff_cache.get("full", "")
    lines_changed = sum(
        1 for line in full_diff.splitlines()
        if (line.startswith("+") or line.startswith("-"))
        and not line.startswith("+++")
        and not line.startswith("---")
    )
    diff_stats = DiffStats(
        files_changed=len(changed_files),
        lines_changed=lines_changed,
    )
    decisions: list[ActivationDecision] = decide_specialists(changed_files, diff_stats)

    return [
        SpecialistRunInput(
            specialist_input=SpecialistInput(
                specialist=d.specialist,
                relevant_files=changed_files,
                context=f"Activated by rule: {d.reason}",
                focus=None,
            ),
        )
        for d in decisions
    ]


def _build_user_message(run_input: SpecialistRunInput) -> str:
    inp = run_input.specialist_input
    if run_input.full_scan:
        return f"Perform a full {inp.specialist.value} review of the codebase."
    files = ", ".join(inp.relevant_files) if inp.relevant_files else "the changed files"
    return f"Review the recent changes. Focus on: {files}."


def _scope_registry(full_registry: ToolRegistry, specialist: Category) -> ToolRegistry:
    """Return a registry with only the tools for this specialist."""
    from code_review_agent.tools.registry import ToolRegistry as TR
    allowed = set(SPECIALIST_TOOLS.get(specialist, []))
    scoped = TR(full_registry._repo_root)
    for name in full_registry.names():
        if name in allowed:
            scoped.register(full_registry._tools[name])
    return scoped