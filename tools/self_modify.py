"""
Self-Modify Tool — Jarvis leser og endrer sin egen kode direkte.

Jarvis kjører på /opt/nexus/. Han kan:
- Lese sine egne filer
- Skrive/endre filer
- Committe til GitHub
- Restarte seg selv
"""
import os
import subprocess
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

BASE = Path("/opt/nexus")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
GITHUB_USERNAME = os.getenv("GITHUB_USERNAME", "nicholaselvegaard-commits")


def read_own_file(relative_path: str) -> str:
    """Les en av Jarvis sine egne filer. Path relativt til /opt/nexus/"""
    try:
        path = BASE / relative_path.lstrip("/")
        if not path.exists():
            return f"Fil ikke funnet: {path}"
        if path.stat().st_size > 100_000:
            return f"Fil for stor ({path.stat().st_size} bytes). Les deler med offset/limit."
        return path.read_text(encoding="utf-8")
    except Exception as e:
        return f"read_own_file error: {e}"


def write_own_file(relative_path: str, content: str) -> str:
    """Skriv/overskriv en av Jarvis sine egne filer. Tar backup automatisk."""
    try:
        path = BASE / relative_path.lstrip("/")
        path.parent.mkdir(parents=True, exist_ok=True)

        # Backup før endring
        if path.exists():
            backup = path.with_suffix(path.suffix + ".bak")
            backup.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")

        path.write_text(content, encoding="utf-8")
        logger.info(f"self_modify: wrote {path}")
        return f"✅ Skrevet: {relative_path} ({len(content)} tegn)"
    except Exception as e:
        return f"write_own_file error: {e}"


def list_own_files(relative_path: str = "") -> str:
    """List filer i en katalog under /opt/nexus/"""
    try:
        path = BASE / relative_path.lstrip("/") if relative_path else BASE
        if not path.exists():
            return f"Katalog ikke funnet: {path}"
        files = []
        for f in sorted(path.iterdir()):
            size = f"({f.stat().st_size}b)" if f.is_file() else "/"
            files.append(f"  {f.name}{size}")
        return f"{path}:\n" + "\n".join(files[:50])
    except Exception as e:
        return f"list_own_files error: {e}"


def git_commit_and_push(message: str, files: list[str] | None = None) -> str:
    """
    Commit og push endringer til GitHub.
    files: liste med relative paths, eller None for å stage alt som er endret.
    """
    try:
        env = os.environ.copy()
        if GITHUB_TOKEN:
            # Sett credentials for push
            repo_url_cmd = subprocess.run(
                ["git", "remote", "get-url", "origin"],
                cwd=BASE, capture_output=True, text=True
            )
            origin = repo_url_cmd.stdout.strip()
            if origin and "github.com" in origin and "@" not in origin:
                # Inject token into URL
                origin_with_token = origin.replace(
                    "https://github.com",
                    f"https://{GITHUB_USERNAME}:{GITHUB_TOKEN}@github.com"
                )
                subprocess.run(
                    ["git", "remote", "set-url", "origin", origin_with_token],
                    cwd=BASE, env=env, capture_output=True
                )

        # Stage files
        if files:
            for f in files:
                subprocess.run(["git", "add", f], cwd=BASE, env=env, check=True)
        else:
            subprocess.run(["git", "add", "-A"], cwd=BASE, env=env, check=True)

        # Check if anything to commit
        status = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=BASE, env=env, capture_output=True, text=True
        )
        if not status.stdout.strip():
            return "Ingen endringer å committe."

        # Commit
        subprocess.run(
            ["git", "-c", "user.email=jordan.develepor@outlook.com",
             "-c", "user.name=Jarvis",
             "commit", "-m", message],
            cwd=BASE, env=env, check=True
        )

        # Push
        push = subprocess.run(
            ["git", "push"],
            cwd=BASE, env=env, capture_output=True, text=True
        )
        if push.returncode == 0:
            logger.info(f"self_modify: committed & pushed — {message}")
            return f"✅ Committed og pushet: \"{message}\""
        else:
            return f"Commit OK, push feilet: {push.stderr[:200]}"

    except subprocess.CalledProcessError as e:
        return f"git error: {e.stderr if hasattr(e, 'stderr') else e}"
    except Exception as e:
        return f"git_commit error: {e}"


def restart_self() -> str:
    """
    Restart Jarvis sin egen service (nexus.service).
    ADVARSEL: Denne samtalen avsluttes. Jarvis kommer opp igjen om ~5 sekunder.
    """
    try:
        logger.info("self_modify: restarting nexus.service...")
        # Delayed restart so we can return the message first
        subprocess.Popen(
            ["bash", "-c", "sleep 2 && systemctl restart nexus"],
            close_fds=True
        )
        return "🔄 Restarter om 2 sekunder... Jarvis kommer opp igjen straks."
    except Exception as e:
        return f"restart error: {e}"


def run_shell(command: str, timeout: int = 30) -> str:
    """
    Kjør en shell-kommando på serveren (begrenset til /opt/nexus/).
    Bruk for git status, pip install, python -c, etc.
    IKKE bruk for destruktive kommandoer (rm -rf, etc.)
    """
    # Safety check — block destructive/exfiltration patterns
    dangerous = [
        "rm -rf", "rm -r /", "dd if", "mkfs", "> /dev/", ":(){:|:&};:",
        "chmod 777 /", "chown -R", "shutdown", "reboot", "init 0",
        "curl | bash", "curl|bash", "wget | bash", "wget|bash",
        "| sh", "| bash", "base64 -d", "eval ", "/etc/passwd",
        "/etc/shadow", "DROP TABLE", "format c:", "del /f /s",
    ]
    for d in dangerous:
        if d.lower() in command.lower():
            return f"❌ Kommando blokkert (destruktiv): {command}"

    try:
        result = subprocess.run(
            command, shell=True, cwd=BASE,
            capture_output=True, text=True, timeout=timeout
        )
        output = (result.stdout + result.stderr).strip()
        return output[:2000] if output else "(ingen output)"
    except subprocess.TimeoutExpired:
        return f"Timeout etter {timeout}s"
    except Exception as e:
        return f"shell error: {e}"
