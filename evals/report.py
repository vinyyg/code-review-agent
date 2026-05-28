from statistics import mean


def generate_html_report(evaluation_results: list[dict], specialist: str) -> str:
    total_tests = len(evaluation_results)
    scores = [r["score"] for r in evaluation_results]
    avg_score = mean(scores) if scores else 0
    pass_rate = (
        100 * len([s for s in scores if s >= 7]) / total_tests
        if total_tests else 0
    )

    def score_class(score):
        if score >= 7:
            return "score-high"
        elif score >= 4:
            return "score-medium"
        return "score-low"

    rows = ""
    for r in evaluation_results:
        tc = r["test_case"]
        sc = score_class(r["score"])
        code = tc["prompt_inputs"]["code"].replace("<", "&lt;").replace(">", "&gt;")
        rows += f"""
        <tr>
            <td>{tc["scenario"]}</td>
            <td><pre>{code}</pre></td>
            <td>{tc["solution_criteria"]}</td>
            <td class="output"><pre>{r["output"][:800]}</pre></td>
            <td class="score-col">
                <span class="score {sc}">{r["score"]}/10</span>
                <br><small>{r["reasoning"][:200]}</small>
            </td>
        </tr>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>{specialist.title()} Specialist — Prompt Eval</title>
    <style>
        body {{ font-family: Arial, sans-serif; padding: 20px; color: #333; }}
        .header {{ background: #f0f0f0; padding: 20px; border-radius: 5px; margin-bottom: 20px; }}
        .summary-stats {{ display: flex; gap: 10px; flex-wrap: wrap; }}
        .stat-box {{
            background: #fff; border-radius: 5px; padding: 15px;
            box-shadow: 0 2px 5px rgba(0,0,0,0.1); min-width: 180px;
        }}
        .stat-value {{ font-size: 24px; font-weight: bold; margin-top: 5px; }}
        table {{ width: 100%; border-collapse: collapse; margin-top: 20px; }}
        th {{ background: #4a4a4a; color: white; text-align: left; padding: 12px; }}
        td {{ padding: 10px; border-bottom: 1px solid #ddd; vertical-align: top; width: 20%; }}
        pre {{
            background: #f5f5f5; border: 1px solid #ddd; border-radius: 4px;
            padding: 10px; font-size: 13px; white-space: pre-wrap; word-wrap: break-word;
        }}
        .score {{ font-weight: bold; padding: 5px 10px; border-radius: 3px; display: inline-block; }}
        .score-high {{ background: #c8e6c9; color: #2e7d32; }}
        .score-medium {{ background: #fff9c4; color: #f57f17; }}
        .score-low {{ background: #ffcdd2; color: #c62828; }}
        .score-col {{ width: 140px; }}
        tr:nth-child(even) {{ background: #f9f9f9; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>🔍 {specialist.title()} Specialist — Prompt Evaluation</h1>
        <div class="summary-stats">
            <div class="stat-box">
                <div>Total Cases</div>
                <div class="stat-value">{total_tests}</div>
            </div>
            <div class="stat-box">
                <div>Average Score</div>
                <div class="stat-value">{avg_score:.1f} / 10</div>
            </div>
            <div class="stat-box">
                <div>Pass Rate (≥7)</div>
                <div class="stat-value">{pass_rate:.1f}%</div>
            </div>
        </div>
    </div>
    <table>
        <thead>
            <tr>
                <th>Scenario</th>
                <th>Code</th>
                <th>Solution Criteria</th>
                <th>Output</th>
                <th>Score</th>
            </tr>
        </thead>
        <tbody>{rows}</tbody>
    </table>
</body>
</html>"""