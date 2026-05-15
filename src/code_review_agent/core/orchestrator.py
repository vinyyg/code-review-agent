from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from pathlib import Path

from code_review_agent.core.agent_loop import AgentConfig, AgentResult
from code_review_agent.core.dispatcher import run_dispatcher
from code_review_agent.core.routing_builder import (
    build_dispatcher_inputs,
    build_fallback_inputs,
    build_full_scan_inputs,
)
from code_review_agent.core.specialist_runner import run_all_specialists
from code_review_agent.schema.report import SpecialistReport
from code_review_agent.schema.routing import RoutingDecision
from code_review_agent.tools import git as git_module

logger = logging.getLogger(__name__)


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


def run_review(
    repo_root: Path,
    base_sha: str,
    head_sha: str,
    full_scan: bool = False,
    agent_config: AgentConfig | None = None,
) -> OrchestratorResult:
    result = OrchestratorResult()

    # Load diff
    logger.info(f"Loading diff {base_sha[:7]}..{head_sha[:7]}")
    git_module.load_diff(repo_root, base_sha, head_sha)
    changed_files = git_module.get_changed_files(repo_root)

    if not changed_files and not full_scan:
        logger.warning("No changed files found in diff.")
        return result

    logger.info(f"Changed files: {changed_files}")

    # Build routing
    if full_scan:
        logger.info("Full scan mode — activating all specialists.")
        run_inputs = build_full_scan_inputs(repo_root)

    else:
        logger.info("Running dispatcher...")
        routing = run_dispatcher(repo_root, base_sha, head_sha)

        if routing is not None:
            result.routing = routing
            run_inputs = build_dispatcher_inputs(routing)
            logger.info(f"Dispatcher routed to: {[i.specialist.value for i in run_inputs]}")
        else:
            logger.warning("Dispatcher failed — falling back to rule-based router.")
            result.used_fallback_router = True
            run_inputs = build_fallback_inputs(changed_files)
            logger.info(f"Fallback activated: {[i.specialist.value for i in run_inputs]}")

    if not run_inputs:
        logger.warning("No specialists activated.")
        return result

    # Run specialists
    reports, agent_results, errors = asyncio.run(
        run_all_specialists(run_inputs, repo_root, agent_config)
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