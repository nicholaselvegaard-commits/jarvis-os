"""
SelfImproveAgent — weekly self-analysis and auto-fix loop.

1. Read /opt/nexus/logs/errors.jsonl — find top 5 errors this week
2. Analyze with Groq: "What is root cause? How to fix?"
3. For fixes < 20 lines and low risk → implement automatically via write_own_file
4. For larger fixes → send Telegram message to Nicholas with proposal
5. Commit all auto-fixes to GitHub
"""

import json
import logging
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from tools.groq_client import chat as groq_chat
from tools.self_modify import write_own_file, git_commit_and_push
from telegram_bot import notify_owner
from memory.smart_memory import save

logger = logging.getLogger(__name__)

ERRORS_PATH = Path("/opt/nexus/logs/errors.jsonl")
LOOKBACK_DAYS = 7

# Groq model — fast and capable enough for code analysis
_GROQ_MODEL = "llama-3.3-70b-versatile"

# Heuristic: proposed fixes with fewer than this many non-blank lines are
# considered "small" and safe to auto-apply without human review.
AUTO_APPLY_MAX_LINES = 20

# Keywords that flag a fix as high-risk regardless of line count.
_HIGH_RISK_PATTERNS = [
    "os.remove",
    "shutil.rmtree",
    "subprocess",
    "exec(",
    "eval(",
    "DROP TABLE",
    "delete_from",
    "__import__",
    "open(",
]


def _load_recent_errors() -> list[dict[str, Any]]:
    """Read errors.jsonl, return entries from the last LOOKBACK_DAYS days."""
    if not ERRORS_PATH.exists():
        logger.warning(f"Error log not found: {ERRORS_PATH}")
        return []

    cutoff = datetime.now(timezone.utc) - timedelta(days=LOOKBACK_DAYS)
    recent: list[dict[str, Any]] = []

    try:
        for raw_line in ERRORS_PATH.read_text(encoding="utf-8").splitlines():
            raw_line = raw_line.strip()
            if not raw_line:
                continue
            try:
                entry = json.loads(raw_line)
            except json.JSONDecodeError:
                continue

            # Accept ISO timestamps or skip if missing
            ts_str = entry.get("timestamp") or entry.get("time") or entry.get("ts")
            if ts_str:
                try:
                    ts = datetime.fromisoformat(ts_str.rstrip("Z")).replace(tzinfo=timezone.utc)
                    if ts < cutoff:
                        continue
                except ValueError:
                    pass  # malformed timestamp — include it anyway

            recent.append(entry)
    except Exception as exc:
        logger.error(f"Failed to read errors.jsonl: {exc}")

    return recent


def _group_by_type(errors: list[dict[str, Any]]) -> list[tuple[str, int, list[dict]]]:
    """Group errors by their 'error_type' or 'message' field.

    Returns list of (error_key, count, sample_entries) sorted by count descending.
    """
    groups: dict[str, list[dict]] = {}
    for entry in errors:
        key = (
            entry.get("error_type")
            or entry.get("type")
            or entry.get("level")
            or (entry.get("message", "unknown")[:80])
        )
        groups.setdefault(key, []).append(entry)

    # Sort by frequency, return top 5
    ranked = sorted(groups.items(), key=lambda kv: len(kv[1]), reverse=True)[:5]
    return [(k, len(v), v[:3]) for k, v in ranked]


def _build_analysis_prompt(error_key: str, count: int, samples: list[dict]) -> str:
    sample_text = json.dumps(samples, indent=2, ensure_ascii=False)[:2000]
    return (
        f"You are a senior Python engineer reviewing production errors in an autonomous AI agent "
        f"system (NEXUS, running on /opt/nexus/).\n\n"
        f"ERROR TYPE: {error_key}\n"
        f"OCCURRENCES THIS WEEK: {count}\n\n"
        f"SAMPLE LOG ENTRIES:\n{sample_text}\n\n"
        f"Task:\n"
        f"1. Identify the most likely root cause (1-2 sentences).\n"
        f"2. Propose a concrete code fix. If the fix is small (<= 20 lines of Python), "
        f"output ONLY the complete corrected function/block wrapped in triple backticks "
        f"with the file path as the first line inside the block, like this:\n"
        f"```python\n# file: agents/some_module.py\ndef fixed_function(...):\n    ...\n```\n"
        f"3. After the code block, write one sentence: either "
        f"'RISK: low' or 'RISK: high' and a brief reason.\n"
        f"4. If the fix requires more than 20 lines or is high risk, write 'PROPOSAL:' "
        f"followed by a plain-English description of what should be changed and why.\n"
        f"Do not add extra commentary."
    )


