# CP5 — Corrupted Data Evidence Report

Frozen test-set SHA-256: `88846fd8575b8fe78cd02cc8e3647a06833666568a430c04d030acac8d13ba00`

## Metric comparison

| Metric | Baseline | Corrupted | Delta |
| --- | ---: | ---: | ---: |
| `retrieval_hit_rate` | 1.0000 | 0.5000 | -0.5000 |
| `mean_token_f1` | 1.0000 | 0.6337 | -0.3663 |
| `judge_accuracy` | 1.0000 | 0.6875 | -0.3125 |
| `mean_judge_score` | 5 | 3.8750 | -1.1250 |

## Evaluator integrity

- Judge mode: `structured_llm`
- Recorded fallback judges: 0
- Silent fallback detected: no

A fallback is never counted silently: fallback reasoning is stored per answer and counted in the checkpoint.

## Corruption log summary

| Type | Log events | Affected references |
| --- | ---: | ---: |
| `add_duplicates` | 1 | 2 |
| `blank_summary` | 6 | 6 |
| `drop_latest` | 1 | 2 |
| `inject_noise` | 6 | 6 |
| `stale_date` | 6 | 6 |
| `truncate_title` | 6 | 6 |

## Quality and freshness signals

| Signal | Baseline | Corrupted | Delta | State |
| --- | ---: | ---: | ---: | --- |
| `row_count` | 24 | 24 | +0.0000 | unchanged |
| `null_paper_id_rows` | 0 | 0 | +0.0000 | unchanged |
| `null_title_rows` | 0 | 0 | +0.0000 | unchanged |
| `null_summary_rows` | 0 | 4 | +4.0000 | changed |
| `duplicate_paper_id_rows` | 0 | 4 | +4.0000 | changed |
| `duplicate_record_rows` | 0 | 4 | +4.0000 | changed |
| `short_summary_rows` | 0 | 4 | +4.0000 | changed |
| `stale_rows` | 0 | 6 | +6.0000 | changed |
| `max_age_days` | 175 | 1161 | +986.0000 | changed |
| `latest_published` | 2026-08-01 | 2026-07-13 | N/A | changed |
| `oldest_published` | 2026-02-12 | 2026-02-12 | N/A | unchanged |
| `is_fresh` | PASS | FAIL | N/A | changed |

## One measured worse case

- Sample: `q01-authors` (authors)
- Ground-truth document IDs: ["10.1111/exsy.70341"]
- Retrieval hit: PASS → FAIL
- Token F1: 1.0000 → 0.0000
- Judge score: 5 → 1
- Corrupted answer: Khoa Pham, Jiacheng Li, Hassan S. Al Khatib, Shahram Rahimi, Noorbakhsh Amiri Golilarz, Andy Perkins
- Retrieved IDs: ["10.32473/flairs.39.1.141782", "10.63646/kpqm1958", "10.36227/techrxiv.177272838.89432844/v1", "10.20944/preprints202604.0339.v1"]
- Judge reasoning: The model answer lists authors who are not mentioned in the reference answer, indicating a complete mismatch with the correct authors of the paper.

## Supported evidence links

- drop_latest IDs equal the missing ground-truth index IDs and cover all worsened samples.
- blank_summary coincides with increased null_summary_rows.
- add_duplicates coincides with increased duplicate_paper_id_rows.
- stale_date coincides with increased stale_rows.

## Guard against over-claiming

Unchanged signals: ["row_count", "null_paper_id_rows", "null_title_rows", "oldest_published"].

Corruption types without direct per-question metric attribution: ["add_duplicates", "blank_summary", "inject_noise", "stale_date", "truncate_title"].

These types may have changed data-quality signals, but this run does not isolate their individual causal contribution to an answer metric.
