import pytest

from csv_checker.checks import (
    describe_type_error,
    find_duplicates,
    find_malformed_rows,
    find_missing_values,
    find_out_of_range,
    find_schema_mismatch,
    find_type_errors,
    run_checks,
)
from csv_checker.reader import read_csv
from csv_checker.schema import load_schema, parse_schema


def make_schema(**columns):
    return parse_schema({"columns": columns})


def summary(issues):
    """(line, type, column) for each issue: short and easy to compare in tests."""
    return [(issue.line, issue.type, issue.column) for issue in issues]


# --- missing values -----------------------------------------------------------------


def test_missing_values_include_whitespace_only_cells(load):
    data = load("a,b\n1,\n  ,2\n3,4\n")

    assert summary(find_missing_values(data)) == [
        (2, "missing_value", "b"),
        (3, "missing_value", "a"),
    ]


def test_no_missing_values(load):
    assert find_missing_values(load("a,b\n1,2\n")) == []


# --- malformed rows -----------------------------------------------------------------


def test_malformed_rows_are_reported_once_and_skipped_by_other_checks(load):
    data = load("a,b\n1\n1,2,3\n4,5\n")

    assert summary(find_malformed_rows(data)) == [
        (2, "malformed_row", None),
        (3, "malformed_row", None),
    ]
    assert "expected 2" in find_malformed_rows(data)[0].message
    # the short row has an "empty" b, but that must not be reported as a missing value
    assert find_missing_values(data) == []


# --- duplicates ---------------------------------------------------------------------


def test_duplicates_report_later_copies_only(load):
    data = load("a,b\n1,x\n2,y\n1,x\n1, x\n")

    issues = find_duplicates(data)

    assert summary(issues) == [(4, "duplicate_row", None), (5, "duplicate_row", None)]
    assert issues[0].message == "Duplicate of line 2"


def test_rows_that_differ_are_not_duplicates(load):
    assert find_duplicates(load("a,b\n1,x\n1,y\n")) == []


# --- types --------------------------------------------------------------------------

TYPE_CASES = [
    ("int", "28", False),
    ("int", "abc", True),
    ("int", "1.5", True),
    ("int", "1_000", True),
    ("float", "1.5", False),
    ("float", "7", False),
    ("float", "abc", True),
    ("float", "nan", True),
    ("date", "2024-02-29", False),
    ("date", "2023-02-29", True),
    ("date", "2024-13-45", True),
    ("date", "not a date", True),
    ("email", "a@b.co", False),
    ("email", "a@b", True),
    ("text", "Kyiv", False),
    ("text", "Nan", False),  # a real name, even though float("Nan") works in Python
    ("text", "Infinity", False),
    ("text", "123", True),
    ("text", "3.14", True),
]


@pytest.mark.parametrize(("column_type", "value", "is_error"), TYPE_CASES)
def test_describe_type_error(column_type, value, is_error):
    assert (describe_type_error(value, column_type) is not None) is is_error


def test_find_type_errors_reports_line_column_and_message(load):
    data = load("id,age\n1,28\n2,abc\n")

    issues = find_type_errors(data, make_schema(id={"type": "int"}, age={"type": "int"}))

    assert summary(issues) == [(3, "invalid_type", "age")]
    assert issues[0].message == "age: 'abc' is not an integer"


def test_type_check_skips_empty_values(load):
    # the empty cell is a *missing* value, not an invalid integer
    data = load("a,b\n1,\n")

    assert find_type_errors(data, make_schema(b={"type": "int"})) == []


def test_type_check_ignores_schema_columns_that_are_not_in_the_file(load):
    data = load("a\n1\n")

    assert find_type_errors(data, make_schema(a={"type": "int"}, ghost={"type": "int"})) == []


def test_type_check_skips_malformed_rows(load):
    data = load("a,b\nabc\n")

    assert find_type_errors(data, make_schema(a={"type": "int"})) == []


# --- ranges -------------------------------------------------------------------------


def test_out_of_range_checks_both_bounds_and_allows_the_bounds_themselves(load):
    data = load("age\n-5\n0\n120\n121\n")

    issues = find_out_of_range(data, make_schema(age={"type": "int", "min": 0, "max": 120}))

    assert summary(issues) == [(2, "out_of_range", "age"), (5, "out_of_range", "age")]
    assert issues[0].message == "age: -5 is below the minimum 0"
    assert issues[1].message == "age: 121 is above the maximum 120"


def test_out_of_range_works_for_float_columns(load):
    data = load("price\n0.25\n0.5\n")

    issues = find_out_of_range(data, make_schema(price={"type": "float", "min": 0.5}))

    assert [issue.message for issue in issues] == ["price: 0.25 is below the minimum 0.5"]


def test_out_of_range_ignores_values_that_are_not_numbers(load):
    data = load("age\nabc\n\n10\n")  # blank line is skipped, "abc" is a type error

    assert find_out_of_range(data, make_schema(age={"type": "int", "min": 0})) == []


# --- schema mismatch ----------------------------------------------------------------


def test_schema_mismatch_reports_both_directions_on_line_one(load):
    data = load("a,extra\n1,2\n")

    issues = find_schema_mismatch(data, make_schema(a={"type": "int"}, b={"type": "int"}))

    assert summary(issues) == [(1, "missing_column", "b"), (1, "unexpected_column", "extra")]


# --- everything together ------------------------------------------------------------


def test_run_checks_on_the_sample_file(sample_dir):
    data = read_csv(sample_dir / "people.csv")
    schema = load_schema(sample_dir / "people.schema.json")

    assert summary(run_checks(data, schema)) == [
        (4, "missing_value", "email"),
        (5, "invalid_type", "age"),
        (6, "invalid_type", "signup_date"),
        (7, "duplicate_row", None),
        (8, "out_of_range", "age"),
        (8, "missing_value", "city"),
        (9, "invalid_type", "signup_date"),
        (10, "missing_value", "name"),
    ]


def test_run_checks_finds_nothing_in_a_clean_file(sample_dir):
    data = read_csv(sample_dir / "clean.csv")
    schema = load_schema(sample_dir / "people.schema.json")

    assert run_checks(data, schema) == []
