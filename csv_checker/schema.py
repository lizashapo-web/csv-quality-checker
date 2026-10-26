"""Column schema: what we expect from each column of a CSV file.

A schema can be written by hand as JSON::

    {"columns": {"age": {"type": "int", "min": 0, "max": 120},
                 "email": {"type": "email"}}}

or guessed from the data with :func:`infer_schema`.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, get_args

from csv_checker.reader import CsvData
from csv_checker.validators import is_email, is_float, is_int, looks_like_date

logger = logging.getLogger(__name__)

ColumnType = Literal["int", "float", "date", "email", "text"]
COLUMN_TYPES: tuple[str, ...] = get_args(ColumnType)
NUMERIC_TYPES: tuple[str, ...] = ("int", "float")

# A column gets a type when at least this share of its values look like it.
# Below 100% on purpose: real data is dirty, and we want to *find* the bad values.
INFERENCE_THRESHOLD = 0.8


class SchemaError(ValueError):
    """The schema is invalid or does not match the CSV file."""


@dataclass(frozen=True)
class ColumnRule:
    type: ColumnType
    min: float | None = None
    max: float | None = None


Schema = dict[str, ColumnRule]


def load_schema(path: str | Path) -> Schema:
    """Load and validate a schema from a JSON file."""
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except OSError as error:
        raise SchemaError(f"Cannot read schema file '{path}': {error}") from error
    except json.JSONDecodeError as error:
        raise SchemaError(f"Schema file '{path}' is not valid JSON: {error}") from error
    except UnicodeDecodeError as error:
        raise SchemaError(f"Schema file '{path}' is not valid UTF-8") from error
    return parse_schema(raw)


def parse_schema(raw: object) -> Schema:
    """Validate an already-parsed JSON object and turn it into a ``Schema``."""
    if not isinstance(raw, dict) or not isinstance(raw.get("columns"), dict):
        raise SchemaError('Schema must be a JSON object with a "columns" object')
    if not raw["columns"]:
        raise SchemaError("Schema does not describe any columns")
    return {str(name): _parse_rule(str(name), rule) for name, rule in raw["columns"].items()}


def _parse_rule(name: str, rule: object) -> ColumnRule:
    if not isinstance(rule, dict):
        raise SchemaError(f"Column '{name}': the rule must be an object")

    unknown = sorted(set(rule) - {"type", "min", "max"})
    if unknown:
        raise SchemaError(f"Column '{name}': unknown keys {unknown}")

    column_type = rule.get("type")
    if column_type not in COLUMN_TYPES:
        raise SchemaError(
            f"Column '{name}': type must be one of {list(COLUMN_TYPES)}, got {column_type!r}"
        )

    bounds: dict[str, float | None] = {}
    for key in ("min", "max"):
        value = rule.get(key)
        if value is not None:
            if column_type not in NUMERIC_TYPES:
                raise SchemaError(f"Column '{name}': '{key}' is only allowed for int/float")
            if isinstance(value, bool) or not isinstance(value, int | float):
                raise SchemaError(f"Column '{name}': '{key}' must be a number")
        bounds[key] = value

    low, high = bounds["min"], bounds["max"]
    if low is not None and high is not None and low > high:
        raise SchemaError(f"Column '{name}': min ({low}) is greater than max ({high})")
    return ColumnRule(type=column_type, min=low, max=high)


def save_schema(schema: Schema, path: str | Path) -> None:
    """Write a schema as JSON (so an inferred schema can be edited by hand)."""
    columns: dict[str, dict[str, object]] = {}
    for name, rule in schema.items():
        entry: dict[str, object] = {"type": rule.type}
        if rule.min is not None:
            entry["min"] = rule.min
        if rule.max is not None:
            entry["max"] = rule.max
        columns[name] = entry
    text = json.dumps({"columns": columns}, indent=2, ensure_ascii=False)
    Path(path).write_text(text + "\n", encoding="utf-8")


def infer_schema(data: CsvData) -> Schema:
    """Guess a type for every column from its non-empty values.

    Dates are recognised by their *shape* (``YYYY-MM-DD``), so a value such as
    ``2024-13-45`` still counts as "date-like" and is reported later as an
    invalid date instead of silently turning the whole column into text.
    """
    rows = data.valid_rows()
    schema: Schema = {}
    for column in data.columns:
        values = [value for row in rows if (value := row.values[column].strip())]
        schema[column] = ColumnRule(type=_infer_type(values))
        logger.info("Inferred type of '%s': %s", column, schema[column].type)
    return schema


_INFERENCE_ORDER: list[tuple[ColumnType, Callable[[str], bool]]] = [
    ("int", is_int),
    ("float", is_float),
    ("date", looks_like_date),
    ("email", is_email),
]


def _infer_type(values: list[str]) -> ColumnType:
    if not values:
        return "text"
    for column_type, matches in _INFERENCE_ORDER:
        share = sum(1 for value in values if matches(value)) / len(values)
        if share >= INFERENCE_THRESHOLD:
            return column_type
    return "text"
