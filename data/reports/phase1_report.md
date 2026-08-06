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

## Embedding manifest and collection audit

| Signal | Value |
| --- | --- |
| Status | pass |
| Backend/model | chroma / sentence-transformers/all-MiniLM-L6-v2 |
| Collection | papers-baseline |
| Expected collection | papers-baseline |
| Manifest documents | 24 |
| Chroma documents | 24 |
| Duplicate document IDs | 0 |
| Missing clean IDs | [] |
| Warnings | ["manifest persist_path differs from the runtime Chroma path; the runtime path was used for collection audit"] |

## Frozen evaluation-set audit

| Signal | Value |
| --- | --- |
| Status | pass |
| Frozen path | C:\Users\ADMIN\.vscode\VinAI_LAB\K4_Day10_Data-Pipeline-Data-Observability\data\eval\test_set.json |
| SHA-256 | `88846fd8575b8fe78cd02cc8e3647a06833666568a430c04d030acac8d13ba00` |
| Samples | 16 |
| Question types | ["authors", "categories", "date", "summary"] |
| Ground-truth documents | 4 |
| All IDs present in index | PASS |

### Persisted-row preview

| ID | Type | Question | Ground truth | Document IDs |
| --- | --- | --- | --- | --- |
| `q01-summary` | summary | What is the main point summarized for paper '10.1111/exsy.70341' titled "Hi‐ <scp>RAG</scp> : A Hierarchical Retrieval‐Augmented Generation Framework for Scalable and Generalisabl… | ABSTRACT As tool repositories for Large Language Model (LLM) agents grow from dozens to hundreds of endpoints, flat retrieval paradigms that treat the repository as an unstructure… | ["10.1111/exsy.70341"] |
| `q01-authors` | authors | Who authored paper '10.1111/exsy.70341' titled "Hi‐ <scp>RAG</scp> : A Hierarchical Retrieval‐Augmented Generation Framework for Scalable and Generalisable Tool Selection in Large… | Wei Tian, Yuhao Zhou | ["10.1111/exsy.70341"] |
| `q01-date` | date | When was paper '10.1111/exsy.70341' titled "Hi‐ <scp>RAG</scp> : A Hierarchical Retrieval‐Augmented Generation Framework for Scalable and Generalisable Tool Selection in Large Lan… | 2026-08-01 | ["10.1111/exsy.70341"] |

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

Overall status: **PASS** ({"failed": 0, "passed": 10, "total": 10})

| Check | Dimension | Result | Observed | Expected |
| --- | --- | --- | ---: | --- |
| `row_count` | volume | PASS | 24 | >= 4 |
| `paper_id_not_null` | completeness | PASS | 0 | 0 missing rows |
| `paper_id_unique` | uniqueness | PASS | 0 | 0 duplicate rows |
| `records_unique` | uniqueness | PASS | 0 | 0 duplicate records |
| `title_not_null` | completeness | PASS | 0 | 0 missing rows |
| `summary_not_null` | completeness | PASS | 0 | 0 missing rows |
| `summary_min_length` | validity | PASS | 0 | 0 rows shorter than 80 characters |
| `age_days_not_null` | completeness | PASS | 0 | 0 missing rows |
| `age_days_valid` | validity | PASS | 0 | 0 negative ages |
| `age_days_fresh` | freshness | PASS | 0 | 0 rows older than 180 days |

### Baseline comparison signals

These values are the control signals to compare with corrupted and repaired runs.

| Signal | Baseline |
| --- | ---: |
| Row count | 24 |
| Null paper IDs | 0 |
| Null titles | 0 |
| Null summaries | 0 |
| Duplicate paper-ID rows | 0 |
| Duplicate records | 0 |
| Stale rows | 0 |
| Maximum age (days) | 175 |

## Freshness

| Signal | Value |
| --- | --- |
| Timestamp source | cleaned published field sourced from Crossref |
| Observation time | 2026-08-06T09:11:38.270792+00:00 |
| Threshold (days) | 180 |
| Latest publication | 2026-08-01 |
| Oldest publication | 2026-02-12 |
| Stale rows | 0 |
| Invalid timestamps | 0 |
| Total rows | 24 |
| Fresh | PASS |

## Baseline interpretation

This report establishes the clean-data control. The same frozen evaluation set must be reused for corrupted and repaired indexes; otherwise metric changes cannot be attributed to the data state.
