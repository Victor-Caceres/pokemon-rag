"""
load_structured.py — populate Supabase relational tables from pokemon_raw.json

Insertion order (respects foreign keys):
  1. pokemon
  2. moves          (fetches from PokeAPI)
  3. pokemon_moves  (join table)
  4. evolutions

Inserts use the supabase-py REST client (not subject to statement timeouts).
psycopg2 is kept only for SET statement_timeout and SELECT queries.
"""

import json
import logging
import os
import sys
import time
from collections import Counter
from pathlib import Path

import psycopg2
import requests
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

POKEAPI = "https://pokeapi.co/api/v2"
MOVE_SLEEP = 0.3
BATCH_SIZE = 500

# national_dex boundaries for each generation
GENERATION_RANGES = [
    (1,   151,  1),
    (152, 251,  2),
    (252, 386,  3),
    (387, 493,  4),
    (494, 649,  5),
    (650, 721,  6),
    (722, 809,  7),
    (810, 905,  8),
    (906, 1025, 9),
]

# Suffixes appended by PokeAPI to variant names
FORM_SUFFIXES = [
    "-alola", "-galar", "-hisui", "-paldea",
    "-blade", "-shield", "-school", "-10", "-50", "-complete",
]

# How each form_label is displayed
FORM_DISPLAY = {
    "alolan":      "Alolan",
    "galarian":    "Galarian",
    "hisuian":     "Hisuian",
    "paldean":     "Paldean",
    "10-percent":  "10%",
    "50-percent":  "50%",
    "complete":    "Complete",
    "school":      "School Form",
    "blade":       "Blade Forme",
    "shield":      "Shield Forme",
}

REGIONAL_LABELS = {"alolan", "galarian", "hisuian", "paldean"}


# ── helpers ───────────────────────────────────────────────────────────────────

def get_generation(national_dex: int) -> int:
    for lo, hi, gen in GENERATION_RANGES:
        if lo <= national_dex <= hi:
            return gen
    return 9


def get_base_name(name: str, form_label: str) -> str:
    """Strip variant suffix to recover the species base name."""
    if form_label == "base":
        return name
    for suffix in FORM_SUFFIXES:
        if name.endswith(suffix):
            return name[: -len(suffix)]
    return name


def make_display_name(raw_name: str, form_label: str) -> str:
    base = get_base_name(raw_name, form_label).replace("-", " ").title()
    if form_label == "base":
        return base
    label = FORM_DISPLAY.get(form_label, form_label.title())
    if form_label in REGIONAL_LABELS:
        return f"{label} {base}"          # "Alolan Vulpix"
    return f"{base} ({label})"            # "Aegislash (Blade Forme)"


def fetch_move_data(move_name: str) -> dict | None:
    try:
        time.sleep(MOVE_SLEEP)
        resp = requests.get(f"{POKEAPI}/move/{move_name}", timeout=15)
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:
        logger.error("Failed to fetch move %s: %s", move_name, exc)
        return None


def get_move_description(move_data: dict) -> str:
    for entry in move_data.get("effect_entries", []):
        if entry["language"]["name"] == "en":
            return entry.get("short_effect") or entry.get("effect", "")
    entries = [
        e for e in move_data.get("flavor_text_entries", [])
        if e["language"]["name"] == "en"
    ]
    if entries:
        return " ".join(entries[-1]["flavor_text"].split())
    return ""


def _chunks(lst: list, size: int):
    for i in range(0, len(lst), size):
        yield lst[i: i + size]


# ── step 1: pokemon ───────────────────────────────────────────────────────────

