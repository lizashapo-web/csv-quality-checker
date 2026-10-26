"""Building the quality report: per-column statistics, a summary, JSON and text output."""

from __future__ import annotations

import json
import logging
from collections import Counter
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from csv_checker import __version__
from csv_checker.checks import Issue
from csv_checker.reader import CsvData, Row
from csv_checker.schema import ColumnRule, Schema
from csv_checker.validators import parse_date, parse_float, parse_int

logger = logging.getLogger(__name__)


def column_stats(rows: list[Row], column: str, rule: ColumnRule) -> dict[str, Any]:
    """Statistics for one column.

    Every column gets the number of missing and unique values. Numeric columns also
    get min / max / mean, date columns the earliest and latest date, and the other
    columns their most common value. Invalid values are left out of min / max / mean
    (the type check reports them separately).
    """
    values = [value for row in rows if (value := row.values[column].strip())]
    stats: dict[str, Any] = {
        "expected_type": rule.type,
        "missing": len(rows) - len(values),
        "unique": len(set(values)),
    }

    if rule.type == "int":
        integers = [whole for value in values if (whole := parse_int(value)) is not None]
        if integers:
            stats |= {
                "min": min(integers),
                "max": max(integers),
                "mean": round(sum(integers) / len(integers), 2),
            }
    elif rule.type == "float":
        decimals = [number for value in values if (number := parse_float(value)) is not None]
        if decimals:
            stats |= {
                "min": min(decimals),
                "max": max(decimals),
                "mean": round(sum(decimals) / len(decimals), 2),
            }
    elif rule.type == "date":
        dates = [d for value in values if (d := parse_date(value)) is not None]
        if dates:
            stats |= {
                "earliest": min(dates).date().isoformat(),
                "latest": max(dates).date().isoformat(),
            }
    elif values:
        value, count = Counter(values).most_common(1)[0]
        stats["most_common"] = {"value": value, "count": count}

    return stats


def build_report(
    path: str,
    data: CsvData,
    schema: Schema,
    issues: list[Issue],
    schema_path: str | None = None,
) -> dict[str, Any]:
    """Collect everything into one dictionary that can be written as JSON."""
    # Line 1 is the header: problems there (missing columns) do not make a *row* dirty.
    dirty_lines = {issue.line for issue in issues if issue.line > 1}
    total_rows = len(data.rows)
    clean_rows = total_rows - len(dirty_lines)
    issues_per_column = Counter(issue.column for issue in issues if issue.column)

    valid_rows = data.valid_rows()
    columns: dict[str, dict[str, Any]] = {}
    for column in data.columns:
        if column in schema:
            stats = column_stats(valid_rows, column, schema[column])
            columns[column] = {**stats, "issues": issues_per_column[column]}

    return {
        "tool_version": __version__,
        "file": path,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "schema": {
            "source": "file" if schema_path else "inferred",
            "path": schema_path,
        },
        "summary": {
            "rows": total_rows,
            "columns": len(data.columns),
            "issues_total": len(issues),
            "rows_with_issues": len(dirty_lines),
            "clean_rows_percent": round(100 * clean_rows / total_rows, 1) if total_rows else None,
            "issues_by_type": dict(sorted(Counter(issue.type for issue in issues).items())),
        },
        "columns": columns,
        "issues": [asdict(issue) for issue in issues],
    }


def save_report(report: dict[str, Any], output_path: str | Path) -> None:
    """Write the report as pretty-printed UTF-8 JSON.

    ``ensure_ascii=False`` keeps non-English text readable instead of ``\\u0414...``.
    """
    with Path(output_path).open("w", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    logger.info("Report written to %s", output_path)


def format_text_report(report: dict[str, Any], max_issues: int = 20) -> str:
    """Render the report for the terminal. ``max_issues=0`` shows every issue."""
    summary = report["summary"]
    schema = report["schema"]
    lines = [
        "CSV Quality Report",
        "==================",
        f"File:    {report['file']}",
        "Schema:  " + (schema["path"] if schema["source"] == "file" else "inferred from the data"),
        f"Size:    {summary['rows']} rows, {summary['columns']} columns",
    ]

    if summary["rows"] == 0:
        lines.append("Clean:   no data rows")
    else:
        lines.append(
            f"Clean:   {summary['clean_rows_percent']}% of rows "
            f"({summary['rows'] - summary['rows_with_issues']} of {summary['rows']}) have no issues"
        )

    issues = report["issues"]
    if not issues:
        lines += ["", "No issues found."]
        return "\n".join(lines)

    lines += ["", f"Issues by type ({summary['issues_total']} in total)"]
    width = max(len(name) for name in summary["issues_by_type"])
    lines += [f"  {name:<{width}}  {count}" for name, count in summary["issues_by_type"].items()]

    shown = issues if max_issues == 0 else issues[:max_issues]
    if len(shown) == len(issues):
        heading = "Issues"
    else:
        heading = f"Issues (first {len(shown)} of {len(issues)})"
    lines += ["", heading]
    lines += [f"  line {issue['line']:>3}  {issue['message']}" for issue in shown]
    return "\n".join(lines)
