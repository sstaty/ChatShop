"""
Ingest headphones.json → clean → embed → ChromaDB.

Usage:
    uv run python scripts/ingest.py
    uv run python scripts/ingest.py --json data/headphones.json
    uv run python scripts/ingest.py --batch-size 64
"""

import argparse
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from chatshop.data.cleaner import clean_headphones
from chatshop.data.loader import load_json
from chatshop.embeddings.embedder import Embedder
from chatshop.vectorstore.chroma import ChromaStore

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

_UPSERT_BATCH = 512
_DEFAULT_JSON = Path(__file__).parent.parent / "data" / "headphones.json"


def ingest(json_path: Path, embed_batch_size: int = 128) -> None:
    log.info("Loading embedder …")
    embedder = Embedder()

    log.info("Connecting to ChromaDB …")
    store = ChromaStore()
    log.info("Collection currently holds %d documents.", store.count())

    log.info("Loading %s …", json_path)
    raw_list = load_json(json_path)
    log.info("Loaded %d raw records.", len(raw_list))

    t0 = time.perf_counter()
    products = clean_headphones(raw_list)
    log.info("%d raw → %d clean products", len(raw_list), len(products))

    texts = [p.to_document_text() for p in products]
    vectors: list[list[float]] = []
    for start in range(0, len(texts), embed_batch_size):
        vectors.extend(embedder.encode(texts[start : start + embed_batch_size], batch_size=embed_batch_size))

    for start in range(0, len(products), _UPSERT_BATCH):
        store.upsert(products[start : start + _UPSERT_BATCH], vectors[start : start + _UPSERT_BATCH])

    elapsed = time.perf_counter() - t0
    log.info("Done. Upserted %d products in %.1f s. Collection now holds %d documents.", len(products), elapsed, store.count())


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest headphones into ChromaDB.")
    parser.add_argument(
        "--json",
        type=Path,
        default=_DEFAULT_JSON,
        help=f"Path to headphones JSON file (default: {_DEFAULT_JSON})",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=128,
        help="Embedding batch size (reduce if OOM).",
    )
    args = parser.parse_args()

    if not args.json.exists():
        log.error("JSON not found: %s", args.json)
        sys.exit(1)

    ingest(args.json, embed_batch_size=args.batch_size)


if __name__ == "__main__":
    main()
