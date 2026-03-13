"""
One-shot ingestion script: CSV or JSON → clean → embed → ChromaDB.

Usage:
    uv run python scripts/ingest.py
    uv run python scripts/ingest.py --csv data/raw/amazon_products.csv --batch-size 256
    uv run python scripts/ingest.py --json data/headphones.json --category headphones
"""

import argparse
import logging
import sys
import time
from pathlib import Path

# Make sure src/ is on the path when run directly
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from chatshop.config import settings
from chatshop.data.cleaner import clean_headphones, clean_products
from chatshop.data.loader import iter_raw_products, load_json
from chatshop.embeddings.embedder import Embedder
from chatshop.vectorstore.chroma import ChromaStore

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

_UPSERT_BATCH = 512  # products per ChromaDB upsert call

_JSON_CLEANERS = {
    "headphones": clean_headphones,
}


def ingest_csv(csv_path: Path, embed_batch_size: int = 128) -> None:
    log.info("Loading embedder …")
    embedder = Embedder()

    log.info("Connecting to ChromaDB at %s …", settings.chroma_persist_dir)
    store = ChromaStore()
    before = store.count()
    log.info("Collection currently holds %d documents.", before)

    total_upserted = 0
    buffer: list = []
    chunk_index = 0

    log.info("Starting CSV ingestion from %s …", csv_path)
    t0 = time.perf_counter()

    for raw_record in iter_raw_products(csv_path):
        buffer.append(raw_record)
        if len(buffer) < 5_000:
            continue
        total_upserted += _flush_raw(buffer, embedder, store, embed_batch_size, chunk_index)
        buffer.clear()
        chunk_index += 1

    if buffer:
        total_upserted += _flush_raw(buffer, embedder, store, embed_batch_size, chunk_index)

    _log_done(total_upserted, time.perf_counter() - t0, store.count())


def ingest_json(json_path: Path, category: str, embed_batch_size: int = 128) -> None:
    cleaner = _JSON_CLEANERS.get(category)
    if cleaner is None:
        log.error("Unknown category '%s'. Supported: %s", category, list(_JSON_CLEANERS))
        sys.exit(1)

    log.info("Loading embedder …")
    embedder = Embedder()

    log.info("Connecting to ChromaDB at %s …", settings.chroma_persist_dir)
    store = ChromaStore()
    log.info("Collection currently holds %d documents.", store.count())

    log.info("Loading %s …", json_path)
    raw_list = load_json(json_path)
    log.info("Loaded %d raw records.", len(raw_list))

    t0 = time.perf_counter()
    products = cleaner(raw_list)
    log.info("%d raw → %d clean products", len(raw_list), len(products))

    texts = [p.to_document_text() for p in products]
    vectors: list[list[float]] = []
    for start in range(0, len(texts), embed_batch_size):
        vectors.extend(embedder.encode(texts[start : start + embed_batch_size], batch_size=embed_batch_size))

    for start in range(0, len(products), _UPSERT_BATCH):
        store.upsert(products[start : start + _UPSERT_BATCH], vectors[start : start + _UPSERT_BATCH])

    _log_done(len(products), time.perf_counter() - t0, store.count())


def _flush_raw(
    raw_records: list[dict],
    embedder: Embedder,
    store: ChromaStore,
    embed_batch_size: int,
    chunk_index: int,
) -> int:
    products = clean_products(raw_records)
    if not products:
        return 0

    log.info("Chunk %d: %d raw → %d clean products", chunk_index, len(raw_records), len(products))

    texts = [p.to_document_text() for p in products]
    vectors: list[list[float]] = []
    for start in range(0, len(texts), embed_batch_size):
        vectors.extend(embedder.encode(texts[start : start + embed_batch_size], batch_size=embed_batch_size))

    for start in range(0, len(products), _UPSERT_BATCH):
        store.upsert(products[start : start + _UPSERT_BATCH], vectors[start : start + _UPSERT_BATCH])

    return len(products)


def _log_done(total: int, elapsed: float, count: int) -> None:
    log.info(
        "Done. Upserted %d products in %.1f s. Collection now holds %d documents.",
        total,
        elapsed,
        count,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest products into ChromaDB.")
    source = parser.add_mutually_exclusive_group()
    source.add_argument(
        "--csv",
        type=Path,
        default=None,
        help="Path to an Amazon Products CSV file.",
    )
    source.add_argument(
        "--json",
        type=Path,
        default=None,
        help="Path to a structured JSON product file.",
    )
    parser.add_argument(
        "--category",
        type=str,
        default=None,
        help="Product category for JSON ingestion (e.g. headphones).",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=128,
        help="Embedding batch size (reduce if OOM).",
    )
    args = parser.parse_args()

    if args.json is not None:
        if not args.category:
            parser.error("--category is required when using --json")
        if not args.json.exists():
            log.error("JSON not found: %s", args.json)
            sys.exit(1)
        ingest_json(args.json, args.category, embed_batch_size=args.batch_size)
    else:
        csv_path = args.csv or Path(settings.data_raw_dir) / "amazon_products.csv"
        if not csv_path.exists():
            log.error("CSV not found: %s", csv_path)
            log.error("Download the Kaggle Amazon Products Dataset 2023 and place it there.")
            sys.exit(1)
        ingest_csv(csv_path, embed_batch_size=args.batch_size)


if __name__ == "__main__":
    main()
