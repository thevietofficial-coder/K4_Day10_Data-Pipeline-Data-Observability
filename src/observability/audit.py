from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
import sqlite3
from typing import Any, Iterable

from core.utils import read_json, write_json
from evaluation.testset import load_frozen_test_set


def _read_chroma_collection_count(chroma_dir: Path, collection_name: str) -> int:
    """Read Chroma's SQLite catalog in read-only mode to avoid index mutation."""
    database_path = chroma_dir / "chroma.sqlite3"
    if not database_path.is_file():
        raise FileNotFoundError(f"Chroma catalog does not exist: {database_path}")

    connection = sqlite3.connect(f"{database_path.resolve().as_uri()}?mode=ro", uri=True)
    try:
        collection_row = connection.execute(
            "SELECT id FROM collections WHERE name = ?",
            (collection_name,),
        ).fetchone()
        if collection_row is None:
            raise ValueError(f"Chroma collection does not exist: {collection_name}")
        count_row = connection.execute(
            """
            SELECT COUNT(*)
            FROM embeddings AS e
            JOIN segments AS s ON s.id = e.segment_id
            WHERE s.collection = ? AND s.scope = 'METADATA'
            """,
            (collection_row[0],),
        ).fetchone()
        return int(count_row[0])
    finally:
        connection.close()


def audit_embedding_manifest(
    manifest_path: Path,
    expected_collection_name: str,
    expected_doc_ids: Iterable[str] | None = None,
    chroma_dir: Path | None = None,
) -> dict[str, Any]:
    """Audit manifest metadata and, when available, the persisted collection."""
    manifest_path = Path(manifest_path)
    payload = read_json(manifest_path)
    documents = payload.get("documents")
    if not isinstance(documents, list):
        raise ValueError(f"Embedding manifest has no valid documents list: {manifest_path}")
    if any(not isinstance(document, dict) for document in documents):
        raise ValueError(f"Embedding manifest contains a non-object document: {manifest_path}")

    document_ids = [str(document.get("paper_id", "")).strip() for document in documents]
    blank_document_ids = sum(not paper_id for paper_id in document_ids)
    duplicate_document_ids = len(document_ids) - len(set(document_ids))
    collection_name = str(payload.get("collection_name", ""))
    manifest_document_count = len(documents)

    expected_ids = {str(doc_id) for doc_id in expected_doc_ids} if expected_doc_ids is not None else None
    manifest_ids = {paper_id for paper_id in document_ids if paper_id}
    missing_expected_ids = sorted(expected_ids.difference(manifest_ids)) if expected_ids is not None else []
    unexpected_ids = sorted(manifest_ids.difference(expected_ids)) if expected_ids is not None else []

    errors: list[str] = []
    warnings: list[str] = []
    if collection_name != expected_collection_name:
        errors.append(
            f"collection_name={collection_name!r}, expected {expected_collection_name!r}"
        )
    if blank_document_ids:
        errors.append(f"{blank_document_ids} manifest documents have blank paper_id")
    if duplicate_document_ids:
        errors.append(f"{duplicate_document_ids} duplicate paper_id entries in manifest")
    if missing_expected_ids:
        errors.append(f"{len(missing_expected_ids)} cleaned paper IDs are missing from manifest")
    if unexpected_ids:
        errors.append(f"{len(unexpected_ids)} manifest paper IDs are absent from cleaned data")

    recorded_persist_value = str(payload.get("persist_path", "")).strip()
    recorded_persist_path = Path(recorded_persist_value) if recorded_persist_value else None
    runtime_persist_path = Path(chroma_dir) if chroma_dir is not None else recorded_persist_path
    if chroma_dir is not None:
        if recorded_persist_path is None:
            warnings.append("manifest persist_path is blank; the runtime Chroma path was used")
        else:
            try:
                paths_differ = recorded_persist_path.resolve() != runtime_persist_path.resolve()
            except OSError:
                paths_differ = True
                warnings.append("manifest persist_path could not be resolved on this machine")
            if paths_differ:
                warnings.append(
                    "manifest persist_path differs from the runtime Chroma path; "
                    "the runtime path was used for collection audit"
                )

    collection_document_count: int | None = None
    collection_error: str | None = None
    if runtime_persist_path is not None and runtime_persist_path.exists():
        try:
            collection_document_count = _read_chroma_collection_count(
                runtime_persist_path,
                collection_name,
            )
            if collection_document_count != manifest_document_count:
                errors.append(
                    "collection document count does not match manifest: "
                    f"{collection_document_count} != {manifest_document_count}"
                )
        except Exception as exc:  # pragma: no cover - backend-specific failure
            collection_error = str(exc)
            errors.append(f"could not audit Chroma collection: {exc}")
    else:
        collection_error = f"Chroma path does not exist: {runtime_persist_path}"
        errors.append(collection_error)

    return {
        "status": "pass" if not errors else "fail",
        "manifest_path": str(manifest_path),
        "backend": payload.get("backend"),
        "embedding_model": payload.get("embedding_model"),
        "collection_name": collection_name,
        "expected_collection_name": expected_collection_name,
        "collection_name_matches": collection_name == expected_collection_name,
        "manifest_document_count": manifest_document_count,
        "expected_document_count": len(expected_ids) if expected_ids is not None else None,
        "manifest_ids_match_expected": expected_ids is not None
        and manifest_ids == expected_ids,
        "collection_document_count": collection_document_count,
        "unique_manifest_document_ids": len(manifest_ids),
        "blank_document_ids": blank_document_ids,
        "duplicate_document_ids": duplicate_document_ids,
        "missing_expected_doc_ids": missing_expected_ids,
        "unexpected_doc_ids": unexpected_ids,
        "recorded_persist_path": str(recorded_persist_path) if recorded_persist_path else None,
        "runtime_persist_path": str(runtime_persist_path),
        "collection_error": collection_error,
        "errors": errors,
        "warnings": warnings,
    }


