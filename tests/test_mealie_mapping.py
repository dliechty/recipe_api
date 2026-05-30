from types import SimpleNamespace

from migration_scripts.mealie_mapping import (
    slugify,
    format_quantity,
    format_time,
)


def test_slugify_lowercases_and_hyphenates():
    assert slugify("Mom's Apple Pie!") == "mom-s-apple-pie"


def test_slugify_collapses_and_strips_separators():
    assert slugify("  Beef   &  Broccoli  ") == "beef-broccoli"


def test_format_quantity_integer_drops_decimal():
    assert format_quantity(2.0) == "2"


def test_format_quantity_trims_trailing_zeros():
    assert format_quantity(0.5) == "0.5"
    assert format_quantity(0.333) == "0.333"


def test_format_quantity_zero_and_none_are_empty():
    assert format_quantity(0) == ""
    assert format_quantity(None) == ""


def test_format_time_minutes():
    assert format_time(30) == "30 minutes"


def test_format_time_zero_or_none_is_none():
    assert format_time(0) is None
    assert format_time(None) is None
