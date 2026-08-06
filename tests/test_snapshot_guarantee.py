"""Test that the source fetcher enforces a frozen snapshot and never re-fetches mid-run."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from core.config import Paths, Settings
from ingestion.crossref import fetch_source_records


def _make_settings(tmp_path: Path, **overrides) -> Settings:
    data_dir = tmp_path / "data"
    paths = Paths(
        project_dir=tmp_path,
        workspace_dir=tmp_path,
        raw_api_response=data_dir / "raw" / "crossref_response.json",
        raw_records_json=data_dir / "raw" / "crossref_records.json",
        clean_csv=data_dir / "clean" / "papers_clean.csv",
        clean_json=data_dir / "clean" / "papers_clean.json",
        chroma_dir=data_dir / "chroma",
        embeddings_json=data_dir / "embeddings" / "papers_embeddings.json",
        corrupted_clean_csv=data_dir / "clean" / "papers_clean_corrupted.csv",
        corrupted_clean_json=data_dir / "clean" / "papers_clean_corrupted.json",
        corrupted_embeddings_json=data_dir / "embeddings" / "papers_embeddings_corrupted.json",
        repaired_clean_csv=data_dir / "clean" / "papers_clean_repaired.csv",
        repaired_clean_json=data_dir / "clean" / "papers_clean_repaired.json",
        repaired_embeddings_json=data_dir / "embeddings" / "papers_embeddings_repaired.json",
        eval_testset=data_dir / "eval" / "test_set.json",
        baseline_metrics=data_dir / "results" / "baseline_metrics.json",
        baseline_answers=data_dir / "results" / "baseline_answers.json",
        demo_answers=data_dir / "results" / "agent_demo_answers.json",
        quality_dir=data_dir / "quality",
        gx_dir=data_dir / "quality" / "gx",
        freshness_report=data_dir / "quality" / "freshness_report.json",
        baseline_report=data_dir / "reports" / "phase1_report.md",
        corruption_log=data_dir / "results" / "corruption_log.json",
        corrupted_metrics=data_dir / "results" / "corrupted_metrics.json",
        corrupted_answers=data_dir / "results" / "corrupted_answers.json",
        repaired_metrics=data_dir / "results" / "repaired_metrics.json",
        repaired_answers=data_dir / "results" / "repaired_answers.json",
        comparison_report=data_dir / "reports" / "corruption_report.md",
    )
    defaults = dict(
        llm_provider="gemini",
        model_name="gemini-2.5-flash",
        google_api_key=None,
        openai_api_key=None,
        anthropic_api_key=None,
        openrouter_api_key=None,
        openrouter_base_url="https://openrouter.ai/api/v1",
        ollama_base_url="http://localhost:11434",
        custom_llm_api_key=None,
        custom_llm_base_url=None,
        embedding_model="sentence-transformers/all-MiniLM-L6-v2",
        baseline_collection_name="papers-baseline",
        corrupted_collection_name="papers-corrupted",
        repaired_collection_name="papers-repaired",
        source_api="Crossref REST API",
        source_query="test query",
        source_filter="has-abstract:true",
        max_results=5,
        top_k=4,
        freshness_threshold_days=180,
        crossref_base_url="https://api.crossref.org/works",
        crossref_mailto="test@example.com",
        crossref_timeout=10,
        crossref_max_retries=3,
        refresh_source=False,
        refresh_test_set=False,
        paths=paths,
    )
    defaults.update(overrides)
    return Settings(**defaults)


@patch("ingestion.crossref.requests.get")
def test_no_fetch_mid_run(mock_get, tmp_path: Path):
    """Ensure that if refresh_source is False and cache is missing, it raises an error."""
    settings = _make_settings(tmp_path, refresh_source=False)
    
    # Assert raw_records_json doesn't exist
    assert not settings.paths.raw_records_json.exists()
    
    with pytest.raises(RuntimeError) as exc_info:
        fetch_source_records(settings)
        
    assert "Frozen snapshot not found" in str(exc_info.value)
    assert "Live fetch is disabled" in str(exc_info.value)
    
    # Assert no HTTP call was made
    mock_get.assert_not_called()