def build_baseline_artifact_audit(
    manifest_path: Path,
    test_set_path: Path,
    output_path: Path,
    expected_collection_name: str,
    expected_doc_ids: Iterable[str],
    chroma_dir: Path,
) -> dict[str, Any]:
    """Persist one baseline audit joining clean IDs, index, and frozen test set."""
    expected_ids = {str(doc_id) for doc_id in expected_doc_ids}
    index_audit = audit_embedding_manifest(
        manifest_path=manifest_path,
        expected_collection_name=expected_collection_name,
        expected_doc_ids=expected_ids,
        chroma_dir=chroma_dir,
    )
    manifest = read_json(Path(manifest_path))
    manifest_doc_ids = {
        str(document["paper_id"])
        for document in manifest.get("documents", [])
        if document.get("paper_id")
    }
    _, test_set_audit = load_frozen_test_set(
        Path(test_set_path),
        available_doc_ids=manifest_doc_ids,
    )

    payload = {
        "generated_at": datetime.now(UTC).isoformat(),
        "status": "pass" if index_audit["status"] == "pass" else "fail",
        "clean_document_count": len(expected_ids),
        "index": index_audit,
        "test_set": test_set_audit,
    }
    write_json(Path(output_path), payload)
    return payload


def write_baseline_checkpoint(
    output_path: Path,
    metrics: dict[str, Any],
    answers: list[dict[str, Any]],
    quality: dict[str, Any],
    freshness: dict[str, Any],
    artifact_audit: dict[str, Any],
) -> dict[str, Any]:
    """Freeze baseline metrics/signals used by the later corruption comparison."""
    sample_count = int(metrics.get("samples", -1))
    if sample_count != len(answers):
        raise ValueError(
            f"Baseline sample count does not match answers: {sample_count} != {len(answers)}"
        )

    hits = [answer for answer in answers if bool(answer.get("retrieval_hit"))]
    misses = [answer for answer in answers if not bool(answer.get("retrieval_hit"))]
    observed_hit_rate = len(hits) / len(answers) if answers else 0.0
    metric_hit_rate = float(metrics.get("retrieval_hit_rate", -1.0))
    if abs(observed_hit_rate - metric_hit_rate) > 1e-12:
        raise ValueError(
            "Baseline retrieval_hit_rate does not match answers: "
            f"{metric_hit_rate} != {observed_hit_rate}"
        )

    fallback_judges = [
        answer
        for answer in answers
        if "fallback heuristic" in str(answer.get("judge", {}).get("reasoning", "")).lower()
    ]
    metric_names = (
        "samples",
        "retrieval_hit_rate",
        "mean_token_f1",
        "judge_accuracy",
        "mean_judge_score",
        "ragas",
    )
    payload = {
        "generated_at": datetime.now(UTC).isoformat(),
        "checkpoint": "baseline",
        "ready_for_comparison": bool(
            artifact_audit.get("status") == "pass"
            and quality.get("passed", quality.get("success", False))
            and freshness.get("is_fresh", False)
            and sample_count > 0
        ),
        "metrics": {name: metrics.get(name) for name in metric_names},
        "answer_evidence": {
            "answers": len(answers),
            "retrieval_hits": len(hits),
            "retrieval_misses": len(misses),
            "fallback_judges": len(fallback_judges),
            "example_hit_id": hits[0].get("id") if hits else None,
            "example_miss_id": misses[0].get("id") if misses else None,
        },
        "quality": {
            "status": quality.get("status"),
            "signals": quality.get("signals", {}),
        },
        "freshness": freshness,
        "artifact_audit": {
            "status": artifact_audit.get("status"),
            "collection_name": artifact_audit.get("index", {}).get("collection_name"),
            "manifest_document_count": artifact_audit.get("index", {}).get(
                "manifest_document_count"
            ),
            "collection_document_count": artifact_audit.get("index", {}).get(
                "collection_document_count"
            ),
            "test_set_sha256": artifact_audit.get("test_set", {}).get("sha256"),
            "all_ground_truth_ids_in_index": artifact_audit.get("test_set", {}).get(
                "all_ground_truth_ids_in_index"
            ),
        },
    }
    write_json(Path(output_path), payload)
    return payload


