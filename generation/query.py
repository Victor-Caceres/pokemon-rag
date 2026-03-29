"""
query.py — full RAG pipeline: classify → retrieve → generate.

Entry point: run_query(question) -> str
"""

import logging

from retrieval.classify_intent import classify_intent
from retrieval.retrieve_structured import (
    get_evolution,
    get_move_info,
    get_move_learners,
    get_moves,
    get_stats_ranking,
    get_weaknesses,
    resolve_variant,
)
from retrieval.retrieve_rag import retrieve_rag
from generation.generate import generate_answer

logger = logging.getLogger(__name__)

# ── stat keyword extraction ───────────────────────────────────────────────────

# Order matters: more-specific phrases before single words
_STAT_KEYWORDS: list[tuple[str, str]] = [
    ("base stat total", "total"),
    ("overall stats",   "total"),
    ("best stats",      "total"),
    ("special attack",  "special_attack"),
    ("special defense", "special_defense"),
    ("sp. atk",         "special_attack"),
    ("sp. def",         "special_defense"),
    ("heaviest",        "weight"),
    ("lightest",        "weight"),
    ("tallest",         "height"),
    ("shortest",        "height"),
    ("fastest",         "speed"),
    ("slowest",         "speed"),
    ("strongest",       "attack"),
    ("highest hp",      "hp"),
    ("most hp",         "hp"),
    ("by hp",           "hp"),
    ("highest attack",  "attack"),
    ("highest defense", "defense"),
    ("highest speed",   "speed"),
    ("by attack",       "attack"),
    ("by defense",      "defense"),
    ("by speed",        "speed"),
    ("weight",          "weight"),
    ("height",          "height"),
    ("speed",           "speed"),
    (" hp",             "hp"),
]

_ALL_TYPES = {
    "normal", "fire", "water", "electric", "grass", "ice",
    "fighting", "poison", "ground", "flying", "psychic", "bug",
    "rock", "ghost", "dragon", "dark", "steel", "fairy",
}


def _extract_stat(question: str) -> str | None:
    q = question.lower()
    for phrase, stat in _STAT_KEYWORDS:
        if phrase in q:
            return stat
    return None


def _extract_type_filter(question: str) -> str | None:
    q = question.lower()
    for t in _ALL_TYPES:
        if t in q:
            return t
    return None


# ── retrieval helpers ─────────────────────────────────────────────────────────

def _rag_context(question: str, top_k: int = 5) -> str:
    results = retrieve_rag(question, top_k=top_k)
    return "\n\n".join(r["content"] for r in results)


def _structured_context_for_hybrid(
    question: str,
    pokemon_name: str | None,
    form_label: str = "base",
    display_name: str | None = None,
) -> str:
    """Best-effort structured lookup for hybrid queries."""
    if not pokemon_name:
        return ""
    q = question.lower()
    if any(w in q for w in ("weak", "resist", "immune", "effective", "strong against")):
        return get_weaknesses(pokemon_name, form_label=form_label, display_name=display_name)
    if any(w in q for w in ("evolve", "evolution", "evolves")):
        return get_evolution(pokemon_name)
    if any(w in q for w in ("move", "learn", "attack", "tm", "hm")):
        return get_moves(pokemon_name, form_label=form_label, display_name=display_name)
    # Default: return empty and let RAG carry the hybrid
    return ""


# ── main pipeline ─────────────────────────────────────────────────────────────

