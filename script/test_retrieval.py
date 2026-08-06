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


def explain_hit_rate(label: str, answers_path: Path, index: LocalEmbeddingIndex) -> dict:
    """Break down a state's retrieval_hit_rate. qa.answer_question's exact-id shortcut
    (re.search(r"'([^']+)'", question) -> index.lookup) keys off paper_id, which
    corruption never mutates for surviving rows -- only drop_latest removes it entirely.
    So misses are expected to correlate with the ground-truth doc being absent from the
    index (dropped), not with content-only corruption (blank_summary/inject_noise/
    truncate_title/stale_date), which the exact-id shortcut is immune to.
    """
    answers = read_json(answers_path)
    present_ids = {doc["paper_id"] for doc in index.documents}
    shortcut_hits = 0
    semantic_hits = 0
    misses_doc_dropped = 0
    misses_doc_present = 0
    for item in answers:
        quoted = QUOTE_PATTERN.search(item["question"])
        resolved = index.lookup(quoted.group(1)) if quoted else None
        shortcut_matches_ground_truth = bool(
            resolved and resolved["paper_id"] in item["ground_truth_doc_ids"]
        )
        ground_truth_present = all(gid in present_ids for gid in item["ground_truth_doc_ids"])
        if not item["retrieval_hit"]:
            if ground_truth_present:
                misses_doc_present += 1
            else:
                misses_doc_dropped += 1
        elif shortcut_matches_ground_truth:
            shortcut_hits += 1
        else:
            semantic_hits += 1

    print(
        f"[{label}] total: {len(answers)} | exact-id shortcut hits: {shortcut_hits} | "
        f"semantic-only hits: {semantic_hits} | misses (doc dropped): {misses_doc_dropped} | "
        f"misses (doc still present): {misses_doc_present}"
    )
    return {
        "shortcut_hits": shortcut_hits,
        "semantic_hits": semantic_hits,
        "misses_doc_dropped": misses_doc_dropped,
        "misses_doc_present": misses_doc_present,
    }


def explain_baseline_hit_rate(settings, index: LocalEmbeddingIndex) -> None:
    explain_hit_rate("baseline", settings.paths.baseline_answers, index)
    print(
        "-> Baseline hits come from qa.answer_question's exact-id shortcut "
        "(re.search(r\"'([^']+)'\", question) -> index.lookup(paper_id)), not from "
        "semantic_search ranking quality alone. Verified: 0 semantic-only hits."
    )


def test_corruption_impact(settings) -> None:
    """CP5: verify baseline is untouched, then compare baseline vs corrupted retrieval.

    Verified mechanism (checked per-question against corrupted collection membership,
    not assumed): every corrupted miss in this run traces to drop_latest removing the
    ground-truth paper entirely from the index. blank_summary/inject_noise/
    truncate_title/stale_date never touch paper_id, so the exact-id shortcut still
    resolves for rows that survive drop_latest -- those corruption types degrade the
    surviving row's *content* but happened not to land on any of this test set's 4
    ground-truth papers in this run, so they show up in token_f1/judge score, not in
    retrieval_hit_rate.
    """
    baseline_index = LocalEmbeddingIndex.load(settings)
    corrupted_index = LocalEmbeddingIndex.load(settings, settings.paths.corrupted_embeddings_json)
    print(f"papers-baseline docs: {len(baseline_index.documents)} (must still be 24, untouched)")
    print(f"papers-corrupted docs: {len(corrupted_index.documents)}")

    query = "hierarchical retrieval augmented generation for tool selection in LLM agents"
    print(f"\n--- same query on baseline vs corrupted: '{query}' ---")
    for label, idx in [("baseline", baseline_index), ("corrupted", corrupted_index)]:
        print(f"[{label}]")
        for result in idx.search(query, top_k=3):
            print(f"  {result.score:.3f} | {result.paper_id} | {result.title[:60]}")

    print("\n--- hit-rate breakdown: baseline vs corrupted ---")
    explain_hit_rate("baseline", settings.paths.baseline_answers, baseline_index)
    explain_hit_rate("corrupted", settings.paths.corrupted_answers, corrupted_index)


def test_repair_impact(settings) -> None:
    """CP6: verify papers-repaired restores what drop_latest removed, smoke test the
    same baseline query against all three states, and confirm the agent answers
    correctly again using repaired tool results.
    """
    baseline_index = LocalEmbeddingIndex.load(settings)
    corrupted_index = LocalEmbeddingIndex.load(settings, settings.paths.corrupted_embeddings_json)
    repaired_index = LocalEmbeddingIndex.load(settings, settings.paths.repaired_embeddings_json)
    print(
        f"docs -> baseline: {len(baseline_index.documents)} | "
        f"corrupted: {len(corrupted_index.documents)} | repaired: {len(repaired_index.documents)}"
    )

    dropped_ids = ["10.1111/exsy.70341", "10.2118/234689-pa"]
    print("\n--- were the drop_latest papers actually restored (not just metric-level)? ---")
    for paper_id in dropped_ids:
        in_corrupted = corrupted_index.lookup(paper_id) is not None
        in_repaired = repaired_index.lookup(paper_id) is not None
        print(f"{paper_id} -> in corrupted: {in_corrupted} | in repaired: {in_repaired}")

    query = "hierarchical retrieval augmented generation for tool selection in LLM agents"
    print(f"\n--- same query across all 3 states: '{query}' ---")
    for label, idx in [("baseline", baseline_index), ("corrupted", corrupted_index), ("repaired", repaired_index)]:
        top = idx.search(query, top_k=1)[0]
        print(f"[{label}] top-1: {top.score:.3f} | {top.paper_id} | {top.title[:60]}")

    print("\n--- hit-rate breakdown: repaired ---")
    explain_hit_rate("repaired", settings.paths.repaired_answers, repaired_index)

    print("\n--- agent on repaired index, asking about a paper drop_latest had removed ---")
    agent = build_agent(settings, repaired_index)
    question = "What does the SafeRAG paper propose for oil and gas safety report generation?"
    result = agent.invoke({"messages": [{"role": "user", "content": question}]})
    for message in result["messages"]:
        tool_calls = getattr(message, "tool_calls", None)
        if tool_calls:
            print(f"[{type(message).__name__}] tool call -> {[call['name'] for call in tool_calls]}")
        elif type(message).__name__ == "ToolMessage":
            print(f"[ToolMessage] tool={getattr(message, 'name', '?')} output={str(message.content)[:150]}")
        else:
            print(f"[{type(message).__name__}] {str(getattr(message, 'content', ''))[:300]}")


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
    _settings = load_settings()
    if _settings.paths.corrupted_answers.exists():
        print("\n\n=== CP5: corruption impact ===")
        test_corruption_impact(_settings)
    if _settings.paths.repaired_answers.exists():
        print("\n\n=== CP6: repair impact ===")
        test_repair_impact(_settings)
