from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from core.utils import write_text


_CORE_METRICS = (
    "samples",
    "retrieval_hit_rate",
    "mean_token_f1",
    "judge_accuracy",
    "mean_judge_score",
)


def _display(value: Any) -> str:
    if value is None:
        return "N/A"
    if isinstance(value, bool):
        return "PASS" if value else "FAIL"
    if isinstance(value, float):
        return f"{value:.4f}"
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value).replace("|", "\\|").replace("\n", " ")


def _metric_rows(metrics: dict[str, Any]) -> list[str]:
    rows = [f"| `{name}` | {_display(metrics.get(name))} |" for name in _CORE_METRICS]
    rows.append(f"| `ragas` | {_display(metrics.get('ragas', 'N/A'))} |")
    return rows


def _quality_rows(quality: dict[str, Any]) -> list[str]:
    rows: list[str] = []
    for item in quality.get("checks", []):
        rows.append(
            "| `{}` | {} | {} | {} | {} |".format(
                _display(item.get("name")),
                _display(item.get("dimension")),
                _display(bool(item.get("passed"))),
                _display(item.get("observed")),
                _display(item.get("expected")),
            )
        )
    if not rows:
        rows.append("| N/A | N/A | N/A | N/A | No check details supplied |")
    return rows


def _quality_state(quality: dict[str, Any]) -> str:
    if "status" in quality:
        return str(quality["status"]).upper()
    if "passed" in quality:
        return "PASS" if quality["passed"] else "FAIL"
    if "success" in quality:
        return "PASS" if quality["success"] else "FAIL"
    return "UNKNOWN"


def _numeric_delta(after: dict[str, Any], before: dict[str, Any], metric: str) -> float | None:
    left, right = after.get(metric), before.get(metric)
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return float(left) - float(right)
    return None


def _delta_display(delta: float | None) -> str:
    return "N/A" if delta is None else f"{delta:+.4f}"


def generate_phase1_report(
    report_path,
    source_summary: dict[str, Any],
    metrics: dict[str, Any],
    quality: dict[str, Any],
    freshness: dict[str, Any],
) -> None:
    """Write a baseline report whose values come only from pipeline artifacts."""
    source_rows = [f"| `{key}` | {_display(value)} |" for key, value in sorted(source_summary.items())]
    if not source_rows:
        source_rows = ["| N/A | No source summary supplied |"]

    artifact_rows = [
        "| Raw response and parsed records | `data/raw/` |",
        "| Clean CSV and JSON | `data/clean/` |",
        "| Embedding manifest and Chroma collection | `data/embeddings/`, `data/chroma/` |",
        "| Fixed evaluation set | `data/eval/test_set.json` |",
        "| Baseline metrics and per-question answers | `data/results/baseline_metrics.json`, `data/results/baseline_answers.json` |",
        "| Quality and freshness evidence | `data/quality/` |",
        "| This baseline report | `data/reports/phase1_report.md` |",
    ]
    lines = [
        "# Phase 1 — Baseline Data and RAG Report",
        "",
        "All values below are rendered from the source, evaluation, quality, and freshness payloads passed by the baseline pipeline.",
        "",
        "## Source and lineage",
        "",
        "| Field | Value |",
        "| --- | --- |",
        *source_rows,
        "",
        "## Required baseline artifacts",
        "",
        "| Artifact | Expected path |",
        "| --- | --- |",
        *artifact_rows,
        "",
        "## RAG evaluation",
        "",
        "| Metric | Value |",
        "| --- | ---: |",
        *_metric_rows(metrics),
        "",
        "`retrieval_hit_rate` checks whether a retrieved document ID occurs in the sample's clean `ground_truth_doc_ids`; answer metrics compare the returned answer with ground truth derived from that same clean row.",
        "",
        "## Data quality",
        "",
        f"Overall status: **{_quality_state(quality)}** ({_display(quality.get('check_summary', {}))})",
        "",
        "| Check | Dimension | Result | Observed | Expected |",
        "| --- | --- | --- | ---: | --- |",
        *_quality_rows(quality),
        "",
        "## Freshness",
        "",
        "| Signal | Value |",
        "| --- | --- |",
        f"| Timestamp source | {_display(freshness.get('timestamp_source'))} |",
        f"| Observation time | {_display(freshness.get('generated_at'))} |",
        f"| Threshold (days) | {_display(freshness.get('freshness_threshold_days'))} |",
        f"| Latest publication | {_display(freshness.get('latest_published'))} |",
        f"| Oldest publication | {_display(freshness.get('oldest_published'))} |",
        f"| Stale rows | {_display(freshness.get('stale_rows'))} |",
        f"| Invalid timestamps | {_display(freshness.get('invalid_timestamp_rows'))} |",
        f"| Total rows | {_display(freshness.get('total_rows'))} |",
        f"| Fresh | {_display(freshness.get('is_fresh'))} |",
        "",
        "## Baseline interpretation",
        "",
        "This report establishes the clean-data control. The same frozen evaluation set must be reused for corrupted and repaired indexes; otherwise metric changes cannot be attributed to the data state.",
        "",
    ]
    write_text(Path(report_path), "\n".join(lines))


