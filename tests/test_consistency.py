"""Test that paper_id is consistently propagated through the pipeline without re-derivation."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

from core.config import Settings
from ingestion.cleaning import build_clean_dataframe
from ingestion.crossref import parse_crossref_payload
from retrieval.index import LocalEmbeddingIndex


def test_paper_id_consistency(tmp_path: Path):
    """Verify that paper_id is identical from raw parsing to index build."""
    
    # 1. Start with a raw payload containing mixed-case DOIs and URL prefixes
    raw_payload = {
        "message": {
            "items": [
                {
                    "DOI": "https://doi.org/10.1234/aBcD-EfgH",
                    "title": ["Test Paper"],
                    "abstract": "Test abstract",
                    "published": {"date-parts": [[2024, 1, 1]]},
                },
                {
                    "DOI": "10.5678/IxY-z",
                    "title": ["Test Paper 2"],
                    "abstract": "Test abstract 2",
                    "published": {"date-parts": [[2024, 2, 2]]},
                }
            ]
        }
    }
    
    # 2. Parse into PaperRecord
    records = parse_crossref_payload(raw_payload)
    
    assert len(records) == 2
    
    # Expected normalized IDs
    expected_id_1 = "10.1234/abcd-efgh"
    expected_id_2 = "10.5678/ixy-z"
    
    assert records[0].paper_id == expected_id_1
    assert records[1].paper_id == expected_id_2
    
    # 3. Pass through the cleaning pipeline
    df = build_clean_dataframe(records, run_date=datetime(2024, 5, 1))
    
    # Verify the DataFrame maintains the exact same IDs
    df_ids = df["paper_id"].tolist()
    # Note: df is sorted by published descending by default in cleaning.py
    # So record 2 (published 2024-02-02) should be first, record 1 (2024-01-01) second
    assert expected_id_1 in df_ids
    assert expected_id_2 in df_ids
    
    # 4. Pass through index building
    settings = MagicMock(spec=Settings)
    settings.embedding_model = "sentence-transformers/all-MiniLM-L6-v2"
    settings.baseline_collection_name = "test-collection"
    settings.paths = MagicMock()
    settings.paths.chroma_dir = tmp_path / "chroma"
    settings.paths.embeddings_json = tmp_path / "embeddings.json"
    
    # We mock the embedding model to avoid downloading weights during test
    with patch("retrieval.index.MiniLMEmbeddings") as mock_embeddings:
        mock_instance = mock_embeddings.return_value
        mock_instance.embed_documents.return_value = [[0.0] * 384, [0.0] * 384]
        
        index = LocalEmbeddingIndex.build(df, settings=settings)
    
    # 5. Verify the documents in the index have the exact same IDs
    assert len(index.documents) == 2
    index_ids = [doc["paper_id"] for doc in index.documents]
    assert expected_id_1 in index_ids
    assert expected_id_2 in index_ids
    
    # Verify metadata also has the exact same IDs
    index_metadata_ids = [doc["metadata"]["paper_id"] for doc in index.documents]
    assert expected_id_1 in index_metadata_ids
    assert expected_id_2 in index_metadata_ids

    # 6. Verify idempotency: re-ingesting the exact same ID doesn't change it
    raw_payload_2 = {
        "message": {
            "items": [
                {
                    "DOI": "10.1234/abcd-efgh",  # Already normalized form
                    "title": ["Test Paper"],
                    "abstract": "Test abstract",
                }
            ]
        }
    }
    records_2 = parse_crossref_payload(raw_payload_2)
    assert records_2[0].paper_id == expected_id_1
