"""
embed_and_store.py — embed pokemon_chunks.json and store in Supabase.

For each chunk:
  - Embed content with OpenAI text-embedding-3-small (dim 1536)
  - Resolve pokemon_id from Supabase pokemon table via name + form_label
  - Insert into pokemon_embeddings

Chunks whose (pokemon_id, chunk_type) already exist in the table are skipped,
making repeated runs safe.
"""

import json
import os
import sys
from pathlib import Path

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

EMBED_MODEL = "text-embedding-3-small"
BATCH_SIZE  = 50


# ── db helpers ────────────────────────────────────────────────────────────────

def load_pokemon_id_map(cur) -> dict[tuple[str, str], int]:
    """Return {(name, form_label): pokemon_id} for every row in pokemon."""
    cur.execute("SELECT name, form_label, id FROM pokemon")
    return {(row[0], row[1]): row[2] for row in cur.fetchall()}


def load_existing_embeddings(cur) -> set[tuple[int, str]]:
    """Return set of (pokemon_id, chunk_type) that already have an embedding."""
    cur.execute("SELECT pokemon_id, chunk_type FROM pokemon_embeddings")
    return {(row[0], row[1]) for row in cur.fetchall()}


def insert_embedding_rows(cur, rows: list[tuple]) -> None:
    """Bulk-insert embedding rows: (pokemon_id, chunk_type, content, embedding, metadata)."""
    psycopg2.extras.execute_batch(
        cur,
        """
        INSERT INTO pokemon_embeddings
            (pokemon_id, chunk_type, content, embedding, metadata)
        VALUES (%s, %s, %s, %s::vector, %s)
        """,
        rows,
        page_size=BATCH_SIZE,
    )


# ── embedding ─────────────────────────────────────────────────────────────────

def embed_batch(client: OpenAI, texts: list[str]) -> list[list[float]]:
    resp = client.embeddings.create(model=EMBED_MODEL, input=texts)
    # Results are returned in the same order as input
    return [item.embedding for item in sorted(resp.data, key=lambda x: x.index)]


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    openai_key   = os.environ.get("OPENAI_API_KEY", "")
    database_url = os.environ.get("DATABASE_URL", "")

    if not openai_key:
        sys.exit("ERROR: OPENAI_API_KEY not set in .env")
    if not database_url or "YOUR_DB_PASSWORD" in database_url:
        sys.exit("ERROR: DATABASE_URL not set or still contains placeholder in .env")

    chunks_path = Path("data/pokemon_chunks.json")
    if not chunks_path.exists():
        sys.exit("ERROR: data/pokemon_chunks.json not found — run chunk.py first")

    chunks: list[dict] = json.loads(chunks_path.read_text(encoding="utf-8"))
    print(f"Loaded {len(chunks)} chunks from {chunks_path}")

    client = OpenAI(api_key=openai_key)
    conn   = psycopg2.connect(database_url)
    conn.autocommit = False

    try:
        with conn.cursor() as cur:
            pokemon_id_map = load_pokemon_id_map(cur)
            existing       = load_existing_embeddings(cur)
            print(f"  {len(pokemon_id_map)} pokemon in DB, {len(existing)} embeddings already stored")

            # Filter to only chunks that still need embedding
            pending = []
            skipped = 0
            for chunk in chunks:
                meta       = chunk["metadata"]
                pokemon_id = pokemon_id_map.get((meta["name"], meta["form_label"]))
                if pokemon_id is None:
                    skipped += 1
                    continue
                if (pokemon_id, meta["chunk_type"]) in existing:
                    skipped += 1
                    continue
                pending.append((chunk, pokemon_id))

            print(f"  {len(pending)} chunks to embed, {skipped} skipped")

            if not pending:
                print("Nothing to do.")
                return

            inserted = 0

            for batch_start in range(0, len(pending), BATCH_SIZE):
                batch = pending[batch_start: batch_start + BATCH_SIZE]
                texts = [item[0]["content"] for item in batch]

                vectors = embed_batch(client, texts)

                rows = []
                for (chunk, pokemon_id), vector in zip(batch, vectors):
                    meta = chunk["metadata"]
                    rows.append((
                        pokemon_id,
                        meta["chunk_type"],
                        chunk["content"],
                        # pgvector expects a list literal: '[0.1,0.2,...]'
                        "[" + ",".join(str(v) for v in vector) + "]",
                        json.dumps(meta),
                    ))

                insert_embedding_rows(cur, rows)
                conn.commit()

                inserted += len(rows)
                if inserted % BATCH_SIZE == 0 or inserted == len(pending):
                    print(f"  Progress: {inserted} / {len(pending)} embeddings stored")

    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    print(f"\nDone — {inserted} embeddings stored.")


if __name__ == "__main__":
    main()
