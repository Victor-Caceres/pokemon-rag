"""
retrieve_structured.py — query Supabase relational tables and return
formatted context strings for the generation prompt.
"""

import logging
import os

import psycopg2
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

load_dotenv()

ALL_TYPES = [
    "normal", "fire", "water", "electric", "grass", "ice",
    "fighting", "poison", "ground", "flying", "psychic", "bug",
    "rock", "ghost", "dragon", "dark", "steel", "fairy",
]

# Whitelist of valid stat column names (prevents SQL injection)
STAT_COLUMNS = {
    "hp":               "hp",
    "attack":           "attack",
    "defense":          "defense",
    "special_attack":   "special_attack",
    "special-attack":   "special_attack",
    "spatk":            "special_attack",
    "sp. atk":          "special_attack",
    "special_defense":  "special_defense",
    "special-defense":  "special_defense",
    "spdef":            "special_defense",
    "sp. def":          "special_defense",
    "speed":            "speed",
    "height":           "height_m",
    "weight":           "weight_kg",
}


def _connect():
    return psycopg2.connect(os.environ["DATABASE_URL"])


# ── 1. moves ──────────────────────────────────────────────────────────────────

def _vg_display(vg: str) -> str:
    """Convert a version-group slug to a human-readable name."""
    return vg.replace("-", "/").title()


