from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from observability.audit import write_recovery_checkpoint


def _answer() -> dict:
    return {
        "id": "q01-authors",
        "question_type": "authors",
        "question": "Who authored the paper?",
        "ground_truth": "A. Author",
        "ground_truth_doc_ids": ["10.1234/example"],
        "answer": "A. Author",
        "retrieved_doc_ids": ["10.1234/example"],
        "retrieval_hit": True,
        "token_f1": 1.0,
        "judge": {"score": 5, "correct": True, "reasoning": "Exact match."},
    }


def _metrics() -> dict:
    return {
        "samples": 1,
        "retrieval_hit_rate": 1.0,
        "mean_token_f1": 1.0,
        "judge_accuracy": 1.0,
        "mean_judge_score": 5.0,
        "test_set_audit": {"sha256": "fixed-test-sha"},
    }


def _quality() -> dict:
    return {
        "status": "pass",
        "signals": {
            "row_count": 1,
            "null_paper_id_rows": 0,
            "null_title_rows": 0,
            "null_summary_rows": 0,
            "duplicate_paper_id_rows": 0,
            "duplicate_record_rows": 0,
            "short_summary_rows": 0,
            "stale_rows": 0,
            "max_age_days": 10,
        },
    }


def _freshness() -> dict:
    return {
        "total_rows": 1,
        "stale_rows": 0,
        "max_age_days": 10,
        "latest_published": "2026-08-01",
        "oldest_published": "2026-08-01",
        "is_fresh": True,
    }


def _write_checkpoint(output_path: Path, corrupted_freshness: dict) -> dict:
    answer = _answer()
    metrics = _metrics()
    quality = _quality()
    freshness = _freshness()
    return write_recovery_checkpoint(
        output_path=output_path,
        baseline_metrics=deepcopy(metrics),
        corrupted_metrics=deepcopy(metrics),
        repaired_metrics=deepcopy(metrics),
        baseline_answers=[deepcopy(answer)],
        corrupted_answers=[deepcopy(answer)],
        repaired_answers=[deepcopy(answer)],
        baseline_quality=deepcopy(quality),
        corrupted_quality=deepcopy(quality),
        repaired_quality=deepcopy(quality),
        baseline_freshness=deepcopy(freshness),
        corrupted_freshness=corrupted_freshness,
        repaired_freshness=deepcopy(freshness),
        repaired_index_audit={"status": "pass"},
    )


def test_recovery_checkpoint_accepts_aligned_quality_and_freshness(tmp_path: Path):
    output_path = tmp_path / "recovery_checkpoint.json"

    checkpoint = _write_checkpoint(output_path, deepcopy(_freshness()))

    assert checkpoint["recovery_complete"] is True
    assert checkpoint["unrecovered_metrics"] == []
    assert checkpoint["unrecovered_signals"] == []
    assert output_path.is_file()


@pytest.mark.parametrize(
    ("freshness_field", "invalid_value", "quality_field"),
    [
        ("total_rows", 2, "row_count"),
        ("stale_rows", 1, "stale_rows"),
        ("max_age_days", 11, "max_age_days"),
    ],
)
def test_recovery_checkpoint_rejects_quality_freshness_mismatch(
    tmp_path: Path,
    freshness_field: str,
    invalid_value: int,
    quality_field: str,
):
    output_path = tmp_path / "recovery_checkpoint.json"
    corrupted_freshness = deepcopy(_freshness())
    corrupted_freshness[freshness_field] = invalid_value

    with pytest.raises(ValueError, match=rf"corrupted quality {quality_field}"):
        _write_checkpoint(output_path, corrupted_freshness)

    assert not output_path.exists()