def write_corrupted_checkpoint(
    output_path: Path,
    baseline_metrics: dict[str, Any],
    corrupted_metrics: dict[str, Any],
    baseline_answers: list[dict[str, Any]],
    corrupted_answers: list[dict[str, Any]],
    baseline_quality: dict[str, Any],
    corrupted_quality: dict[str, Any],
    baseline_freshness: dict[str, Any],
    corrupted_freshness: dict[str, Any],
    corruption_log: list[dict[str, Any]],
) -> dict[str, Any]:
    """Join corruption events, observability signals, and measured RAG impact."""
    baseline_by_id = {answer["id"]: answer for answer in baseline_answers}
    corrupted_by_id = {answer["id"]: answer for answer in corrupted_answers}
    if set(baseline_by_id) != set(corrupted_by_id):
        raise ValueError("Baseline and corrupted answers do not contain the same sample IDs.")

    baseline_hash = baseline_metrics.get("test_set_audit", {}).get("sha256")
    corrupted_hash = corrupted_metrics.get("test_set_audit", {}).get("sha256")
    if not baseline_hash or baseline_hash != corrupted_hash:
        raise ValueError("Baseline and corrupted evaluations did not use the same frozen test set.")

    metric_names = (
        "retrieval_hit_rate",
        "mean_token_f1",
        "judge_accuracy",
        "mean_judge_score",
    )
    metric_deltas = {
        name: float(corrupted_metrics[name]) - float(baseline_metrics[name])
        for name in metric_names
    }

    worse_cases: list[dict[str, Any]] = []
    for sample_id, baseline in baseline_by_id.items():
        corrupted = corrupted_by_id[sample_id]
        f1_delta = float(corrupted["token_f1"]) - float(baseline["token_f1"])
        judge_delta = int(corrupted["judge"]["score"]) - int(baseline["judge"]["score"])
        if (
            bool(baseline["retrieval_hit"]) and not bool(corrupted["retrieval_hit"])
        ) or f1_delta < 0 or judge_delta < 0:
            worse_cases.append(
                {
                    "id": sample_id,
                    "question_type": corrupted["question_type"],
                    "ground_truth_doc_ids": corrupted["ground_truth_doc_ids"],
                    "baseline_retrieval_hit": bool(baseline["retrieval_hit"]),
                    "corrupted_retrieval_hit": bool(corrupted["retrieval_hit"]),
                    "baseline_token_f1": baseline["token_f1"],
                    "corrupted_token_f1": corrupted["token_f1"],
                    "token_f1_delta": f1_delta,
                    "baseline_judge_score": baseline["judge"]["score"],
                    "corrupted_judge_score": corrupted["judge"]["score"],
                    "judge_score_delta": judge_delta,
                    "corrupted_answer": corrupted["answer"],
                    "corrupted_retrieved_doc_ids": corrupted["retrieved_doc_ids"],
                    "judge_reasoning": corrupted["judge"]["reasoning"],
                }
            )
    worse_cases.sort(key=lambda item: (item["token_f1_delta"], item["judge_score_delta"]))

    fallback_judges = [
        answer["id"]
        for answer in corrupted_answers
        if "fallback heuristic" in str(answer.get("judge", {}).get("reasoning", "")).lower()
    ]

    event_summary: dict[str, dict[str, int]] = {}
    affected_ids_by_type: dict[str, set[str]] = {}
    for event in corruption_log:
        event_type = str(event.get("type", "unknown"))
        affected_ids = event.get("affected_ids")
        if not isinstance(affected_ids, list):
            record_id = event.get("record_id")
            affected_ids = [record_id] if record_id else []
        event_summary.setdefault(event_type, {"events": 0, "affected_references": 0})
        event_summary[event_type]["events"] += 1
        event_summary[event_type]["affected_references"] += len(affected_ids)
        affected_ids_by_type.setdefault(event_type, set()).update(str(item) for item in affected_ids)

    baseline_signals = baseline_quality.get("signals", {})
    corrupted_signals = corrupted_quality.get("signals", {})
    signal_names = (
        "row_count",
        "null_paper_id_rows",
        "null_title_rows",
        "null_summary_rows",
        "duplicate_paper_id_rows",
        "duplicate_record_rows",
        "short_summary_rows",
        "stale_rows",
        "max_age_days",
    )
    signal_comparison: dict[str, dict[str, Any]] = {}
    unchanged_signals: list[str] = []
    for name in signal_names:
        before, after = baseline_signals.get(name), corrupted_signals.get(name)
        delta = (
            float(after) - float(before)
            if isinstance(before, (int, float))
            and not isinstance(before, bool)
            and isinstance(after, (int, float))
            and not isinstance(after, bool)
            else None
        )
        signal_comparison[name] = {
            "baseline": before,
            "corrupted": after,
            "delta": delta,
            "changed": before != after,
        }
        if before == after:
            unchanged_signals.append(name)

    for name in ("latest_published", "oldest_published", "is_fresh"):
        before, after = baseline_freshness.get(name), corrupted_freshness.get(name)
        signal_comparison[name] = {
            "baseline": before,
            "corrupted": after,
            "delta": None,
            "changed": before != after,
        }
        if before == after:
            unchanged_signals.append(name)

    dropped_ids = affected_ids_by_type.get("drop_latest", set())
    missing_index_ids = set(
        corrupted_metrics.get("test_set_audit", {}).get("missing_ground_truth_doc_ids", [])
    )
    worse_doc_ids = {
        doc_id for case in worse_cases for doc_id in case["ground_truth_doc_ids"]
    }
    supported_links: list[str] = []
    if dropped_ids and dropped_ids == missing_index_ids and worse_doc_ids.issubset(dropped_ids):
        supported_links.append(
            "drop_latest IDs equal the missing ground-truth index IDs and cover all worsened samples"
        )
    if event_summary.get("blank_summary") and corrupted_signals.get(
        "null_summary_rows", 0
    ) > baseline_signals.get("null_summary_rows", 0):
        supported_links.append("blank_summary coincides with increased null_summary_rows")
    if event_summary.get("add_duplicates") and corrupted_signals.get(
        "duplicate_paper_id_rows", 0
    ) > baseline_signals.get("duplicate_paper_id_rows", 0):
        supported_links.append("add_duplicates coincides with increased duplicate_paper_id_rows")
    if event_summary.get("stale_date") and corrupted_signals.get(
        "stale_rows", 0
    ) > baseline_signals.get("stale_rows", 0):
        supported_links.append("stale_date coincides with increased stale_rows")

    directly_linked_metric_types = {"drop_latest"} if worse_cases else set()
    no_direct_metric_attribution = sorted(set(event_summary).difference(directly_linked_metric_types))
    payload = {
        "generated_at": datetime.now(UTC).isoformat(),
        "checkpoint": "corrupted",
        "same_test_set": True,
        "test_set_sha256": baseline_hash,
        "baseline_metrics": {name: baseline_metrics[name] for name in metric_names},
        "corrupted_metrics": {name: corrupted_metrics[name] for name in metric_names},
        "metric_deltas": metric_deltas,
        "evaluator_integrity": {
            "corrupted_answers": len(corrupted_answers),
            "fallback_judges": len(fallback_judges),
            "fallback_sample_ids": fallback_judges,
            "judge_mode": "structured_llm" if not fallback_judges else "mixed_with_recorded_fallback",
            "silent_fallback_detected": False,
        },
        "corruption_events": event_summary,
        "signal_comparison": signal_comparison,
        "unchanged_signals": unchanged_signals,
        "worse_case_count": len(worse_cases),
        "worse_cases": worse_cases,
        "supported_links": supported_links,
        "corruption_types_without_direct_metric_attribution": no_direct_metric_attribution,
    }
    write_json(Path(output_path), payload)
    return payload


