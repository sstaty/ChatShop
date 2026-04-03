import html
import re

from chatshop.data.models import Product


_HTML_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"\s+")

_HEADPHONES_EXTRA_KEYS = (
    "type",
    "wireless",
    "anc",
    "battery_hours",
    "waterproof_rating",
    "driver_size_mm",
    "use_cases",
)


def clean_headphones(raw_list: list[dict]) -> list[Product]:
    """Clean a headphones JSON list → list[Product].

    JSON schema expected:
        id, brand, name, price_usd, description,
        type, wireless, anc, battery_hours,
        waterproof_rating, driver_size_mm, use_cases
    """
    seen_ids: set[str] = set()
    products: list[Product] = []

    for record in raw_list:
        product = _parse_headphone(record)
        if product is None or product.product_id in seen_ids:
            continue
        seen_ids.add(product.product_id)
        products.append(product)

    return products


def _parse_headphone(record: dict) -> Product | None:
    product_id = _str(record.get("id"))
    brand = _str(record.get("brand"))
    name = _str(record.get("name"))

    if not product_id or not name:
        return None

    title = _clean_text(f"{brand} {name}".strip() if brand else name)
    if len(title) < 5:
        return None

    description = _clean_text(_str(record.get("description", "")))
    price = _parse_float(record.get("price_usd"))
    if price is not None and price <= 0:
        price = None

    # use_cases: JSON array → list[str]
    raw_use_cases = record.get("use_cases")
    use_cases: list[str] = []
    if isinstance(raw_use_cases, list):
        use_cases = [str(v) for v in raw_use_cases if v]

    # battery_hours: may be null (wired headphones)
    raw_battery = record.get("battery_hours")
    battery_hours = _parse_int(raw_battery) if raw_battery is not None else None

    # driver_size_mm: may be int or float
    raw_driver = record.get("driver_size_mm")
    driver_size_mm = _parse_float(raw_driver) if raw_driver is not None else None

    return Product(
        product_id=product_id,
        title=title,
        description=description,
        price=price,
        brand=brand,
        type=_str(record.get("type")),
        wireless=record.get("wireless"),
        anc=record.get("anc"),
        battery_hours=battery_hours,
        waterproof_rating=_str(record.get("waterproof_rating")) or None,
        driver_size_mm=driver_size_mm,
        use_cases=use_cases,
    )


def _clean_text(text: str) -> str:
    text = html.unescape(text)
    text = _HTML_TAG_RE.sub(" ", text)
    text = _WHITESPACE_RE.sub(" ", text)
    return text.strip()


def _str(value) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _parse_float(value) -> float | None:
    if value is None:
        return None
    try:
        cleaned = re.sub(r"[^\d.]", "", str(value))
        return float(cleaned) if cleaned else None
    except (ValueError, TypeError):
        return None


def _parse_int(value) -> int | None:
    if value is None:
        return None
    try:
        cleaned = re.sub(r"[^\d]", "", str(value))
        return int(cleaned) if cleaned else None
    except (ValueError, TypeError):
        return None
