"""
Prompt evaluation pipeline for all specialists.

Usage:
    python evals/run_evals.py                        # all specialists
    python evals/run_evals.py --specialist security  # one only
    python evals/run_evals.py --skip-generate        # reuse existing datasets
"""
from __future__ import annotations

import argparse
from pathlib import Path

import anthropic
from dotenv import load_dotenv

load_dotenv()

from evals.evaluator import SpecialistEvaluator
from code_review_agent.core.prompts import get_specialist_prompt


# ── Specialist configs ────────────────────────────────────────────────────────

SPECIALIST_CONFIGS = {
    "security": {
        "issues": [
            "SQL injection via string interpolation",
            "Hardcoded API key or password (use fake placeholder)",
            "Use of eval() with user input",
            "subprocess call with shell=True",
            "Missing authentication check on endpoint",
        ],
        "extra_criteria": (
            "The reviewer must identify the specific vulnerability type, "
            "explain the concrete risk ('an attacker could...'), "
            "and suggest a secure alternative."
        ),
    },
    "quality": {
        "issues": [
            "Unused import statement",
            "Dead code (unreachable or unused variable)",
            "Magic number without named constant",
            "Misleading or unclear variable name",
            "Function doing too many things (multiple responsibilities)",
        ],
        "extra_criteria": (
            "The reviewer must identify the specific smell, "
            "explain why it harms readability or maintainability, "
            "and suggest a concrete improvement."
        ),
    },
    "architecture": {
        "issues": [
            "Function with cyclomatic complexity > 10",
            "Class with more than one clear responsibility (SRP violation)",
            "Tight coupling between two modules",
            "Function longer than 50 lines",
            "Missing dependency injection (hardcoded dependency)",
        ],
        "extra_criteria": (
            "The reviewer must identify the structural problem, "
            "explain the future maintainability impact, "
            "and suggest a refactoring approach."
        ),
    },
    "testing": {
        "issues": [
            "Test with no meaningful assertion",
            "Missing test for a new public function",
            "Test that mocks the thing under test",
            "Missing edge case: None or empty input",
            "Test name that does not describe the scenario",
        ],
        "extra_criteria": (
            "The reviewer must identify the specific testing weakness, "
            "explain why it makes the test unreliable or incomplete, "
            "and suggest a concrete fix."
        ),
    },
}


# ── Prompt runner ─────────────────────────────────────────────────────────────

def make_prompt_runner(specialist: str):
    """
    Returns a function that sends a code snippet to the specialist prompt
    and returns the raw model output.
    No tool use — single API call per test case (cheap and fast).
    """
    system_prompt = get_specialist_prompt(specialist)
    client = anthropic.Anthropic()

    def run_prompt(prompt_inputs: dict) -> str:
        code = prompt_inputs["code"]
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1024,
            temperature=0.1,
            system=system_prompt,
            messages=[{
                "role": "user",
                "content": (
                    f"Review this Python code and identify any {specialist} issues.\n\n"
                    f"```python\n{code}\n```\n\n"
                    f"Describe what you find. Be specific about file location "
                    f"(assume file is 'review_target.py'), line numbers, and suggestions."
                ),
            }],
        )
        return response.content[0].text

    return run_prompt


# ── Main ──────────────────────────────────────────────────────────────────────

def run(specialists: list[str], skip_generate: bool) -> None:
    evaluator = SpecialistEvaluator(max_concurrent_tasks=1)

    for specialist in specialists:
        print(f"\n{'='*50}")
        print(f"Evaluating: {specialist.upper()}")
        print(f"{'='*50}")

        config = SPECIALIST_CONFIGS[specialist]
        dataset_file = f"evals/datasets/{specialist}.json"

        if not skip_generate or not Path(dataset_file).exists():
            print("Generating dataset...")
            evaluator.generate_dataset(
                specialist=specialist,
                issues_to_cover=config["issues"],
                output_file=dataset_file,
                num_cases=5,
            )
        else:
            print(f"Reusing existing dataset: {dataset_file}")

        print("Running evaluation...")
        evaluator.run_evaluation(
            specialist=specialist,
            run_prompt_function=make_prompt_runner(specialist),
            dataset_file=dataset_file,
            extra_criteria=config["extra_criteria"],
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Run prompt evaluations for specialist agents."
    )
    parser.add_argument(
        "--specialist",
        choices=list(SPECIALIST_CONFIGS.keys()),
        help="Run eval for a single specialist only",
    )
    parser.add_argument(
        "--skip-generate",
        action="store_true",
        help="Skip dataset generation and reuse existing datasets",
    )
    args = parser.parse_args()

    specialists = (
        [args.specialist] if args.specialist
        else list(SPECIALIST_CONFIGS.keys())
    )

    run(specialists, args.skip_generate)