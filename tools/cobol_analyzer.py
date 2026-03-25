"""
COBOL codebase analyzer. Builds dependency maps and modernization reports.
Used as the entry point for COBOL modernization sales pitch.
"""
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class CobolAnalysis:
    total_lines: int
    program_count: int
    copybook_count: int
    dead_code_lines: int
    perform_calls: list[str]
    file_operations: list[str]
    database_calls: list[str]
    complexity_score: int  # 1-10
    modernization_effort: str  # S/M/L/XL
    issues: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)


def analyze_file(cobol_path: str | Path) -> CobolAnalysis:
    """
    Analyze a single COBOL file.

    Args:
        cobol_path: Path to .cbl, .cob, or .cobol file

    Returns:
        CobolAnalysis with findings
    """
    path = Path(cobol_path)
    if not path.exists():
        raise FileNotFoundError(f"COBOL file not found: {path}")

    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    total_lines = len(lines)

    # Count programs
    program_count = len(re.findall(r"PROGRAM-ID\.", text, re.IGNORECASE))
    copybook_count = len(re.findall(r"COPY\s+\w+", text, re.IGNORECASE))

    # Identify PERFORM calls
    performs = re.findall(r"PERFORM\s+([\w-]+)", text, re.IGNORECASE)

    # File operations
    file_ops = re.findall(r"\b(OPEN|CLOSE|READ|WRITE|REWRITE|DELETE)\s+\w+", text, re.IGNORECASE)

    # Database calls (EXEC SQL or EXEC DLI for IMS)
    db_calls = re.findall(r"EXEC\s+(SQL|DLI)\s+\w+", text, re.IGNORECASE)

    # Dead code heuristic: paragraphs that are defined but never PERFORMed
    defined_paras = re.findall(r"^[\s]{4,8}([\w-]+)\.\s*$", text, re.MULTILINE)
    called_paras = set(p.upper() for p in performs)
    dead_paras = [p for p in defined_paras if p.upper() not in called_paras]
    dead_code_lines = len(dead_paras) * 5  # estimate

    # Complexity scoring
    complexity = min(10, max(1,
        (total_lines // 500)
        + len(db_calls) // 5
        + len(file_ops) // 10
        + (1 if "GOBACK" in text else 0)
        + (2 if "ALTER" in text.upper() else 0)  # ALTER is evil in COBOL
    ))

    # Effort estimate
    if total_lines < 1000:
        effort = "S"
    elif total_lines < 5000:
        effort = "M"
    elif total_lines < 20000:
        effort = "L"
    else:
        effort = "XL"

    issues = []
    recommendations = []

    if "ALTER" in text.upper():
        issues.append("Uses ALTER verb — highly problematic for modernization")
    if "GO TO" in text.upper():
        issues.append("Uses GO TO — spaghetti code indicator")
    if total_lines > 10000:
        issues.append(f"Very large program ({total_lines} lines) — should be decomposed")
    if dead_code_lines > 0:
        issues.append(f"~{dead_code_lines} lines of potential dead code")

    recommendations.append("Wrap COBOL logic in REST API with Spring Boot or FastAPI adapter")
    recommendations.append("Migrate file I/O to PostgreSQL with JDBC")
    if db_calls:
        recommendations.append("Externalize SQL to a separate persistence layer")

    return CobolAnalysis(
        total_lines=total_lines,
        program_count=program_count,
        copybook_count=copybook_count,
        dead_code_lines=dead_code_lines,
        perform_calls=list(set(performs))[:20],
        file_operations=list(set(f[0] for f in file_ops))[:10],
        database_calls=[f[0] + " " + f[1] for f in db_calls][:10],
        complexity_score=complexity,
        modernization_effort=effort,
        issues=issues,
        recommendations=recommendations,
    )


def analyze_directory(cobol_dir: str | Path) -> dict:
    """
    Analyze an entire COBOL codebase directory.

    Returns:
        Summary dict with aggregate stats and per-file analyses
    """
    base = Path(cobol_dir)
    files = list(base.rglob("*.cbl")) + list(base.rglob("*.cob")) + list(base.rglob("*.cobol"))

    if not files:
        return {"error": "No COBOL files found"}

    analyses = []
    for f in files:
        try:
            analyses.append((f.name, analyze_file(f)))
        except Exception as exc:
            logger.warning(f"Failed to analyze {f}: {exc}")

    total_lines = sum(a.total_lines for _, a in analyses)
    avg_complexity = sum(a.complexity_score for _, a in analyses) / len(analyses) if analyses else 0

    return {
        "file_count": len(analyses),
        "total_lines": total_lines,
        "average_complexity": round(avg_complexity, 1),
        "total_copybooks": sum(a.copybook_count for _, a in analyses),
        "estimated_effort": "XL" if total_lines > 50000 else "L" if total_lines > 10000 else "M",
        "estimated_cost_nok": _estimate_cost(total_lines),
        "files": {name: _summary(a) for name, a in analyses[:10]},
    }


def _estimate_cost(total_lines: int) -> str:
    if total_lines < 2000:
        return "150,000 – 250,000 kr"
    elif total_lines < 10000:
        return "250,000 – 500,000 kr"
    elif total_lines < 50000:
        return "500,000 – 1,500,000 kr"
    return "1,500,000+ kr"


def _summary(a: CobolAnalysis) -> dict:
    return {
        "lines": a.total_lines,
        "complexity": a.complexity_score,
        "effort": a.modernization_effort,
        "issues": len(a.issues),
    }
