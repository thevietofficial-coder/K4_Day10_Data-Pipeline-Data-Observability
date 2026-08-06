"""Test that QA evidence is properly attached to AnswerResult."""
from __future__ import annotations

from unittest.mock import MagicMock

from core.config import Settings
from retrieval.index import LocalEmbeddingIndex, SearchResult
from retrieval.qa import answer_question


def test_answer_question_attaches_sources():
    """Verify that answer_question attaches structured sources pointing to real paper_ids."""
    
    # Mock settings and index
    settings = MagicMock(spec=Settings)
    settings.top_k = 2
    
    index = MagicMock(spec=LocalEmbeddingIndex)
    index.lookup.return_value = None
    
    # Mock search to return deliberately wrong/dummy results
    dummy_results = [
        SearchResult(
            paper_id="10.1234/test1",
            title="A Test Paper 1",
            score=0.9,
            content="Evidence from test paper 1.",
            metadata={"summary": "This is summary 1."},
        ),
        SearchResult(
            paper_id="10.5678/test2",
            title="A Test Paper 2",
            score=0.8,
            content="Evidence from test paper 2.",
            metadata={"summary": "This is summary 2."},
        ),
    ]
    index.search.return_value = dummy_results
    
    question = "What is the capital of France?"
    
    # Even though the question is unrelated, the retrieval pipeline will return the dummy results.
    # The answer extraction logic will use the first sentence of the summary.
    # We want to ensure that 'sources' are attached properly regardless of right/wrong answer.
    
    result = answer_question(question, settings, index)
    
    # The answer should be extracted from the first result's summary
    assert result.answer == "This is summary 1."
    
    # Verify sources are attached
    assert hasattr(result, "sources")
    assert len(result.sources) == 2
    
    assert result.sources[0]["paper_id"] == "10.1234/test1"
    assert result.sources[0]["title"] == "A Test Paper 1"
    assert result.sources[0]["evidence"] == "Evidence from test paper 1."
    
    assert result.sources[1]["paper_id"] == "10.5678/test2"
    assert result.sources[1]["title"] == "A Test Paper 2"
    assert result.sources[1]["evidence"] == "Evidence from test paper 2."
