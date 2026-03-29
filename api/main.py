"""
api/main.py — FastAPI app for the Pokémon RAG system.

Endpoints:
  POST /ask   — run a question through the full query pipeline
  POST /eval  — run the full eval suite and return results
  GET  /health — liveness check
"""

import json
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

load_dotenv()

# ── startup env check ─────────────────────────────────────────────────────────

REQUIRED_ENV_VARS = [
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
    "SUPABASE_URL",
    "SUPABASE_KEY",
    "DATABASE_URL",
]

missing = [v for v in REQUIRED_ENV_VARS if not os.environ.get(v)]
if missing:
    sys.exit(f"ERROR: Missing required environment variables: {', '.join(missing)}")

# ── app ───────────────────────────────────────────────────────────────────────

app = FastAPI(title="Pokémon RAG API", version="1.0.0")

ALLOWED_ORIGINS = [
    "http://localhost:5173",                   # local Vite dev server
    "https://pokemon-rag.vercel.app",          # production frontend (update after Vercel deploy)
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Import pipeline lazily after env check so import errors surface cleanly
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from generation.query import run_query
from retrieval.classify_intent import classify_intent
from retrieval.retrieve_structured import detect_variant_conflict, find_display_name


# ── schemas ───────────────────────────────────────────────────────────────────

class AskRequest(BaseModel):
    question: str
    selected_variant: str | None = None


class AskResponse(BaseModel):
    answer: str | None
    intent: str
    context_used: str
    needs_clarification: bool = False
    pokemon: str | None = None
    variants: list[str] | None = None
    original_question: str | None = None


class EvalResponse(BaseModel):
    score: str
    by_intent: dict
    results: list


# ── endpoints ─────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok"}


_REGIONAL_PREFIXES = ("alolan", "galarian", "hisuian", "paldean")
# Corresponding PokeAPI suffixes the classifier may accidentally include
_REGIONAL_SUFFIXES = ("-alola", "-galar", "-hisui", "-paldea")


@app.post("/ask", response_model=AskResponse)
def ask(body: AskRequest):
    if not body.question.strip():
        raise HTTPException(status_code=400, detail="question must not be empty")

    try:
        classification = classify_intent(body.question)
        intent = classification.get("intent", "unknown")
        pokemon_name = classification.get("pokemon_name")

        # If the user explicitly named a regional form in the question
        # (e.g. "Alolan Vulpix"), skip clarification and resolve the
        # display_name directly from the question text.
        selected_variant = body.selected_variant
        if not selected_variant and pokemon_name:
            q_lower = body.question.lower()
            for prefix in _REGIONAL_PREFIXES:
                if prefix in q_lower:
                    # Strip any regional suffix the classifier may have included
                    # (e.g. "exeggutor-alola" → "exeggutor")
                    base_name = pokemon_name
                    for suffix in _REGIONAL_SUFFIXES:
                        if base_name.endswith(suffix):
                            base_name = base_name[: -len(suffix)]
                            break
                    candidate = f"{prefix.capitalize()} {base_name.replace('-', ' ').title()}"
                    matched = find_display_name(candidate)
                    if matched:
                        selected_variant = matched
                    break

        # Variant conflict check — skip if variant is already known
        if pokemon_name and not selected_variant:
            variants = detect_variant_conflict(pokemon_name)
            if variants:
                return AskResponse(
                    answer=None,
                    intent="clarification_needed",
                    context_used="",
                    needs_clarification=True,
                    pokemon=pokemon_name,
                    variants=variants,
                    original_question=body.question,
                )

        answer = run_query(body.question, selected_variant=selected_variant)

        return AskResponse(
            answer=answer,
            intent=intent,
            context_used=classification.get("notes") or "",
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/eval", response_model=EvalResponse)
def run_eval():
    qa_path = Path("eval/qa_pairs.json")
    if not qa_path.exists():
        raise HTTPException(status_code=500, detail="eval/qa_pairs.json not found")

    pairs = json.loads(qa_path.read_text(encoding="utf-8"))
    if not pairs:
        raise HTTPException(status_code=500, detail="eval/qa_pairs.json is empty")

    results = []
    for pair in pairs:
        question = pair["question"]
        keywords = [kw.lower() for kw in pair.get("expected_keywords", [])]
        t0 = time.time()

        try:
            answer = run_query(question)
            answer_lower = answer.lower()
            missing = [kw for kw in keywords if kw not in answer_lower]
            passed = len(missing) == 0
        except Exception as exc:
            answer = f"ERROR: {exc}"
            missing = keywords
            passed = False

        results.append({
            "id":               pair["id"],
            "intent":           pair["intent"],
            "question":         question,
            "answer":           answer,
            "expected_keywords": pair.get("expected_keywords", []),
            "missing_keywords": missing,
            "passed":           passed,
            "elapsed_s":        round(time.time() - t0, 2),
        })

    # Save outputs
    results_dir = Path("results")
    results_dir.mkdir(exist_ok=True)
    (results_dir / "eval_results.json").write_text(
        json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    # Aggregate
    total  = len(results)
    passed = sum(1 for r in results if r["passed"])

    intents = sorted({r["intent"] for r in results})
    by_intent = {}
    for intent in intents:
        group = [r for r in results if r["intent"] == intent]
        n_pass = sum(1 for r in group if r["passed"])
        by_intent[intent] = f"{n_pass}/{len(group)}"

    return EvalResponse(
        score=f"{passed}/{total}",
        by_intent=by_intent,
        results=results,
    )
