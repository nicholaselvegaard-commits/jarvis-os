"""File management tool with backup support."""
import logging
import shutil
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def read_file(path: str | Path) -> str:
    """Read and return file contents."""
    p = Path(path)
    logger.info(f"Reading file: {p}")
    return p.read_text(encoding="utf-8")


def write_file(path: str | Path, content: str, backup: bool = True) -> Path:
    """
    Write content to a file, optionally creating a backup first.

    Args:
        path: Target file path.
        content: Content to write.
        backup: If True and file exists, create a .bak copy first.

    Returns:
        Path to the written file.
    """
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)

    if backup and p.exists():
        backup_path = p.with_suffix(p.suffix + ".bak")
        shutil.copy2(p, backup_path)
        logger.info(f"Backup created: {backup_path}")

    p.write_text(content, encoding="utf-8")
    logger.info(f"Written: {p}")
    return p


def move_file(src: str | Path, dst: str | Path) -> Path:
    """Move a file from src to dst."""
    src_p, dst_p = Path(src), Path(dst)
    dst_p.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src_p), str(dst_p))
    logger.info(f"Moved: {src_p} → {dst_p}")
    return dst_p


def delete_file(path: str | Path, backup: bool = True) -> None:
    """
    Delete a file. Creates a .bak backup by default before deletion.
    Caller is responsible for confirming deletion before calling this.
    """
    p = Path(path)
    if not p.exists():
        logger.warning(f"Delete called on non-existent file: {p}")
        return

    if backup:
        backup_path = p.with_suffix(p.suffix + ".bak")
        shutil.copy2(p, backup_path)
        logger.info(f"Backup before delete: {backup_path}")

    p.unlink()
    logger.info(f"Deleted: {p}")


def list_files(directory: str | Path, pattern: str = "*") -> list[Path]:
    """List files in a directory matching a glob pattern."""
    d = Path(directory)
    files = list(d.glob(pattern))
    logger.info(f"Found {len(files)} files in {d} matching '{pattern}'")
    return files
