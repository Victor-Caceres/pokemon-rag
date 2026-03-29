-- ============================================================
-- pokemon-rag Supabase schema
-- Run enable_pgvector.sql first to ensure vector extension is available
-- ============================================================

-- ------------------------------------------------------------
-- pokemon
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS pokemon (
    id                  SERIAL PRIMARY KEY,
    name                TEXT        NOT NULL,           -- lowercase base name, e.g. "vulpix"
    display_name        TEXT        NOT NULL,           -- e.g. "Alolan Vulpix"
    national_dex        INTEGER     NOT NULL,
    form_label          TEXT        NOT NULL DEFAULT 'base', -- "base", "alolan", "galarian", "hisuian", "paldean"
    generation          INTEGER     NOT NULL,
    types               TEXT[]      NOT NULL,
    hp                  INTEGER     NOT NULL,
    attack              INTEGER     NOT NULL,
    defense             INTEGER     NOT NULL,
    special_attack      INTEGER     NOT NULL,
    special_defense     INTEGER     NOT NULL,
    speed               INTEGER     NOT NULL,
    height_m            NUMERIC,
    weight_kg           NUMERIC,
    abilities           TEXT[]      NOT NULL DEFAULT '{}',
    flavor_text         TEXT        NOT NULL DEFAULT '',
    has_variants        BOOLEAN     NOT NULL DEFAULT FALSE,
    mega_note           TEXT
);

-- ------------------------------------------------------------
-- moves
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS moves (
    id              SERIAL PRIMARY KEY,
    name            TEXT    NOT NULL UNIQUE,
    type            TEXT    NOT NULL,
    power           INTEGER,                    -- NULL for status moves
    accuracy        INTEGER,                    -- NULL for moves that never miss
    pp              INTEGER NOT NULL,
    damage_class    TEXT    NOT NULL,           -- "physical", "special", "status"
    description     TEXT    NOT NULL DEFAULT ''
);

-- ------------------------------------------------------------
-- version_groups
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS version_groups (
    id          SERIAL PRIMARY KEY,
    name        TEXT    NOT NULL UNIQUE,        -- e.g. "red-blue", "scarlet-violet"
    generation  INTEGER NOT NULL
);

-- ------------------------------------------------------------
-- pokemon_moves  (join between pokemon, moves, and version_groups)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS pokemon_moves (
    id                  SERIAL PRIMARY KEY,
    pokemon_id          INTEGER NOT NULL REFERENCES pokemon(id)        ON DELETE CASCADE,
    move_id             INTEGER NOT NULL REFERENCES moves(id)          ON DELETE CASCADE,
    version_group_id    INTEGER NOT NULL REFERENCES version_groups(id) ON DELETE CASCADE,
    learn_method        TEXT    NOT NULL,       -- "level-up", "tm", "egg", "tutor"
    level_learned       INTEGER                -- only populated for level-up moves
);

-- ------------------------------------------------------------
-- evolutions
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS evolutions (
    id              SERIAL PRIMARY KEY,
    from_pokemon    TEXT    NOT NULL,           -- base name of the pre-evolution
    to_pokemon      TEXT    NOT NULL,           -- base name of the evolution
    method          TEXT    NOT NULL,           -- "level-up", "stone", "trade", "friendship", "other"
    detail          TEXT    NOT NULL DEFAULT '' -- e.g. "fire-stone", "level 36", "high friendship at night"
);

-- ------------------------------------------------------------
-- type_effectiveness
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS type_effectiveness (
    id              SERIAL PRIMARY KEY,
    attacking_type  TEXT    NOT NULL,
    defending_type  TEXT    NOT NULL,
    multiplier      NUMERIC NOT NULL            -- 0, 0.5, 1, or 2
);

-- ------------------------------------------------------------
-- pokemon_embeddings  (requires pgvector)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS pokemon_embeddings (
    id          SERIAL PRIMARY KEY,
    pokemon_id  INTEGER NOT NULL REFERENCES pokemon(id) ON DELETE CASCADE,
    chunk_type  TEXT    NOT NULL,              -- "stats", "abilities", "description"
    content     TEXT    NOT NULL,
    embedding   vector(1536),
    metadata    JSONB   NOT NULL DEFAULT '{}'
);

-- ------------------------------------------------------------
-- indexes
-- ------------------------------------------------------------
ALTER TABLE pokemon
    ADD CONSTRAINT IF NOT EXISTS uq_pokemon_name_form UNIQUE (name, form_label);

CREATE INDEX IF NOT EXISTS idx_pokemon_national_dex   ON pokemon(national_dex);
CREATE INDEX IF NOT EXISTS idx_pokemon_name           ON pokemon(name);
CREATE INDEX IF NOT EXISTS idx_pokemon_form_label     ON pokemon(form_label);

CREATE INDEX IF NOT EXISTS idx_pokemon_moves_pokemon  ON pokemon_moves(pokemon_id);
CREATE INDEX IF NOT EXISTS idx_pokemon_moves_move     ON pokemon_moves(move_id);
CREATE INDEX IF NOT EXISTS idx_pokemon_moves_vg       ON pokemon_moves(version_group_id);

CREATE INDEX IF NOT EXISTS idx_evolutions_from        ON evolutions(from_pokemon);
CREATE INDEX IF NOT EXISTS idx_evolutions_to          ON evolutions(to_pokemon);

CREATE INDEX IF NOT EXISTS idx_type_effectiveness     ON type_effectiveness(attacking_type, defending_type);

CREATE INDEX IF NOT EXISTS idx_embeddings_pokemon     ON pokemon_embeddings(pokemon_id);
CREATE INDEX IF NOT EXISTS idx_embeddings_chunk_type  ON pokemon_embeddings(chunk_type);
