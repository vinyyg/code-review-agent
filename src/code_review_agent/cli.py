from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.logging import RichHandler
from rich.table import Table
from rich import print as rprint

from dotenv import load_dotenv
load_dotenv()

app = typer.Typer(
    name="review-agent",
    help="AI-powered Python code review agent built on Claude.",
    add_completion=False,
)

console = Console()


def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(message)s",
        handlers=[RichHandler(rich_tracebacks=True, show_path=False)],
    )


@app.command()
def run(
    base: str = typer.Option(..., help="Base commit SHA"),
    head: str = typer.Option(..., help="Head commit SHA"),
    clean: bool = typer.Option(False, "--clean", help="Delete comments from specialists not active in this run"),
    pr: Optional[int] = typer.Option(None, help="PR number to post comments to"),
    full_scan: bool = typer.Option(False, "--full-scan", help="Review entire codebase"),
    repo_path: Path = typer.Option(Path("."), "--repo", help="Path to repository"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose logging"),
) -> None:
    """Run a code review between two commits."""
    _setup_logging(verbose)
    logger = logging.getLogger(__name__)

    from code_review_agent.core.orchestrator import run_review
    from code_review_agent.core.agent_loop import AgentConfig

    console.rule("[bold blue]Code Review Agent")

    with console.status("[bold green]Running review..."):
        result = run_review(
            repo_root=repo_path.resolve(),
            base_sha=base,
            head_sha=head,
            full_scan=full_scan,
        )

    # Print summary table
    table = Table(title="Review Summary")
    table.add_column("Specialist", style="cyan")
    table.add_column("Findings", justify="right")
    table.add_column("Tokens", justify="right")
    table.add_column("Status", justify="center")

    for report, agent_result in zip(result.reports, result.agent_results):
        status = "✅" if agent_result.success else "❌"
        table.add_row(
            report.specialist.value,
            str(len(report.findings)),
            str(agent_result.total_tokens),
            status,
        )

    console.print(table)

    console.print(
        f"\n[bold]Total:[/bold] "
        f"{result.total_tokens} tokens · "
        f"~${result.total_cost_usd:.4f} · "
        f"{len(result.reports)} reports"
    )

    if result.used_fallback_router:
        console.print("[yellow]⚠ Dispatcher failed — used fallback router[/yellow]")

    if result.errors:
        console.print("\n[red]Errors:[/red]")
        for error in result.errors:
            console.print(f"  [red]• {error}[/red]")

    # Post to GitHub if PR number provided
    if pr and result.reports:
        console.print(f"\n[bold green]Posting comments to PR #{pr}...[/bold green]")
        try:
            from code_review_agent.github.comment_manager import post_reports
            post_reports(
                reports=result.reports,
                pr_number=pr,
                commit_sha=head,
                clean_orphans=clean,
            )
            console.print(f"[green]✅ Posted {len(result.reports)} comment(s) to PR #{pr}[/green]")
        except Exception as e:
            console.print(f"[red]❌ Failed to post comments: {e}[/red]")
            sys.exit(1)

    elif result.reports:
        console.print(
            "\n[dim]Tip: use --pr <number> to post comments to a GitHub PR[/dim]"
        )

    # Exit with error code if there are critical findings
    critical_count = sum(
        1 for r in result.reports
        for f in r.findings
        if f.severity.value in ("critical", "high")
    )
    if critical_count > 0:
        console.print(
            f"\n[red]Found {critical_count} critical/high finding(s)[/red]"
        )


@app.command()
def version() -> None:
    """Show version information."""
    rprint("[bold]review-agent[/bold] v0.1.0")
    rprint("Built on Claude · github.com/vinyyg/code-review-agent")


if __name__ == "__main__":
    app()