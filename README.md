# Pokédex AI

A conversational Pokédex powered by a hybrid RAG pipeline — ask anything about Pokémon moves, types, evolutions, and lore. [**Try it live →**](https://pokemon-rag.vercel.app)

## What it demonstrates

- **Hybrid RAG** — routes questions to either structured SQL queries or vector similarity search depending on what the question needs, then synthesizes the result with Claude
- **Intent classification** — a Claude-powered classifier reads each question and assigns one of nine intent types (move lookup, type weakness, evolution chain, stats ranking, move info, move learners, semantic search, hybrid, clarification) before any retrieval happens
- **Structured query routing** — factual questions (stats, moves, weaknesses, evolutions) bypass the vector store entirely and hit purpose-built SQL functions, so answers are always accurate and never hallucinated
- **Hand-rolled eval suite** — 30 question/answer pairs with keyword assertions, run against the full pipeline to catch regressions across all intent types

## Architecture

```
User question
      ↓
Intent Classifier (Claude)
      ↓
┌──────────────┬──────────────┐
│ Structured   │     RAG      │
│ Query (SQL)  │  (pgvector)  │
└──────────────┴──────────────┘
      ↓
Answer Generation (Claude)
```

The classifier determines the retrieval path. Structured intents (moves, stats, weaknesses, evolutions) query Supabase relational tables directly via psycopg2. Descriptive intents embed the question with OpenAI and run a cosine similarity search via pgvector. Hybrid intents do both. The retrieved context is passed to Claude for final answer generation.

## Tech Stack

| Layer | Technology | Purpose |
|---|---|---|
| Frontend | React + Vite + Tailwind CSS v4 | Chat UI |
| Backend | FastAPI + Python | API server |
| LLM | Claude (Anthropic) | Intent classification + answer generation |
| Embeddings | text-embedding-3-small (OpenAI) | Semantic search vectors |
| Database | Supabase (PostgreSQL + pgvector) | Relational data + vector store |
| Hosting | Vercel (frontend) + Render (backend) | Deployment |

## Data

- 1,205 Pokémon across 9 generations including regional variants (Alolan, Galarian, Hisuian, Paldean)
- 833 unique moves with type, power, accuracy, PP, damage class, and effect descriptions
- 561,654 move-learn records mapping Pokémon to moves across every game version group
- Complete evolution chains with method and trigger details
- Full 18×18 type effectiveness chart
- 3,615 vector embeddings (stats, abilities, and flavor text chunks) for semantic search

## Eval Suite

The eval suite (`eval/qa_pairs.json`) contains 30 hand-written question/answer pairs covering all structured intent types and RAG. Each pair includes a list of expected keywords; the suite runs the full pipeline against every question and checks that all keywords appear in the answer. Baseline score: **90% overall, 100% on structured queries**. Run it via `POST /eval` on the API or directly with `python eval/run_eval.py`.

## Local Setup

**Prerequisites:** Python 3.11+, Node 18+, a Supabase project with pgvector enabled.

1. **Clone the repo**
   ```bash
   git clone https://github.com/Victor-Caceres/pokemon-rag.git
   cd pokemon-rag
   ```

2. **Install Python dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure environment variables** — create a `.env` file in the project root with your keys:
   ```
   ANTHROPIC_API_KEY=...
   OPENAI_API_KEY=...
   SUPABASE_URL=...
   SUPABASE_KEY=...
   DATABASE_URL=postgresql://...
   ```

4. **Apply the database schema**
   ```bash
   python database/apply_schema.py
   ```

5. **Run the ingest pipeline** (fetches from PokeAPI, loads structured data, builds embeddings — takes ~20 minutes)
   ```bash
   python ingest/run_ingest.py
   ```

6. **Start the API server**
   ```bash
   uvicorn api.main:app --reload
   ```

7. **Start the frontend**
   ```bash
   cd frontend
   npm install
   npm run dev
   ```
   Open [http://localhost:5173](http://localhost:5173).

## Author

[Victor Caceres](https://victorcaceres.com)
