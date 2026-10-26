"""Reading CSV files into a simple in-memory structure."""

from __future__ import annotations

import csv
import logging
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


class CsvReadError(Exception):
    """The file could not be read as CSV (missing, empty, bad encoding, ...)."""


@dataclass(frozen=True)
class Row:
    """One data row.

    ``line`` is the line number in the file where the row starts (the header is
    line 1). ``field_count`` is how many fields the row really had, which can
    differ from the header when the file is malformed.
    """

    line: int
    values: dict[str, str]
    field_count: int


@dataclass(frozen=True)
class CsvData:
    columns: list[str]
    rows: list[Row]

    def valid_rows(self) -> list[Row]:
        """Rows with the same number of fields as the header."""
        expected = len(self.columns)
        return [row for row in self.rows if row.field_count == expected]


def read_csv(path: str | Path, delimiter: str = ",") -> CsvData:
    """Read a CSV file.

    All values stay strings: deciding whether ``"abc"`` is a valid age is the
    job of the checks, not of the reader. Blank lines are skipped and a UTF-8
    BOM (added by Excel) is handled.

    Raises:
        CsvReadError: if the file cannot be read or has no usable header.
    """
    file_path = Path(path)

    if len(delimiter) != 1:
        raise CsvReadError(f"Delimiter must be a single character, got {delimiter!r}")
    if not file_path.exists():
        raise CsvReadError(f"File not found: {file_path}")
    if file_path.is_dir():
        raise CsvReadError(f"Expected a file but got a directory: {file_path}")

    try:
        with file_path.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.reader(handle, delimiter=delimiter)

            header = next((record for record in reader if record), None)
            if header is None:
                raise CsvReadError(f"File is empty (no header row): {file_path}")
            columns = _validate_header(header)

            rows: list[Row] = []
            previous_line = reader.line_num
            for record in reader:
                # A quoted field can span several lines, so the row starts on
                # the line after the previous record ended.
                start_line = previous_line + 1
                previous_line = reader.line_num
                if not record:  # blank line
                    continue
                rows.append(_make_row(start_line, record, columns))
    except UnicodeDecodeError as error:
        raise CsvReadError(
            f"File is not valid UTF-8 (byte {error.start}). Re-save it as UTF-8 and try again."
        ) from error
    except csv.Error as error:
        raise CsvReadError(f"Malformed CSV: {error}") from error
    except OSError as error:  # e.g. no permission to read the file
        raise CsvReadError(f"Cannot read file '{file_path}': {error}") from error

    logger.info("Read %d rows and %d columns from %s", len(rows), len(columns), path)
    return CsvData(columns=columns, rows=rows)


def _validate_header(header: list[str]) -> list[str]:
    columns = [name.strip() for name in header]
    if any(name == "" for name in columns):
        raise CsvReadError("Header contains an empty column name")
    duplicates = sorted({name for name in columns if columns.count(name) > 1})
    if duplicates:
        raise CsvReadError(f"Header contains duplicate column names: {duplicates}")
    return columns


def _make_row(line: int, record: list[str], columns: list[str]) -> Row:
    """Pad or cut the record to the header width so every column has a value."""
    width = len(columns)
    padded = (record + [""] * width)[:width]
    return Row(line=line, values=dict(zip(columns, padded, strict=True)), field_count=len(record))
