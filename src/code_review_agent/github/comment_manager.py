from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from code_review_agent.github.client import GitHubClient
from code_review_agent.github.renderer import (
    extract_specialist_from_marker,
    make_marker,
    render_report,
)
from code_review_agent.schema.report import SpecialistReport

logger = logging.getLogger(__name__)


# ── Existing comment ──────────────────────────────────────────────────────────

@dataclass
class ExistingComment:
    comment_id: int
    specialist: str
    body: str


# ── Comment Manager ───────────────────────────────────────────────────────────

class CommentManager:
    """
    Manages review-agent comments on a PR.
    Creates new comments or updates existing ones per specialist.
    Cleans up comments from specialists no longer active.
    """

    def __init__(self, client: GitHubClient, pr_number: int):
        self.client = client
        self.pr_number = pr_number
        self._existing: dict[str, ExistingComment] = {}
        self._loaded = False

    def load_existing_comments(self) -> None:
        """Fetch and index all existing review-agent comments on the PR."""
        comments = self.client.list_issue_comments(self.pr_number)
        self._existing = {}

        for comment in comments:
            body = comment.get("body", "")
            specialist = extract_specialist_from_marker(body)
            if specialist:
                self._existing[specialist] = ExistingComment(
                    comment_id=comment["id"],
                    specialist=specialist,
                    body=body,
                )
                logger.debug(
                    f"Found existing comment for {specialist} "
                    f"(id={comment['id']})"
                )

        logger.info(
            f"Loaded {len(self._existing)} existing review-agent comments "
            f"on PR #{self.pr_number}"
        )
        self._loaded = True

    def upsert_report(
        self,
        report: SpecialistReport,
        commit_sha: str,
    ) -> None:
        """Create or update the comment for a specialist report."""
        if not self._loaded:
            self.load_existing_comments()

        specialist = report.specialist.value
        body = render_report(report, commit_sha)

        if specialist in self._existing:
            comment_id = self._existing[specialist].comment_id
            self.client.update_comment(comment_id, body)
            logger.info(f"Updated {specialist} comment on PR #{self.pr_number}")
        else:
            self.client.create_comment(self.pr_number, body)
            logger.info(f"Created {specialist} comment on PR #{self.pr_number}")

    def delete_orphan_comments(
        self,
        active_specialists: list[str],
    ) -> None:
        """
        Delete comments from specialists that are no longer active.
        Example: security ran last time but not this time — remove old comment.
        """
        if not self._loaded:
            self.load_existing_comments()

        active_set = set(active_specialists)

        for specialist, comment in list(self._existing.items()):
            if specialist not in active_set:
                logger.info(
                    f"Deleting orphan comment for {specialist} "
                    f"(not active in this run)"
                )
                self.client.delete_comment(comment.comment_id)

    def get_existing(self, specialist: str) -> Optional[ExistingComment]:
        """Return existing comment for a specialist, if any."""
        if not self._loaded:
            self.load_existing_comments()
        return self._existing.get(specialist)


# ── Convenience function ──────────────────────────────────────────────────────

def post_reports(
    reports: list[SpecialistReport],
    pr_number: int,
    commit_sha: str,
    repository: str | None = None,
) -> None:
    """
    Post all specialist reports to a PR.
    Creates or updates comments as needed.
    Deletes orphan comments from previous runs.

    This is the main entry point called by the CLI and GitHub Action.
    """
    with GitHubClient(repository=repository) as client:
        manager = CommentManager(client, pr_number)
        manager.load_existing_comments()

        for report in reports:
            manager.upsert_report(report, commit_sha)

        active = [r.specialist.value for r in reports]
        manager.delete_orphan_comments(active)

        logger.info(
            f"Posted {len(reports)} report(s) to PR #{pr_number}"
        )