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


def _preview(value: Any, limit: int = 180) -> str:
    rendered = _display(value)
    return rendered if len(rendered) <= limit else rendered[: limit - 1] + "…"


def generate_phase1_report(
    report_path,
    source_summary: dict[str, Any],
    metrics: dict[str, Any],
    quality: dict[str, Any],
    freshness: dict[str, Any],
    index_audit: dict[str, Any] | None = None,
    test_set_audit: dict[str, Any] | None = None,
) -> None:
    """Write a CP3-ready baseline report using only supplied artifact values."""
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
    if index_audit is None:
        index_audit_lines = [
            "Index audit was not supplied. CP3 must pass the embedding manifest audit payload; no value is inferred.",
        ]
    else:
        index_audit_lines = [
            "| Signal | Value |",
            "| --- | --- |",
            f"| Status | {_display(index_audit.get('status'))} |",
            f"| Backend/model | {_display(index_audit.get('backend'))} / {_display(index_audit.get('embedding_model'))} |",
            f"| Collection | {_display(index_audit.get('collection_name'))} |",
            f"| Expected collection | {_display(index_audit.get('expected_collection_name'))} |",
            f"| Manifest documents | {_display(index_audit.get('manifest_document_count'))} |",
            f"| Chroma documents | {_display(index_audit.get('collection_document_count'))} |",
            f"| Duplicate document IDs | {_display(index_audit.get('duplicate_document_ids'))} |",
            f"| Missing clean IDs | {_display(index_audit.get('missing_expected_doc_ids'))} |",
            f"| Warnings | {_display(index_audit.get('warnings'))} |",
        ]

    if test_set_audit is None:
        test_set_audit_lines = [
            "Test-set audit was not supplied. CP3 must load and validate the frozen JSON before evaluation.",
        ]
        test_set_preview_lines: list[str] = []
    else:
        test_set_audit_lines = [
            "| Signal | Value |",
            "| --- | --- |",
            f"| Status | {_display(test_set_audit.get('status'))} |",
            f"| Frozen path | {_display(test_set_audit.get('path'))} |",
            f"| SHA-256 | `{_display(test_set_audit.get('sha256'))}` |",
            f"| Samples | {_display(test_set_audit.get('samples'))} |",
            f"| Question types | {_display(test_set_audit.get('question_types'))} |",
            f"| Ground-truth documents | {_display(test_set_audit.get('unique_ground_truth_doc_ids'))} |",
            f"| All IDs present in index | {_display(test_set_audit.get('all_ground_truth_ids_in_index'))} |",
        ]
        preview_rows = test_set_audit.get("preview", [])
        test_set_preview_lines = [
            "",
            "### Persisted-row preview",
            "",
            "| ID | Type | Question | Ground truth | Document IDs |",
            "| --- | --- | --- | --- | --- |",
            *[
                "| `{}` | {} | {} | {} | {} |".format(
                    _display(item.get("id")),
                    _display(item.get("question_type")),
                    _preview(item.get("question")),
                    _preview(item.get("ground_truth")),
                    _display(item.get("ground_truth_doc_ids")),
                )
                for item in preview_rows
            ],
        ]

    quality_signals = quality.get("signals", {})
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
        "## Embedding manifest and collection audit",
        "",
        *index_audit_lines,
        "",
        "## Frozen evaluation-set audit",
        "",
        *test_set_audit_lines,
        *test_set_preview_lines,
        "",
        "## RAG evaluation",
        "",
        "| Metric | Value |",
        "| --- | ---: |",
        *_metric_rows(metrics),
        "",
        "### Metric definitions",
        "",
        "- `retrieval_hit_rate`: mean of the per-question retrieval hit flag. A hit means at least one retrieved `paper_id` occurs in that question's clean `ground_truth_doc_ids`.",
        "- `mean_token_f1`: mean harmonic score of token precision and recall after whitespace normalization and lower-casing. The current implementation uses unique token sets, so it measures lexical overlap rather than semantic equivalence or token order.",
        "- `judge_accuracy`: fraction of answers that the structured LLM judge marks `correct=true`; if the provider is unavailable, the evaluator records a token-F1-based fallback reason in each answer.",
        "- `mean_judge_score`: mean structured judge score on the 1–5 scale.",
        "",
        "## Data quality",
        "",
        f"Overall status: **{_quality_state(quality)}** ({_display(quality.get('check_summary', {}))})",
        "",
        "| Check | Dimension | Result | Observed | Expected |",
        "| --- | --- | --- | ---: | --- |",
        *_quality_rows(quality),
        "",
        "### Baseline comparison signals",
        "",
        "These values are the control signals to compare with corrupted and repaired runs.",
        "",
        "| Signal | Baseline |",
        "| --- | ---: |",
        f"| Row count | {_display(quality_signals.get('row_count'))} |",
        f"| Null paper IDs | {_display(quality_signals.get('null_paper_id_rows'))} |",
        f"| Null titles | {_display(quality_signals.get('null_title_rows'))} |",
        f"| Null summaries | {_display(quality_signals.get('null_summary_rows'))} |",
        f"| Duplicate paper-ID rows | {_display(quality_signals.get('duplicate_paper_id_rows'))} |",
        f"| Duplicate records | {_display(quality_signals.get('duplicate_record_rows'))} |",
        f"| Stale rows | {_display(freshness.get('stale_rows'))} |",
        f"| Maximum age (days) | {_display(freshness.get('max_age_days'))} |",
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


