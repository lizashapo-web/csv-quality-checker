"""Shared fixtures for the tests."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from csv_checker.reader import CsvData, read_csv

SAMPLE_DIR = Path(__file__).resolve().parent.parent / "sample_data"


@pytest.fixture
def sample_dir() -> Path:
    """The folder with the example CSV files that ship with the project."""
    return SAMPLE_DIR


@pytest.fixture
def write_csv(tmp_path: Path) -> Callable[..., Path]:
    """Write text to a temporary file and return its path."""

    def _write(text: str, name: str = "data.csv") -> Path:
        path = tmp_path / name
        path.write_text(text, encoding="utf-8", newline="")
        return path

    return _write


@pytest.fixture
def load(write_csv: Callable[..., Path]) -> Callable[[str], CsvData]:
    """Turn CSV text straight into ``CsvData``."""

    def _load(text: str) -> CsvData:
        return read_csv(write_csv(text))

    return _load
