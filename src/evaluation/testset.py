from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pandas as pd

from core.utils import first_sentence, normalize_whitespace, read_json, write_json


_REQUIRED_COLUMNS = {
    "paper_id",
    "title",
    "summary",
    "authors_joined",
    "published",
    "categories_joined",
    "age_days",
    "text_for_embedding",
}
_MINIMUM_DOCUMENTS = 4
_QUESTION_TYPES = {"summary", "authors", "date", "categories"}
_TEST_SET_FIELDS = {
    "id",
    "question_type",
    "question",
    "ground_truth",
    "ground_truth_doc_ids",
}


def _blank_mask(series: pd.Series) -> pd.Series:
    return series.isna() | series.astype("string").str.strip().eq("").fillna(True)


def _required_text(row: pd.Series, column: str) -> str:
    """Return a normalized scalar value, rejecting null/blank ground truth."""
    value = row[column]
    if pd.isna(value):
        raise ValueError(f"Selected paper {row.get('paper_id', '<unknown>')!r} has null {column!r}.")
    normalized = normalize_whitespace(str(value))
    if not normalized:
        raise ValueError(f"Selected paper {row.get('paper_id', '<unknown>')!r} has blank {column!r}.")
    return normalized


def _assert_stable_paper_ids(df: pd.DataFrame) -> None:
    """Fail before writing an evaluation set when clean IDs are not stable."""
    missing_count = int(_blank_mask(df["paper_id"]).sum())
    if missing_count:
        raise ValueError(f"paper_id is not stable: {missing_count} cleaned rows have a missing ID.")

    normalized_ids = df["paper_id"].astype("string").str.strip().str.lower()
    duplicate_mask = normalized_ids.duplicated(keep=False)
    if duplicate_mask.any():
        duplicate_ids = sorted(set(normalized_ids[duplicate_mask].astype(str)))
        raise ValueError(
            "paper_id is not stable: duplicate cleaned IDs found: "
            + ", ".join(duplicate_ids[:10])
        )