def generate_corrupted_evidence_report(
    report_path,
    checkpoint: dict[str, Any],
) -> None:
    """Render CP5 evidence without attributing unsupported metric changes."""
    metric_rows = []
    for name, baseline in checkpoint.get("baseline_metrics", {}).items():
        corrupted = checkpoint.get("corrupted_metrics", {}).get(name)
        delta = checkpoint.get("metric_deltas", {}).get(name)
        metric_rows.append(
            f"| `{name}` | {_display(baseline)} | {_display(corrupted)} | {_delta_display(delta)} |"
        )

    event_rows = [
        f"| `{name}` | {_display(values.get('events'))} | {_display(values.get('affected_references'))} |"
        for name, values in sorted(checkpoint.get("corruption_events", {}).items())
    ]
    signal_rows = [
        "| `{}` | {} | {} | {} | {} |".format(
            name,
            _display(values.get("baseline")),
            _display(values.get("corrupted")),
            _delta_display(values.get("delta")),
            "changed" if values.get("changed") else "unchanged",
        )
        for name, values in checkpoint.get("signal_comparison", {}).items()
    ]

    worse_cases = checkpoint.get("worse_cases", [])
    if worse_cases:
        case = worse_cases[0]
        case_lines = [
            f"- Sample: `{_display(case.get('id'))}` ({_display(case.get('question_type'))})",
            f"- Ground-truth document IDs: {_display(case.get('ground_truth_doc_ids'))}",
            f"- Retrieval hit: {_display(case.get('baseline_retrieval_hit'))} → {_display(case.get('corrupted_retrieval_hit'))}",
            f"- Token F1: {_display(case.get('baseline_token_f1'))} → {_display(case.get('corrupted_token_f1'))}",
            f"- Judge score: {_display(case.get('baseline_judge_score'))} → {_display(case.get('corrupted_judge_score'))}",
            f"- Corrupted answer: {_display(case.get('corrupted_answer'))}",
            f"- Retrieved IDs: {_display(case.get('corrupted_retrieved_doc_ids'))}",
            f"- Judge reasoning: {_display(case.get('judge_reasoning'))}",
        ]
    else:
        case_lines = ["No per-question degradation was measured."]

    integrity = checkpoint.get("evaluator_integrity", {})
    supported_links = checkpoint.get("supported_links", [])
    unsupported_types = checkpoint.get("corruption_types_without_direct_metric_attribution", [])
    unchanged_signals = checkpoint.get("unchanged_signals", [])
    silent_fallback = "yes" if integrity.get("silent_fallback_detected") else "no"
    lines = [
        "# CP5 — Corrupted Data Evidence Report",
        "",
        f"Frozen test-set SHA-256: `{_display(checkpoint.get('test_set_sha256'))}`",
        "",
        "## Metric comparison",
        "",
        "| Metric | Baseline | Corrupted | Delta |",
        "| --- | ---: | ---: | ---: |",
        *metric_rows,
        "",
        "## Evaluator integrity",
        "",
        f"- Judge mode: `{_display(integrity.get('judge_mode'))}`",
        f"- Recorded fallback judges: {_display(integrity.get('fallback_judges'))}",
        f"- Silent fallback detected: {silent_fallback}",
        "",
        "A fallback is never counted silently: fallback reasoning is stored per answer and counted in the checkpoint.",
        "",
        "## Corruption log summary",
        "",
        "| Type | Log events | Affected references |",
        "| --- | ---: | ---: |",
        *event_rows,
        "",
        "## Quality and freshness signals",
        "",
        "| Signal | Baseline | Corrupted | Delta | State |",
        "| --- | ---: | ---: | ---: | --- |",
        *signal_rows,
        "",
        "## One measured worse case",
        "",
        *case_lines,
        "",
        "## Supported evidence links",
        "",
        *([f"- {item}." for item in supported_links] or ["- No supported link was measured."]),
        "",
        "## Guard against over-claiming",
        "",
        f"Unchanged signals: {_display(unchanged_signals)}.",
        "",
        f"Corruption types without direct per-question metric attribution: {_display(unsupported_types)}.",
        "",
        "These types may have changed data-quality signals, but this run does not isolate their individual causal contribution to an answer metric.",
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
