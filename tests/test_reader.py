from pathlib import Path

import pytest

from csv_checker.reader import CsvReadError, read_csv


def test_reads_columns_and_rows(load):
    data = load("id,name\n1,Olena\n2,Andrii\n")

    assert data.columns == ["id", "name"]
    assert [row.values for row in data.rows] == [
        {"id": "1", "name": "Olena"},
        {"id": "2", "name": "Andrii"},
    ]


def test_line_numbers_start_after_the_header(load):
    data = load("a,b\n1,2\n3,4\n")

    assert [row.line for row in data.rows] == [2, 3]


def test_blank_lines_are_skipped_but_line_numbers_stay_correct(load):
    data = load("a,b\n1,2\n\n3,4\n")

    assert [row.line for row in data.rows] == [2, 4]


def test_quoted_field_spanning_two_lines_is_one_row(load):
    data = load('a,b\n"first\nsecond",2\n3,4\n')

    assert len(data.rows) == 2
    assert data.rows[0].values["a"] == "first\nsecond"
    assert [row.line for row in data.rows] == [2, 4]


def test_header_names_are_stripped(load):
    assert load(" id , name \n1,x\n").columns == ["id", "name"]


def test_utf8_bom_and_ukrainian_text(write_csv):
    path = write_csv("﻿міcто,вік\nКиїв,30\n")

    data = read_csv(path)

    assert data.columns == ["міcто", "вік"]
    assert data.rows[0].values == {"міcто": "Київ", "вік": "30"}


def test_custom_delimiter(load, write_csv):
    path = write_csv("a;b\n1;2\n")

    assert read_csv(path, delimiter=";").rows[0].values == {"a": "1", "b": "2"}


def test_header_only_file_has_no_rows(load):
    data = load("a,b\n")

    assert data.columns == ["a", "b"]
    assert data.rows == []


def test_short_row_is_padded_and_marked_as_malformed(load):
    data = load("a,b,c\n1,2\n4,5,6\n")

    short = data.rows[0]
    assert short.field_count == 2
    assert short.values == {"a": "1", "b": "2", "c": ""}
    assert data.valid_rows() == [data.rows[1]]


def test_long_row_is_cut_and_marked_as_malformed(load):
    data = load("a,b\n1,2,3\n")

    assert data.rows[0].field_count == 3
    assert data.rows[0].values == {"a": "1", "b": "2"}
    assert data.valid_rows() == []


def test_missing_file(tmp_path):
    with pytest.raises(CsvReadError, match="File not found"):
        read_csv(tmp_path / "nope.csv")


def test_directory_instead_of_file(tmp_path):
    with pytest.raises(CsvReadError, match="directory"):
        read_csv(tmp_path)


@pytest.mark.parametrize("text", ["", "\n\n"])
def test_empty_file(load, text):
    with pytest.raises(CsvReadError, match="empty"):
        load(text)


def test_duplicate_column_names(load):
    with pytest.raises(CsvReadError, match="duplicate"):
        load("a,b,a\n1,2,3\n")


def test_empty_column_name(load):
    with pytest.raises(CsvReadError, match="empty column name"):
        load("a,,c\n1,2,3\n")


def test_invalid_utf8(tmp_path):
    path = tmp_path / "latin1.csv"
    path.write_bytes(b"a,b\n\xff\xfe,2\n")

    with pytest.raises(CsvReadError, match="UTF-8"):
        read_csv(path)


def test_unreadable_file_is_reported_as_a_read_error(write_csv, monkeypatch):
    path = write_csv("a,b\n")

    def deny(self, *args, **kwargs):
        raise PermissionError("denied")

    monkeypatch.setattr(Path, "open", deny)

    with pytest.raises(CsvReadError, match="Cannot read file"):
        read_csv(path)


def test_delimiter_must_be_one_character(write_csv):
    with pytest.raises(CsvReadError, match="single character"):
        read_csv(write_csv("a,b\n"), delimiter="ab")
