"""Data quality checks.

Every check takes the parsed CSV data (and, when needed, the schema) and returns a
list of :class:`Issue` objects. Checks never raise on bad data: finding bad data is
their job.

Only *well-formed* rows (same number of fields as the header) are inspected by the
value checks. A malformed row is reported once, by :func:`find_malformed_rows`,
instead of producing a confusing pile of follow-up errors.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from csv_checker.reader import CsvData
from csv_checker.schema import NUMERIC_TYPES, ColumnType, Schema
from csv_checker.validators import is_date, is_email, is_float, is_int, parse_float, parse_int

logger = logging.getLogger(__name__)

# Issue types (the "type" field of an Issue and the keys of the report summary).
MALFORMED_ROW = "malformed_row"
MISSING_VALUE = "missing_value"
DUPLICATE_ROW = "duplicate_row"
INVALID_TYPE = "invalid_type"
OUT_OF_RANGE = "out_of_range"
MISSING_COLUMN = "missing_column"
UNEXPECTED_COLUMN = "unexpected_column"


@dataclass(frozen=True)
class Issue:
    """One problem found in the file.

    ``line`` is the line number in the CSV file (the header is line 1).
    ``column`` is ``None`` when the problem concerns the whole row.
    """

    type: str
    line: int
    column: str | None
    message: str


def find_malformed_rows(data: CsvData) -> list[Issue]:
    """Rows with more or fewer fields than the header."""
    expected = len(data.columns)
    return [
        Issue(
            MALFORMED_ROW, row.line, None, f"Row has {row.field_count} fields, expected {expected}"
        )
        for row in data.rows
        if row.field_count != expected
    ]


def find_missing_values(data: CsvData) -> list[Issue]:
    """Empty cells (or cells that contain only spaces)."""
    return [
        Issue(MISSING_VALUE, row.line, column, f"Missing value in column '{column}'")
        for row in data.valid_rows()
        for column in data.columns
        if not row.values[column].strip()
    ]


def find_duplicates(data: CsvData) -> list[Issue]:
    """Rows that repeat an earlier row exactly (the first copy is not reported)."""
    issues: list[Issue] = []
    first_seen: dict[tuple[str, ...], int] = {}  # row content -> line of first copy

    for row in data.valid_rows():
        # A tuple (unlike a list) can be a dictionary key.
        key = tuple(row.values[column].strip() for column in data.columns)
        if key in first_seen:
            issues.append(
                Issue(DUPLICATE_ROW, row.line, None, f"Duplicate of line {first_seen[key]}")
            )
        else:
            first_seen[key] = row.line
    return issues


def find_schema_mismatch(data: CsvData, schema: Schema) -> list[Issue]:
    """Columns that the schema expects but the file lacks, and the other way round."""
    issues = [
        Issue(MISSING_COLUMN, 1, name, f"Column '{name}' is in the schema but not in the file")
        for name in schema
        if name not in data.columns
    ]
    issues += [
        Issue(UNEXPECTED_COLUMN, 1, name, f"Column '{name}' is in the file but not in the schema")
        for name in data.columns
        if name not in schema
    ]
    return issues


def describe_type_error(value: str, column_type: ColumnType) -> str | None:
    """Explain why ``value`` does not fit ``column_type``, or return ``None`` if it fits."""
    if column_type == "int":
        return None if is_int(value) else f"'{value}' is not an integer"
    if column_type == "float":
        return None if is_float(value) else f"'{value}' is not a number"
    if column_type == "date":
        return None if is_date(value) else f"'{value}' is not a valid date (expected YYYY-MM-DD)"
    if column_type == "email":
        return None if is_email(value) else f"'{value}' is not a valid email address"
    # text: anything goes, except a bare number, which usually means a column mix-up
    return f"'{value}' is a number, but text was expected" if is_float(value) else None


def find_type_errors(data: CsvData, schema: Schema) -> list[Issue]:
    """Values that do not match the type the schema expects for their column.

    Empty values are skipped here: :func:`find_missing_values` already reports them.
    """
    issues: list[Issue] = []
    for row in data.valid_rows():
        for column, rule in schema.items():
            if column not in row.values:
                continue
            value = row.values[column].strip()
            if not value:
                continue
            problem = describe_type_error(value, rule.type)
            if problem:
                issues.append(Issue(INVALID_TYPE, row.line, column, f"{column}: {problem}"))
    return issues


def find_out_of_range(data: CsvData, schema: Schema) -> list[Issue]:
    """Numbers below ``min`` or above ``max``. Non-numbers are a type error, not this."""
    issues: list[Issue] = []
    for column, rule in schema.items():
        if column not in data.columns or rule.type not in NUMERIC_TYPES:
            continue
        for row in data.valid_rows():
            value = row.values[column].strip()
            number = parse_int(value) if rule.type == "int" else parse_float(value)
            if number is None:
                continue
            if rule.min is not None and number < rule.min:
                message = f"{column}: {value} is below the minimum {rule.min:g}"
            elif rule.max is not None and number > rule.max:
                message = f"{column}: {value} is above the maximum {rule.max:g}"
            else:
                continue
            issues.append(Issue(OUT_OF_RANGE, row.line, column, message))
    return issues


def run_checks(data: CsvData, schema: Schema) -> list[Issue]:
    """Run every check and return all issues ordered by line, then column."""
    issues: list[Issue] = []
    checks = (
        ("malformed rows", find_malformed_rows(data)),
        ("schema mismatch", find_schema_mismatch(data, schema)),
        ("missing values", find_missing_values(data)),
        ("duplicate rows", find_duplicates(data)),
        ("type errors", find_type_errors(data, schema)),
        ("out-of-range values", find_out_of_range(data, schema)),
    )
    for name, found in checks:
        logger.debug("Check '%s' found %d issue(s)", name, len(found))
        issues += found
    return sorted(issues, key=lambda issue: (issue.line, issue.column or "", issue.type))
