import json
from collections.abc import Iterator
from pathlib import Path

import pandas as pd


# Columns we actually need from the Kaggle Amazon Products Dataset 2023
_REQUIRED_COLUMNS = {"asin", "title"}
_OPTIONAL_COLUMNS = {"description", "categories", "price", "stars", "reviews"}

_CHUNK_SIZE = 5_000


def iter_raw_products(csv_path: str | Path, chunksize: int = _CHUNK_SIZE) -> Iterator[dict]:
    """Yield raw product dicts from the CSV one chunk at a time.

    Only the columns we use are read; pandas will silently skip missing optional
    columns so the loader works across minor dataset variants.
    """
    path = Path(csv_path)
    available = _probe_columns(path)
    usecols = list(_REQUIRED_COLUMNS | (_OPTIONAL_COLUMNS & available))

    reader = pd.read_csv(
        path,
        usecols=usecols,
        chunksize=chunksize,
        on_bad_lines="skip",
        low_memory=False,
    )
    for chunk in reader:
        chunk = chunk.where(pd.notna(chunk), other=None)
        yield from chunk.to_dict(orient="records")


def _probe_columns(path: Path) -> set[str]:
    """Read just the header row to discover available columns."""
    header = pd.read_csv(path, nrows=0)
    return set(header.columns)


def load_json(path: str | Path) -> list[dict]:
    """Load a JSON file that contains a list of product dicts."""
    with open(path, encoding="utf-8") as f:
        return json.load(f)
