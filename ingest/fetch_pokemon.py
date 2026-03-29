import argparse
import json
import logging
import time
from pathlib import Path

import requests

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

BASE_URL = "https://pokeapi.co/api/v2"
SLEEP = 0.5

# Varieties containing these are never saved as separate documents
SKIP_KEYWORDS = ("totem", "gmax", "mega", "primal", "eternamax")

# Varieties containing these are situational forms and ARE saved as separate docs
SITUATIONAL_KEYWORDS = ("10", "50", "complete", "school", "blade", "shield")

# Ordered by specificity so earlier rules win
FORM_LABEL_RULES = [
    ("alola", "alolan"),
    ("galar", "galarian"),
    ("hisui", "hisuian"),
    ("paldea", "paldean"),
    ("10", "10-percent"),
    ("50", "50-percent"),
    ("complete", "complete"),
    ("school", "school"),
    ("blade", "blade"),
    ("shield", "shield"),
]


def fetch_json(url: str) -> dict | None:
    try:
        time.sleep(SLEEP)
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:
        logger.error("Failed to fetch %s: %s", url, exc)
        return None


def get_form_label(variety_name: str) -> str:
    for keyword, label in FORM_LABEL_RULES:
        if keyword in variety_name:
            return label
    return "base"


def get_english_flavor_text(species_data: dict) -> str:
    entries = [
        e for e in species_data.get("flavor_text_entries", [])
        if e["language"]["name"] == "en"
    ]
    if not entries:
        return ""
    raw = entries[-1]["flavor_text"]
    return " ".join(raw.split())


def extract_moves(pokemon_data: dict) -> list[dict]:
    """Flatten the moves array into one record per (move, version_group) pair."""
    result = []
    for move_entry in pokemon_data.get("moves", []):
        move_name = move_entry["move"]["name"]
        for vgd in move_entry.get("version_group_details", []):
            result.append({
                "move": move_name,
                "version_group": vgd["version_group"]["name"],
                "learn_method": vgd["move_learn_method"]["name"],
                "level": vgd["level_learned_at"],
            })
    return result


def parse_evolution_method(detail: dict) -> tuple[str, str]:
    """Return (method, detail_str) for one evolution_detail entry."""
    trigger = detail["trigger"]["name"]

    if trigger == "level-up":
        if detail.get("min_happiness"):
            parts = ["high friendship"]
            if detail.get("time_of_day"):
                parts.append(f"at {detail['time_of_day']}")
            if detail.get("known_move"):
                parts.append(f"knowing {detail['known_move']['name']}")
            return "friendship", " ".join(parts)

        parts = []
        if detail.get("min_level"):
            parts.append(f"level {detail['min_level']}")
        if detail.get("held_item"):
            parts.append(f"holding {detail['held_item']['name']}")
        if detail.get("known_move"):
            parts.append(f"knowing {detail['known_move']['name']}")
        if detail.get("known_move_type"):
            parts.append(f"knowing a {detail['known_move_type']['name']}-type move")
        if detail.get("location"):
            parts.append(f"at {detail['location']['name']}")
        if detail.get("time_of_day"):
            parts.append(f"at {detail['time_of_day']}")
        if detail.get("min_affection"):
            parts.append(f"high affection")
        return "level-up", ", ".join(parts) if parts else "level-up"

    if trigger == "use-item":
        item_name = detail.get("item", {}).get("name", "unknown-item")
        method = "stone" if "stone" in item_name else "other"
        return method, item_name

    if trigger == "trade":
        if detail.get("held_item"):
            return "trade", f"trade holding {detail['held_item']['name']}"
        return "trade", "trade"

    return "other", trigger


def parse_chain(node: dict, parent: str | None = None) -> list[dict]:
    """Recursively walk an evolution chain node and return edge dicts."""
    edges: list[dict] = []
    current = node["species"]["name"]

    if parent is not None:
        for detail in node.get("evolution_details", []):
            method, detail_str = parse_evolution_method(detail)
            edges.append({"from": parent, "to": current, "method": method, "detail": detail_str})

    for child in node.get("evolves_to", []):
        edges.extend(parse_chain(child, current))

    return edges


def get_evolution_chain(species_data: dict) -> list[dict]:
    """Fetch and parse the evolution chain for a species. Returns [] on failure."""
    chain_url = (species_data.get("evolution_chain") or {}).get("url")
    if not chain_url:
        return []

    chain_data = fetch_json(chain_url)
    if not chain_data:
        return []

    return parse_chain(chain_data["chain"])


