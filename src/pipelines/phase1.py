from __future__ import annotations

from core.config import load_settings
from core.utils import ensure_parent, now_utc, read_json, write_csv, write_json
from evaluation.metrics import evaluate_pipeline
from evaluation.testset import build_test_set
from ingestion.cleaning import build_clean_dataframe
from ingestion.crossref import fetch_source_records
from observability.quality import build_freshness_report, run_data_quality_checks
from observability.reporting import generate_phase1_report
from retrieval.agent import build_agent, run_agent_question
from retrieval.index import LocalEmbeddingIndex


def _write_clean_dataframe(df, csv_path, json_path) -> None:
    write_csv(df, csv_path)
    ensure_parent(json_path)
    json_path.write_text(df.to_json(orient="records", indent=2, force_ascii=True), encoding="utf-8")


def _demo_agent(settings, index) -> None:
    """Best-effort demo: run a few test-set questions through the agent."""
    try:
        test_set = read_json(settings.paths.eval_testset)
        agent = build_agent(settings, index)
        demo = [
            {"question": item["question"], "answer": run_agent_question(agent, item["question"])}
            for item in test_set[:3]
        ]
        write_json(settings.paths.demo_answers, demo)
        print(f"  Agent demo answers -> {settings.paths.demo_answers}")
    except Exception as exc:  # pragma: no cover - demo is best-effort, must not fail the pipeline
        print(f"  Agent demo skipped: {exc}")


def main() -> None:
    settings = load_settings()

    print("== 1/8 Fetch/load raw records ==")
    records = fetch_source_records(settings)
    print(f"  {len(records)} raw records")

    print("== 2/8 Clean data ==")
    df = build_clean_dataframe(records, now_utc())
    if df.empty:
        raise RuntimeError("Cleaning produced an empty dataframe; check raw records and cleaning rules.")
    _write_clean_dataframe(df, settings.paths.clean_csv, settings.paths.clean_json)
    print(f"  {len(df)} clean records -> {settings.paths.clean_csv}")

    print("== 3/8 Build baseline embedding index ==")
    index = LocalEmbeddingIndex.build(df, settings)
    print(f"  collection={index.collection_name} documents={len(index.documents)}")

    print("== 4/8 Test set ==")
    if settings.refresh_test_set or not settings.paths.eval_testset.exists():
        test_set = build_test_set(df, settings.paths.eval_testset)
        print(f"  built {len(test_set)} questions -> {settings.paths.eval_testset}")
    else:
        print(f"  reusing existing test set at {settings.paths.eval_testset}")

    print("== 5/8 Evaluate ==")
    bundle = evaluate_pipeline(
        settings=settings,
        index=index,
        test_set_path=settings.paths.eval_testset,
        metrics_output_path=settings.paths.baseline_metrics,
        answers_output_path=settings.paths.baseline_answers,
    )
    summary = bundle.summary
    print(
        f"  retrieval_hit_rate={summary['retrieval_hit_rate']:.3f} "
        f"mean_token_f1={summary['mean_token_f1']:.3f} "
        f"judge_accuracy={summary['judge_accuracy']:.3f}"
    )

    print("== 6/8 Data quality checks ==")
    quality = run_data_quality_checks(df, settings, "baseline")

    print("== 7/8 Freshness report ==")
    freshness = build_freshness_report(df, settings, settings.paths.freshness_report)

    print("== 8/8 Phase 1 report ==")
    source_summary = {
        "source_api": settings.source_api,
        "source_query": settings.source_query,
        "source_filter": settings.source_filter,
        "raw_record_count": len(records),
        "clean_record_count": len(df),
    }
    generate_phase1_report(
        report_path=settings.paths.baseline_report,
        source_summary=source_summary,
        metrics=summary,
        quality=quality,
        freshness=freshness,
    )
    print(f"  report -> {settings.paths.baseline_report}")

    print("== Agent demo (optional) ==")
    _demo_agent(settings, index)

    print("Phase 1 baseline pipeline complete.")
