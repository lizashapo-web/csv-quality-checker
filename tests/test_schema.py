import json

import pytest

from csv_checker.schema import (
    ColumnRule,
    SchemaError,
    infer_schema,
    load_schema,
    parse_schema,
    save_schema,
)


def test_load_sample_schema(sample_dir):
    schema = load_schema(sample_dir / "people.schema.json")

    assert list(schema) == ["id", "name", "email", "age", "signup_date", "city"]
    assert schema["age"] == ColumnRule(type="int", min=0, max=120)
    assert schema["email"] == ColumnRule(type="email")


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        ([], 'must be a JSON object with a "columns" object'),
        ({"cols": {}}, 'must be a JSON object with a "columns" object'),
        ({"columns": []}, 'must be a JSON object with a "columns" object'),
        ({"columns": {}}, "does not describe any columns"),
        ({"columns": {"a": "int"}}, "the rule must be an object"),
        ({"columns": {"a": {"type": "int", "mni": 0}}}, "unknown keys"),
        ({"columns": {"a": {"type": "number"}}}, "type must be one of"),
        ({"columns": {"a": {}}}, "type must be one of"),
        ({"columns": {"a": {"type": "text", "min": 1}}}, "only allowed for int/float"),
        ({"columns": {"a": {"type": "int", "min": "0"}}}, "must be a number"),
        ({"columns": {"a": {"type": "int", "max": True}}}, "must be a number"),
        ({"columns": {"a": {"type": "int", "min": 5, "max": 1}}}, "greater than max"),
    ],
)
def test_invalid_schemas_are_rejected_with_a_clear_message(raw, message):
    with pytest.raises(SchemaError, match=message):
        parse_schema(raw)


def test_load_schema_errors(tmp_path):
    with pytest.raises(SchemaError, match="Cannot read"):
        load_schema(tmp_path / "missing.json")

    broken = tmp_path / "broken.json"
    broken.write_text("{not json", encoding="utf-8")
    with pytest.raises(SchemaError, match="not valid JSON"):
        load_schema(broken)

    binary = tmp_path / "binary.json"
    binary.write_bytes(b"\xff\xfe\x00")
    with pytest.raises(SchemaError, match="UTF-8"):
        load_schema(binary)


def test_save_then_load_round_trip(tmp_path):
    schema = {
        "age": ColumnRule(type="int", min=0, max=120),
        "price": ColumnRule(type="float", min=0.5),
        "city": ColumnRule(type="text"),
    }
    path = tmp_path / "schema.json"

    save_schema(schema, path)

    assert load_schema(path) == schema
    assert json.loads(path.read_text(encoding="utf-8"))["columns"]["city"] == {"type": "text"}


# --- inference ----------------------------------------------------------------------


def test_infer_schema_on_the_sample_file(sample_dir):
    from csv_checker.reader import read_csv

    schema = infer_schema(read_csv(sample_dir / "people.csv"))

    assert {name: rule.type for name, rule in schema.items()} == {
        "id": "int",
        "name": "text",
        "email": "email",
        "age": "int",  # one bad value ("abc") must not turn the column into text
        "signup_date": "date",  # ...and neither must "not a date"
        "city": "text",
    }


def test_inference_prefers_float_when_integers_and_decimals_are_mixed(load):
    assert infer_schema(load("x\n1\n2.5\n3.5\n"))["x"].type == "float"


def test_inference_falls_back_to_text_for_mixed_columns(load):
    assert infer_schema(load("x\na\nb\n1\n"))["x"].type == "text"


def test_inference_of_an_empty_column_is_text(load):
    assert infer_schema(load("a,x\n1,\n2,\n"))["x"].type == "text"
