import json
import subprocess
import sys
from pathlib import Path

import pytest

from csv_checker.cli import EXIT_ERROR, EXIT_ISSUES, EXIT_OK, main
from csv_checker.schema import load_schema

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def test_exit_code_1_and_report_when_issues_are_found(sample_dir, capsys):
    code = main(
        [str(sample_dir / "people.csv"), "--schema", str(sample_dir / "people.schema.json")]
    )

    out = capsys.readouterr().out
    assert code == EXIT_ISSUES
    assert "8 in total" in out
    assert "Duplicate of line 3" in out
    assert "age: -5 is below the minimum 0" in out


def test_exit_code_0_for_a_clean_file(sample_dir, capsys):
    code = main([str(sample_dir / "clean.csv")])

    assert code == EXIT_OK
    assert "No issues found." in capsys.readouterr().out


def test_schema_is_inferred_when_not_given(sample_dir, capsys):
    main([str(sample_dir / "people.csv")])

    assert "inferred from the data" in capsys.readouterr().out


def test_missing_csv_file_is_a_clean_error(capsys):
    code = main(["definitely-not-here.csv"])

    captured = capsys.readouterr()
    assert code == EXIT_ERROR
    assert "File not found" in captured.err
    assert "Traceback" not in captured.err


def test_missing_schema_file_is_a_clean_error(sample_dir, capsys):
    code = main([str(sample_dir / "clean.csv"), "--schema", "nope.json"])

    assert code == EXIT_ERROR
    assert "Cannot read schema file" in capsys.readouterr().err


def test_json_output(sample_dir, tmp_path, capsys):
    output = tmp_path / "report.json"

    code = main(
        [
            str(sample_dir / "people.csv"),
            "-s",
            str(sample_dir / "people.schema.json"),
            "-o",
            str(output),
        ]
    )

    report = json.loads(output.read_text(encoding="utf-8"))
    assert code == EXIT_ISSUES
    assert report["summary"]["issues_total"] == 8
    assert "JSON report written" in capsys.readouterr().out


def test_unwritable_output_path_is_a_clean_error(sample_dir, tmp_path, capsys):
    bad_path = tmp_path / "no-such-folder" / "report.json"

    code = main([str(sample_dir / "clean.csv"), "-o", str(bad_path)])

    assert code == EXIT_ERROR
    assert "Could not write output file" in capsys.readouterr().err


def test_save_schema_writes_a_reusable_schema(sample_dir, tmp_path, capsys):
    saved = tmp_path / "schema.json"

    main([str(sample_dir / "people.csv"), "--save-schema", str(saved)])

    assert load_schema(saved)["age"].type == "int"
    # and the saved schema can be fed straight back in
    capsys.readouterr()
    assert main([str(sample_dir / "people.csv"), "--schema", str(saved)]) == EXIT_ISSUES


def test_max_issues_limits_terminal_output(sample_dir, capsys):
    main([str(sample_dir / "people.csv"), "--max-issues", "2"])

    assert "first 2 of 7" in capsys.readouterr().out


def test_negative_max_issues_is_rejected_by_argparse(sample_dir, capsys):
    with pytest.raises(SystemExit) as exit_info:
        main([str(sample_dir / "people.csv"), "--max-issues", "-1"])

    assert exit_info.value.code == 2
    assert "must be 0 or greater" in capsys.readouterr().err


def test_custom_delimiter(write_csv, capsys):
    path = write_csv("a;b\n1;x\n2;y\n")

    assert main([str(path), "--delimiter", ";"]) == EXIT_OK


def test_version_flag(capsys):
    with pytest.raises(SystemExit) as exit_info:
        main(["--version"])

    assert exit_info.value.code == 0
    assert "1.0.0" in capsys.readouterr().out


def test_verbose_flag_prints_debug_messages(sample_dir, capsys):
    main([str(sample_dir / "clean.csv"), "--verbose"])

    assert "DEBUG" in capsys.readouterr().err


def test_large_file_is_processed(write_csv, capsys):
    rows = "\n".join(f"{i},user{i},user{i}@example.com,{20 + i % 50}" for i in range(20_000))
    path = write_csv("id,name,email,age\n" + rows + "\n")

    code = main([str(path)])

    assert code == EXIT_OK
    assert "Size:    20000 rows, 4 columns" in capsys.readouterr().out


def test_runs_as_a_module():
    result = subprocess.run(
        [sys.executable, "-m", "csv_checker", "sample_data/people.csv"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )

    assert result.returncode == EXIT_ISSUES
    assert "CSV Quality Report" in result.stdout
