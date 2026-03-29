"""
generate.py — final answer generation using Claude.

Takes a user question and a pre-built context string, returns an answer.
"""

import os

from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv()

MODEL = "claude-sonnet-4-5"

SYSTEM_PROMPT = """\
You are a Pokédex assistant. Answer using only the provided context.

Guidelines:
- For factual questions (stats, moves, types, weaknesses, evolutions): be precise \
and complete. List all relevant data from the context.
- For descriptive questions: answer naturally using the retrieved text.
- If the provided context is empty or does not contain enough information \
to answer the question, respond only with: \
"My Pokédex database doesn't have that information." \
Do not supplement with outside knowledge under any circumstances. \
Never say "based on general knowledge" or similar phrases.
- For unanswerable questions (favorite food, opinions, preferences, feelings): \
respond in a dry Pokédex voice with light humor. \
Example: "This unit does not record dessert preferences."
- Never invent stats, types, moves, or abilities not present in the context.
- Keep answers concise unless the question asks for a full list.
- When the context is a move-learners list (formatted as "N Pokémon can learn X: / By level-up: ... / By TM/HM: ..."), \
present it exactly as given. Do not regroup by evolution line, do not reorder, do not add your own structure or headers. \
Copy the groups and comma-separated names verbatim.
"""


def generate_answer(question: str, context: str) -> str:
    """
    Call Claude with *question* and *context*, return the answer string.
    Raises on API errors — callers should handle accordingly.
    """
    client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    user_message = f"Context:\n{context}\n\nQuestion: {question}"

    message = client.messages.create(
        model=MODEL,
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}],
    )
    return message.content[0].text


# ── smoke test ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    sample_context = (
        "Gengar is a Ghost/Poison type Pokémon. "
        "Gengar: Under a full moon, this Pokémon likes to mimic the shadows "
        "of people and laugh at their fright."
    )
    print(generate_answer("What does Gengar look like and what does it do at night?", sample_context))
