from __future__ import annotations

import json
import concurrent.futures
from pathlib import Path
from statistics import mean

import anthropic
from dotenv import load_dotenv

from evals.report import generate_html_report

load_dotenv()


class SpecialistEvaluator:
    """
    Evaluates a specialist prompt against a dataset of code cases.
    Adapted from the Anthropic 'Building with Claude API' course.
    """

    def __init__(self, max_concurrent_tasks: int = 1):
        self.client = anthropic.Anthropic()
        self.max_concurrent_tasks = max_concurrent_tasks

    def generate_dataset(
        self,
        specialist: str,
        issues_to_cover: list[str],
        output_file: str,
        num_cases: int = 5,
    ) -> list[dict]:
        prompt = f"""Generate {num_cases} Python code test cases to evaluate a {specialist} code reviewer.

Each test case must cover a DIFFERENT issue from this list:
{json.dumps(issues_to_cover, indent=2)}

Return ONLY a JSON array. Each item must have exactly these fields:
{{
  "scenario": "short name of the issue being tested",
  "prompt_inputs": {{
    "code": "the Python code snippet with the issue (10-30 lines)"
  }},
  "solution_criteria": "exactly what the reviewer must identify to pass"
}}

Rules for the code snippets:
- Each snippet must have exactly ONE clear issue to find
- Use realistic variable and function names
- Do NOT add comments pointing to the issue
- Keep snippets short (10-30 lines)
- Do NOT include real API keys, passwords, or secrets — use obviously fake placeholders like FAKE_KEY_HERE

Return ONLY the JSON array, no markdown, no explanation."""

        response = self.client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
        )

        raw = response.content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        raw = raw.strip()

        dataset = json.loads(raw)

        Path(output_file).parent.mkdir(parents=True, exist_ok=True)
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(dataset, f, indent=2)

        print(f"Generated {len(dataset)} test cases → {output_file}")
        return dataset

    def grade_output(
        self,
        test_case: dict,
        output: str,
        extra_criteria: str | None = None,
    ) -> dict:
        criteria = test_case["solution_criteria"]
        if extra_criteria:
            criteria += f"\n{extra_criteria}"

        prompt = f"""You are grading a code review output.

CODE BEING REVIEWED:
{test_case["prompt_inputs"]["code"]}

SOLUTION CRITERIA (what must be found to pass):
{criteria}

REVIEWER OUTPUT:
{output}

Grade the output from 0 to 10:
- 9-10: Correctly identified the issue, correct severity, actionable suggestion
- 7-8: Identified the issue, minor gaps in severity or suggestion
- 4-6: Partially identified the issue or found it but missed key details
- 1-3: Missed the issue or reported something unrelated
- 0: No useful output

Respond ONLY with this JSON:
{{"score": <integer 0-10>, "reasoning": "<one sentence explanation>"}}"""

        response = self.client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=256,
            temperature=0.0,
            messages=[{"role": "user", "content": prompt}],
        )

        raw = response.content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]

        return json.loads(raw.strip())

    def run_test_case(
        self,
        test_case: dict,
        run_prompt_function,
        extra_criteria: str | None = None,
    ) -> dict:
        output = run_prompt_function(test_case["prompt_inputs"])
        grade = self.grade_output(test_case, output, extra_criteria)

        return {
            "output": output,
            "test_case": test_case,
            "score": grade["score"],
            "reasoning": grade["reasoning"],
        }

    def run_evaluation(
        self,
        specialist: str,
        run_prompt_function,
        dataset_file: str,
        extra_criteria: str | None = None,
        reports_dir: str = "evals/reports",
    ) -> list[dict]:
        with open(dataset_file, "r", encoding="utf-8") as f:
            dataset = json.load(f)

        results = []
        completed = 0
        total = len(dataset)

        with concurrent.futures.ThreadPoolExecutor(
            max_workers=self.max_concurrent_tasks
        ) as executor:
            futures = {
                executor.submit(
                    self.run_test_case, tc, run_prompt_function, extra_criteria
                ): tc
                for tc in dataset
            }

            for future in concurrent.futures.as_completed(futures):
                result = future.result()
                results.append(result)
                completed += 1
                print(f"Graded {completed}/{total} — score: {result['score']}/10")

        avg = mean([r["score"] for r in results])
        print(f"\nAverage score: {avg:.1f}/10")

        json_path = Path(reports_dir) / f"{specialist}_results.json"
        json_path.parent.mkdir(parents=True, exist_ok=True)
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2)

        html_path = Path(reports_dir) / f"{specialist}_report.html"
        html = generate_html_report(results, specialist)
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html)

        print(f"Report saved → {html_path}")
        return results