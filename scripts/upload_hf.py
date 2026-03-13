"""
Upload a local JSON product file to HuggingFace Hub as a dataset.

Usage:
    uv run python scripts/upload_hf.py --path data/headphones.json
    uv run python scripts/upload_hf.py --path data/headphones.json --repo your-username/chatshop-headphones
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from chatshop.config import settings


def main() -> None:
    parser = argparse.ArgumentParser(description="Push a JSON dataset to HuggingFace Hub.")
    parser.add_argument("--path", type=Path, required=True, help="Path to the JSON file.")
    parser.add_argument(
        "--repo",
        type=str,
        default=None,
        help="HF Hub repo (e.g. username/chatshop-headphones). Falls back to HF_DATASET_REPO env var.",
    )
    args = parser.parse_args()

    repo = args.repo or settings.hf_dataset_repo
    token = settings.hf_token

    if not repo:
        print("ERROR: Provide --repo or set HF_DATASET_REPO in .env", file=sys.stderr)
        sys.exit(1)
    if not token:
        print("ERROR: Set HF_TOKEN in .env", file=sys.stderr)
        sys.exit(1)
    if not args.path.exists():
        print(f"ERROR: File not found: {args.path}", file=sys.stderr)
        sys.exit(1)

    try:
        from datasets import Dataset
    except ImportError:
        print("ERROR: Run `uv add datasets` first.", file=sys.stderr)
        sys.exit(1)

    print(f"Loading {args.path} …")
    with open(args.path, encoding="utf-8") as f:
        data = json.load(f)

    print(f"Loaded {len(data)} records. Building Dataset …")
    ds = Dataset.from_list(data)

    print(f"Pushing to {repo} …")
    ds.push_to_hub(repo, token=token)
    print("Done.")


if __name__ == "__main__":
    main()
