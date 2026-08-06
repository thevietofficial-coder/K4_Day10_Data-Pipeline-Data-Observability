"""Tests for ingestion.crossref — no network calls, all HTTP is mocked."""
from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import requests

from ingestion.crossref import (
    PaperRecord,
    _RetryableHTTPError,
    _do_fetch,
    fetch_source_records,
    load_raw_records,
    normalize_doi,
    parse_crossref_payload,
    parse_date_parts,
)


# ---------------------------------------------------------------------------
# Fixtures — realistic Crossref payloads
# ---------------------------------------------------------------------------

FULL_ITEM: dict = {
    "DOI": "10.1234/test-paper-001",
    "title": ["A Survey on Agentic RAG Systems"],
    "abstract": "<jats:p>This paper surveys agentic RAG architectures for LLMs.</jats:p>",
    "author": [
        {"given": "Alice", "family": "Smith"},
        {"given": "Bob", "family": "Jones"},
    ],
    "subject": ["Computer Science", "Artificial Intelligence"],
    "published-print": {"date-parts": [[2024, 3, 15]]},
    "deposited": {"date-parts": [[2024, 4, 1]]},
    "link": [
        {"content-type": "application/pdf", "URL": "https://example.com/paper.pdf"},
        {"content-type": "text/html", "URL": "https://example.com/paper.html"},
    ],
    "funder": [
        {"name": "National Science Foundation"},
    ],
}

PARTIAL_ITEM: dict = {
    "DOI": "10.5678/PARTIAL",
    "title": ["Partial Record"],
    # no abstract
    # no author
    "subject": [],
    "published": {"date-parts": [[2023]]},  # year-only
    # no deposited
    # no link
    # no funder
}

NO_DOI_ITEM: dict = {
    "title": ["Record Without DOI"],
    "abstract": "Should be skipped.",
}

FULL_PAYLOAD: dict = {
    "status": "ok",
    "message": {
        "total-results": 2,
        "items": [FULL_ITEM, PARTIAL_ITEM],
    },
}


# ---------------------------------------------------------------------------
# normalize_doi
# ---------------------------------------------------------------------------

class TestNormalizeDoi:
    def test_strips_https_doi_org(self):
        assert normalize_doi("https://doi.org/10.1234/Abc") == "10.1234/abc"

    def test_strips_http_doi_org(self):
        assert normalize_doi("http://doi.org/10.1234/Abc") == "10.1234/abc"

    def test_strips_dx_doi_org(self):
        assert normalize_doi("http://dx.doi.org/10.1234/XYZ") == "10.1234/xyz"

    def test_plain_doi(self):
        assert normalize_doi("10.1234/Test") == "10.1234/test"

    def test_strips_whitespace(self):
        assert normalize_doi("  10.1234/Test  ") == "10.1234/test"


# ---------------------------------------------------------------------------
# parse_date_parts
# ---------------------------------------------------------------------------

class TestParseDateParts:
    def test_full_date(self):
        assert parse_date_parts({"date-parts": [[2024, 3, 15]]}) == "2024-03-15"

    def test_year_month(self):
        assert parse_date_parts({"date-parts": [[2024, 7]]}) == "2024-07-01"

    def test_year_only(self):
        assert parse_date_parts({"date-parts": [[2023]]}) == "2023-01-01"

    def test_none(self):
        assert parse_date_parts(None) == ""

    def test_empty_dict(self):
        assert parse_date_parts({}) == ""

    def test_empty_date_parts(self):
        assert parse_date_parts({"date-parts": []}) == ""

    def test_empty_inner_list(self):
        assert parse_date_parts({"date-parts": [[]]}) == ""


# ---------------------------------------------------------------------------
# parse_crossref_payload
# ---------------------------------------------------------------------------

class TestParseCrossrefPayload:
    def test_full_payload(self):
        records = parse_crossref_payload(FULL_PAYLOAD)
        assert len(records) == 2

        r = records[0]
        assert r.paper_id == "10.1234/test-paper-001"
        assert r.title == "A Survey on Agentic RAG Systems"
        assert "agentic RAG architectures" in r.summary
        assert "<jats:p>" not in r.summary  # HTML stripped
        assert r.authors == ["Alice Smith", "Bob Jones"]
        assert r.categories == ["Computer Science", "Artificial Intelligence"]
        assert r.primary_category == "Computer Science"
        assert r.published == "2024-03-15"
        assert r.updated == "2024-04-01"
        assert r.abs_url == "https://doi.org/10.1234/test-paper-001"
        assert r.pdf_url == "https://example.com/paper.pdf"
        assert "National Science Foundation" in r.comment

    def test_partial_payload(self):
        payload = {"message": {"items": [PARTIAL_ITEM]}}
        records = parse_crossref_payload(payload)
        assert len(records) == 1

        r = records[0]
        assert r.paper_id == "10.5678/partial"
        assert r.title == "Partial Record"
        assert r.summary == ""
        assert r.authors == []
        assert r.categories == []
        assert r.primary_category == ""
        assert r.published == "2023-01-01"  # year-only → defaults
        assert r.updated == ""
        assert r.pdf_url == ""
        assert r.comment == ""

    def test_skips_missing_doi(self):
        payload = {"message": {"items": [NO_DOI_ITEM, FULL_ITEM]}}
        records = parse_crossref_payload(payload)
        assert len(records) == 1
        assert records[0].paper_id == "10.1234/test-paper-001"

    def test_empty_payload(self):
        assert parse_crossref_payload({}) == []
        assert parse_crossref_payload({"message": {}}) == []
        assert parse_crossref_payload({"message": {"items": []}}) == []


