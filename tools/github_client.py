"""
GitHub tool — creates repos and deploys websites to GitHub Pages.
Uses PyGithub + direct REST calls for Pages configuration.
"""
import logging
import os
import time
import base64

import httpx
from github import Github, GithubException
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


def _get_github() -> tuple[Github, str]:
    """Return authenticated Github client and username."""
    token = os.getenv("GITHUB_TOKEN")
    if not token:
        raise ValueError("GITHUB_TOKEN not set in .env")
    g = Github(token)
    username = g.get_user().login
    return g, username


def deploy_to_pages(
    repo_name: str,
    description: str,
    files: dict[str, str],
) -> str:
    """
    Create a GitHub repo, push files, enable GitHub Pages, and return the live URL.

    Args:
        repo_name: Repo name (lowercase, hyphens). Will be created if it doesn't exist.
        description: Short description of the site/repo.
        files: Dict of {filename: content}, e.g. {'index.html': '<html>...', 'style.css': '...'}

    Returns:
        Live GitHub Pages URL (https://{username}.github.io/{repo_name}/)
    """
    g, username = _get_github()
    token = os.getenv("GITHUB_TOKEN")

    # ── Create or get repo ──────────────────────────────────────────────────
    try:
        repo = g.get_user().get_repo(repo_name)
        logger.info(f"Using existing repo: {repo.full_name}")
    except GithubException:
        repo = g.get_user().create_repo(
            name=repo_name,
            description=description,
            auto_init=True,
            private=False,
        )
        logger.info(f"Created repo: {repo.full_name}")
        time.sleep(1)  # Let GitHub initialise the repo

    # ── Push all files ───────────────────────────────────────────────────────
    for filename, content in files.items():
        encoded = base64.b64encode(content.encode("utf-8")).decode("utf-8")
        try:
            # Try to get existing file (need sha to update)
            existing = repo.get_contents(filename, ref="main")
            repo.update_file(
                path=filename,
                message=f"Update {filename}",
                content=content,
                sha=existing.sha,
                branch="main",
            )
            logger.info(f"Updated file: {filename}")
        except GithubException:
            # File doesn't exist — create it
            repo.create_file(
                path=filename,
                message=f"Add {filename}",
                content=content,
                branch="main",
            )
            logger.info(f"Created file: {filename}")

    # ── Enable GitHub Pages via REST API ────────────────────────────────────
    pages_url = f"https://api.github.com/repos/{username}/{repo_name}/pages"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    with httpx.Client(timeout=15) as client:
        # Check if Pages already enabled
        check = client.get(pages_url, headers=headers)
        if check.status_code == 404:
            # Enable Pages from main branch root
            resp = client.post(
                pages_url,
                headers=headers,
                json={"source": {"branch": "main", "path": "/"}},
            )
            if resp.status_code not in (200, 201):
                logger.warning(f"Pages enable returned {resp.status_code}: {resp.text}")
            else:
                logger.info("GitHub Pages enabled")
        else:
            logger.info("GitHub Pages already enabled")

    live_url = f"https://{username}.github.io/{repo_name}/"
    logger.info(f"Site will be live at: {live_url}")

    # Pages can take 1-2 min to build — we return the URL immediately
    return live_url
