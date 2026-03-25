"""Shell command runner with output capture and timeout."""
import logging
import subprocess
from dataclasses import dataclass

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 60  # seconds


@dataclass
class CommandResult:
    command: str
    returncode: int
    stdout: str
    stderr: str

    @property
    def success(self) -> bool:
        return self.returncode == 0


def run(command: str | list[str], timeout: int = DEFAULT_TIMEOUT, cwd: str | None = None) -> CommandResult:
    """
    Run a shell command and capture its output.

    Args:
        command: Command string or list of arguments.
        timeout: Timeout in seconds before killing the process.
        cwd: Working directory for the command.

    Returns:
        CommandResult with stdout, stderr, and return code.

    Raises:
        subprocess.TimeoutExpired: If command exceeds timeout.
        RuntimeError: If command is blocked or fails critically.
    """
    cmd_str = command if isinstance(command, str) else " ".join(command)
    logger.info(f"Running: {cmd_str}")

    try:
        result = subprocess.run(
            command,
            shell=isinstance(command, str),
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd,
        )
        level = logging.DEBUG if result.returncode == 0 else logging.WARNING
        logger.log(level, f"Exit {result.returncode}: {cmd_str}")
        if result.stderr:
            logger.warning(f"stderr: {result.stderr[:500]}")

        return CommandResult(
            command=cmd_str,
            returncode=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr,
        )

    except subprocess.TimeoutExpired as e:
        logger.error(f"Command timed out after {timeout}s: {cmd_str}")
        raise
