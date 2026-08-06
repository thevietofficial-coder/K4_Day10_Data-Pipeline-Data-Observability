# Phase 1 — Baseline Data and RAG Report

All values below are rendered from the source, evaluation, quality, and freshness payloads passed by the baseline pipeline.

## Source and lineage

| Field | Value |
| --- | --- |
| `clean_record_count` | 24 |
| `raw_record_count` | 24 |
| `source_api` | Crossref REST API |
| `source_filter` | from-pub-date:2026-02-07,has-abstract:true |
| `source_query` | agentic retrieval augmented generation large language model |

## Required baseline artifacts

| Artifact | Expected path |
| --- | --- |
| Raw response and parsed records | `data/raw/` |
| Clean CSV and JSON | `data/clean/` |
| Embedding manifest and Chroma collection | `data/embeddings/`, `data/chroma/` |
| Fixed evaluation set | `data/eval/test_set.json` |
| Baseline metrics and per-question answers | `data/results/baseline_metrics.json`, `data/results/baseline_answers.json` |
| Quality and freshness evidence | `data/quality/` |
| This baseline report | `data/reports/phase1_report.md` |

## RAG evaluation

| Metric | Value |
| --- | ---: |
| `samples` | 16 |
| `retrieval_hit_rate` | 1.0000 |
| `mean_token_f1` | 1.0000 |
| `judge_accuracy` | 1.0000 |
| `mean_judge_score` | 5 |
| `ragas` | {"skipped": "Set RUN_RAGAS=1 to enable the slower Ragas pass."} |

`retrieval_hit_rate` checks whether a retrieved document ID occurs in the sample's clean `ground_truth_doc_ids`; answer metrics compare the returned answer with ground truth derived from that same clean row.

## Data quality

Overall status: **PASS** ({"failed": 0, "passed": 9, "total": 9})

| Check | Dimension | Result | Observed | Expected |
| --- | --- | --- | ---: | --- |
| `row_count` | volume | PASS | 24 | >= 4 |
| `paper_id_not_null` | completeness | PASS | 0 | 0 missing rows |
| `paper_id_unique` | uniqueness | PASS | 0 | 0 duplicate rows |
| `title_not_null` | completeness | PASS | 0 | 0 missing rows |
| `summary_not_null` | completeness | PASS | 0 | 0 missing rows |
| `summary_min_length` | validity | PASS | 0 | 0 rows shorter than 80 characters |
| `age_days_not_null` | completeness | PASS | 0 | 0 missing rows |
| `age_days_valid` | validity | PASS | 0 | 0 negative ages |
| `age_days_fresh` | freshness | PASS | 0 | 0 rows older than 180 days |

## Freshness

| Signal | Value |
| --- | --- |
| Timestamp source | Crossref published field in the cleaned dataset |
| Observation time | 2026-08-06T08:48:36.588279+00:00 |
| Threshold (days) | 180 |
| Latest publication | 2026-08-01 |
| Oldest publication | 2026-02-12 |
| Stale rows | 0 |
| Invalid timestamps | 0 |
| Total rows | 24 |
| Fresh | PASS |

## Baseline interpretation

This report establishes the clean-data control. The same frozen evaluation set must be reused for corrupted and repaired indexes; otherwise metric changes cannot be attributed to the data state.
