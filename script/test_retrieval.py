from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from core.config import load_settings
from core.utils import read_json
from retrieval.agent import build_agent
from retrieval.index import LocalEmbeddingIndex

QUOTE_PATTERN = re.compile(r"'([^']+)'")


def explain_baseline_hit_rate(settings, index: LocalEmbeddingIndex) -> None:
    """Break down baseline_metrics.json's 100% hit rate: how many hits come from
    the exact-quoted-id shortcut in qa.answer_question vs real semantic ranking.
    """
    answers = read_json(settings.paths.baseline_answers)
    shortcut_hits = 0
    semantic_hits = 0
    misses = 0
    for item in answers:
        quoted = QUOTE_PATTERN.search(item["question"])
        resolved = index.lookup(quoted.group(1)) if quoted else None
        shortcut_matches_ground_truth = bool(
            resolved and resolved["paper_id"] in item["ground_truth_doc_ids"]
        )
        if not item["retrieval_hit"]:
            misses += 1
        elif shortcut_matches_ground_truth:
            shortcut_hits += 1
        else:
            semantic_hits += 1

    print(f"total: {len(answers)} | exact-quote shortcut hits: {shortcut_hits} | "
          f"semantic-only hits: {semantic_hits} | misses: {misses}")
    print(
        f"-> {shortcut_hits}/{len(answers)} of baseline's retrieval hits come from "
        "qa.answer_question's regex shortcut (re.search(r\"'([^']+)'\", question)) matching the "
        "exact paper_id/title embedded in the question text, not from semantic_search ranking "
        "quality alone. Corruption's 'truncate_title' step should break this shortcut for "
        "affected rows, making semantic_search's real ranking quality the deciding factor there."
    )


def test_retrieval() -> None:
    settings = load_settings()
    index = LocalEmbeddingIndex.load(settings)
    print(f"Loaded collection '{index.collection_name}' with {len(index.documents)} documents")

    print("\n--- semantic_search ---")
    query = "hierarchical retrieval augmented generation for tool selection in LLM agents"
    for result in index.search(query, top_k=3):
        print(f"{result.score:.3f} | {result.paper_id} | {result.title[:70]}")

    print("\n--- lookup (exact paper_id) ---")
    sample_id = index.documents[0]["paper_id"]
    found = index.lookup(sample_id)
    print(f"lookup({sample_id}) -> {'FOUND' if found else 'MISS'}")

    print("\n--- CP3: explain baseline retrieval_hit_rate ---")
    if settings.paths.baseline_answers.exists():
        explain_baseline_hit_rate(settings, index)
    else:
        print("baseline_answers.json not found, run script/run_phase1.py first")

    print("\n--- agent (must use tools, must fall back to semantic search on failed lookup) ---")
    agent = build_agent(settings, index)
    question = "What does the Hi-RAG paper propose for tool selection in LLM agents?"
    result = agent.invoke({"messages": [{"role": "user", "content": question}]})
    for message in result["messages"]:
        tool_calls = getattr(message, "tool_calls", None)
        if tool_calls:
            print(f"[{type(message).__name__}] tool call -> {[call['name'] for call in tool_calls]}")
        elif type(message).__name__ == "ToolMessage":
            print(f"[ToolMessage] tool={getattr(message, 'name', '?')} output={str(message.content)[:150]}")
        else:
            print(f"[{type(message).__name__}] {str(getattr(message, 'content', ''))[:300]}")


if __name__ == "__main__":
    test_retrieval()
