"""
run_eval.py — evaluate the full RAG pipeline against qa_pairs.json.

For each Q&A pair:
  - Runs the question through generation/query.py
  - Checks that ALL expected_keywords appear in the lowercased answer
  - Marks pass / fail

Outputs:
  results/eval_results.json   — full per-question detail
  results/eval_summary.md     — markdown table broken down by intent
"""

import json
import logging
import sys
import time
from datetime import datetime
from pathlib import Path

# Allow running from the project root
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from generation.query import run_query

logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")

QA_PATH      = Path("eval/qa_pairs.json")
RESULTS_DIR  = Path("results")
RESULTS_JSON = RESULTS_DIR / "eval_results.json"
RESULTS_MD   = RESULTS_DIR / "eval_summary.md"


# ── evaluation ────────────────────────────────────────────────────────────────

def evaluate_pair(pair: dict) -> dict:
    question = pair["question"]
    keywords = [kw.lower() for kw in pair.get("expected_keywords", [])]

    print(f"  [{pair['id']}] {question}")
    t0 = time.time()

    try:
        answer = run_query(question)
        elapsed = round(time.time() - t0, 2)
        answer_lower = answer.lower()

        missing = [kw for kw in keywords if kw not in answer_lower]
        passed  = len(missing) == 0

    except Exception as exc:
        elapsed = round(time.time() - t0, 2)
        answer  = f"ERROR: {exc}"
        missing = keywords
        passed  = False

    status = "PASS" if passed else "FAIL"
    print(f"    → {status}  ({elapsed}s){'' if passed else f'  missing: {missing}'}")

    return {
        "id":       pair["id"],
        "intent":   pair["intent"],
        "question": question,
        "answer":   answer,
        "expected_keywords": pair.get("expected_keywords", []),
        "missing_keywords":  missing,
        "passed":   passed,
        "elapsed_s": elapsed,
    }


# ── reporting ─────────────────────────────────────────────────────────────────

def build_markdown(results: list[dict], timestamp: str) -> str:
    # Overall stats
    total  = len(results)
    passed = sum(1 for r in results if r["passed"])
    pct    = round(100 * passed / total, 1) if total else 0

    lines = [
        f"# Eval Results — {timestamp}",
        "",
        f"**Overall: {passed}/{total} passed ({pct}%)**",
        "",
    ]

    # Per-intent breakdown
    intents = sorted({r["intent"] for r in results})
    lines += ["## By Intent", ""]
    lines += ["| Intent | Pass | Total | % |", "|--------|------|-------|---|"]

    for intent in intents:
        group   = [r for r in results if r["intent"] == intent]
        n_pass  = sum(1 for r in group if r["passed"])
        n_total = len(group)
        n_pct   = round(100 * n_pass / n_total, 1) if n_total else 0
        lines.append(f"| {intent} | {n_pass} | {n_total} | {n_pct}% |")

    # Per-question detail
    lines += ["", "## Per-Question Detail", ""]
    lines += [
        "| ID | Intent | Pass | Question | Missing Keywords |",
        "|----|--------|------|----------|-----------------|",
    ]
    for r in results:
        status  = "✅" if r["passed"] else "❌"
        missing = ", ".join(r["missing_keywords"]) if r["missing_keywords"] else "—"
        q       = r["question"].replace("|", "\\|")
        lines.append(f"| {r['id']} | {r['intent']} | {status} | {q} | {missing} |")

    return "\n".join(lines) + "\n"


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    if not QA_PATH.exists():
        sys.exit(f"ERROR: {QA_PATH} not found")

    pairs: list[dict] = json.loads(QA_PATH.read_text(encoding="utf-8"))
    if not pairs:
        sys.exit(f"ERROR: {QA_PATH} is empty — add Q&A pairs first")

    RESULTS_DIR.mkdir(exist_ok=True)

    print(f"Running eval on {len(pairs)} questions...\n")
    t_start   = time.time()
    results   = [evaluate_pair(p) for p in pairs]
    total_sec = round(time.time() - t_start, 1)

    # Summary to console
    passed = sum(1 for r in results if r["passed"])
    total  = len(results)
    print(f"\n{'='*50}")
    print(f"Result: {passed}/{total} passed ({round(100*passed/total,1)}%)  in {total_sec}s")
    print(f"{'='*50}\n")

    # Intent breakdown
    intents = sorted({r["intent"] for r in results})
    for intent in intents:
        group  = [r for r in results if r["intent"] == intent]
        n_pass = sum(1 for r in group if r["passed"])
        print(f"  {intent:30s}  {n_pass}/{len(group)}")

    # Write outputs
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")

    RESULTS_JSON.write_text(
        json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"\nFull results → {RESULTS_JSON}")

    RESULTS_MD.write_text(build_markdown(results, timestamp), encoding="utf-8")
    print(f"Markdown summary → {RESULTS_MD}")


if __name__ == "__main__":
    main()
