import pytest

from csv_checker.validators import is_date, is_email, is_float, is_int, parse_float, parse_int


@pytest.mark.parametrize("value", ["0", "7", "-5", "+12", "123456789"])
def test_is_int_accepts_integers(value):
    assert is_int(value)


@pytest.mark.parametrize("value", ["", "abc", "1.5", "1_000", "1e3", " 5", "١٢"])
def test_is_int_rejects_everything_else(value):
    # "1_000" and the Arabic digits are accepted by Python's int(), but are not valid data
    assert not is_int(value)


@pytest.mark.parametrize("value", ["7", "1.5", ".5", "5.", "-2.5", "1e3", "-2.5E-3"])
def test_is_float_accepts_decimal_numbers(value):
    assert is_float(value)


@pytest.mark.parametrize("value", ["", "abc", "nan", "inf", "-Infinity", "1_0", "1e999", "1,5"])
def test_is_float_rejects_non_numbers_and_non_finite_values(value):
    assert not is_float(value)


def test_parse_functions_return_values_or_none():
    assert parse_int("42") == 42
    assert parse_int("4.2") is None
    assert parse_float("4.2") == 4.2
    assert parse_float("abc") is None


@pytest.mark.parametrize("value", ["2024-01-15", "2024-02-29", "1999-12-31"])
def test_is_date_accepts_real_dates(value):
    assert is_date(value)


@pytest.mark.parametrize(
    "value",
    ["2023-02-29", "2024-13-45", "2024-00-10", "2024-1-5", "15.01.2024", "not a date", ""],
)
def test_is_date_rejects_fake_and_wrongly_formatted_dates(value):
    assert not is_date(value)


@pytest.mark.parametrize(
    "value", ["a@b.co", "olena@example.com", "first.last+tag@mail.example.org"]
)
def test_is_email_accepts_normal_addresses(value):
    assert is_email(value)


@pytest.mark.parametrize(
    "value", ["", "a@b", "a@@b.com", "a b@c.com", "@b.com", "a@.com", "a@b..com", "plain text"]
)
def test_is_email_rejects_broken_addresses(value):
    assert not is_email(value)
