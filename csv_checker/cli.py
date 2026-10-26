"""Command-line interface: ``csv-quality-checker data.csv``."""

from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Sequence

from csv_checker import __version__
from csv_checker.checks import run_checks
from csv_checker.reader import CsvReadError, read_csv
from csv_checker.report import build_report, format_text_report, save_report
from csv_checker.schema import SchemaError, infer_schema, load_schema, save_schema

logger = logging.getLogger(__name__)

EXIT_OK = 0
EXIT_ISSUES = 1
EXIT_ERROR = 2


def _non_negative_int(text: str) -> int:
    try:
        number = int(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"{text!r} is not a whole number") from None
    if number < 0:
        raise argparse.ArgumentTypeError("must be 0 or greater")
    return number


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="csv-quality-checker",
        description="Check the quality of a CSV file: missing values, duplicate rows, "
        "wrong types, out-of-range numbers and invalid dates.",
        epilog="exit codes: 0 = no issues, 1 = issues found, 2 = error (bad file, bad schema, ...)",
    )
    parser.add_argument("csv_path", help="path to the CSV file to check (UTF-8)")
    parser.add_argument(
        "-s",
        "--schema",
        metavar="FILE",
        help="JSON file describing the expected column types "
        "(default: guess the types from the data)",
    )
    parser.add_argument(
        "-o", "--output", metavar="FILE", help="also write the full report to FILE as JSON"
    )
    parser.add_argument(
        "--save-schema",
        metavar="FILE",
        help="write the schema that was used to FILE, so it can be edited and reused with --schema",
    )
    parser.add_argument(
        "-d", "--delimiter", default=",", help="field delimiter, one character (default: ',')"
    )
    parser.add_argument(
        "--max-issues",
        type=_non_negative_int,
        default=20,
        metavar="N",
        help="show at most N issues in the terminal, 0 = all (default: 20)",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="show debug messages")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the tool and return the process exit code."""
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="%(levelname)s: %(message)s",
        stream=sys.stderr,
        force=True,
    )

    try:
        data = read_csv(args.csv_path, delimiter=args.delimiter)
        schema = load_schema(args.schema) if args.schema else infer_schema(data)
        issues = run_checks(data, schema)
        report = build_report(args.csv_path, data, schema, issues, schema_path=args.schema)

        print(format_text_report(report, max_issues=args.max_issues))
        if args.output:
            save_report(report, args.output)
            print(f"\nJSON report written to {args.output}")
        if args.save_schema:
            save_schema(schema, args.save_schema)
            print(f"Schema written to {args.save_schema}")
    except (CsvReadError, SchemaError) as error:
        logger.error("%s", error)
        return EXIT_ERROR
    except OSError as error:  # cannot write the report or the schema
        logger.error("Could not write output file: %s", error)
        return EXIT_ERROR

    return EXIT_ISSUES if issues else EXIT_OK
