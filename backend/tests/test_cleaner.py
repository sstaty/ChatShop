"""Unit tests for data.cleaner — synthetic data only, no I/O."""

import pytest

from chatshop.data.cleaner import clean_headphones, _clean_text, _parse_float, _parse_int


# ── _clean_text ───────────────────────────────────────────────────────────────

def test_clean_text_strips_html():
    assert _clean_text("<b>Hello</b> <em>world</em>") == "Hello world"


def test_clean_text_unescapes_html_entities():
    assert _clean_text("A &amp; B &lt;3") == "A & B <3"


def test_clean_text_collapses_whitespace():
    assert _clean_text("  lots   of   spaces  ") == "lots of spaces"


# ── _parse_float ──────────────────────────────────────────────────────────────

def test_parse_float_plain():
    assert _parse_float("99.99") == pytest.approx(99.99)


def test_parse_float_dollar_sign():
    assert _parse_float("$49.99") == pytest.approx(49.99)


def test_parse_float_none():
    assert _parse_float(None) is None


def test_parse_float_empty():
    assert _parse_float("") is None


# ── _parse_int ────────────────────────────────────────────────────────────────

def test_parse_int_plain():
    assert _parse_int("1234") == 1234


def test_parse_int_with_commas():
    assert _parse_int("12,345") == 12345


def test_parse_int_none():
    assert _parse_int(None) is None


# ── clean_headphones ──────────────────────────────────────────────────────────

def _make_record(**kwargs) -> dict:
    base = {
        "id": "1",
        "brand": "Sony",
        "name": "WH-1000XM5",
        "price_usd": 349,
        "type": "over-ear",
        "wireless": True,
        "anc": True,
        "battery_hours": 30,
        "waterproof_rating": None,
        "driver_size_mm": 30,
        "use_cases": ["travel", "office"],
        "description": "Great headphones.",
    }
    base.update(kwargs)
    return base


def test_clean_headphones_basic():
    products = clean_headphones([_make_record()])
    assert len(products) == 1
    p = products[0]
    assert p.product_id == "1"
    assert p.title == "Sony WH-1000XM5"
    assert p.price == pytest.approx(349.0)
    assert p.brand == "Sony"
    assert p.wireless is True
    assert p.anc is True
    assert p.battery_hours == 30
    assert p.use_cases == ["travel", "office"]


def test_clean_headphones_deduplicates():
    products = clean_headphones([_make_record(), _make_record()])
    assert len(products) == 1


def test_clean_headphones_drops_missing_id():
    assert clean_headphones([_make_record(id=None)]) == []


def test_clean_headphones_drops_missing_name():
    assert clean_headphones([_make_record(name=None)]) == []


def test_clean_headphones_wired_has_no_battery():
    p = clean_headphones([_make_record(battery_hours=None, wireless=False)])[0]
    assert p.battery_hours is None
    assert p.wireless is False


def test_clean_headphones_use_cases_list_to_list():
    p = clean_headphones([_make_record(use_cases=["sport", "gaming"])])[0]
    assert p.use_cases == ["sport", "gaming"]


def test_clean_headphones_waterproof_rating_none():
    p = clean_headphones([_make_record(waterproof_rating=None)])[0]
    assert p.waterproof_rating is None


def test_clean_headphones_waterproof_rating_value():
    p = clean_headphones([_make_record(waterproof_rating="IPX4")])[0]
    assert p.waterproof_rating == "IPX4"
