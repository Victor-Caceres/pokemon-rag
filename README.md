# Pokédex AI

A natural language Pokédex that actually knows the difference between a question that needs a database and a question that needs a search engine. [**Try it live →**](https://pokemon-rag.vercel.app)

---

## The Core Design Decision

Pure RAG would have been wrong here.

The default move for an AI chatbot is: embed everything, run similarity search, hand the results to an LLM. That works fine for descriptive questions. It fails completely for questions like "what moves does Pikachu learn in Red and Blue?" — because that's not a retrieval problem. That's a lookup against a structured dataset with 561,654 records across every game version ever released.

The system is built around a strict routing decision made before any retrieval happens:

- **Claude handles classification** — reads the question, assigns one of nine intent types, extracts parameters
- **SQL handles facts** — moves, stats, weaknesses, evolutions hit purpose-built query functions against relational tables
- **pgvector handles semantics** — descriptive questions about lore, appearance, and behavior run cosine similarity search
- **Claude handles generation** — synthesizes retrieved context into a final answer

Factual answers are never generated. They're retrieved. Claude can't hallucinate a move list it didn't write.

---

## Try It

The system understands natural language across nine generations of Pokémon data. Ask it the way you'd ask a person.

**Move lookups**
> "What moves does Gengar learn in Gold and Silver?"
> "Which Pokémon can learn Surf?"
> "What does Earthquake do?"

**Type matchups**
> "What is Mawile weak against?"
> "Which of Flygon's moves are super effective against Charizard?"
> "What are Flygon's STAB moves?"

**Evolution chains**
> "How do I evolve Eevee into Umbreon?"
> "What does Slowpoke evolve into?"

**Stats**
> "What are the top 5 fastest Pokémon?"
> "Which Fire type has the highest Special Attack?"

**Regional variants**
> "What type is Alolan Exeggutor?"
> "What moves does Galarian Meowth learn?"

The system will ask for clarification when a Pokémon has multiple regional forms and you haven't specified which one you mean.

---

## How It Works

```
User types question
        ↓
React chat UI
        ↓ POST /ask
FastAPI backend
        ↓
Intent Classifier (Claude) — assigns intent + extracts parameters
        ↓
┌─────────────────────┬─────────────────────┐
│   Structured Query  │        RAG          │
│   (psycopg2 + SQL)  │  (OpenAI + pgvector)│
└─────────────────────┴─────────────────────┘
        ↓
Answer Generation (Claude) — or bypassed for pure data intents
        ↓
Frontend renders answer + intent badge
```

Move lookups, learner lists, and effectiveness queries bypass Claude generation entirely — the retrieval functions return clean formatted output directly. There's no value in asking Claude to restate a list it didn't reason about.

---

## Intent Types

Nine intent types cover the full question surface area. The classifier assigns one before any retrieval runs.

| Intent | What it handles | Retrieval path |
|---|---|---|
| `structured_moves` | Move learnsets by game version | SQL |
| `structured_weakness` | Type weaknesses, resistances, immunities | SQL |
| `structured_evolution` | Evolution chains and conditions | SQL |
| `structured_stats` | Stat rankings by type, weight, etc. | SQL |
| `structured_move_info` | What a specific move does | SQL |
| `structured_move_learners` | Which Pokémon learn a move | SQL |
| `hybrid_effectiveness` | Move effectiveness between two Pokémon | SQL × SQL |
| `rag` | Lore, flavor text, descriptive questions | pgvector |
| `clarification_needed` | Unrecognized Pokémon or ambiguous regional form | None |

---

## Data

- **1,205 Pokémon** across all 9 generations, including 180 regional variants (Alolan, Galarian, Hisuian, Paldean)
- **833 unique moves** with type, power, accuracy, PP, damage class, and effect descriptions
- **561,654 move-learn records** mapping every Pokémon to every move across every game version group
- **Complete evolution chains** with method and trigger details
- **Full 18×18 type effectiveness chart** — pre-computed, queried directly for matchup calculations
- **3,615 vector embeddings** (stats, abilities, flavor text chunks) for semantic search

---

## Eval Suite

The eval suite (`eval/qa_pairs.json`) contains 30 hand-written question/answer pairs with keyword assertions, run against the full pipeline end-to-end. Catching regressions across nine intent types without automated ground truth required building the measurement layer from scratch — which is most of what makes it useful.

Baseline: **90% overall, 100% on all structured query types.**

The 10% failure rate is a known data coverage limitation: PokeAPI flavor text is terse and game-specific, which makes keyword matching on descriptive questions brittle. Every failure passes a manual domain check.

Run via `POST /eval` on the API or directly:
```bash
python -m eval.run_eval
```

---

## Stack

| Layer | Technology | Purpose |
|---|---|---|
| Frontend | React + Vite + Tailwind CSS | Chat UI with intent badges |
| Backend | Python + FastAPI | API server + query routing |
| LLM | Claude (Anthropic) | Intent classification + answer generation |
| Embeddings | text-embedding-3-small (OpenAI) | Semantic search vectors |
| Database | Supabase (PostgreSQL + pgvector) | Relational data + vector store |
| Frontend hosting | Vercel | [pokemon-rag.vercel.app](https://pokemon-rag.vercel.app) |
| Backend hosting | Render | Free tier with cold start handling |

---

## Project Structure

```
pokemon-rag/
├── api/
│   └── main.py
├── database/
│   ├── add_pokemon_unique_constraint.sql
│   ├── apply_schema.py
│   ├── enable_pgvector.sql
│   ├── match_documents.sql
│   ├── schema.sql
│   └── seed_version_groups.sql
├── eval/
│   ├── qa_pairs.json
│   └── run_eval.py
├── frontend/
│   ├── public/
│   │   ├── favicon.svg
│   │   └── icons.svg
│   ├── src/
│   │   ├── assets/
│   │   ├── App.css
│   │   ├── App.jsx
│   │   ├── index.css
│   │   └── main.jsx
│   ├── eslint.config.js
│   ├── index.html
│   ├── package.json
│   └── vite.config.js
├── generation/
│   ├── generate.py
│   └── query.py
├── ingest/
│   ├── build_type_chart.py
│   ├── chunk.py
│   ├── embed_and_store.py
│   ├── fetch_pokemon.py
│   ├── load_structured.py
│   ├── run_ingest.py
│   └── transform.py
├── results/
│   ├── eval_results.json
│   └── eval_summary.md
├── retrieval/
│   ├── classify_intent.py
│   ├── retrieve.py
│   ├── retrieve_rag.py
│   └── retrieve_structured.py
├── scripts/
│   └── reset_db.py
├── .gitignore
├── README.md
└── requirements.txt
```

---

## Running Your Own Instance

**Prerequisites:** Python 3.11+, Node 18+, Supabase project with pgvector enabled.

1. Clone the repo
   ```bash
   git clone https://github.com/Victor-Caceres/pokemon-rag.git
   cd pokemon-rag
   ```

2. Install Python dependencies
   ```bash
   pip install -r requirements.txt
   ```

3. Create a `.env` file in the project root:
   ```
   ANTHROPIC_API_KEY=...
   OPENAI_API_KEY=...
   SUPABASE_URL=...
   SUPABASE_KEY=...
   DATABASE_URL=postgresql://...
   ```

4. Apply the database schema
   ```bash
   python database/apply_schema.py
   ```

5. Run the ingest pipeline — fetches from PokeAPI, loads structured data, builds embeddings (~20 min, runs once)
   ```bash
   python ingest/run_ingest.py
   ```

6. Start the backend
   ```bash
   python -m uvicorn api.main:app --reload
   ```

7. Start the frontend
   ```bash
   cd frontend && npm install && npm run dev
   ```

   Open [http://localhost:5173](http://localhost:5173).

---

## Author

[Victor Caceres](https://victorcaceres.com) — built using a structured five-phase product and engineering framework before any code was written.
