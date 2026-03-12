"""
Dev utility: peek at stored vectors in ChromaDB.

Usage:
    uv run python scripts/inspect_chroma.py
    uv run python scripts/inspect_chroma.py --query "wireless headphones" --top-k 10
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from chatshop.config import settings
from chatshop.vectorstore.chroma import ChromaStore


def main() -> None:
    parser = argparse.ArgumentParser(description="Inspect ChromaDB contents.")
    parser.add_argument("--query", type=str, default=None, help="Run a similarity query.")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--peek", type=int, default=5, help="Print first N stored documents.")
    args = parser.parse_args()

    store = ChromaStore()
    print(f"Collection '{settings.chroma_collection}' contains {store.count():,} documents.\n")

    if args.query:
        from chatshop.rag.retriever import Retriever

        retriever = Retriever(store=store)
        results = retriever.retrieve(args.query, top_k=args.top_k)
        print(f"Top {args.top_k} results for: '{args.query}'\n" + "-" * 50)
        for i, product in enumerate(results, 1):
            price = f"${product.price:.2f}" if product.price else "N/A"
            rating = f"{product.rating}/5" if product.rating else "N/A"
            print(f"[{i}] {product.title}")
            print(f"    Price: {price}  Rating: {rating}")
            print(f"    ID: {product.product_id}\n")
    else:
        # Raw peek at the collection
        raw = store._collection.peek(limit=args.peek)
        ids = raw.get("ids", [])
        docs = raw.get("documents", [])
        print(f"First {len(ids)} stored document(s):\n" + "-" * 50)
        for doc_id, doc in zip(ids, docs):
            print(f"[{doc_id}]\n{doc[:300]}\n")


if __name__ == "__main__":
    main()
