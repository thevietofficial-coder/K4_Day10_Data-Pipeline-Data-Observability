# Corruption Impact and Repair Report

The baseline, corrupted, and repaired values must come from runs over the same fixed evaluation set. Deltas are computed directly from the supplied metric artifacts.

## Required corruption-flow artifacts

| Artifact | Expected path |
| --- | --- |
| Frozen evaluation set | `data/eval/test_set.json` |
| Corrupted/repaired clean data | `data/clean/papers_clean_corrupted.*`, `data/clean/papers_clean_repaired.*` |
| Corrupted/repaired embedding manifests | `data/embeddings/papers_embeddings_corrupted.json`, `data/embeddings/papers_embeddings_repaired.json` |
| Corruption audit log | `data/results/corruption_log.json` |
| Three metric and answer pairs | `data/results/*_metrics.json`, `data/results/*_answers.json` |
| Quality/freshness evidence | `data/quality/` |
| Comparison report | `data/reports/corruption_report.md` |

## RAG metric comparison

| Metric | Baseline | Corrupted | Repaired | Corruption Δ | Repair Δ |
| --- | ---: | ---: | ---: | ---: | ---: |
| `samples` | 16 | 16 | 16 | +0.0000 | +0.0000 |
| `retrieval_hit_rate` | 1.0000 | 0.5000 | 1.0000 | -0.5000 | +0.5000 |
| `mean_token_f1` | 1.0000 | 0.6337 | 1.0000 | -0.3663 | +0.3663 |
| `judge_accuracy` | 1.0000 | 0.6875 | 1.0000 | -0.3125 | +0.3125 |
| `mean_judge_score` | 5 | 3.8750 | 5 | -1.1250 | +1.1250 |

Corruption Δ = corrupted − baseline; Repair Δ = repaired − corrupted. For quality metrics, a negative corruption delta is degradation and a positive repair delta is recovery.

## Quality signal comparison

Corrupted quality status: **FAIL**  
Repaired quality status: **PASS**

| Signal | Corrupted | Repaired |
| --- | ---: | ---: |
| `row_count` | 24 | 24 |
| `null_paper_id_rows` | 0 | 0 |
| `null_title_rows` | 0 | 0 |
| `null_summary_rows` | 4 | 0 |
| `duplicate_paper_id_rows` | 4 | 0 |
| `short_summary_rows` | 4 | 0 |
| `stale_rows` | 6 | 0 |
| `max_age_days` | 1161 | 175 |

## Freshness comparison

| Signal | Corrupted | Repaired |
| --- | ---: | ---: |
| Total rows | 24 | 24 |
| Latest publication | 2026-07-13 | 2026-08-01 |
| Oldest publication | 2026-02-12 | 2026-02-12 |
| Stale rows | 0 | 0 |
| Max age (days) | 175 | 175 |
| Fresh | PASS | PASS |

Timestamp source: Crossref `published` in each cleaned artifact; observation time and threshold are recorded in the corresponding freshness JSON.

## Evidence chains

1. Corrupted data → quality status **FAIL**, stale rows 0 → `retrieval_hit_rate` (-0.5000), `mean_token_f1` (-0.3663), `judge_accuracy` (-0.3125), `mean_judge_score` (-1.1250).
2. Repair from raw data → quality status **PASS**, stale rows 0 → `retrieval_hit_rate` (+0.5000), `mean_token_f1` (+0.3663), `judge_accuracy` (+0.3125), `mean_judge_score` (+1.1250).

If the report says that no metric moved, the artifacts do not support a degradation/recovery claim; inspect per-question answers and corruption coverage instead of asserting impact without evidence.