def get_moves(pokemon_name: str, version_group: str | None = None, form_label: str = "base", display_name: str | None = None) -> str:
    """
    Return a formatted string of moves for *pokemon_name*, organised by game.

    Single-game (version_group provided):
        "{Pokémon} in {Game}:\n  By level-up: ...\n  By TM/HM: ..."

    All-games (no filter):
        "{Pokémon}'s moves by game:\n\n{Game1}:\n  ...\n\n{Game2 & Game3}:\n  ..."
    Version groups with identical move lists are merged with " & ".

    When *display_name* is provided it overrides the name + form_label lookup.
    """
    conn = _connect()
    try:
        with conn.cursor() as cur:
            if display_name:
                sql = """
                    SELECT m.name, pm.learn_method, pm.level_learned, vg.name
                    FROM pokemon_moves pm
                    JOIN pokemon        p  ON p.id  = pm.pokemon_id
                    JOIN moves          m  ON m.id  = pm.move_id
                    JOIN version_groups vg ON vg.id = pm.version_group_id
                    WHERE p.display_name = %s
                """
                params: list = [display_name]
            else:
                sql = """
                    SELECT m.name, pm.learn_method, pm.level_learned, vg.name
                    FROM pokemon_moves pm
                    JOIN pokemon        p  ON p.id  = pm.pokemon_id
                    JOIN moves          m  ON m.id  = pm.move_id
                    JOIN version_groups vg ON vg.id = pm.version_group_id
                    WHERE p.name = %s
                      AND p.form_label = %s
                """
                params: list = [pokemon_name, form_label]

            if version_group:
                sql += " AND vg.name = %s"
                params.append(version_group)

            sql += " ORDER BY vg.generation, vg.id, pm.level_learned NULLS LAST, m.name"
            cur.execute(sql, params)
            rows = cur.fetchall()
    finally:
        conn.close()

    poke_d = display_name or pokemon_name.replace("-", " ").title()

    if not rows:
        scope = f" in {_vg_display(version_group)}" if version_group else ""
        return f"No move data found for {poke_d}{scope}."

    # ── helpers ───────────────────────────────────────────────────────────────

    def _morder(m: str) -> int:
        return {"level-up": 0, "machine": 1, "tm": 1, "egg": 2, "tutor": 3}.get(m, 99)

    def _mlabel(m: str) -> str:
        return {
            "level-up": "By level-up",
            "machine":  "By TM/HM",
            "tm":       "By TM/HM",
            "egg":      "By egg move",
            "tutor":    "By tutor",
        }.get(m, f"By {m.title()}")

    def _section(method: str, move_set: set) -> str:
        if method == "level-up":
            parts = [
                f"{n} ({lvl})" if lvl else n
                for n, lvl in sorted(move_set, key=lambda t: (t[1] or 0, t[0]))
            ]
        else:
            parts = [n for n, _ in sorted(move_set, key=lambda t: t[0])]
        return f"  {_mlabel(method)}: {', '.join(parts)}"

    # ── build vg → method → set[(move_d, level)] ──────────────────────────────

    vg_order: list[str] = []
    vg_moves: dict[str, dict[str, set]] = {}

    for move_name, method, level, vg in rows:
        if vg not in vg_moves:
            vg_order.append(vg)
            vg_moves[vg] = {}
        move_d = move_name.replace("-", " ").title()
        norm_level = level if method == "level-up" else None
        vg_moves[vg].setdefault(method, set()).add((move_d, norm_level))

    # ── group VGs with identical move lists ───────────────────────────────────

    def _fingerprint(vg: str) -> frozenset:
        return frozenset(
            (method, move_d, lvl)
            for method, moves in vg_moves[vg].items()
            for move_d, lvl in moves
        )

    fp_to_vgs: dict[frozenset, list[str]] = {}
    vg_to_fp: dict[str, frozenset] = {}
    for vg in vg_order:
        fp = _fingerprint(vg)
        vg_to_fp[vg] = fp
        fp_to_vgs.setdefault(fp, []).append(vg)

    # Preserve first-occurrence order for groups
    seen_fps: set = set()
    ordered_fps: list[frozenset] = []
    for vg in vg_order:
        fp = vg_to_fp[vg]
        if fp not in seen_fps:
            seen_fps.add(fp)
            ordered_fps.append(fp)

    # ── format ────────────────────────────────────────────────────────────────

    if version_group:
        lines = [f"{poke_d} in {_vg_display(version_group)}:"]
        for method in sorted(vg_moves.get(version_group, {}), key=_morder):
            lines.append(_section(method, vg_moves[version_group][method]))
        result = "\n".join(lines)
        print(f"[DEBUG get_moves] first 500 chars:\n{result[:500]!r}")
        return result

    lines = [f"{poke_d}'s moves by game:", ""]
    for fp in ordered_fps:
        vgs = fp_to_vgs[fp]
        header = " & ".join(_vg_display(vg) for vg in vgs)
        lines.append(f"{header}:")
        for method in sorted(vg_moves[vgs[0]], key=_morder):
            lines.append(_section(method, vg_moves[vgs[0]][method]))
        lines.append("")

    result = "\n".join(lines).rstrip()
    print(f"[DEBUG get_moves] first 500 chars:\n{result[:500]!r}")
    return result


# ── 1b. move info ─────────────────────────────────────────────────────────────