def _parse_groq_response(response: str) -> dict[str, Any]:
    """Extract code block, target file path, line count, and risk level from Groq output."""
    import re

    result: dict[str, Any] = {
        "has_code": False,
        "file_path": None,
        "code": None,
        "line_count": 0,
        "risk": "unknown",
        "proposal": None,
        "raw": response,
    }

    # Extract code block
    code_match = re.search(r"```python\n(.*?)```", response, re.DOTALL)
    if code_match:
        block = code_match.group(1)
        lines = block.splitlines()

        # First line may be "# file: path/to/module.py"
        file_path: str | None = None
        code_lines: list[str] = []
        for i, line in enumerate(lines):
            stripped = line.strip()
            if i == 0 and stripped.startswith("# file:"):
                file_path = stripped.replace("# file:", "").strip()
            else:
                code_lines.append(line)

        code_text = "\n".join(code_lines).strip()
        non_blank = [l for l in code_lines if l.strip()]

        result.update({
            "has_code": True,
            "file_path": file_path,
            "code": code_text,
            "line_count": len(non_blank),
        })

    # Extract risk level
    risk_match = re.search(r"RISK:\s*(low|high)", response, re.IGNORECASE)
    if risk_match:
        result["risk"] = risk_match.group(1).lower()

    # Extract PROPOSAL section
    proposal_match = re.search(r"PROPOSAL:(.*?)(?:\n\n|\Z)", response, re.DOTALL)
    if proposal_match:
        result["proposal"] = proposal_match.group(1).strip()

    return result


def _is_high_risk(code: str) -> bool:
    """Return True if any high-risk pattern is found in the proposed code."""
    code_lower = code.lower()
    return any(pat.lower() in code_lower for pat in _HIGH_RISK_PATTERNS)