# ---------------------------------------------------------------------------
# load_raw_records — round-trip
# ---------------------------------------------------------------------------

class TestLoadRawRecords:
    def test_round_trip(self, tmp_path: Path):
        records = parse_crossref_payload(FULL_PAYLOAD)
        out_path = tmp_path / "records.json"
        out_path.write_text(
            json.dumps([asdict(r) for r in records], indent=2, ensure_ascii=True),
            encoding="utf-8",
        )
        loaded = load_raw_records(out_path)
        assert len(loaded) == len(records)
        for original, reloaded in zip(records, loaded):
            assert asdict(original) == asdict(reloaded)


# ---------------------------------------------------------------------------
# fetch_source_records — retry logic (mocked HTTP)
# ---------------------------------------------------------------------------

def _make_settings(tmp_path: Path, **overrides):
    """Build a minimal Settings-like object for testing fetch_source_records."""
    from core.config import Paths, Settings

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
        refresh_source=True,
        refresh_test_set=False,
        paths=paths,
    )
    defaults.update(overrides)
    return Settings(**defaults)


def _mock_response(status_code: int, payload: dict | None = None, headers: dict | None = None):
    """Create a mock requests.Response."""
    resp = MagicMock(spec=["status_code", "headers", "content", "json", "raise_for_status"])
    resp.status_code = status_code
    resp.headers = headers or {}
    if payload is not None:
        body = json.dumps(payload).encode()
        resp.content = body
        resp.json.return_value = payload
    else:
        resp.content = b""
        resp.json.return_value = {}
    if status_code >= 400:
        resp.raise_for_status.side_effect = requests.HTTPError(f"HTTP {status_code}")
    else:
        resp.raise_for_status.return_value = None
    return resp


class TestFetchRetry:
    @patch("ingestion.crossref.requests.get")
    def test_retry_429_then_success(self, mock_get, tmp_path: Path):
        """Two 429 responses followed by a 200 should succeed."""
        mock_get.side_effect = [
            _mock_response(429, headers={"Retry-After": "0"}),
            _mock_response(429, headers={"Retry-After": "0"}),
            _mock_response(200, payload=FULL_PAYLOAD),
        ]
        settings = _make_settings(tmp_path, crossref_max_retries=5)
        records = fetch_source_records(settings)
        assert len(records) == 2
        assert settings.paths.raw_api_response.exists()
        assert settings.paths.raw_records_json.exists()

    @patch("ingestion.crossref.requests.get")
    def test_retry_503_then_success(self, mock_get, tmp_path: Path):
        """One 503 then a 200 should succeed."""
        mock_get.side_effect = [
            _mock_response(503),
            _mock_response(200, payload=FULL_PAYLOAD),
        ]
        settings = _make_settings(tmp_path, crossref_max_retries=3)
        records = fetch_source_records(settings)
        assert len(records) == 2

    @patch("ingestion.crossref.requests.get")
    def test_retries_exhausted(self, mock_get, tmp_path: Path):
        """Three 429s with max_retries=3 should raise."""
        mock_get.side_effect = [
            _mock_response(429, headers={"Retry-After": "0"}),
            _mock_response(429, headers={"Retry-After": "0"}),
            _mock_response(429, headers={"Retry-After": "0"}),
        ]
        settings = _make_settings(tmp_path, crossref_max_retries=3)
        with pytest.raises(_RetryableHTTPError):
            fetch_source_records(settings)

    @patch("ingestion.crossref.requests.get")
    def test_uses_cache_when_not_refreshing(self, mock_get, tmp_path: Path):
        """When refresh_source=False and cache exists, no HTTP call is made."""
        settings = _make_settings(tmp_path, refresh_source=False)

        # Pre-populate cache
        records = parse_crossref_payload(FULL_PAYLOAD)
        settings.paths.raw_records_json.parent.mkdir(parents=True, exist_ok=True)
        settings.paths.raw_records_json.write_text(
            json.dumps([asdict(r) for r in records], indent=2, ensure_ascii=True),
            encoding="utf-8",
        )

        loaded = fetch_source_records(settings)
        assert len(loaded) == 2
        mock_get.assert_not_called()

    @patch("ingestion.crossref.requests.get")
    def test_raw_response_persisted_before_parsing(self, mock_get, tmp_path: Path):
        """The raw response bytes must be written to disk before parsing."""
        mock_get.return_value = _mock_response(200, payload=FULL_PAYLOAD)
        settings = _make_settings(tmp_path)
        fetch_source_records(settings)

        raw_bytes = settings.paths.raw_api_response.read_bytes()
        reparsed = json.loads(raw_bytes)
        assert reparsed["message"]["items"][0]["DOI"] == "10.1234/test-paper-001"
