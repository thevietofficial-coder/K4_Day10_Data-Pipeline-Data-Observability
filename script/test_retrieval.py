from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from core.config import load_settings
from retrieval.agent import build_agent
from retrieval.index import LocalEmbeddingIndex


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
