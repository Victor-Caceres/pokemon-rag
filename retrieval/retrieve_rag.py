"""
retrieve_rag.py — vector similarity search against pokemon_embeddings via pgvector.

Embeds the query with OpenAI text-embedding-3-small, then calls the
match_documents Supabase RPC function and returns the top-k chunks.
"""

import logging
import os

from dotenv import load_dotenv
from openai import OpenAI
from supabase import create_client, Client

load_dotenv()

logger = logging.getLogger(__name__)

EMBED_MODEL = "text-embedding-3-small"

# Module-level singletons — initialised once on first call to retrieve_rag()
_openai_client: OpenAI | None = None
_supabase_client: Client | None = None


def _get_openai() -> OpenAI:
    global _openai_client
    if _openai_client is None:
        _openai_client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    return _openai_client


def _get_supabase() -> Client:
    global _supabase_client
    if _supabase_client is None:
        _supabase_client = create_client(
            os.environ["SUPABASE_URL"],
            os.environ["SUPABASE_KEY"],
        )
    return _supabase_client


def _embed(text: str) -> list[float]:
    resp = _get_openai().embeddings.create(model=EMBED_MODEL, input=text)
    return resp.data[0].embedding


def retrieve_rag(query: str, top_k: int = 5) -> list[dict]:
    """
    Embed *query* and return the *top_k* most similar chunks from
    pokemon_embeddings.

    Each result dict has keys:
      content     — the raw chunk text
      metadata    — dict with name, display_name, form_label, chunk_type, …
      similarity  — cosine similarity score (0-1, higher is better)
    """
    logger.debug("Embedding query: %r", query)
    embedding = _embed(query)

    # pgvector expects the vector as a string "[x, y, z, ...]" when sent
    # through PostgREST / supabase-py RPC JSON serialisation
    vector_str = "[" + ",".join(str(v) for v in embedding) + "]"

    response = (
        _get_supabase()
        .rpc("match_documents", {"query_embedding": vector_str, "match_count": top_k})
        .execute()
    )

    results = []
    for row in response.data:
        similarity = row.get("similarity", 0.0)
        metadata   = row.get("metadata", {})
        content    = row.get("content", "")

        display = metadata.get("display_name") or metadata.get("name", "?")
        chunk_type = metadata.get("chunk_type", "?")
        logger.info("  [%.4f] %s — %s", similarity, display, chunk_type)

        results.append({
            "content":    content,
            "metadata":   metadata,
            "similarity": similarity,
        })

    return results


# ── smoke test ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    results = retrieve_rag("What does Gengar look like?")
    for r in results:
        print(r["content"])
        print()
