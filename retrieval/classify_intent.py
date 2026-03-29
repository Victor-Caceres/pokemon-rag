"""
classify_intent.py — classify a user question before routing it to the
right retrieval strategy.

Returns a dict with keys:
  intent            — one of the 7 intent labels
  pokemon_name      — lowercase normalised name, or null
  secondary_pokemon — second Pokémon if comparison is involved, or null
  version_group     — PokeAPI-style slug (e.g. "red-blue"), or null
  notes             — free-text explanation from the classifier
"""

import json
import os

from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv()

MODEL = "claude-sonnet-4-5"

SYSTEM_PROMPT = """You are a Pokémon question classifier. Your only job is to read a user question and return a JSON object — nothing else. Do not add any explanation, markdown, or code fences.

Classify the question into exactly one of these intents:

  structured_moves         — what moves a Pokémon learns, in which game, at what level
  structured_move_info     — what a specific move does: its type, power, accuracy, PP, or effect — NOT asking which Pokémon learns it
  structured_move_learners — which Pokémon can learn a specific move, optionally filtered by generation or game
  structured_stats         — comparing or ranking stats (heaviest, fastest, highest attack, etc.)
  structured_evolution     — how to evolve a Pokémon or what it evolves into/from
  structured_weakness      — type weaknesses, resistances, or immunities
  rag                      — descriptive questions: appearance, lore, flavor text, personality
  hybrid                   — needs both structured data AND descriptive context
  clarification_needed     — the Pokémon name is not recognisable or the question is too vague

Examples for structured_move_info:
  "What does Seed Bomb do?"          → structured_move_info, move_name: "seed-bomb"
  "How powerful is Earthquake?"      → structured_move_info, move_name: "earthquake"
  "What type is Flamethrower?"       → structured_move_info, move_name: "flamethrower"
  "How many PP does Recover have?"   → structured_move_info, move_name: "recover"

Examples for structured_move_learners:
  "Which Pokémon can learn Razor Leaf?"          → structured_move_learners, move_name: "razor-leaf"
  "Who learns Earthquake?"                       → structured_move_learners, move_name: "earthquake"
  "What Pokémon know Surf?"                      → structured_move_learners, move_name: "surf"
  "Which Pokémon learn Flamethrower in Gen 1?"   → structured_move_learners, move_name: "flamethrower", version_group: "red-blue"

pokemon_name rules — IMPORTANT:
  Always return the BASE species name only. Never include regional suffixes like -alola, -galar, -hisui, -paldea.
  Regional form information is conveyed by the question text; do not encode it in pokemon_name.
  Examples:
    "what type is alolan exeggutor"       → pokemon_name: "exeggutor"   (NOT "exeggutor-alola")
    "what type is galarian meowth"        → pokemon_name: "meowth"      (NOT "meowth-galar")
    "what moves does hisuian voltorb learn" → pokemon_name: "voltorb"   (NOT "voltorb-hisui")
    "what is paldean tauros weak to"      → pokemon_name: "tauros"      (NOT "tauros-paldea")

Return this exact JSON shape (keep null for absent fields — do not omit keys):
{
  "intent": "<one of the 9 labels above>",
  "pokemon_name": "<lowercase BASE species name only — no regional suffixes, or null>",
  "secondary_pokemon": "<second pokémon for comparisons, or null>",
  "move_name": "<lowercase hyphenated move name e.g. seed-bomb, or null>",
  "version_group": "<pokeapi slug e.g. red-blue / gold-silver / scarlet-violet, or null>",
  "notes": "<one sentence explaining your classification>"
}

Version group normalisation rules:
  "Red and Blue" / "Red/Blue" / "Gen 1"       → "red-blue"
  "Yellow"                                     → "yellow"
  "Gold and Silver" / "Gold/Silver" / "Gen 2"  → "gold-silver"
  "Crystal"                                    → "crystal"
  "Ruby and Sapphire" / "Gen 3"                → "ruby-sapphire"
  "Emerald"                                    → "emerald"
  "FireRed / LeafGreen"                        → "firered-leafgreen"
  "Diamond and Pearl" / "Gen 4"                → "diamond-pearl"
  "Platinum"                                   → "platinum"
  "HeartGold / SoulSilver"                     → "heartgold-soulsilver"
  "Black and White" / "Gen 5"                  → "black-white"
  "Black 2 / White 2"                          → "black-2-white-2"
  "X and Y" / "Gen 6"                          → "x-y"
  "Omega Ruby / Alpha Sapphire"                → "omega-ruby-alpha-sapphire"
  "Sun and Moon" / "Gen 7"                     → "sun-moon"
  "Ultra Sun / Ultra Moon"                     → "ultra-sun-ultra-moon"
  "Let's Go"                                   → "lets-go"
  "Sword and Shield" / "Gen 8"                 → "sword-shield"
  "Brilliant Diamond / Shining Pearl"          → "brilliant-diamond-shining-pearl"
  "Legends: Arceus"                            → "legends-arceus"
  "Scarlet and Violet" / "Gen 9"               → "scarlet-violet"
"""


def classify_intent(question: str) -> dict:
    """
    Classify a user question.

    Returns a dict with keys: intent, pokemon_name, secondary_pokemon,
    version_group, notes.  Raises on API or parse errors.
    """
    client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    message = client.messages.create(
        model=MODEL,
        max_tokens=256,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": question}],
    )

    raw = message.content[0].text.strip()

    # Strip accidental markdown fences if the model adds them despite instructions
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()

    result = json.loads(raw)

    # Normalise: ensure all expected keys are present
    for key in ("intent", "pokemon_name", "secondary_pokemon", "move_name", "version_group", "notes"):
        result.setdefault(key, None)

    return result


# ── smoke test ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    test_questions = [
        "What moves does Pikachu learn in Red and Blue?",
        "What is the heaviest Pokémon?",
        "What is Mawile weak against?",
        "How do I evolve Eevee into Umbreon?",
        "Describe what Gengar looks like",
    ]

    for question in test_questions:
        print(f"\nQ: {question}")
        result = classify_intent(question)
        print(json.dumps(result, indent=2))
