"""
GitHub-verktøy — Jarvis kan opprette repos, pushe filer, sjekke status.

Bruker GITHUB_TOKEN fra .env.
Konto: nicholaselvegaard-commits
"""
import logging
import os
import base64
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

BASE = "https://api.github.com"
OWNER = "nicholaselvegaard-commits"


def _headers() -> dict:
    token = os.getenv("GITHUB_TOKEN", "")
    if not token:
        raise ValueError("GITHUB_TOKEN not set")
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def list_repos() -> list[dict]:
    """List alle repos under nicholaselvegaard-commits."""
    resp = httpx.get(f"{BASE}/user/repos", headers=_headers(),
                      params={"per_page": 50, "sort": "updated"}, timeout=15)
    resp.raise_for_status()
    return [{"name": r["name"], "url": r["html_url"], "private": r["private"]} for r in resp.json()]


def create_repo(
    name: str,
    description: str = "",
    private: bool = False,
    auto_init: bool = True,
) -> dict:
    """
    Opprett et nytt GitHub-repo.

    Returns:
        {name, url, clone_url}
    """
    resp = httpx.post(f"{BASE}/user/repos", headers=_headers(), json={
        "name": name,
        "description": description,
        "private": private,
        "auto_init": auto_init,
    }, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    logger.info(f"GitHub repo created: {data['html_url']}")
    return {"name": data["name"], "url": data["html_url"], "clone_url": data["clone_url"]}


def push_file(
    repo: str,
    path: str,
    content: str,
    message: str,
    branch: str = "main",
) -> dict:
    """
    Push en fil til et GitHub-repo (create or update).

    Args:
        repo:    Repo-navn (uten owner prefix)
        path:    Filsti i repo, f.eks. "index.html"
        content: Filinnhold
        message: Commit-melding
        branch:  Branch (default: main)

    Returns:
        {sha, url}
    """
    url = f"{BASE}/repos/{OWNER}/{repo}/contents/{path}"

    # Sjekk om filen finnes (for update)
    existing = httpx.get(url, headers=_headers(), params={"ref": branch}, timeout=10)
    sha = existing.json().get("sha") if existing.is_success else None

    payload = {
        "message": message,
        "content": base64.b64encode(content.encode()).decode(),
        "branch": branch,
    }
    if sha:
        payload["sha"] = sha

    resp = httpx.put(url, headers=_headers(), json=payload, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    file_url = data.get("content", {}).get("html_url", "")
    logger.info(f"GitHub file pushed: {OWNER}/{repo}/{path}")
    return {"sha": data.get("commit", {}).get("sha", ""), "url": file_url}


def get_file(repo: str, path: str, branch: str = "main") -> str:
    """Les en fil fra GitHub-repo."""
    url = f"{BASE}/repos/{OWNER}/{repo}/contents/{path}"
    resp = httpx.get(url, headers=_headers(), params={"ref": branch}, timeout=10)
    resp.raise_for_status()
    return base64.b64decode(resp.json()["content"]).decode()


def list_repo_files(repo: str, path: str = "", branch: str = "main") -> list[dict]:
    """List filer og mapper i et repo-path."""
    url = f"{BASE}/repos/{OWNER}/{repo}/contents/{path}"
    resp = httpx.get(url, headers=_headers(), params={"ref": branch}, timeout=10)
    resp.raise_for_status()
    return [{"name": f["name"], "type": f["type"], "path": f["path"]} for f in resp.json()]
