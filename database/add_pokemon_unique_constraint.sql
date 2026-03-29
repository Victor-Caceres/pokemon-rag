-- Migration: add unique constraint on (name, form_label) to the pokemon table.
-- Safe to run multiple times — the IF NOT EXISTS guard prevents duplicate constraint errors.
-- Run this once against the live DB before re-running load_structured.py.

ALTER TABLE pokemon
    ADD CONSTRAINT IF NOT EXISTS uq_pokemon_name_form UNIQUE (name, form_label);