def insert_pokemon(supabase: Client, entries: list[dict]) -> dict[str, int]:
    """
    Insert all pokemon rows via supabase REST and return raw_name → db_id.
    has_variants is True for any national_dex that appears more than once.
    """
    dex_counts = Counter(e["national_dex"] for e in entries)
    name_to_id: dict[str, int] = {}

    for entry in entries:
        raw_name   = entry["name"]
        form_label = entry["form_label"]
        ndex       = entry["national_dex"]
        stats      = entry.get("base_stats", {})

        note_parts = []
        if entry.get("mega_evolutions"):
            note_parts.append(entry["mega_evolutions"])
        if entry.get("gmax_note"):
            note_parts.append(entry["gmax_note"])

        row = {
            "name":            get_base_name(raw_name, form_label),
            "display_name":    make_display_name(raw_name, form_label),
            "national_dex":    ndex,
            "form_label":      form_label,
            "generation":      get_generation(ndex),
            "types":           entry.get("types", []),
            "hp":              stats.get("hp", 0),
            "attack":          stats.get("attack", 0),
            "defense":         stats.get("defense", 0),
            "special_attack":  stats.get("special-attack", 0),
            "special_defense": stats.get("special-defense", 0),
            "speed":           stats.get("speed", 0),
            "height_m":        entry.get("height_m"),
            "weight_kg":       entry.get("weight_kg"),
            "abilities":       entry.get("abilities", []),
            "flavor_text":     entry.get("flavor_text", ""),
            "has_variants":    dex_counts[ndex] > 1,
            "mega_note":       " ".join(note_parts) if note_parts else None,
        }

        result = (
            supabase.table("pokemon")
            .upsert(row, on_conflict="name,form_label")
            .execute()
        )
        name_to_id[raw_name] = result.data[0]["id"]

    return name_to_id


# ── step 2: moves ─────────────────────────────────────────────────────────────

def insert_moves(supabase: Client, cur, all_move_names: list[str]) -> dict[str, int]:
    """
    Fetch each unique move from PokeAPI and upsert via supabase REST.
    Each move is inserted individually so a single failure doesn't abort the batch.
    Falls back to a psycopg2 SELECT to recover the id when the row already exists.
    Returns move_name → db_id.
    """
    move_to_id: dict[str, int] = {}
    total = len(all_move_names)

    for i, move_name in enumerate(all_move_names, 1):
        if i % 100 == 0:
            logger.info("  Moves: %d / %d", i, total)

        data = fetch_move_data(move_name)
        if not data:
            continue

        row = {
            "name":         move_name,
            "type":         data["type"]["name"],
            "power":        data.get("power"),       # NULL for status moves
            "accuracy":     data.get("accuracy"),    # NULL for moves that never miss
            "pp":           data.get("pp", 0),
            "damage_class": data["damage_class"]["name"],
            "description":  get_move_description(data),
        }

        try:
            # ignore_duplicates=True → ON CONFLICT (name) DO NOTHING
            result = (
                supabase.table("moves")
                .upsert(row, on_conflict="name", ignore_duplicates=True)
                .execute()
            )
            if result.data:
                move_to_id[move_name] = result.data[0]["id"]
            else:
                # Row already existed — recover id via psycopg2 SELECT
                cur.execute("SELECT id FROM moves WHERE name = %s", (move_name,))
                existing = cur.fetchone()
                if existing:
                    move_to_id[move_name] = existing[0]

        except Exception as exc:
            logger.error("Failed to insert move '%s': %s", move_name, exc)

    return move_to_id


# ── step 3: pokemon_moves ─────────────────────────────────────────────────────

def insert_pokemon_moves(
    supabase: Client,
    entries: list[dict],
    name_to_id: dict[str, int],
    move_to_id: dict[str, int],
    vg_to_id: dict[str, int],
) -> int:
    rows: list[dict] = []

    for entry in entries:
        pokemon_id = name_to_id.get(entry["name"])
        if pokemon_id is None:
            continue

        for m in entry.get("moves", []):
            move_id = move_to_id.get(m["move"])
            if move_id is None:
                continue

            vg_id = vg_to_id.get(m["version_group"])
            if vg_id is None:
                continue  # version group not in our seed — skip

            level = m.get("level") or None
            if level == 0:
                level = None

            rows.append({
                "pokemon_id":       pokemon_id,
                "move_id":          move_id,
                "version_group_id": vg_id,
                "learn_method":     m["learn_method"],
                "level_learned":    level,
            })

    for batch in _chunks(rows, BATCH_SIZE):
        supabase.table("pokemon_moves").insert(batch).execute()

    return len(rows)


