"""
classify_intent.py — classify a user question before routing it to the
right retrieval strategy.

Returns a dict with keys:
  intent            — one of the intent labels
  pokemon_name      — lowercase normalised name, or null
  secondary_pokemon — second Pokémon if comparison is involved, or null
  attacker          — for hybrid_effectiveness: the attacking Pokémon, or null
  defender          — for hybrid_effectiveness: the defending Pokémon, or null
  mode              — for hybrid_effectiveness: effectiveness filter mode, or null
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
  structured_weakness      — type weaknesses, resistances, or immunities FOR a single Pokémon (no attacker/defender dynamic)
  hybrid_effectiveness     — how effective one Pokémon's moves are against another Pokémon, regardless of phrasing direction or perspective
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

Examples for hybrid_effectiveness — pay close attention to mode:
  super_effective (attacker's strong moves):
    "What moves does Flygon have that are good against Charizard?"  → attacker: "flygon", defender: "charizard", mode: "super_effective"
    "Which of Garchomp's moves hit Skarmory hard?"                  → attacker: "garchomp", defender: "skarmory", mode: "super_effective"
    "What does Tyranitar do well against Gengar?"                   → attacker: "tyranitar", defender: "gengar", mode: "super_effective"
    "How can Flygon hurt Togekiss?"                                 → attacker: "flygon", defender: "togekiss", mode: "super_effective"
    "Which moves would Swampert use to deal damage to Venusaur?"    → attacker: "swampert", defender: "venusaur", mode: "super_effective"
    "What hits Blissey super effectively from Machamp?"             → attacker: "machamp", defender: "blissey", mode: "super_effective"
    "What is Charizard weak to from Gyarados's moveset?"            → attacker: "gyarados", defender: "charizard", mode: "super_effective"
    "What of Mewtwo's moves would hurt Tyranitar?"                  → attacker: "mewtwo", defender: "tyranitar", mode: "super_effective"
  not_effective (resisted/bad moves):
    "Which of Flygon's moves does Charizard resist?"                → attacker: "flygon", defender: "charizard", mode: "not_effective"
    "What moves won't work well against Steelix from Alakazam?"     → attacker: "alakazam", defender: "steelix", mode: "not_effective"
    "What bad matchup moves does Blaziken have against Slowbro?"    → attacker: "blaziken", defender: "slowbro", mode: "not_effective"
  neutral:
    "Which of Raichu's moves are neutral against Jolteon?"          → attacker: "raichu", defender: "jolteon", mode: "neutral"
  immune (0× moves):
    "Which of Haunter's moves have no effect on Snorlax?"           → attacker: "haunter", defender: "snorlax", mode: "immune"
    "What moves from Gengar don't affect Normal types?"             → attacker: "gengar", defender: "snorlax", mode: "immune"
  full_audit (all moves with effectiveness):
    "How does Flygon do against Charizard overall?"                 → attacker: "flygon", defender: "charizard", mode: "full_audit"
    "Show me all of Dragonite's moves against Clefable"             → attacker: "dragonite", defender: "clefable", mode: "full_audit"
    "Full matchup breakdown: Machamp vs Gengar"                     → attacker: "machamp", defender: "gengar", mode: "full_audit"
    "What's the complete effectiveness of Gyarados's moves vs Raichu?" → attacker: "gyarados", defender: "raichu", mode: "full_audit"
  stab_only (STAB moves only, no defender needed):
    "What are Flygon's STAB moves?"                                 → attacker: "flygon", defender: null, mode: "stab_only"
    "Which moves does Charizard get STAB on?"                       → attacker: "charizard", defender: null, mode: "stab_only"
    "Show me Lucario's same-type moves"                             → attacker: "lucario", defender: null, mode: "stab_only"

pokemon_name rules — IMPORTANT:
  Always return the BASE species name only. Never include regional suffixes like -alola, -galar, -hisui, -paldea.
  Regional form information is conveyed by the question text; do not encode it in pokemon_name.
  Examples:
    "what type is alolan exeggutor"       → pokemon_name: "exeggutor"   (NOT "exeggutor-alola")
    "what type is galarian meowth"        → pokemon_name: "meowth"      (NOT "meowth-galar")
    "what moves does hisuian voltorb learn" → pokemon_name: "voltorb"   (NOT "voltorb-hisui")
    "what is paldean tauros weak to"      → pokemon_name: "tauros"      (NOT "tauros-paldea")
  For hybrid_effectiveness, set attacker/defender to lowercase base names (no regional suffixes).
  Also set pokemon_name to the attacker's base name for backwards compatibility.

Return this exact JSON shape (keep null for absent fields — do not omit keys):
{
  "intent": "<one of the 10 labels above>",
  "pokemon_name": "<lowercase BASE species name only — no regional suffixes, or null>",
  "secondary_pokemon": "<second pokémon for comparisons, or null>",
  "attacker": "<for hybrid_effectiveness: lowercase attacker base name, or null>",
  "defender": "<for hybrid_effectiveness: lowercase defender base name, or null>",
  "mode": "<for hybrid_effectiveness: super_effective|not_effective|neutral|immune|full_audit|stab_only, or null>",
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
    for key in ("intent", "pokemon_name", "secondary_pokemon", "attacker", "defender", "mode", "move_name", "version_group", "notes"):
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
