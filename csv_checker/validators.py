"""Small, strict validators for single CSV cell values.

All functions expect a value that is already stripped of surrounding
whitespace. Python's own ``int()`` and ``float()`` are too forgiving for data
validation (``int("1_000")`` works, ``float("nan")`` works), so we check the
text against a regular expression first.
"""

from __future__ import annotations

import math
import re
from datetime import datetime

DATE_FORMAT = "%Y-%m-%d"

_INT_RE = re.compile(r"[+-]?[0-9]+")
_FLOAT_RE = re.compile(r"[+-]?([0-9]+(\.[0-9]*)?|\.[0-9]+)([eE][+-]?[0-9]+)?")
_DATE_RE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
_EMAIL_RE = re.compile(r"[^@\s]+@[^@\s.]+(\.[^@\s.]+)+")


def parse_int(value: str) -> int | None:
    """Return the integer value of ``value`` or ``None`` if it is not an integer."""
    if not _INT_RE.fullmatch(value):
        return None
    try:
        return int(value)
    except ValueError:  # e.g. absurdly long digit strings
        return None


def parse_float(value: str) -> float | None:
    """Return the finite float value of ``value`` or ``None``."""
    if not _FLOAT_RE.fullmatch(value):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def is_int(value: str) -> bool:
    return parse_int(value) is not None


def is_float(value: str) -> bool:
    """True for any decimal number, including integers."""
    return parse_float(value) is not None


def looks_like_date(value: str) -> bool:
    """True if the text has the shape ``YYYY-MM-DD`` (the date may still be fake)."""
    return _DATE_RE.fullmatch(value) is not None


def parse_date(value: str) -> datetime | None:
    """Parse a strict ``YYYY-MM-DD`` date, or return ``None``.

    ``strptime`` alone would also accept ``2024-1-5``, so the shape is checked
    first. ``2024-02-30`` and ``2024-13-45`` are rejected by ``strptime``.
    """
    if not looks_like_date(value):
        return None
    try:
        return datetime.strptime(value, DATE_FORMAT)
    except ValueError:
        return None


def is_date(value: str) -> bool:
    return parse_date(value) is not None


def is_email(value: str) -> bool:
    """A pragmatic email check: ``local@domain.tld`` with no spaces."""
    return _EMAIL_RE.fullmatch(value) is not None
