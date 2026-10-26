# CSV Quality Checker

A small command-line tool that reads a CSV file, finds data quality problems and
produces a report, both in the terminal and as JSON.

Imagine receiving a table with thousands of rows where some values are missing,
some rows are duplicated, some dates are impossible and some "numbers" are text.
This tool finds all of that automatically and tells you **which line** and
**which column** is wrong.

It uses only the Python standard library, so there is nothing to install except
the tool itself.

## What it checks

| Issue type          | Example                                              |
|---------------------|------------------------------------------------------|
| `missing_value`     | an empty cell, or a cell with only spaces            |
| `duplicate_row`     | a row that repeats an earlier row exactly            |
| `invalid_type`      | `abc` in an integer column, `2024-13-45` as a date   |
| `out_of_range`      | age `-5` when the schema says `min: 0`               |
| `malformed_row`     | a row with more or fewer fields than the header      |
| `missing_column`    | the schema expects a column the file does not have   |
| `unexpected_column` | the file has a column the schema does not describe   |

Supported column types: `int`, `float`, `date` (`YYYY-MM-DD`), `email`, `text`.
Numbers must be real numbers: Python-only spellings such as `1_000` or `nan` are rejected.

## Installation

Requires Python 3.10 or newer.

```bash
git clone <your-repo-url>
cd csv-quality-checker
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e .
```

You can also skip the installation and run `python -m csv_checker ...` from the
project folder.

## Usage

```bash
# Let the tool guess the column types from the data
csv-quality-checker sample_data/people.csv

# Use an explicit schema and also write a JSON report
csv-quality-checker sample_data/people.csv \
    --schema sample_data/people.schema.json \
    --output report.json

# Guess the schema, save it, edit it by hand, reuse it later
csv-quality-checker sample_data/people.csv --save-schema my_schema.json
```

All options:

| Option                | Meaning                                                          |
|-----------------------|------------------------------------------------------------------|
| `-s, --schema FILE`   | JSON schema with the expected column types (default: infer them) |
| `-o, --output FILE`   | also write the full report to `FILE` as JSON                     |
| `--save-schema FILE`  | write the schema that was used, so it can be edited and reused   |
| `-d, --delimiter C`   | field delimiter, one character (default `,`)                     |
| `--max-issues N`      | show at most `N` issues in the terminal, `0` = all (default 20)  |
| `-v, --verbose`       | show debug messages                                              |
| `--version`           | print the version                                                |

### Exit codes

The exit code makes the tool usable in scripts and CI pipelines.

| Code | Meaning                                                   |
|------|-----------------------------------------------------------|
| `0`  | the file was checked and no issues were found             |
| `1`  | the file was checked and issues were found                |
| `2`  | the tool could not run (missing file, bad schema, ...)    |

## Example

`sample_data/people.csv` is a small file with deliberately broken data:

```text
$ csv-quality-checker sample_data/people.csv --schema sample_data/people.schema.json
CSV Quality Report
==================
File:    sample_data/people.csv
Schema:  sample_data/people.schema.json
Size:    10 rows, 6 columns
Clean:   30.0% of rows (3 of 10) have no issues

Issues by type (8 in total)
  duplicate_row  1
  invalid_type   3
  missing_value  3
  out_of_range   1

Issues
  line   4  Missing value in column 'email'
  line   5  age: 'abc' is not an integer
  line   6  signup_date: '2024-13-45' is not a valid date (expected YYYY-MM-DD)
  line   7  Duplicate of line 3
  line   8  age: -5 is below the minimum 0
  line   8  Missing value in column 'city'
  line   9  signup_date: 'not a date' is not a valid date (expected YYYY-MM-DD)
  line  10  Missing value in column 'name'
```

Line numbers are real line numbers of the file (the header is line 1), so you can
jump straight to the problem in a spreadsheet or editor.

## Schema file

```json
{
  "columns": {
    "id":          {"type": "int"},
    "email":       {"type": "email"},
    "age":         {"type": "int", "min": 0, "max": 120},
    "signup_date": {"type": "date"},
    "city":        {"type": "text"}
  }
}
```

`min` and `max` are optional and only allowed for `int` and `float`. A broken
schema is rejected with a clear message before any checking starts.

When no schema is given, the type of each column is guessed: a column gets a type
when at least 80% of its non-empty values look like it. The threshold is below
100% on purpose, because real data is dirty and the goal is to *find* the values
that do not fit, not to give up and call the whole column text.

## JSON report

The report written by `--output` has four parts: `summary`, per-column
`columns` statistics, and the full list of `issues`
(see [`examples/report.json`](examples/report.json)):

```json
{
  "summary": {
    "rows": 10,
    "columns": 6,
    "issues_total": 8,
    "rows_with_issues": 7,
    "clean_rows_percent": 30.0,
    "issues_by_type": {"duplicate_row": 1, "invalid_type": 3, "missing_value": 3, "out_of_range": 1}
  },
  "columns": {
    "age": {
      "expected_type": "int", "missing": 0, "unique": 9,
      "min": -5, "max": 52, "mean": 29.89, "issues": 2
    }
  },
  "issues": [
    {"type": "missing_value", "line": 4, "column": "email",
     "message": "Missing value in column 'email'"}
  ]
}
```

## Project structure

```text
csv_checker/
  reader.py      reads the CSV into simple dataclasses (with real line numbers)
  validators.py  strict checks for single values: int, float, date, email
  schema.py      loading, validating, saving and inferring the column schema
  checks.py      the quality checks; each returns a list of Issue objects
  report.py      statistics, JSON report and terminal output
  cli.py         argument parsing and exit codes
tests/           pytest test suite
sample_data/     example CSV files and a schema
examples/        an example JSON report
```

The layers are kept separate on purpose: the reader knows nothing about checks, the
checks know nothing about the terminal, and the CLI is a thin layer on top. That
makes every part testable on its own.

## Design decisions

- **Everything is read as text first.** The reader never decides whether `abc` is a
  valid age; the checks do. That keeps bad data visible instead of crashing the read.
- **Strict validators instead of `int()` / `float()`.** Python accepts `1_000`,
  `nan` and non-Latin digits, none of which is valid data in a CSV file.
- **Malformed rows are reported once** and excluded from the value checks, so one
  broken row does not produce a pile of confusing follow-up errors.
- **Errors never show a traceback.** Missing files, wrong encoding, a broken schema
  or an unwritable output path give a one-line message and exit code `2`.
- **Easy to extend.** Issues are plain frozen dataclasses, so adding a new check means
  writing one function that returns `list[Issue]` and adding it to `run_checks`.

## Development

```bash
pip install -e ".[dev]"

pytest                 # tests
ruff check .           # lint
ruff format --check .  # formatting
mypy                   # strict type checking
```

The same four commands run in GitHub Actions on Python 3.10 to 3.13
(see `.github/workflows/ci.yml`).

## Limitations and ideas for the future

- The whole file is loaded into memory, which is fine for files up to a few hundred
  thousand rows. Checking row by row from the reader would remove that limit.
- Dates must be `YYYY-MM-DD`; other formats are reported as invalid.
- Only UTF-8 files are supported (a UTF-8 BOM from Excel is handled).
- Possible additions: a `unique` rule for key columns, regular-expression rules,
  an HTML report, an `--encoding` option.

## License

MIT
