"""
run_ingest.py — full ingest pipeline entry point.

Runs all six steps in sequence. Stops immediately if any step fails.

Usage:
    python ingest/run_ingest.py
    python ingest/run_ingest.py --limit 10   # fetch only the first 10 base Pokemon
"""

import argparse
import subprocess
import sys
import time


STEPS = [
    ("Fetching Pokemon",           ["python", "ingest/fetch_pokemon.py"]),
    ("Transforming data",          ["python", "ingest/transform.py"]),
    ("Loading structured tables",  ["python", "ingest/load_structured.py"]),
    ("Building type chart",        ["python", "ingest/build_type_chart.py"]),
    ("Chunking for embeddings",    ["python", "ingest/chunk.py"]),
    ("Embedding and storing",      ["python", "ingest/embed_and_store.py"]),
]


def run_step(number: int, label: str, cmd: list[str]) -> None:
    print(f"\n{'='*60}")
    print(f"=== Step {number}: {label} ===")
    print(f"{'='*60}")
    print(f"Running: {' '.join(cmd)}\n")

    start = time.time()
    result = subprocess.run(cmd)
    elapsed = time.time() - start

    if result.returncode != 0:
        print(f"\n[ERROR] Step {number} ({label}) failed with exit code {result.returncode}.")
        sys.exit(result.returncode)

    print(f"\n[OK] Step {number} completed in {elapsed:.1f}s")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the full pokemon-rag ingest pipeline")
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit the number of base Pokemon fetched (passed to fetch_pokemon.py only)",
    )
    args = parser.parse_args()

    pipeline_start = time.time()
    print("Starting pokemon-rag ingest pipeline...")
    if args.limit:
        print(f"  (--limit {args.limit} will be passed to the fetch step)")

    for i, (label, cmd) in enumerate(STEPS, start=1):
        # Inject --limit into the fetch step only
        if i == 1 and args.limit is not None:
            cmd = cmd + ["--limit", str(args.limit)]
        run_step(i, label, cmd)

    total = time.time() - pipeline_start
    print(f"\n{'='*60}")
    print(f"All {len(STEPS)} steps completed successfully in {total:.1f}s")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
