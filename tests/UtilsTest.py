import math
import re
from decimal import Decimal
from datetime import datetime

import pytest

from trading_automation.core.Utils import (
    DATETIME_STRING_FORMAT,
    ARG_FILE_REGEX,
    get_current_datetime_string,
    get_datetime_from_string,
    calculate_pnl_percentage,
    input_to_percentage,
    percentage_to_input,
    round_interval_down,
    round_interval_up,
    round_interval_nearest,
)


@pytest.mark.parametrize(
    "entry, exit_, side, expected",
    [
        (100, 110, "long", 0.10),
        (100, 90, "short", 0.10),
        (250.0, 250.0, "long", 0.0),
        (250.0, 250.0, "short", 0.0),
        # Use Decimals and strings to ensure code paths that cast through Decimal(str(...))
        (Decimal("100"), Decimal("105"), "long", 0.05),
        ("100", "95", "short", 0.05),
    ],
)
def test_calculate_pnl_percentage_valid(entry, exit_, side, expected):
    assert math.isclose(calculate_pnl_percentage(entry, exit_, side), expected, rel_tol=1e-12, abs_tol=1e-12)


def test_calculate_pnl_percentage_invalid_side_raises():
    with pytest.raises(ValueError):
        calculate_pnl_percentage(100, 110, "invalid-side")


@pytest.mark.parametrize(
    "inp, pct",
    [
        (1.8, 0.018),
        (0, 0.0),
        (100, 1.0),
        (Decimal("2.5"), 0.025),
    ],
)
def test_input_to_percentage(inp, pct):
    assert math.isclose(input_to_percentage(inp), pct, rel_tol=1e-12, abs_tol=1e-12)


@pytest.mark.parametrize(
    "pct, out",
    [
        (0.018, 1.8),
        (0.0, 0.0),
        (1.0, 100.0),
        (Decimal("0.025"), 2.5),
    ],
)
def test_percentage_to_input(pct, out):
    assert math.isclose(percentage_to_input(pct), out, rel_tol=1e-12, abs_tol=1e-12)


@pytest.mark.parametrize("value", [0.0, 0.5, 1.5, 2.25, 7.75])
def test_round_trip_percentage(value):
    # percentage_to_input(input_to_percentage(x)) == x
    round_tripped = percentage_to_input(input_to_percentage(value))
    assert math.isclose(round_tripped, value, rel_tol=1e-12, abs_tol=1e-12)


@pytest.mark.parametrize(
    "number, interval, expected_down, expected_up, expected_nearest",
    [
        (1.74, Decimal("0.5"), Decimal("1.5"), Decimal("2.0"), Decimal("1.5")),
        (1.76, Decimal("0.5"), Decimal("1.5"), Decimal("2.0"), Decimal("2.0")),
        (2.0, Decimal("0.5"), Decimal("2.0"), Decimal("2.0"), Decimal("2.0")),
        (0.24, Decimal("0.1"), Decimal("0.2"), Decimal("0.3"), Decimal("0.2")),
        (0.017589, Decimal("0.00001"), Decimal("0.017580"), Decimal("0.017590"), Decimal("0.017590")),
        (Decimal("10.01"), Decimal("1"), Decimal("10"), Decimal("11"), Decimal("10")),
    ],
)
def test_round_interval_helpers(number, interval, expected_down, expected_up, expected_nearest):
    assert round_interval_down(number, interval) == expected_down
    assert round_interval_up(number, interval) == expected_up
    assert round_interval_nearest(number, interval) == expected_nearest


def test_get_datetime_helpers_round_trip():
    s = get_current_datetime_string()
    dt = get_datetime_from_string(s)
    # Ensure we parsed according to the same format
    assert isinstance(dt, datetime)
    assert dt.strftime(DATETIME_STRING_FORMAT) == s


@pytest.mark.parametrize(
    "filename, should_match",
    [
        ("args_run.txt", True),
        ("@args_special.txt", True),
        ("args_run.txt -a", True),
        ("args_run.txt -a -b -c", True),
        ("not_args.txt", False),
        ("#commented_args.txt", False),
        ("args_.txt", True),
        ("args_anything-else.txt", True),
        ("args_file.TXT", False),  # regex expects lowercase .txt
    ],
)
def test_arg_file_regex(filename, should_match):
    matched = re.fullmatch(ARG_FILE_REGEX, filename) is not None
    assert matched is should_match