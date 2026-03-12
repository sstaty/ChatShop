"""Unit tests for data.cleaner — synthetic data only, no I/O."""

import pytest

from chatshop.data.cleaner import clean_products, _clean_text, _parse_float, _parse_int


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


# ── clean_products ────────────────────────────────────────────────────────────

def _make_record(**kwargs) -> dict:
    base = {"asin": "B001TEST01", "title": "Test Product", "price": "29.99", "stars": "4.2"}
    base.update(kwargs)
    return base


def test_clean_products_basic():
    records = [_make_record()]
    products = clean_products(records)
    assert len(products) == 1
    p = products[0]
    assert p.product_id == "B001TEST01"
    assert p.title == "Test Product"
    assert p.price == pytest.approx(29.99)
    assert p.rating == pytest.approx(4.2)


def test_clean_products_deduplicates():
    records = [_make_record(), _make_record()]  # same asin twice
    products = clean_products(records)
    assert len(products) == 1


def test_clean_products_drops_missing_asin():
    records = [_make_record(asin=None)]
    assert clean_products(records) == []


def test_clean_products_drops_missing_title():
    records = [_make_record(title=None)]
    assert clean_products(records) == []


def test_clean_products_drops_short_title():
    records = [_make_record(title="AB")]
    assert clean_products(records) == []


def test_clean_products_strips_html_from_title():
    records = [_make_record(title="<b>Cool Gadget</b>")]
    products = clean_products(records)
    assert products[0].title == "Cool Gadget"


def test_clean_products_ignores_invalid_rating():
    records = [_make_record(stars="99.0")]
    products = clean_products(records)
    assert products[0].rating is None


def test_clean_products_ignores_zero_price():
    records = [_make_record(price="0.00")]
    products = clean_products(records)
    assert products[0].price is None


def test_clean_products_multiple_unique():
    records = [
        _make_record(asin="B001", title="Product One"),
        _make_record(asin="B002", title="Product Two"),
    ]
    products = clean_products(records)
    assert len(products) == 2
    assert {p.product_id for p in products} == {"B001", "B002"}