# ── step 4: evolutions ────────────────────────────────────────────────────────

def insert_evolutions(supabase: Client, entries: list[dict]) -> int:
    rows: list[dict] = []

    for entry in entries:
        if entry.get("form_label") != "base":
            continue
        for evo in entry.get("evolution_chain", []):
            rows.append({
                "from_pokemon": evo["from"],
                "to_pokemon":   evo["to"],
                "method":       evo["method"],
                "detail":       evo["detail"],
            })

    for batch in _chunks(rows, BATCH_SIZE):
        supabase.table("evolutions").insert(batch).execute()

    return len(rows)


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    database_url = os.environ.get("DATABASE_URL", "")
    if not database_url or "YOUR_DB_PASSWORD" in database_url:
        sys.exit("ERROR: DATABASE_URL not set or still contains placeholder in .env")

    supabase_url = os.environ.get("SUPABASE_URL", "")
    supabase_key = os.environ.get("SUPABASE_KEY", "")
    if not supabase_url or not supabase_key:
        sys.exit("ERROR: SUPABASE_URL and SUPABASE_KEY must be set in .env")

    raw_path = Path("data/pokemon_raw.json")
    if not raw_path.exists():
        sys.exit(f"ERROR: {raw_path} not found — run fetch_pokemon.py first")

    logger.info("Loading %s...", raw_path)
    entries: list[dict] = json.loads(raw_path.read_text(encoding="utf-8"))
    logger.info("  %d entries read", len(entries))

    # psycopg2 — used only for SET statement_timeout and SELECT queries
    conn = psycopg2.connect(
        database_url,
        keepalives=1,
        keepalives_idle=30,
        keepalives_interval=10,
        keepalives_count=5,
    )
    conn.autocommit = True  # no writes via psycopg2; no transaction management needed

    with conn.cursor() as cur:
        cur.execute("SET statement_timeout = '60s';")

    # supabase-py REST client — used for all INSERT/UPSERT operations
    supabase: Client = create_client(supabase_url, supabase_key)

    try:
        with conn.cursor() as cur:
            # ── 1. pokemon ──────────────────────────────────────────────────
            logger.info("Step 1/4 — inserting pokemon...")
            name_to_id = insert_pokemon(supabase, entries)
            logger.info("  %d pokemon inserted", len(name_to_id))

            # ── 2. moves ────────────────────────────────────────────────────
            all_move_names = sorted({
                m["move"]
                for entry in entries
                for m in entry.get("moves", [])
            })
            logger.info("Step 2/4 — fetching & inserting %d unique moves...", len(all_move_names))
            move_to_id = insert_moves(supabase, cur, all_move_names)
            logger.info("  %d moves inserted/found", len(move_to_id))

            # ── 3. pokemon_moves ────────────────────────────────────────────
            logger.info("Step 3/4 — inserting pokemon_moves...")
            cur.execute("SELECT name, id FROM version_groups")
            vg_to_id = {row[0]: row[1] for row in cur.fetchall()}
            pm_count = insert_pokemon_moves(supabase, entries, name_to_id, move_to_id, vg_to_id)
            logger.info("  %d pokemon_moves inserted", pm_count)

            # ── 4. evolutions ───────────────────────────────────────────────
            logger.info("Step 4/4 — inserting evolutions...")
            evo_count = insert_evolutions(supabase, entries)
            logger.info("  %d evolutions inserted", evo_count)

    except Exception:
        logger.exception("Fatal error during load")
        raise
    finally:
        conn.close()

    print(
        f"\nLoaded {len(name_to_id)} pokemon, {len(move_to_id)} moves, "
        f"{pm_count} pokemon_moves, {evo_count} evolutions"
    )


if __name__ == "__main__":
    main()