def generate_corruption_report(
    report_path,
    baseline_metrics: dict[str, Any],
    corrupted_metrics: dict[str, Any],
    repaired_metrics: dict[str, Any],
    corrupted_quality: dict[str, Any],
    repaired_quality: dict[str, Any],
    corrupted_freshness: dict[str, Any],
    repaired_freshness: dict[str, Any],
) -> None:
    """Compare all three RAG states and make evidence chains explicit."""
    comparison_rows: list[str] = []
    degraded: list[str] = []
    recovered: list[str] = []
    for metric in _CORE_METRICS:
        corrupt_delta = _numeric_delta(corrupted_metrics, baseline_metrics, metric)
        repair_delta = _numeric_delta(repaired_metrics, corrupted_metrics, metric)
        comparison_rows.append(
            "| `{}` | {} | {} | {} | {} | {} |".format(
                metric,
                _display(baseline_metrics.get(metric)),
                _display(corrupted_metrics.get(metric)),
                _display(repaired_metrics.get(metric)),
                _delta_display(corrupt_delta),
                _delta_display(repair_delta),
            )
        )
        if metric != "samples" and corrupt_delta is not None and corrupt_delta < 0:
            degraded.append(f"`{metric}` ({corrupt_delta:+.4f})")
        if metric != "samples" and repair_delta is not None and repair_delta > 0:
            recovered.append(f"`{metric}` ({repair_delta:+.4f})")

    corrupted_signals = corrupted_quality.get("signals", {})
    repaired_signals = repaired_quality.get("signals", {})
    signal_names = (
        "row_count",
        "null_paper_id_rows",
        "null_title_rows",
        "null_summary_rows",
        "duplicate_paper_id_rows",
        "short_summary_rows",
        "stale_rows",
        "max_age_days",
    )
    signal_rows = [
        f"| `{name}` | {_display(corrupted_signals.get(name))} | {_display(repaired_signals.get(name))} |"
        for name in signal_names
    ]

    degraded_text = ", ".join(degraded) if degraded else "no core RAG metric decreased"
    recovered_text = ", ".join(recovered) if recovered else "no core RAG metric increased after repair"
    artifact_rows = [
        "| Frozen evaluation set | `data/eval/test_set.json` |",
        "| Corrupted/repaired clean data | `data/clean/papers_clean_corrupted.*`, `data/clean/papers_clean_repaired.*` |",
        "| Corrupted/repaired embedding manifests | `data/embeddings/papers_embeddings_corrupted.json`, `data/embeddings/papers_embeddings_repaired.json` |",
        "| Corruption audit log | `data/results/corruption_log.json` |",
        "| Three metric and answer pairs | `data/results/*_metrics.json`, `data/results/*_answers.json` |",
        "| Quality/freshness evidence | `data/quality/` |",
        "| Comparison report | `data/reports/corruption_report.md` |",
    ]
    lines = [
        "# Corruption Impact and Repair Report",
        "",
        "The baseline, corrupted, and repaired values must come from runs over the same fixed evaluation set. Deltas are computed directly from the supplied metric artifacts.",
        "",
        "## Required corruption-flow artifacts",
        "",
        "| Artifact | Expected path |",
        "| --- | --- |",
        *artifact_rows,
        "",
        "## RAG metric comparison",
        "",
        "| Metric | Baseline | Corrupted | Repaired | Corruption Δ | Repair Δ |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
        *comparison_rows,
        "",
        "Corruption Δ = corrupted − baseline; Repair Δ = repaired − corrupted. For quality metrics, a negative corruption delta is degradation and a positive repair delta is recovery.",
        "",
        "## Quality signal comparison",
        "",
        f"Corrupted quality status: **{_quality_state(corrupted_quality)}**  ",
        f"Repaired quality status: **{_quality_state(repaired_quality)}**",
        "",
        "| Signal | Corrupted | Repaired |",
        "| --- | ---: | ---: |",
        *signal_rows,
        "",
        "## Freshness comparison",
        "",
        "| Signal | Corrupted | Repaired |",
        "| --- | ---: | ---: |",
        f"| Total rows | {_display(corrupted_freshness.get('total_rows'))} | {_display(repaired_freshness.get('total_rows'))} |",
        f"| Latest publication | {_display(corrupted_freshness.get('latest_published'))} | {_display(repaired_freshness.get('latest_published'))} |",
        f"| Oldest publication | {_display(corrupted_freshness.get('oldest_published'))} | {_display(repaired_freshness.get('oldest_published'))} |",
        f"| Stale rows | {_display(corrupted_freshness.get('stale_rows'))} | {_display(repaired_freshness.get('stale_rows'))} |",
        f"| Max age (days) | {_display(corrupted_freshness.get('max_age_days'))} | {_display(repaired_freshness.get('max_age_days'))} |",
        f"| Fresh | {_display(corrupted_freshness.get('is_fresh'))} | {_display(repaired_freshness.get('is_fresh'))} |",
        "",
        "Timestamp source: Crossref `published` in each cleaned artifact; observation time and threshold are recorded in the corresponding freshness JSON.",
        "",
        "## Evidence chains",
        "",
        f"1. Corrupted data → quality status **{_quality_state(corrupted_quality)}**, stale rows {_display(corrupted_freshness.get('stale_rows'))} → {degraded_text}.",
        f"2. Repair from raw data → quality status **{_quality_state(repaired_quality)}**, stale rows {_display(repaired_freshness.get('stale_rows'))} → {recovered_text}.",
        "",
        "If the report says that no metric moved, the artifacts do not support a degradation/recovery claim; inspect per-question answers and corruption coverage instead of asserting impact without evidence.",
        "",
    ]
    write_text(Path(report_path), "\n".join(lines))