def extract_entry(pokemon_data: dict, species_data: dict, form_label: str) -> dict:
    return {
        "name": pokemon_data["name"],
        "national_dex": species_data["id"],
        "form_label": form_label,
        "types": [t["type"]["name"] for t in pokemon_data["types"]],
        "base_stats": {s["stat"]["name"]: s["base_stat"] for s in pokemon_data["stats"]},
        "height_m": round(pokemon_data["height"] / 10, 1),
        "weight_kg": round(pokemon_data["weight"] / 10, 1),
        "abilities": [a["ability"]["name"] for a in pokemon_data["abilities"]],
        "flavor_text": get_english_flavor_text(species_data),
        "moves": extract_moves(pokemon_data),
    }


def build_mega_note(base_name: str, mega_varieties: list[dict]) -> str:
    parts = []
    for variety in mega_varieties:
        variety_name = variety["pokemon"]["name"]
        data = fetch_json(variety["pokemon"]["url"])
        if not data:
            logger.warning("Could not fetch mega variant %s", variety_name)
            continue
        types = "/".join(t["type"]["name"].capitalize() for t in data["types"])
        display = variety_name.replace("-", " ").title()
        parts.append(f"{display} ({types})")

    if not parts:
        return ""

    base_display = base_name.replace("-", " ").title()
    joined = " or ".join(parts)
    return f"{base_display} can Mega Evolve into {joined}."


def build_gmax_note(base_name: str) -> str:
    display = base_name.replace("-", " ").title()
    return f"{display} has a Gigantamax form."


def fetch_all(limit: int | None) -> list[dict]:
    max_id = limit if limit else 1025
    results: list[dict] = []

    for dex_id in range(1, max_id + 1):
        if (dex_id - 1) % 50 == 0:
            logger.info("Progress: base Pokemon #%d / %d", dex_id, max_id)

        pokemon_data = fetch_json(f"{BASE_URL}/pokemon/{dex_id}")
        if not pokemon_data:
            logger.warning("Skipping #%d: base data unavailable", dex_id)
            continue

        species_data = fetch_json(f"{BASE_URL}/pokemon-species/{dex_id}")
        if not species_data:
            logger.warning("Skipping #%d: species data unavailable", dex_id)
            continue

        base_entry = extract_entry(pokemon_data, species_data, "base")
        base_entry["evolution_chain"] = get_evolution_chain(species_data)

        mega_varieties: list[dict] = []
        has_gmax = False
        variant_entries: list[dict] = []

        for variety in species_data.get("varieties", []):
            if variety.get("is_default"):
                continue

            vname = variety["pokemon"]["name"].lower()

            # Mega/primal: skip as separate doc, collect for note on base entry
            if any(kw in vname for kw in ("mega", "primal")):
                mega_varieties.append(variety)
                continue
            # Gmax: skip as separate doc, flag for note on base entry
            if "gmax" in vname:
                has_gmax = True
                continue
            # Totem/eternamax: skip entirely
            if any(kw in vname for kw in ("totem", "eternamax")):
                continue

            # Regional or situational form — fetch as a separate document
            variant_data = fetch_json(variety["pokemon"]["url"])
            if not variant_data:
                logger.warning("Skipping variant %s: fetch failed", vname)
                continue

            form_label = get_form_label(vname)
            variant_entries.append(extract_entry(variant_data, species_data, form_label))

        if mega_varieties:
            note = build_mega_note(pokemon_data["name"], mega_varieties)
            if note:
                base_entry["mega_evolutions"] = note

        if has_gmax:
            base_entry["gmax_note"] = build_gmax_note(pokemon_data["name"])

        results.append(base_entry)
        results.extend(variant_entries)

    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch Pokemon data from PokeAPI")
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Cap the number of base Pokemon fetched (variants are still included)",
    )
    args = parser.parse_args()

    logger.info("Starting fetch (limit=%s)...", args.limit or "none")
    entries = fetch_all(args.limit)

    out = Path("data/pokemon_raw.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(entries, indent=2, ensure_ascii=False), encoding="utf-8")

    logger.info("Done -- %d entries saved to %s", len(entries), out)


if __name__ == "__main__":
    main()
