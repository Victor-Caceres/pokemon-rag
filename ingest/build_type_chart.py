"""
build_type_chart.py — fetch type matchups from PokeAPI and populate type_effectiveness.

The table is static (18×18 = 324 rows). Re-run only if a new type is ever added.
"""

import os
import sys
import time

import psycopg2
import psycopg2.extras
import requests
from dotenv import load_dotenv

load_dotenv()

POKEAPI = "https://pokeapi.co/api/v2/type"
SLEEP = 0.4

TYPES = [
    "normal", "fire", "water", "electric", "grass", "ice",
    "fighting", "poison", "ground", "flying", "psychic", "bug",
    "rock", "ghost", "dragon", "dark", "steel", "fairy",
]


def fetch_type(type_name: str) -> dict:
    time.sleep(SLEEP)
    resp = requests.get(f"{POKEAPI}/{type_name}", timeout=15)
    resp.raise_for_status()
    return resp.json()


def build_matrix() -> dict[tuple[str, str], float]:
    """
    Return a dict keyed by (attacking_type, defending_type) → multiplier.
    Start with all 324 pairs at 1.0, then overwrite from PokeAPI damage_relations.
    """
    matrix: dict[tuple[str, str], float] = {
        (atk, dfc): 1.0 for atk in TYPES for dfc in TYPES
    }

    for atk_type in TYPES:
        print(f"  Fetching {atk_type}...", end=" ", flush=True)
        data = fetch_type(atk_type)
        relations = data["damage_relations"]

        for entry in relations.get("double_damage_to", []):
            dfc = entry["name"]
            if dfc in set(TYPES):
                matrix[(atk_type, dfc)] = 2.0

        for entry in relations.get("half_damage_to", []):
            dfc = entry["name"]
            if dfc in set(TYPES):
                matrix[(atk_type, dfc)] = 0.5

        for entry in relations.get("no_damage_to", []):
            dfc = entry["name"]
            if dfc in set(TYPES):
                matrix[(atk_type, dfc)] = 0.0

        print("done")

    return matrix


def main() -> None:
    database_url = os.environ.get("DATABASE_URL", "")
    if not database_url or "YOUR_DB_PASSWORD" in database_url:
        sys.exit("ERROR: DATABASE_URL not set or still contains placeholder in .env")

    print(f"Fetching type data for {len(TYPES)} types from PokeAPI...")
    matrix = build_matrix()

    rows = [
        (atk, dfc, multiplier)
        for (atk, dfc), multiplier in sorted(matrix.items())
    ]

    print(f"\nInserting {len(rows)} rows into type_effectiveness...")
    conn = psycopg2.connect(database_url)
    conn.autocommit = False
    try:
        with conn.cursor() as cur:
            cur.execute("TRUNCATE TABLE type_effectiveness RESTART IDENTITY")
            psycopg2.extras.execute_batch(
                cur,
                "INSERT INTO type_effectiveness (attacking_type, defending_type, multiplier) "
                "VALUES (%s, %s, %s)",
                rows,
                page_size=324,
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    print(f"Type chart loaded: {len(rows)} rows")


if __name__ == "__main__":
    main()
