"""
Apply the pokemon-rag database schema to Supabase.

Execution order:
  1. enable_pgvector.sql  – CREATE EXTENSION IF NOT EXISTS vector
  2. schema.sql           – all tables and indexes
  3. seed_version_groups.sql – static version-group rows

Requires DATABASE_URL in .env (get the password from
Supabase Dashboard → Project Settings → Database → Connection string).
"""

import os
import sys
from pathlib import Path

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

# ── Supabase client (connection validation) ──────────────────────────────────

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")
DATABASE_URL = os.environ.get("DATABASE_URL", "")

if not SUPABASE_URL or not SUPABASE_KEY:
    sys.exit("ERROR: SUPABASE_URL and SUPABASE_KEY must be set in .env")

if not DATABASE_URL or "YOUR_DB_PASSWORD" in DATABASE_URL:
    sys.exit(
        "ERROR: DATABASE_URL is missing or still has the placeholder password.\n"
        "Get your password from: Supabase Dashboard → Project Settings → Database → "
        "Connection string (Session mode), then update DATABASE_URL in .env"
    )

print("Connecting via supabase-py client...")
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
print(f"  supabase-py client initialised for {SUPABASE_URL}")

# ── SQL execution via psycopg2 (direct Postgres) ─────────────────────────────

HERE = Path(__file__).parent

SQL_STEPS = [
    ("enable_pgvector.sql", "Enabling pgvector extension"),
    ("schema.sql",          "Applying schema (tables + indexes)"),
    ("seed_version_groups.sql", "Seeding version groups"),
]


def execute_sql_file(conn, path: Path, description: str) -> None:
    print(f"\n[{description}]  {path.name}")
    sql = path.read_text(encoding="utf-8")

    with conn.cursor() as cur:
        try:
            cur.execute(sql)
            conn.commit()
            print(f"  OK — {path.name} applied successfully.")
        except psycopg2.errors.DuplicateTable as exc:
            conn.rollback()
            print(f"  WARNING — table already exists, skipping: {exc.pgerror.strip()}")
        except psycopg2.errors.DuplicateObject as exc:
            conn.rollback()
            print(f"  WARNING — object already exists, skipping: {exc.pgerror.strip()}")
        except psycopg2.Error as exc:
            conn.rollback()
            # Non-fatal: print and continue so other steps still run
            print(f"  ERROR — {exc.pgcode}: {exc.pgerror.strip() if exc.pgerror else exc}")


def main() -> None:
    print(f"\nConnecting to Postgres via DATABASE_URL...")
    try:
        conn = psycopg2.connect(DATABASE_URL)
        conn.autocommit = False
        print("  Connected.")
    except psycopg2.OperationalError as exc:
        sys.exit(f"ERROR: Could not connect to Postgres.\n{exc}")

    try:
        for filename, description in SQL_STEPS:
            path = HERE / filename
            if not path.exists():
                print(f"  SKIP — {filename} not found")
                continue
            execute_sql_file(conn, path, description)
    finally:
        conn.close()
        print("\nConnection closed.")

    print("\nDone — all schema steps complete.")


if __name__ == "__main__":
    main()
