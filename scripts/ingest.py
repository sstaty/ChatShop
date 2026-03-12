"""
One-shot ingestion script: CSV → clean → embed → ChromaDB.

Usage:
    uv run python scripts/ingest.py
    uv run python scripts/ingest.py --csv data/raw/amazon_products.csv --batch-size 256
"""

import argparse
import logging
import sys
import time
from pathlib import Path

# Make sure src/ is on the path when run directly
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from chatshop.config import settings
from chatshop.data.cleaner import clean_products
from chatshop.data.loader import iter_raw_products
from chatshop.embeddings.embedder import Embedder
from chatshop.vectorstore.chroma import ChromaStore

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

_UPSERT_BATCH = 512  # products per ChromaDB upsert call


def ingest(csv_path: Path, embed_batch_size: int = 128) -> None:
    log.info("Loading embedder …")
    embedder = Embedder()

    log.info("Connecting to ChromaDB at %s …", settings.chroma_persist_dir)
    store = ChromaStore()
    before = store.count()
    log.info("Collection currently holds %d documents.", before)

    total_upserted = 0
    buffer: list = []
    chunk_index = 0

    log.info("Starting ingestion from %s …", csv_path)
    t0 = time.perf_counter()

    for raw_record in iter_raw_products(csv_path):
        buffer.append(raw_record)
        if len(buffer) < 5_000:
            continue
        total_upserted += _flush(buffer, embedder, store, embed_batch_size, chunk_index)
        buffer.clear()
        chunk_index += 1

    # Final partial chunk
    if buffer:
        total_upserted += _flush(buffer, embedder, store, embed_batch_size, chunk_index)

    elapsed = time.perf_counter() - t0
    after = store.count()
    log.info(
        "Done. Upserted %d products in %.1f s. Collection now holds %d documents.",
        total_upserted,
        elapsed,
        after,
    )


def _flush(
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

    # Embed in sub-batches to keep memory bounded
    vectors: list[list[float]] = []
    for start in range(0, len(texts), embed_batch_size):
        batch_texts = texts[start : start + embed_batch_size]
        vectors.extend(embedder.encode(batch_texts, batch_size=embed_batch_size))

    # Upsert in sub-batches
    for start in range(0, len(products), _UPSERT_BATCH):
        store.upsert(products[start : start + _UPSERT_BATCH], vectors[start : start + _UPSERT_BATCH])

    return len(products)


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest Amazon products into ChromaDB.")
    parser.add_argument(
        "--csv",
        type=Path,
        default=Path(settings.data_raw_dir) / "amazon_products.csv",
        help="Path to the raw CSV file.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=128,
        help="Embedding batch size (reduce if OOM).",
    )
    args = parser.parse_args()

    if not args.csv.exists():
        log.error("CSV not found: %s", args.csv)
        log.error("Download the Kaggle Amazon Products Dataset 2023 and place it there.")
        sys.exit(1)

    ingest(args.csv, embed_batch_size=args.batch_size)


if __name__ == "__main__":
    main()
