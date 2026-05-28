from __future__ import annotations

import logging
import os
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

GITHUB_API = "https://api.github.com"


class GitHubClient:
    """
    Thin wrapper over the GitHub REST API.
    Handles authentication, rate limits, and error responses.
    """

    def __init__(
        self,
        token: Optional[str] = None,
        repository: Optional[str] = None,
    ):
        self.token = token or os.environ["GITHUB_TOKEN"]
        self.repository = repository or os.environ["GITHUB_REPOSITORY"]
        self._client = httpx.Client(
            base_url=GITHUB_API,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            timeout=30.0,
        )

    # ── Comments ──────────────────────────────────────────────────────────────

    def list_issue_comments(self, pr_number: int) -> list[dict]:
        """List all comments on a PR (uses issues API)."""
        comments = []
        url = f"/repos/{self.repository}/issues/{pr_number}/comments"

        while url:
            response = self._client.get(url, params={"per_page": 100})
            self._raise_for_status(response)
            comments.extend(response.json())
            url = self._next_link(response)

        return comments

    def create_comment(self, pr_number: int, body: str) -> dict:
        """Create a new comment on a PR."""
        response = self._client.post(
            f"/repos/{self.repository}/issues/{pr_number}/comments",
            json={"body": body},
        )
        self._raise_for_status(response)
        logger.info(f"Created comment on PR #{pr_number}")
        return response.json()

    def update_comment(self, comment_id: int, body: str) -> dict:
        """Update an existing comment."""
        response = self._client.patch(
            f"/repos/{self.repository}/issues/comments/{comment_id}",
            json={"body": body},
        )
        self._raise_for_status(response)
        logger.info(f"Updated comment #{comment_id}")
        return response.json()

    def delete_comment(self, comment_id: int) -> None:
        """Delete a comment."""
        response = self._client.delete(
            f"/repos/{self.repository}/issues/comments/{comment_id}",
        )
        self._raise_for_status(response)
        logger.info(f"Deleted comment #{comment_id}")

    # ── PR info ───────────────────────────────────────────────────────────────

    def get_pr(self, pr_number: int) -> dict:
        """Get PR metadata."""
        response = self._client.get(
            f"/repos/{self.repository}/pulls/{pr_number}"
        )
        self._raise_for_status(response)
        return response.json()

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _raise_for_status(self, response: httpx.Response) -> None:
        if response.status_code >= 400:
            raise GitHubAPIError(
                f"GitHub API error {response.status_code}: {response.text[:200]}"
            )

    def _next_link(self, response: httpx.Response) -> Optional[str]:
        """Parse the 'next' link from GitHub pagination headers."""
        link_header = response.headers.get("link", "")
        for part in link_header.split(","):
            if 'rel="next"' in part:
                url = part.split(";")[0].strip().strip("<>")
                # Strip base URL since httpx uses base_url
                if url.startswith(GITHUB_API):
                    return url[len(GITHUB_API):]
                return url
        return None

    def close(self) -> None:
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


class GitHubAPIError(Exception):
    pass