def run_query(question: str, selected_variant: str | None = None) -> str:
    """
    Full pipeline: classify → retrieve → generate.
    When *selected_variant* is a display_name (e.g. "Alolan Vulpix"), it is
    resolved to (pokemon_name, form_label) and used to override classifier results.
    Returns a final answer string.
    """
    # Resolve variant before classification so we use the canonical name/form
    resolved_name: str | None = None
    form_label: str = "base"
    if selected_variant:
        resolved = resolve_variant(selected_variant)
        if resolved:
            resolved_name, form_label = resolved
            logger.info("Resolved variant '%s' → name=%s form=%s", selected_variant, resolved_name, form_label)

    classification = classify_intent(question)
    intent         = classification.get("intent", "rag")
    # If the variant was resolved, override whatever the classifier guessed for pokemon_name
    pokemon_name   = resolved_name or classification.get("pokemon_name")
    move_name      = classification.get("move_name")
    version_group  = classification.get("version_group")
    notes          = classification.get("notes", "")

    # When a variant is already resolved, the Pokémon is known — never dead-end
    # on clarification_needed regardless of what the classifier returns.
    if intent == "clarification_needed" and resolved_name:
        q = question.lower()
        if any(w in q for w in ("weak", "resist", "immune", "type", "effective")):
            intent = "structured_weakness"
        elif any(w in q for w in ("move", "learn", "attack", "tm", "hm")):
            intent = "structured_moves"
        elif any(w in q for w in ("evolve", "evolution", "evolves")):
            intent = "structured_evolution"
        else:
            intent = "rag"
        logger.info("Overrode clarification_needed → %s (variant already resolved)", intent)

    logger.info("Intent: %s | pokemon: %s | form: %s | vg: %s", intent, pokemon_name, form_label, version_group)
    logger.debug("Classifier notes: %s", notes)

    # ── route by intent ───────────────────────────────────────────────────────

    if intent == "clarification_needed":
        return (
            "I couldn't identify a Pokémon in your question. "
            "Could you check the spelling and try again?"
        )

    elif intent == "structured_move_info":
        if not move_name:
            return "Please specify which move you'd like information about."
        return get_move_info(move_name)

    elif intent == "structured_move_learners":
        if not move_name:
            return "I couldn't identify which move you're asking about. Could you check the spelling and try again?"
        return get_move_learners(move_name, version_group)

    elif intent == "structured_moves":
        if not pokemon_name:
            return "Please specify which Pokémon you'd like move information for."
        context = get_moves(pokemon_name, version_group, form_label=form_label, display_name=selected_variant)

    elif intent == "structured_stats":
        stat        = _extract_stat(question)
        type_filter = _extract_type_filter(question)
        context     = get_stats_ranking(type_filter=type_filter, stat=stat, limit=5)

    elif intent == "structured_evolution":
        # prefer the named Pokémon; fall back to secondary if classifier
        # identified only the target (e.g., "how do I get Umbreon?")
        name = pokemon_name or classification.get("secondary_pokemon")
        if not name:
            return "Please specify which Pokémon you'd like evolution information for."
        context = get_evolution(name)

    elif intent == "structured_weakness":
        if not pokemon_name:
            return "Please specify which Pokémon you'd like weakness information for."
        context = get_weaknesses(pokemon_name, form_label=form_label, display_name=selected_variant)

    elif intent == "rag":
        context = _rag_context(question)

    elif intent == "hybrid":
        structured = _structured_context_for_hybrid(question, pokemon_name, form_label=form_label, display_name=selected_variant)
        rag        = _rag_context(question)
        context    = "\n\n".join(filter(None, [structured, rag]))

    else:
        # Unknown intent — fall back to RAG
        logger.warning("Unknown intent '%s', falling back to RAG", intent)
        context = _rag_context(question)

    if not context.strip():
        context = "No relevant information found in the database."

    return generate_answer(question, context)


# ── smoke test ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    questions = [
        "What moves does Pikachu learn in Red and Blue?",
        "What is the heaviest Pokémon?",
        "What is Mawile weak against?",
        "How do I evolve Eevee into Umbreon?",
        "Describe what Gengar looks like",
        "Tell me about Mew — its stats and what makes it special",
    ]

    for q in questions:
        print(f"\n{'='*60}")
        print(f"Q: {q}")
        print(f"{'='*60}")
        print(run_query(q))