def get_move_info(move_name: str) -> str:
    """
    Return a formatted summary of a single move's stats and effect.
    *move_name* can be in any capitalisation or with spaces (e.g. "Seed Bomb",
    "seed bomb", "seed-bomb") — it is normalised to the lowercase hyphenated
    PokeAPI slug before querying.
    """
    slug = move_name.strip().lower().replace(" ", "-")

    conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT name, type, power, accuracy, pp, damage_class, description
                FROM moves
                WHERE name = %s
                """,
                (slug,),
            )
            row = cur.fetchone()
    finally:
        conn.close()

    if not row:
        display = move_name.replace("-", " ").title()
        return f"No data found for the move '{display}'."

    name, mtype, power, accuracy, pp, damage_class, description = row
    display = name.replace("-", " ").title()

    power_str    = str(power)    if power    is not None else "—"
    accuracy_str = f"{accuracy}%" if accuracy is not None else "—"

    lines = [
        f"{display}",
        f"  Type:         {mtype.capitalize()}",
        f"  Category:     {damage_class.capitalize()}",
        f"  Power:        {power_str}",
        f"  Accuracy:     {accuracy_str}",
        f"  PP:           {pp}",
    ]
    if description:
        lines.append(f"  Effect:       {description}")

    return "\n".join(lines)


# ── 1c. move learners ─────────────────────────────────────────────────────────

# Canonical display order for learn methods
_METHOD_ORDER = {"level-up": 0, "machine": 1, "egg": 2, "tutor": 3}
_METHOD_LABELS = {
    "level-up": "By level-up",
    "machine":  "By TM/HM",
    "egg":      "By egg move",
    "tutor":    "By tutor",
}


def get_move_learners(move_name: str, version_group: str | None = None) -> str:
    """
    Return a formatted summary of all Pokémon that learn *move_name*, grouped
    by learn method.  Each method section lists display_names (deduped, dex
    order) as a comma-separated line.

    *move_name* is normalised (spaces → hyphens, lowercased) before querying.
    Pass *version_group* to restrict results to a single game slug.
    """
    slug = move_name.strip().lower().replace(" ", "-")
    move_d = slug.replace("-", " ").title()

    conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT name FROM moves WHERE name = %s", (slug,))
            if not cur.fetchone():
                return f"No move named '{move_d}' found in the database."

            sql = """
                SELECT DISTINCT
                    p.display_name,
                    p.national_dex,
                    pm.learn_method,
                    vg.generation,
                    vg.id AS vg_id
                FROM pokemon_moves pm
                JOIN pokemon        p  ON p.id  = pm.pokemon_id
                JOIN moves          m  ON m.id  = pm.move_id
                JOIN version_groups vg ON vg.id = pm.version_group_id
                WHERE m.name = %s
            """
            params: list = [slug]
            if version_group:
                sql += " AND vg.name = %s"
                params.append(version_group)

            sql += " ORDER BY p.national_dex, vg.generation, vg.id"
            cur.execute(sql, params)
            rows = cur.fetchall()
    finally:
        conn.close()

    if not rows:
        scope = f" in {_vg_display(version_group)}" if version_group else ""
        return f"No Pokémon learn {move_d}{scope} in the database."

    # method → ordered list of display_names (deduped, dex order preserved)
    by_method: dict[str, list[str]] = {}
    seen_learner: dict[str, set[str]] = {}  # method → set of already-added display_names

    for display_name, _ndex, method, _vg_gen, _vg_id in rows:
        if method not in seen_learner:
            seen_learner[method] = set()
            by_method[method] = []
        if display_name not in seen_learner[method]:
            seen_learner[method].add(display_name)
            by_method[method].append(display_name)

    total = len({name for names in by_method.values() for name in names})
    scope = f" in {_vg_display(version_group)}" if version_group else ""
    lines = [f"{total} Pokémon can learn {move_d}{scope}:", ""]

    for method in sorted(by_method, key=lambda m: _METHOD_ORDER.get(m, 99)):
        label = _METHOD_LABELS.get(method, f"By {method}")
        names_str = ", ".join(by_method[method])
        lines.append(f"{label}: {names_str}")

    return "\n".join(lines)


# ── 2. stats ranking ──────────────────────────────────────────────────────────

def get_stats_ranking(
    type_filter: str | None = None,
    stat: str | None = None,
    limit: int = 5,
) -> str:
    """
    Return the top *limit* Pokémon ordered by *stat* (base-form only).
    Pass *type_filter* to restrict to one type (e.g. "fire").
    *stat* can be any key in STAT_COLUMNS, or "total" / "base total".
    """
    stat_key = (stat or "").lower().strip()
    use_total = stat_key in ("total", "base total", "overall", "base stat total")

    if use_total:
        order_expr = "(hp + attack + defense + special_attack + special_defense + speed)"
        select_expr = f"{order_expr} AS stat_value"
        stat_label = "Base Stat Total"
    else:
        col = STAT_COLUMNS.get(stat_key, "weight_kg")
        order_expr = col
        select_expr = f"{col} AS stat_value"
        stat_label = stat.replace("_", " ").replace("-", " ").title() if stat else "Weight"

    logger.debug(
        "get_stats_ranking: stat=%r → stat_key=%r → col=%r | type_filter=%r | limit=%d",
        stat, stat_key, order_expr, type_filter, limit,
    )

    conn = _connect()
    try:
        with conn.cursor() as cur:
            sql = f"""
                SELECT display_name, types, {select_expr}
                FROM pokemon
                WHERE form_label = 'base'
            """
            params: list = []
            if type_filter:
                sql += " AND types @> %s::text[]"
                params.append([type_filter.lower()])

            sql += f" ORDER BY {order_expr} DESC NULLS LAST LIMIT %s"
            params.append(limit)

            cur.execute(sql, params)
            rows = cur.fetchall()
    finally:
        conn.close()

    if not rows:
        scope = f" ({type_filter.capitalize()} type)" if type_filter else ""
        return f"No Pokémon found{scope}."

    type_scope = f" ({type_filter.capitalize()} type)" if type_filter else ""
    header = f"Top {limit} Pokémon by {stat_label}{type_scope}:"

    unit = ""
    if not use_total:
        if col == "weight_kg":
            unit = " kg"
        elif col == "height_m":
            unit = " m"

    lines = [header]
    for display_name, types, value in rows:
        types_str = "/".join(t.capitalize() for t in types)
        lines.append(f"  {display_name} [{types_str}] — {value}{unit}")
    return "\n".join(lines)


# ── 3. evolution ──────────────────────────────────────────────────────────────

def get_evolution(pokemon_name: str) -> str:
    """
    Return the full evolution chain for *pokemon_name*.

    Uses a two-pass strategy: first find edges directly involving the
    Pokémon, then expand to all edges touching any name in those edges.
    This correctly handles both linear chains (e.g. Ivysaur → full
    Bulbasaur line) and branching chains (e.g. Eevee's 8 branches).
    """
    conn = _connect()
    try:
        with conn.cursor() as cur:
            # Pass 1: direct edges
            cur.execute("""
                SELECT from_pokemon, to_pokemon, method, detail
                FROM evolutions
                WHERE from_pokemon = %s OR to_pokemon = %s
            """, (pokemon_name, pokemon_name))
            direct = cur.fetchall()

            if not direct:
                return f"No evolution data found for {pokemon_name}."

            # Pass 2: full chain — expand to all names touched by pass 1
            chain_names = {p for edge in direct for p in edge[:2]}
            cur.execute("""
                SELECT from_pokemon, to_pokemon, method, detail
                FROM evolutions
                WHERE from_pokemon = ANY(%s) OR to_pokemon = ANY(%s)
            """, (list(chain_names), list(chain_names)))
            all_edges = cur.fetchall()
    finally:
        conn.close()

    name_d = pokemon_name.replace("-", " ").title()
    lines = [f"Evolution chain involving {name_d}:"]
    for from_p, to_p, method, detail in all_edges:
        from_d = from_p.replace("-", " ").title()
        to_d   = to_p.replace("-", " ").title()
        detail_str = f" ({detail})" if detail and detail != method else ""
        lines.append(f"  {from_d} → {to_d}: {method}{detail_str}")
    return "\n".join(lines)


# ── 4. weaknesses ─────────────────────────────────────────────────────────────

def get_weaknesses(pokemon_name: str, form_label: str = "base", display_name: str | None = None) -> str:
    """
    Return a formatted weakness/resistance/immunity summary for *pokemon_name*.
    For dual-type Pokémon the multipliers are combined (multiplied together).
    When *display_name* is provided (e.g. "Alolan Sandshrew"), it is used as
    the lookup key instead of name + form_label.
    """
    conn = _connect()
    try:
        with conn.cursor() as cur:
            if display_name:
                cur.execute(
                    "SELECT types, display_name FROM pokemon WHERE display_name = %s",
                    (display_name,),
                )
            else:
                cur.execute(
                    "SELECT types, display_name FROM pokemon WHERE name = %s AND form_label = %s",
                    (pokemon_name, form_label),
                )
            row = cur.fetchone()
            if not row:
                lookup_desc = display_name or f"{pokemon_name} (form: {form_label})"
                return f"No Pokémon found: '{lookup_desc}'."

            defending_types, display_name = row

            cur.execute("""
                SELECT attacking_type, defending_type, multiplier
                FROM type_effectiveness
                WHERE defending_type = ANY(%s)
            """, (defending_types,))
            matchup_rows = cur.fetchall()
    finally:
        conn.close()

    # Build lookup: defending_type → {attacking_type: multiplier}
    lookup: dict[str, dict[str, float]] = {}
    for atk, dfc, mult in matchup_rows:
        lookup.setdefault(dfc, {})[atk] = float(mult)

    # Combine multipliers across all defending types
    combined: dict[str, float] = {}
    for atk in ALL_TYPES:
        mult = 1.0
        for dfc in defending_types:
            mult *= lookup.get(dfc, {}).get(atk, 1.0)
        combined[atk] = mult

    def fmt(lst: list[str]) -> str:
        return ", ".join(t.capitalize() for t in sorted(lst)) if lst else "none"

    quadruple  = [t for t, m in combined.items() if m == 4.0]
    double     = [t for t, m in combined.items() if m == 2.0]
    half       = [t for t, m in combined.items() if m == 0.5]
    quarter    = [t for t, m in combined.items() if m == 0.25]
    immune     = [t for t, m in combined.items() if m == 0.0]

    types_d = "/".join(t.capitalize() for t in defending_types)
    lines = [
        f"{display_name} is {types_d} type.",
        f"  Weak to      (4×): {fmt(quadruple)}",
        f"  Weak to      (2×): {fmt(double)}",
        f"  Resists    (0.5×): {fmt(half)}",
        f"  Resists   (0.25×): {fmt(quarter)}",
        f"  Immune       (0×): {fmt(immune)}",
    ]
    return "\n".join(lines)


# ── variant resolution ────────────────────────────────────────────────────────

def resolve_variant(display_name: str) -> tuple[str, str] | None:
    """
    Look up a Pokémon by its display_name (e.g. "Alolan Vulpix") and return
    (name, form_label) from the pokemon table, or None if not found.
    """
    conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT name, form_label FROM pokemon WHERE display_name = %s LIMIT 1",
                (display_name,),
            )
            row = cur.fetchone()
    finally:
        conn.close()
    return (row[0], row[1]) if row else None


def find_display_name(candidate: str) -> str | None:
    """
    Case-insensitive lookup of *candidate* against the display_name column.
    Returns the canonical display_name as stored in the DB, or None if not found.
    """
    conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT display_name FROM pokemon WHERE LOWER(display_name) = LOWER(%s) LIMIT 1",
                (candidate,),
            )
            row = cur.fetchone()
    finally:
        conn.close()
    return row[0] if row else None


# ── variant conflict detection ───────────────────────────────────────────────

def detect_variant_conflict(pokemon_name: str) -> list[str] | None:
    """
    Return a list of display_names if *pokemon_name* has more than one
    form in the database (e.g. ["Vulpix", "Alolan Vulpix"]).
    Returns None when only one form exists or the name is not found.
    """
    conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT DISTINCT display_name FROM pokemon WHERE name = %s ORDER BY display_name",
                (pokemon_name,),
            )
            rows = cur.fetchall()
    finally:
        conn.close()

    if len(rows) > 1:
        return [row[0] for row in rows]
    return None


# ── smoke tests ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=== get_moves (pikachu, red-blue) ===")
    print(get_moves("pikachu", "red-blue"))

    print("\n=== get_stats_ranking (heaviest, top 5) ===")
    print(get_stats_ranking(stat="weight", limit=5))

    print("\n=== get_evolution (eevee) ===")
    print(get_evolution("eevee"))

    print("\n=== get_weaknesses (mawile) ===")
    print(get_weaknesses("mawile"))