def audit_test_set(
    test_set: list[dict[str, Any]],
    available_doc_ids: list[str] | set[str] | None = None,
    preview_rows: int = 3,
    require_index_coverage: bool = True,
) -> dict[str, Any]:
    """Validate test-set schema and optionally prove index document coverage."""
    if not isinstance(test_set, list) or not test_set:
        raise ValueError("The evaluation test set must be a non-empty JSON list.")

    sample_ids: list[str] = []
    ground_truth_ids: set[str] = set()
    question_types: set[str] = set()
    for position, sample in enumerate(test_set):
        if not isinstance(sample, dict):
            raise ValueError(f"Test-set item {position} must be a JSON object.")
        missing_fields = sorted(_TEST_SET_FIELDS.difference(sample))
        if missing_fields:
            raise ValueError(
                f"Test-set item {position} is missing fields: {', '.join(missing_fields)}"
            )

        for field in ("id", "question_type", "question", "ground_truth"):
            value = sample[field]
            if not isinstance(value, str) or not normalize_whitespace(value):
                raise ValueError(f"Test-set item {position} has invalid {field!r}.")
        if sample["question_type"] not in _QUESTION_TYPES:
            raise ValueError(
                f"Test-set item {position} has unsupported question_type "
                f"{sample['question_type']!r}."
            )

        doc_ids = sample["ground_truth_doc_ids"]
        if not isinstance(doc_ids, list) or not doc_ids:
            raise ValueError(
                f"Test-set item {position} must have at least one ground_truth_doc_id."
            )
        if any(not isinstance(doc_id, str) or not doc_id.strip() for doc_id in doc_ids):
            raise ValueError(f"Test-set item {position} contains an invalid ground_truth_doc_id.")

        sample_ids.append(sample["id"])
        question_types.add(sample["question_type"])
        ground_truth_ids.update(doc_ids)

    duplicate_sample_ids = sorted(
        {sample_id for sample_id in sample_ids if sample_ids.count(sample_id) > 1}
    )
    if duplicate_sample_ids:
        raise ValueError(f"Duplicate test-set IDs found: {', '.join(duplicate_sample_ids)}")

    missing_from_index: list[str] = []
    index_document_count: int | None = None
    if available_doc_ids is not None:
        index_ids = {str(doc_id) for doc_id in available_doc_ids}
        index_document_count = len(index_ids)
        missing_from_index = sorted(ground_truth_ids.difference(index_ids))
        if missing_from_index and require_index_coverage:
            raise ValueError(
                "Ground-truth document IDs are missing from the index: "
                + ", ".join(missing_from_index)
            )

    canonical = json.dumps(
        test_set,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    preview = [
        {
            "id": item["id"],
            "question_type": item["question_type"],
            "question": item["question"],
            "ground_truth": item["ground_truth"],
            "ground_truth_doc_ids": item["ground_truth_doc_ids"],
        }
        for item in test_set[: max(0, preview_rows)]
    ]
    return {
        "status": "pass" if not missing_from_index else "warning",
        "samples": len(test_set),
        "question_types": sorted(question_types),
        "unique_ground_truth_doc_ids": len(ground_truth_ids),
        "ground_truth_doc_ids": sorted(ground_truth_ids),
        "index_document_count": index_document_count,
        "missing_ground_truth_doc_ids": missing_from_index,
        "all_ground_truth_ids_in_index": available_doc_ids is not None and not missing_from_index,
        "index_coverage_required": require_index_coverage,
        "sha256": hashlib.sha256(canonical).hexdigest(),
        "preview": preview,
    }


def load_frozen_test_set(
    path: Path,
    available_doc_ids: list[str] | set[str] | None = None,
    require_index_coverage: bool = True,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Read the persisted test set and validate it before evaluation."""
    test_set = read_json(Path(path))
    audit = audit_test_set(
        test_set,
        available_doc_ids=available_doc_ids,
        require_index_coverage=require_index_coverage,
    )
    audit["path"] = str(Path(path))
    return test_set, audit


def build_test_set(df: pd.DataFrame, output_path) -> list[dict[str, Any]]:
    """Build a deterministic, auditable evaluation set from cleaned papers.

    Four recent papers are used so every question is backed by a real cleaned
    row. The quoted lookup value is the clean ``paper_id`` rather than a
    generated identifier, while the title keeps semantic retrieval meaningful.
    """
    missing_columns = sorted(_REQUIRED_COLUMNS.difference(df.columns))
    if missing_columns:
        raise ValueError(f"Clean dataframe is missing required columns: {', '.join(missing_columns)}")
    _assert_stable_paper_ids(df)

    candidates = df.copy()
    eligible = pd.Series(True, index=candidates.index)
    for column in _REQUIRED_COLUMNS:
        eligible &= ~_blank_mask(candidates[column])

    candidates["_published_sort"] = pd.to_datetime(candidates["published"], errors="coerce", utc=True)
    eligible &= candidates["_published_sort"].notna()
    candidates = candidates.loc[eligible].copy()
    if len(candidates) < _MINIMUM_DOCUMENTS:
        raise ValueError(
            f"At least {_MINIMUM_DOCUMENTS} complete cleaned documents are required; "
            f"received {len(candidates)} eligible rows out of {len(df)}."
        )

    candidates = candidates.sort_values(
        by=["_published_sort", "paper_id"],
        ascending=[False, True],
        na_position="last",
        kind="stable",
    )
    selected = candidates.head(_MINIMUM_DOCUMENTS)

    test_set: list[dict[str, Any]] = []
    for row_number, (_, row) in enumerate(selected.iterrows(), start=1):
        paper_id = _required_text(row, "paper_id")
        title = _required_text(row, "title")
        summary = first_sentence(_required_text(row, "summary"))
        authors = _required_text(row, "authors_joined")
        published = _required_text(row, "published")
        categories = _required_text(row, "categories_joined")

        # qa.py recognizes the quoted value through LocalEmbeddingIndex.lookup;
        # using the clean paper_id also works when a title contains apostrophes.
        label = f"paper '{paper_id}' titled \"{title}\""
        questions = [
            ("summary", f"What is the main point summarized for {label}?", summary, "summary"),
            ("authors", f"Who authored {label}?", authors, "authors_joined"),
            ("date", f"When was {label} published?", published, "published"),
        ]
        # Crossref often omits `subject`; cleaning.py falls back to the literal
        # "Unknown" for every such record. A categories question built from that
        # fallback would match any document (right or wrong), silently masking
        # retrieval failures in token-F1/judge scoring. Only ask it when the
        # paper actually has real category data.
        raw_categories = row.get("categories")
        if isinstance(raw_categories, list) and raw_categories:
            questions.append(
                (
                    "categories",
                    f"What categories are recorded for {label}?",
                    categories,
                    "categories_joined",
                )
            )
        for question_type, question, ground_truth, ground_truth_field in questions:
            test_set.append(
                {
                    "id": f"q{row_number:02d}-{question_type}",
                    "question_type": question_type,
                    "question": question,
                    "ground_truth": ground_truth,
                    "ground_truth_doc_ids": [paper_id],
                    "ground_truth_source": f"clean.{ground_truth_field}",
                }
            )

    clean_doc_ids = set(df["paper_id"].astype(str))
    audit_test_set(test_set, available_doc_ids=clean_doc_ids)
    output_path = Path(output_path)
    write_json(output_path, test_set)

    # The file on disk is the frozen evaluation contract. Read it back before
    # returning so serialization or partial-write issues cannot reach metrics.
    frozen_test_set, _ = load_frozen_test_set(output_path, available_doc_ids=clean_doc_ids)
    if frozen_test_set != test_set:
        raise RuntimeError(f"Frozen test set did not round-trip cleanly: {output_path}")
    return frozen_test_set
