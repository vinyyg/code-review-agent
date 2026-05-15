from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

import anthropic

from code_review_agent.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


# ─── Config ───────────────────────────────────────────────────────────────────

@dataclass
class AgentConfig:
    model: str = "claude-sonnet-4-20250514"
    max_iterations: int = 20
    max_tokens: int = 4096
    temperature: float = 0.2


# ─── Result ───────────────────────────────────────────────────────────────────

@dataclass
class AgentResult:
    success: bool
    output: dict | None = None        # parsed submit_findings input
    error: str | None = None
    iterations: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    tools_called: list[str] = field(default_factory=list)

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    @property
    def estimated_cost_usd(self) -> float:
        # claude-sonnet-4 pricing: $3/M input, $15/M output
        return (self.input_tokens * 3 + self.output_tokens * 15) / 1_000_000


# ─── Agent loop ───────────────────────────────────────────────────────────────

def run_agent(
    system_prompt: str,
    user_message: str,
    registry: ToolRegistry,
    submit_tool_name: str = "submit_findings",
    config: AgentConfig | None = None,
) -> AgentResult:
    """
    Generic agentic loop using Claude tool use.

    Runs until Claude calls submit_tool_name (success),
    exceeds max_iterations (failure), or an API error occurs.

    The registry provides both the tool schemas (sent to Claude)
    and the handlers (executed locally when Claude calls a tool).
    """
    if config is None:
        config = AgentConfig()

    client = anthropic.Anthropic()
    messages: list[dict[str, Any]] = [{"role": "user", "content": user_message}]

    result = AgentResult(success=False)

    for iteration in range(config.max_iterations):
        result.iterations = iteration + 1
        logger.debug(f"Iteration {iteration + 1}/{config.max_iterations}")

        # ── Call Claude ───────────────────────────────────────────────────────
        try:
            response = client.messages.create(
                model=config.model,
                max_tokens=config.max_tokens,
                temperature=config.temperature,
                system=system_prompt,
                tools=registry.schemas(),
                messages=messages,
            )
        except anthropic.APIError as e:
            result.error = f"Anthropic API error: {e}"
            return result

        # ── Track token usage ─────────────────────────────────────────────────
        result.input_tokens += response.usage.input_tokens
        result.output_tokens += response.usage.output_tokens

        # ── Append assistant response to history ──────────────────────────────
        messages.append({"role": "assistant", "content": response.content})

        # ── Check stop reason ─────────────────────────────────────────────────
        if response.stop_reason == "end_turn":
            result.error = "Agent finished without calling submit_findings."
            return result

        if response.stop_reason != "tool_use":
            result.error = f"Unexpected stop reason: {response.stop_reason}"
            return result

        # ── Process tool calls ────────────────────────────────────────────────
        tool_results = []

        for block in response.content:
            if block.type != "tool_use":
                continue

            tool_name = block.name
            tool_input = block.input
            result.tools_called.append(tool_name)

            logger.info(f"Tool called: {tool_name}({json.dumps(tool_input)[:120]})")

            # ── Submit findings — terminal condition ──────────────────────────
            if tool_name == submit_tool_name:
                result.success = True
                result.output = tool_input
                _log_summary(result)
                return result

            # ── Execute tool and collect result ───────────────────────────────
            tool_response = registry.execute(tool_name, tool_input)

            tool_results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": tool_response.to_content(),
                "is_error": not tool_response.ok,
            })

        # ── Send tool results back to Claude ──────────────────────────────────
        if tool_results:
            messages.append({"role": "user", "content": tool_results})

    # ── Max iterations reached ────────────────────────────────────────────────
    result.error = (
        f"Agent exceeded max iterations ({config.max_iterations}) "
        f"without calling {submit_tool_name}."
    )
    return result


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _log_summary(result: AgentResult) -> None:
    logger.info(
        f"Agent finished — iterations: {result.iterations}, "
        f"tokens: {result.total_tokens} "
        f"(~${result.estimated_cost_usd:.4f}), "
        f"tools: {result.tools_called}"
    )
async def run_agent_async(
    system_prompt: str,
    user_message: str,
    registry: ToolRegistry,
    submit_tool_name: str = "submit_findings",
    config: AgentConfig | None = None,
) -> AgentResult:
    """
    Async wrapper around run_agent for parallel specialist execution.
    Runs the synchronous agent in a thread pool to avoid blocking the event loop.
    """
    import asyncio
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None,  # default ThreadPoolExecutor
        lambda: run_agent(
            system_prompt=system_prompt,
            user_message=user_message,
            registry=registry,
            submit_tool_name=submit_tool_name,
            config=config,
        )
    )    