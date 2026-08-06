from __future__ import annotations

import pandas as pd

from core.config import load_settings
from core.utils import ensure_parent, now_utc, read_json, write_csv
from evaluation.metrics import evaluate_pipeline
from ingestion.cleaning import build_clean_dataframe
from ingestion.corruption import corrupt_clean_dataframe
from ingestion.crossref import load_raw_records
from observability.quality import build_freshness_report, run_data_quality_checks
from observability.reporting import generate_corruption_report
from retrieval.index import LocalEmbeddingIndex


def _write_clean_dataframe(df, csv_path, json_path) -> None:
    write_csv(df, csv_path)
    ensure_parent(json_path)
    json_path.write_text(df.to_json(orient="records", indent=2, force_ascii=True), encoding="utf-8")


def main() -> None:
    settings = load_settings()

    if not settings.paths.baseline_metrics.exists() or not settings.paths.clean_json.exists():
        raise RuntimeError(
            "Baseline artifacts not found. Run script/run_phase1.py successfully before the corruption flow."
        )

    print("== 1/8 Load baseline clean dataset + metrics ==")
    # Read from JSON (not CSV) so list-typed columns (authors/categories) round-trip correctly.
    baseline_df = pd.read_json(settings.paths.clean_json)
    baseline_metrics = read_json(settings.paths.baseline_metrics)
    print(f"  baseline records={len(baseline_df)} retrieval_hit_rate={baseline_metrics.get('retrieval_hit_rate')}")

    print("== 2/8 Corrupt clean dataset ==")
    corrupted_df = corrupt_clean_dataframe(baseline_df, settings.paths.corruption_log)
    _write_clean_dataframe(corrupted_df, settings.paths.corrupted_clean_csv, settings.paths.corrupted_clean_json)
    print(f"  corrupted records={len(corrupted_df)} -> {settings.paths.corrupted_clean_csv}")
    print(f"  corruption log -> {settings.paths.corruption_log}")

    print("== 3/8 Rebuild index (corrupted) ==")
    corrupted_index = LocalEmbeddingIndex.build(
        corrupted_df, settings, embeddings_output_path=settings.paths.corrupted_embeddings_json
    )
    print(f"  collection={corrupted_index.collection_name} documents={len(corrupted_index.documents)}")

    print("== 4/8 Evaluate corrupted (same test set as baseline) ==")
    corrupted_bundle = evaluate_pipeline(
        settings=settings,
        index=corrupted_index,
        test_set_path=settings.paths.eval_testset,
        metrics_output_path=settings.paths.corrupted_metrics,
        answers_output_path=settings.paths.corrupted_answers,
    )
    print(f"  retrieval_hit_rate={corrupted_bundle.summary['retrieval_hit_rate']:.3f}")

    print("== 5/8 Quality/freshness (corrupted) ==")
    corrupted_quality = run_data_quality_checks(corrupted_df, settings, "corrupted")
    corrupted_freshness = build_freshness_report(
        corrupted_df, settings, settings.paths.quality_dir / "freshness_report_corrupted.json"
    )

    print("== 6/8 Repair from raw source ==")
    raw_records = load_raw_records(settings.paths.raw_records_json)
    repaired_df = build_clean_dataframe(raw_records, now_utc())
    _write_clean_dataframe(repaired_df, settings.paths.repaired_clean_csv, settings.paths.repaired_clean_json)
    print(f"  repaired records={len(repaired_df)} -> {settings.paths.repaired_clean_csv}")

    print("== 7/8 Rebuild index (repaired) + evaluate ==")
    repaired_index = LocalEmbeddingIndex.build(
        repaired_df, settings, embeddings_output_path=settings.paths.repaired_embeddings_json
    )
    repaired_bundle = evaluate_pipeline(
        settings=settings,
        index=repaired_index,
        test_set_path=settings.paths.eval_testset,
        metrics_output_path=settings.paths.repaired_metrics,
        answers_output_path=settings.paths.repaired_answers,
    )
    print(f"  retrieval_hit_rate={repaired_bundle.summary['retrieval_hit_rate']:.3f}")

    repaired_quality = run_data_quality_checks(repaired_df, settings, "repaired")
    repaired_freshness = build_freshness_report(
        repaired_df, settings, settings.paths.quality_dir / "freshness_report_repaired.json"
    )

    print("== 8/8 Comparison report ==")
    generate_corruption_report(
        report_path=settings.paths.comparison_report,
        baseline_metrics=baseline_metrics,
        corrupted_metrics=corrupted_bundle.summary,
        repaired_metrics=repaired_bundle.summary,
        corrupted_quality=corrupted_quality,
        repaired_quality=repaired_quality,
        corrupted_freshness=corrupted_freshness,
        repaired_freshness=repaired_freshness,
    )
    print(f"  report -> {settings.paths.comparison_report}")

    print("Corruption/repair/comparison flow complete.")