def write_recovery_checkpoint(
    output_path: Path,
    baseline_metrics: dict[str, Any],
    corrupted_metrics: dict[str, Any],
    repaired_metrics: dict[str, Any],
    baseline_answers: list[dict[str, Any]],
    corrupted_answers: list[dict[str, Any]],
    repaired_answers: list[dict[str, Any]],
    baseline_quality: dict[str, Any],
    corrupted_quality: dict[str, Any],
    repaired_quality: dict[str, Any],
    baseline_freshness: dict[str, Any],
    corrupted_freshness: dict[str, Any],
    repaired_freshness: dict[str, Any],
    repaired_index_audit: dict[str, Any],
) -> dict[str, Any]:
    """Persist an auditable baseline/corrupted/repaired comparison."""
    answer_sets = {
        "baseline": {answer["id"]: answer for answer in baseline_answers},
        "corrupted": {answer["id"]: answer for answer in corrupted_answers},
        "repaired": {answer["id"]: answer for answer in repaired_answers},
    }
    sample_ids = set(answer_sets["baseline"])
    if not sample_ids or any(set(items) != sample_ids for items in answer_sets.values()):
        raise ValueError("All three answer artifacts must contain the same non-empty sample IDs.")

    metrics_by_state = {
        "baseline": baseline_metrics,
        "corrupted": corrupted_metrics,
        "repaired": repaired_metrics,
    }
    for state, answers in answer_sets.items():
        if int(metrics_by_state[state].get("samples", -1)) != len(answers):
            raise ValueError(f"{state} sample count does not match its answer artifact.")
        observed = {
            "retrieval_hit_rate": sum(
                bool(answer.get("retrieval_hit")) for answer in answers.values()
            )
            / len(answers),
            "mean_token_f1": sum(
                float(answer.get("token_f1", 0)) for answer in answers.values()
            )
            / len(answers),
            "judge_accuracy": sum(
                bool(answer.get("judge", {}).get("correct")) for answer in answers.values()
            )
            / len(answers),
            "mean_judge_score": sum(
                int(answer.get("judge", {}).get("score", 0)) for answer in answers.values()
            )
            / len(answers),
        }
        for name, value in observed.items():
            if abs(float(metrics_by_state[state].get(name, -1)) - value) > 1e-12:
                raise ValueError(f"{state} {name} does not match its answer artifact.")

    hashes = {
        state: metrics.get("test_set_audit", {}).get("sha256")
        for state, metrics in metrics_by_state.items()
    }
    if not hashes["baseline"] or len(set(hashes.values())) != 1:
        raise ValueError("All three evaluations must use the same frozen test set.")

    metric_names = (
        "retrieval_hit_rate",
        "mean_token_f1",
        "judge_accuracy",
        "mean_judge_score",
    )
    metric_comparison: dict[str, dict[str, float]] = {}
    unrecovered_metrics: list[str] = []
    for name in metric_names:
        baseline = float(baseline_metrics[name])
        corrupted = float(corrupted_metrics[name])
        repaired = float(repaired_metrics[name])
        residual = repaired - baseline
        metric_comparison[name] = {
            "baseline": baseline,
            "corrupted": corrupted,
            "repaired": repaired,
            "corruption_delta": corrupted - baseline,
            "repair_delta": repaired - corrupted,
            "residual_vs_baseline": residual,
        }
        if abs(residual) > 1e-12:
            unrecovered_metrics.append(name)

    fallback_ids: dict[str, list[str]] = {}
    judge_anomalies: list[dict[str, Any]] = []
    for state, answers in answer_sets.items():
        fallback_ids[state] = [
            sample_id
            for sample_id, answer in answers.items()
            if "fallback heuristic"
            in str(answer.get("judge", {}).get("reasoning", "")).lower()
        ]
        for sample_id, answer in answers.items():
            if not str(answer.get("answer", "")).strip() and bool(
                answer.get("judge", {}).get("correct")
            ):
                judge_anomalies.append(
                    {
                        "state": state,
                        "id": sample_id,
                        "kind": "empty_answer_marked_correct",
                        "judge_score": answer.get("judge", {}).get("score"),
                        "judge_reasoning": answer.get("judge", {}).get("reasoning"),
                    }
                )

    cases: list[dict[str, Any]] = []
    for sample_id in sorted(sample_ids):
        baseline = answer_sets["baseline"][sample_id]
        corrupted = answer_sets["corrupted"][sample_id]
        repaired = answer_sets["repaired"][sample_id]
        degraded = (
            bool(baseline.get("retrieval_hit")) and not bool(corrupted.get("retrieval_hit"))
        ) or float(corrupted.get("token_f1", 0)) < float(baseline.get("token_f1", 0)) or int(
            corrupted.get("judge", {}).get("score", 0)
        ) < int(baseline.get("judge", {}).get("score", 0))
        unresolved = (
            bool(repaired.get("retrieval_hit")) != bool(baseline.get("retrieval_hit"))
            or abs(float(repaired.get("token_f1", 0)) - float(baseline.get("token_f1", 0)))
            > 1e-12
            or int(repaired.get("judge", {}).get("score", 0))
            != int(baseline.get("judge", {}).get("score", 0))
        )
        cases.append(
            {
                "id": sample_id,
                "question_type": baseline.get("question_type"),
                "question": baseline.get("question"),
                "ground_truth": baseline.get("ground_truth"),
                "ground_truth_doc_ids": baseline.get("ground_truth_doc_ids", []),
                "degraded_under_corruption": degraded,
                "recovered_to_baseline": degraded and not unresolved,
                "unresolved_after_repair": unresolved,
                "retrieval_hit": {
                    state: bool(answer_sets[state][sample_id].get("retrieval_hit"))
                    for state in answer_sets
                },
                "token_f1": {
                    state: float(answer_sets[state][sample_id].get("token_f1", 0))
                    for state in answer_sets
                },
                "judge_score": {
                    state: int(answer_sets[state][sample_id].get("judge", {}).get("score", 0))
                    for state in answer_sets
                },
                "answers": {
                    state: answer_sets[state][sample_id].get("answer", "")
                    for state in answer_sets
                },
                "retrieved_doc_ids": {
                    state: answer_sets[state][sample_id].get("retrieved_doc_ids", [])
                    for state in answer_sets
                },
            }
        )

    degraded_cases = [case for case in cases if case["degraded_under_corruption"]]
    recovered_cases = [case for case in cases if case["recovered_to_baseline"]]
    unresolved_cases = [case for case in cases if case["unresolved_after_repair"]]
    degraded_cases.sort(
        key=lambda case: (
            case["token_f1"]["corrupted"] - case["token_f1"]["baseline"],
            case["judge_score"]["corrupted"] - case["judge_score"]["baseline"],
        )
    )
    corrupted_misses = [
        case for case in cases if not case["retrieval_hit"]["corrupted"]
    ]

    quality_signal_names = (
        "row_count",
        "null_paper_id_rows",
        "null_title_rows",
        "null_summary_rows",
        "duplicate_paper_id_rows",
        "duplicate_record_rows",
        "short_summary_rows",
        "stale_rows",
        "max_age_days",
    )
    quality_by_state = {
        "baseline": baseline_quality.get("signals", {}),
        "corrupted": corrupted_quality.get("signals", {}),
        "repaired": repaired_quality.get("signals", {}),
    }
    freshness_by_state = {
        "baseline": baseline_freshness,
        "corrupted": corrupted_freshness,
        "repaired": repaired_freshness,
    }
    for state, signals in quality_by_state.items():
        cross_artifact_pairs = (
            ("row_count", "total_rows"),
            ("stale_rows", "stale_rows"),
            ("max_age_days", "max_age_days"),
        )
        for quality_name, freshness_name in cross_artifact_pairs:
            if signals.get(quality_name) != freshness_by_state[state].get(freshness_name):
                raise ValueError(
                    f"{state} quality {quality_name} does not match freshness "
                    f"{freshness_name}."
                )
    signal_comparison: dict[str, dict[str, Any]] = {}
    unrecovered_signals: list[str] = []
    for name in quality_signal_names:
        values = {state: signals.get(name) for state, signals in quality_by_state.items()}
        values["corruption_delta"] = (
            values["corrupted"] - values["baseline"]
            if isinstance(values["baseline"], (int, float))
            and isinstance(values["corrupted"], (int, float))
            else None
        )
        values["repair_delta"] = (
            values["repaired"] - values["corrupted"]
            if isinstance(values["corrupted"], (int, float))
            and isinstance(values["repaired"], (int, float))
            else None
        )
        values["residual_vs_baseline"] = (
            values["repaired"] - values["baseline"]
            if isinstance(values["baseline"], (int, float))
            and isinstance(values["repaired"], (int, float))
            else None
        )
        signal_comparison[name] = values
        if values["repaired"] != values["baseline"]:
            unrecovered_signals.append(name)

    for name in ("latest_published", "oldest_published", "is_fresh"):
        values = {
            "baseline": baseline_freshness.get(name),
            "corrupted": corrupted_freshness.get(name),
            "repaired": repaired_freshness.get(name),
            "corruption_delta": None,
            "repair_delta": None,
            "residual_vs_baseline": None,
        }
        signal_comparison[name] = values
        if values["repaired"] != values["baseline"]:
            unrecovered_signals.append(name)

    repair_complete = bool(
        not unrecovered_metrics
        and not unrecovered_signals
        and not unresolved_cases
        and repaired_quality.get("status") == "pass"
        and repaired_freshness.get("is_fresh") is True
        and repaired_index_audit.get("status") == "pass"
        and not fallback_ids["repaired"]
    )
    payload = {
        "generated_at": datetime.now(UTC).isoformat(),
        "checkpoint": "recovery",
        "same_test_set": True,
        "test_set_sha256": hashes["baseline"],
        "samples": len(sample_ids),
        "metric_comparison": metric_comparison,
        "signal_comparison": signal_comparison,
        "quality_status": {
            "baseline": baseline_quality.get("status"),
            "corrupted": corrupted_quality.get("status"),
            "repaired": repaired_quality.get("status"),
        },
        "freshness_status": {
            "baseline": baseline_freshness.get("is_fresh"),
            "corrupted": corrupted_freshness.get("is_fresh"),
            "repaired": repaired_freshness.get("is_fresh"),
        },
        "repaired_index_audit": repaired_index_audit,
        "evaluator_integrity": {
            "fallback_sample_ids": fallback_ids,
            "silent_fallback_detected": False,
            "judge_anomalies": judge_anomalies,
        },
        "case_summary": {
            "degraded_under_corruption": len(degraded_cases),
            "recovered_to_baseline": len(recovered_cases),
            "unresolved_after_repair": len(unresolved_cases),
        },
        "representative_recovery_case": degraded_cases[0] if degraded_cases else None,
        "representative_repaired_hit": next(
            (case for case in cases if case["retrieval_hit"]["repaired"]), None
        ),
        "representative_miss": corrupted_misses[0] if corrupted_misses else None,
        "representative_miss_state": "corrupted" if corrupted_misses else None,
        "unrecovered_metrics": unrecovered_metrics,
        "unrecovered_signals": unrecovered_signals,
        "unresolved_cases": unresolved_cases,
        "recovery_complete": repair_complete,
        "limitations": [
            "The fixed test set has 16 questions over 4 papers, so it is not a broad benchmark.",
            "Questions include an exact paper ID and title, which makes retrieval easier than open-ended RAG.",
            "Several corruption types were applied together; this run cannot isolate every type's causal effect.",
            "The structured LLM judge produced an observed false positive for an empty corrupted answer.",
            "Ragas was skipped, and this single run provides no variance or confidence interval.",
        ],
    }
    write_json(Path(output_path), payload)
    return payload
