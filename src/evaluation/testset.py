from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from core.utils import first_sentence, normalize_whitespace, write_json


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

    write_json(Path(output_path), test_set)
    return test_set
