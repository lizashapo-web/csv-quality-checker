import json

from csv_checker.checks import run_checks
from csv_checker.reader import read_csv
from csv_checker.report import build_report, column_stats, format_text_report, save_report
from csv_checker.schema import ColumnRule, infer_schema, load_schema, parse_schema


def sample_report(sample_dir, **kwargs):
    data = read_csv(sample_dir / "people.csv")
    schema_path = sample_dir / "people.schema.json"
    schema = load_schema(schema_path)
    issues = run_checks(data, schema)
    return build_report("people.csv", data, schema, issues, schema_path=str(schema_path), **kwargs)


# --- column statistics --------------------------------------------------------------


def test_integer_stats_skip_invalid_and_empty_values(load):
    data = load("id,age\n1,10\n2,abc\n3,20\n4,\n")

    stats = column_stats(data.rows, "age", ColumnRule(type="int"))

    assert stats == {
        "expected_type": "int",
        "missing": 1,
        "unique": 3,  # "10", "abc", "20"
        "min": 10,
        "max": 20,
        "mean": 15.0,
    }


def test_float_stats(load):
    data = load("price\n1.5\n2.5\n")

    stats = column_stats(data.rows, "price", ColumnRule(type="float"))

    assert (stats["min"], stats["max"], stats["mean"]) == (1.5, 2.5, 2.0)


def test_date_stats_ignore_invalid_dates(load):
    data = load("d\n2024-03-01\n2024-01-15\nnot a date\n")

    stats = column_stats(data.rows, "d", ColumnRule(type="date"))

    assert (stats["earliest"], stats["latest"]) == ("2024-01-15", "2024-03-01")


def test_text_stats_show_the_most_common_value(load):
    data = load("city\nKyiv\nLviv\nKyiv\n")

    stats = column_stats(data.rows, "city", ColumnRule(type="text"))

    assert stats["most_common"] == {"value": "Kyiv", "count": 2}


def test_stats_of_a_column_without_values_have_no_extras(load):
    data = load("a,city\n1,\n2,\n")

    stats = column_stats(data.rows, "city", ColumnRule(type="text"))

    assert stats == {"expected_type": "text", "missing": 2, "unique": 0}


# --- the full report ----------------------------------------------------------------


def test_report_summary_for_the_sample_file(sample_dir):
    report = sample_report(sample_dir)

    assert report["summary"] == {
        "rows": 10,
        "columns": 6,
        "issues_total": 8,
        "rows_with_issues": 7,
        "clean_rows_percent": 30.0,
        "issues_by_type": {
            "duplicate_row": 1,
            "invalid_type": 3,
            "missing_value": 3,
            "out_of_range": 1,
        },
    }
    assert report["schema"]["source"] == "file"
    assert len(report["issues"]) == 8
    assert report["issues"][0] == {
        "type": "missing_value",
        "line": 4,
        "column": "email",
        "message": "Missing value in column 'email'",
    }


def test_report_counts_issues_per_column(sample_dir):
    columns = sample_report(sample_dir)["columns"]

    assert columns["age"]["issues"] == 2  # 'abc' and -5
    assert columns["signup_date"]["issues"] == 2
    assert columns["id"]["issues"] == 0
    assert columns["age"]["min"] == -5  # valid integers only, so -5 counts but 'abc' does not


def test_report_with_an_inferred_schema(sample_dir):
    data = read_csv(sample_dir / "people.csv")
    schema = infer_schema(data)

    report = build_report("people.csv", data, schema, run_checks(data, schema))

    assert report["schema"] == {"source": "inferred", "path": None}
    assert report["summary"]["issues_total"] == 7  # no min/max, so -5 is not an issue


def test_report_for_a_file_without_data_rows(load):
    data = load("a,b\n")
    schema = parse_schema({"columns": {"a": {"type": "int"}, "b": {"type": "text"}}})

    report = build_report("empty.csv", data, schema, run_checks(data, schema))

    assert report["summary"]["rows"] == 0
    assert report["summary"]["clean_rows_percent"] is None
    assert "no data rows" in format_text_report(report)


def test_problems_in_the_header_do_not_make_rows_dirty(load):
    data = load("a\n1\n2\n")
    schema = parse_schema({"columns": {"a": {"type": "int"}, "b": {"type": "int"}}})

    report = build_report("x.csv", data, schema, run_checks(data, schema))

    assert report["summary"]["issues_by_type"] == {"missing_column": 1}
    assert report["summary"]["rows_with_issues"] == 0
    assert report["summary"]["clean_rows_percent"] == 100.0


# --- JSON and text output -----------------------------------------------------------


def test_save_report_keeps_ukrainian_text_readable(tmp_path):
    path = tmp_path / "report.json"

    save_report({"city": "Київ"}, path)

    text = path.read_text(encoding="utf-8")
    assert "Київ" in text
    assert json.loads(text) == {"city": "Київ"}


def test_text_report_limits_the_number_of_issues(sample_dir):
    report = sample_report(sample_dir)

    limited = format_text_report(report, max_issues=3)
    everything = format_text_report(report, max_issues=0)

    assert "Issues (first 3 of 8)" in limited
    assert limited.count("  line ") == 3
    assert everything.count("  line ") == 8
    assert "first" not in everything


def test_text_report_for_a_clean_file(sample_dir):
    data = read_csv(sample_dir / "clean.csv")
    schema = infer_schema(data)

    text = format_text_report(build_report("clean.csv", data, schema, run_checks(data, schema)))

    assert "No issues found." in text
    assert "100.0% of rows" in text
