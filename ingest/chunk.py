"""
chunk.py — convert pokemon_raw.json into text chunks for embedding.

Produces 3 chunks per Pokémon:
  stats       — type, base stats, height/weight, mega note
  abilities   — ability list
  description — flavor text

Output: data/pokemon_chunks.json
"""

import json
from collections import Counter
from pathlib import Path

# ── display-name helpers (mirrors load_structured.py) ────────────────────────

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

FORM_SUFFIXES = [
    "-alola", "-galar", "-hisui", "-paldea",
    "-blade", "-shield", "-school", "-10", "-50", "-complete",
]

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


def get_generation(national_dex: int) -> int:
    for lo, hi, gen in GENERATION_RANGES:
        if lo <= national_dex <= hi:
            return gen
    return 9


def get_base_name(name: str, form_label: str) -> str:
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
        return f"{label} {base}"
    return f"{base} ({label})"


# ── chunk builders ────────────────────────────────────────────────────────────

def build_stats_chunk(entry: dict, display_name: str) -> str:
    types_str = "/".join(t.capitalize() for t in entry.get("types", []))
    s = entry.get("base_stats", {})
    parts = [
        f"{display_name} is a {types_str} type Pokémon.",
        f"Base stats: HP {s.get('hp', '?')}, Attack {s.get('attack', '?')}, "
        f"Defense {s.get('defense', '?')}, Sp. Atk {s.get('special-attack', '?')}, "
        f"Sp. Def {s.get('special-defense', '?')}, Speed {s.get('speed', '?')}.",
        f"Height: {entry.get('height_m', '?')}m, Weight: {entry.get('weight_kg', '?')}kg.",
    ]
    if entry.get("mega_evolutions"):
        parts.append(entry["mega_evolutions"])
    if entry.get("gmax_note"):
        parts.append(entry["gmax_note"])
    return " ".join(parts)


def build_abilities_chunk(entry: dict, display_name: str) -> str:
    abilities = ", ".join(a.replace("-", " ") for a in entry.get("abilities", []))
    return f"{display_name} has the following abilities: {abilities}."


def build_description_chunk(entry: dict, display_name: str) -> str:
    flavor = entry.get("flavor_text", "").strip()
    if not flavor:
        return f"{display_name}: No description available."
    return f"{display_name}: {flavor}"


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    raw_path = Path("data/pokemon_raw.json")
    if not raw_path.exists():
        raise FileNotFoundError(f"{raw_path} not found — run fetch_pokemon.py first")

    entries: list[dict] = json.loads(raw_path.read_text(encoding="utf-8"))
    print(f"Loaded {len(entries)} Pokemon entries")

    # has_variants: True for any national_dex that appears more than once
    dex_counts = Counter(e["national_dex"] for e in entries)

    chunks: list[dict] = []

    for entry in entries:
        raw_name   = entry["name"]
        form_label = entry["form_label"]
        ndex       = entry["national_dex"]
        display    = make_display_name(raw_name, form_label)
        base_name  = get_base_name(raw_name, form_label)

        meta_base = {
            "name":         base_name,
            "display_name": display,
            "national_dex": ndex,
            "form_label":   form_label,
            "generation":   get_generation(ndex),
            "has_variants": dex_counts[ndex] > 1,
        }

        for chunk_type, content in [
            ("stats",       build_stats_chunk(entry, display)),
            ("abilities",   build_abilities_chunk(entry, display)),
            ("description", build_description_chunk(entry, display)),
        ]:
            chunks.append({
                "content":  content,
                "metadata": {**meta_base, "chunk_type": chunk_type},
            })

    out = Path("data/pokemon_chunks.json")
    out.write_text(json.dumps(chunks, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {len(chunks)} chunks to {out}  ({len(entries)} Pokemon x 3)")


if __name__ == "__main__":
    main()
