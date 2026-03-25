"""Git operations tool. Never pushes to main without approval."""
import logging
from datetime import datetime
from pathlib import Path
from tools.shell_runner import run, CommandResult

logger = logging.getLogger(__name__)

BRANCH_PREFIX = "agent"


def _git(args: list[str], cwd: str | Path | None = None) -> CommandResult:
    """Run a git command in the specified directory."""
    result = run(["git"] + args, cwd=str(cwd) if cwd else None)
    if not result.success:
        raise RuntimeError(f"git {' '.join(args)} failed:\n{result.stderr}")
    return result


def create_branch(task_name: str, repo_path: str | Path = ".") -> str:
    """Create and checkout a new agent branch."""
    date = datetime.now().strftime("%Y%m%d")
    branch = f"{BRANCH_PREFIX}/{task_name}-{date}"
    _git(["checkout", "-b", branch], cwd=repo_path)
    logger.info(f"Created branch: {branch}")
    return branch


def commit(message: str, files: list[str] | None = None, repo_path: str | Path = ".") -> str:
    """Stage specified files (or all) and commit with a message."""
    if files:
        _git(["add"] + files, cwd=repo_path)
    else:
        _git(["add", "-A"], cwd=repo_path)

    result = _git(["commit", "-m", message], cwd=repo_path)
    logger.info(f"Committed: {message}")
    return result.stdout


def get_status(repo_path: str | Path = ".") -> str:
    """Return git status output."""
    return _git(["status", "--short"], cwd=repo_path).stdout


def get_diff(repo_path: str | Path = ".") -> str:
    """Return git diff of unstaged changes."""
    return _git(["diff"], cwd=repo_path).stdout


def push(branch: str, remote: str = "origin", repo_path: str | Path = ".") -> None:
    """
    Push a branch to remote.
    NEVER call this for 'main' without explicit user approval.
    """
    if branch in ("main", "master"):
        raise ValueError(
            f"Refusing to push to '{branch}' without explicit approval. "
            "Get confirmation from the user before proceeding."
        )
    _git(["push", "-u", remote, branch], cwd=repo_path)
    logger.info(f"Pushed {branch} to {remote}")