async def run_self_improve() -> str:
    """
    Main weekly self-improvement function.

    Returns a summary string suitable for logging or Telegram notification.
    """
    logger.info("[SelfImproveAgent] Starting weekly self-improvement run")
    start_ts = datetime.now(timezone.utc).isoformat()

    # ── 1. Load and group errors ──────────────────────────────────────────────
    errors = _load_recent_errors()
    if not errors:
        summary = "SelfImproveAgent: No errors found in the last 7 days. Nothing to do."
        logger.info(summary)
        save("learning", f"[{start_ts}] Self-improve: no errors this week.", priority=1)
        return summary

    grouped = _group_by_type(errors)
    logger.info(f"[SelfImproveAgent] Loaded {len(errors)} errors, grouped into {len(grouped)} types")

    # ── 2–4. Analyze each error type with Groq ────────────────────────────────
    auto_fixed: list[str] = []
    proposals: list[str] = []
    committed_files: list[str] = []

    for error_key, count, samples in grouped:
        logger.info(f"[SelfImproveAgent] Analyzing: '{error_key}' ({count}x)")

        prompt = _build_analysis_prompt(error_key, count, samples)
        try:
            groq_response = groq_chat(
                prompt=prompt,
                model=_GROQ_MODEL,
                system=(
                    "You are a senior Python engineer. "
                    "Be concise. Output only what is asked — no preamble."
                ),
                temperature=0.2,
                max_tokens=1024,
            )
        except Exception as exc:
            logger.error(f"[SelfImproveAgent] Groq call failed for '{error_key}': {exc}")
            proposals.append(f"[{error_key}] Groq analysis failed: {exc}")
            continue

        parsed = _parse_groq_response(groq_response)

        # ── 3. Auto-fix: small + low risk ────────────────────────────────────
        if (
            parsed["has_code"]
            and parsed["file_path"]
            and parsed["line_count"] <= AUTO_APPLY_MAX_LINES
            and parsed["risk"] != "high"
            and not _is_high_risk(parsed["code"] or "")
        ):
            rel_path: str = parsed["file_path"]
            code_content: str = parsed["code"]  # type: ignore[assignment]
            logger.info(
                f"[SelfImproveAgent] Auto-applying fix for '{error_key}' "
                f"→ {rel_path} ({parsed['line_count']} lines)"
            )
            write_result = write_own_file(rel_path, code_content)
            auto_fixed.append(
                f"'{error_key}' ({count}x) → {rel_path}: {write_result}"
            )
            committed_files.append(rel_path)
            save(
                "learning",
                f"Auto-fix applied for {error_key}: {rel_path} ({parsed['line_count']} lines)",
                priority=2,
            )

        # ── 4. Large/high-risk: send proposal to Nicholas ────────────────────
        else:
            proposal_text = parsed.get("proposal") or parsed["raw"][:400]
            risk_label = parsed["risk"]
            line_count = parsed["line_count"]

            reason = []
            if line_count > AUTO_APPLY_MAX_LINES:
                reason.append(f"{line_count} lines (limit: {AUTO_APPLY_MAX_LINES})")
            if risk_label == "high":
                reason.append("high risk")
            if not parsed["file_path"] and parsed["has_code"]:
                reason.append("no target file identified")
            if not parsed["has_code"]:
                reason.append("no code fix generated")

            reason_str = ", ".join(reason) if reason else "no auto-applicable fix"

            telegram_msg = (
                f"NEXUS Self-Improve — manual fix needed\n\n"
                f"Error: {error_key}\n"
                f"Frequency: {count}x this week\n"
                f"Reason not auto-applied: {reason_str}\n\n"
                f"Proposed fix:\n{proposal_text}"
            )
            try:
                notify_owner(telegram_msg)
                proposals.append(f"'{error_key}' ({count}x) — proposal sent via Telegram")
            except Exception as exc:
                logger.error(f"[SelfImproveAgent] Telegram notify failed: {exc}")
                proposals.append(f"'{error_key}' ({count}x) — Telegram failed: {exc}")

            save(
                "learning",
                f"Manual fix proposed for {error_key} ({count}x/week): {proposal_text[:120]}",
                priority=2,
            )

    # ── 5. Commit all auto-fixes ──────────────────────────────────────────────
    commit_result = ""
    if committed_files:
        commit_msg = (
            f"self-improve: auto-fix {len(committed_files)} issue(s) "
            f"[{datetime.now(timezone.utc).strftime('%Y-%m-%d')}]"
        )
        try:
            commit_result = git_commit_and_push(commit_msg, files=committed_files)
            logger.info(f"[SelfImproveAgent] Git: {commit_result}")
        except Exception as exc:
            commit_result = f"Git commit failed: {exc}"
            logger.error(f"[SelfImproveAgent] {commit_result}")

    # ── Build summary ─────────────────────────────────────────────────────────
    summary_lines = [
        f"SelfImproveAgent run — {start_ts}",
        f"Total errors analysed: {len(errors)} across {len(grouped)} types",
        "",
    ]
    if auto_fixed:
        summary_lines.append(f"AUTO-FIXED ({len(auto_fixed)}):")
        summary_lines.extend(f"  - {item}" for item in auto_fixed)
        summary_lines.append(f"  Git: {commit_result}")
    else:
        summary_lines.append("AUTO-FIXED: none")

    summary_lines.append("")
    if proposals:
        summary_lines.append(f"PROPOSALS SENT ({len(proposals)}):")
        summary_lines.extend(f"  - {item}" for item in proposals)
    else:
        summary_lines.append("PROPOSALS: none")

    summary = "\n".join(summary_lines)
    logger.info(f"[SelfImproveAgent] Complete:\n{summary}")

    # Persist overall result to memory
    save(
        "learning",
        f"Weekly self-improve: {len(auto_fixed)} auto-fixed, {len(proposals)} proposals",
        priority=1,
    )

    return summary
