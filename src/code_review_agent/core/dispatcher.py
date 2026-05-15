from __future__ import annotations

import json
import logging
from pathlib import Path

import anthropic

from code_review_agent.schema.finding import Category
from code_review_agent.schema.routing import RoutingDecision, SpecialistInput
from code_review_agent.tools.registry import build_registry

logger = logging.getLogger(__name__)

# ─── Tool: submit_routing ─────────────────────────────────────────────────────

SUBMIT_ROUTING_SCHEMA = {
    "name": "submit_routing",
    "description": (
        "Submit the routing decision after investigating the diff. "
        "Call this exactly once when you have enough context to decide "
        "which specialists should review this PR and what they should focus on."
    ),
    "input_schema": RoutingDecision.model_json_schema(),
}

# ─── System prompt ────────────────────────────────────────────────────────────

DISPATCHER_SYSTEM_PROMPT = """You are a code review dispatcher. Your job is to analyze a diff and decide which specialist reviewers are needed.

Available specialists:
- quality: code smells, unused code, readability, PEP-8
- security: vulnerabilities, hardcoded secrets, injection, auth issues
- architecture: structural changes, high complexity, coupling, SOLID violations
- testing: missing tests, weak assertions, untested edge cases

Your workflow:
1. Call get_diff to see what changed
2. Call read_file to read context around changed lines (use line ranges, not full files)
3. Call submit_routing with your decision

Rules:
- quality is ALWAYS included
- Only include specialists that are genuinely relevant to the changes
- For each specialist, list only the files relevant to their focus
- Be specific in the focus field — give the specialist a concrete question to answer
- Keep context brief and factual
- Aim to finish in 3-6 tool calls

Do NOT perform the review yourself. Only route."""

# ─── Dispatcher ───────────────────────────────────────────────────────────────

def run_dispatcher(
    repo_root: Path,
    base_sha: str,
    head_sha: str,
    max_iterations: int = 8,
) -> RoutingDecision | None:
    """
    Run the dispatcher agent to decide which specialists to activate.
    Returns RoutingDecision on success, None on failure (caller should fall back to rules).
    """
    client = anthropic.Anthropic()
    registry = build_registry(repo_root)

    # Dispatcher only needs read tools + submit_routing
    dispatcher_tools = [
        t for t in registry.schemas()
        if t["name"] in {"get_diff", "read_file", "list_files"}
    ]
    dispatcher_tools.append(SUBMIT_ROUTING_SCHEMA)

    messages = [{
        "role": "user",
        "content": (
            f"Analyze the diff between {base_sha[:7]} and {head_sha[:7]} "
            f"and decide which specialists should review this PR."
        ),
    }]

    for iteration in range(max_iterations):
        logger.debug(f"Dispatcher iteration {iteration + 1}/{max_iterations}")

        try:
            response = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=2048,
                temperature=0.1,
                system=DISPATCHER_SYSTEM_PROMPT,
                tools=dispatcher_tools,
                messages=messages,
            )
        except anthropic.APIError as e:
            logger.error(f"Dispatcher API error: {e}")
            return None

        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason == "end_turn":
            logger.warning("Dispatcher finished without calling submit_routing.")
            return None

        if response.stop_reason != "tool_use":
            logger.warning(f"Dispatcher unexpected stop reason: {response.stop_reason}")
            return None

        tool_results = []

        for block in response.content:
            if block.type != "tool_use":
                continue

            logger.info(f"Dispatcher tool: {block.name}")

            # Terminal condition
            if block.name == "submit_routing":
                try:
                    decision = RoutingDecision.model_validate(block.input)
                    logger.info(
                        f"Dispatcher routed to: "
                        f"{[s.specialist.value for s in decision.specialists]}"
                    )
                    return decision
                except Exception as e:
                    logger.error(f"Dispatcher submit_routing validation failed: {e}")
                    return None

            # Execute tool
            tool_response = registry.execute(block.name, block.input)
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": tool_response.to_content(),
                "is_error": not tool_response.ok,
            })

        if tool_results:
            messages.append({"role": "user", "content": tool_results})

    logger.warning(f"Dispatcher exceeded max iterations ({max_iterations}).")
    return None