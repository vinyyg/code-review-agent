from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from code_review_agent.core.agent_loop import AgentConfig, AgentResult, run_agent_async
from code_review_agent.core.prompt_builder import build_system_prompt, build_user_message
from code_review_agent.schema.finding import Category
from code_review_agent.schema.report import SpecialistReport
from code_review_agent.schema.routing import SpecialistRunInput
from code_review_agent.tools.registry import ToolRegistry, build_registry

logger = logging.getLogger(__name__)

STAGGER_SECONDS = 15

SPECIALIST_TOOLS: dict[Category, list[str]] = {
    Category.QUALITY:      ["get_diff", "read_file", "list_files", "run_ruff", "run_radon", "submit_findings"],
    Category.SECURITY:     ["get_diff", "read_file", "list_files", "run_bandit", "submit_findings"],
    Category.ARCHITECTURE: ["get_diff", "read_file", "list_files", "run_radon", "submit_findings"],
    Category.TESTING:      ["get_diff", "read_file", "list_files", "submit_findings"],
}


def build_scoped_registry(full_registry: ToolRegistry, specialist: Category) -> ToolRegistry:
    """Return a registry with only the tools for this specialist."""
    allowed = set(SPECIALIST_TOOLS.get(specialist, []))
    scoped = ToolRegistry(full_registry._repo_root)
    for name in full_registry.names():
        if name in allowed:
            scoped.register(full_registry._tools[name])
    return scoped


async def run_all_specialists(
    run_inputs: list[SpecialistRunInput],
    repo_root: Path,
    agent_config: AgentConfig | None,
) -> tuple[list[SpecialistReport], list[AgentResult], list[str]]:
    """Run all specialists in parallel with staggered start times."""
    full_registry = build_registry(repo_root)

    async def run_with_delay(inp: SpecialistRunInput, delay: float):
        if delay > 0:
            await asyncio.sleep(delay)
        return await _run_single(inp, full_registry, agent_config)

    tasks = [
        run_with_delay(inp, i * STAGGER_SECONDS)
        for i, inp in enumerate(run_inputs)
    ]

    results = await asyncio.gather(*tasks, return_exceptions=True)

    reports: list[SpecialistReport] = []
    agent_results: list[AgentResult] = []
    errors: list[str] = []

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


async def _run_single(
    run_input: SpecialistRunInput,
    full_registry: ToolRegistry,
    agent_config: AgentConfig | None,
) -> tuple[SpecialistReport | None, AgentResult]:
    """Run a single specialist agent and return its report."""
    specialist = run_input.specialist
    logger.info(f"Starting {specialist.value} specialist...")

    scoped_registry = build_scoped_registry(full_registry, specialist)
    system_prompt = build_system_prompt(run_input)
    user_message = build_user_message(run_input)

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