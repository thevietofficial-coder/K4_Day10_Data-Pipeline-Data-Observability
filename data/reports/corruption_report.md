# CP6 - Baseline, Corrupted, and Repaired Comparison

Frozen test-set SHA-256: `88846fd8575b8fe78cd02cc8e3647a06833666568a430c04d030acac8d13ba00`
Samples: 16

All values below are rendered from the validated metrics, answers, quality, freshness, manifest, and collection artifacts. Delta corruption = corrupted - baseline; delta repair = repaired - corrupted; residual = repaired - baseline.

## RAG metrics

| Metric | Baseline | Corrupted | Repaired | Delta corruption | Delta repair | Residual |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `retrieval_hit_rate` | 1.0000 | 0.5000 | 1.0000 | -0.5000 | +0.5000 | +0.0000 |
| `mean_token_f1` | 1.0000 | 0.6337 | 1.0000 | -0.3663 | +0.3663 | +0.0000 |
| `judge_accuracy` | 1.0000 | 0.6875 | 1.0000 | -0.3125 | +0.3125 | +0.0000 |
| `mean_judge_score` | 5.0000 | 3.8750 | 5.0000 | -1.1250 | +1.1250 | +0.0000 |

## Quality and freshness signals

| Signal | Baseline | Corrupted | Repaired | Delta corruption | Delta repair | Residual |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `row_count` | 24 | 24 | 24 | +0.0000 | +0.0000 | +0.0000 |
| `null_paper_id_rows` | 0 | 0 | 0 | +0.0000 | +0.0000 | +0.0000 |
| `null_title_rows` | 0 | 0 | 0 | +0.0000 | +0.0000 | +0.0000 |
| `null_summary_rows` | 0 | 4 | 0 | +4.0000 | -4.0000 | +0.0000 |
| `duplicate_paper_id_rows` | 0 | 4 | 0 | +4.0000 | -4.0000 | +0.0000 |
| `duplicate_record_rows` | 0 | 4 | 0 | +4.0000 | -4.0000 | +0.0000 |
| `short_summary_rows` | 0 | 4 | 0 | +4.0000 | -4.0000 | +0.0000 |
| `stale_rows` | 0 | 6 | 0 | +6.0000 | -6.0000 | +0.0000 |
| `max_age_days` | 175 | 1161 | 175 | +986.0000 | -986.0000 | +0.0000 |
| `latest_published` | 2026-08-01 | 2026-07-13 | 2026-08-01 | N/A | N/A | N/A |
| `oldest_published` | 2026-02-12 | 2026-02-12 | 2026-02-12 | N/A | N/A | N/A |
| `is_fresh` | PASS | FAIL | PASS | N/A | N/A | N/A |

Quality status: baseline `pass`, corrupted `fail`, repaired `pass`.
Freshness status: baseline `True`, corrupted `False`, repaired `True`.

Freshness uses the cleaned `published` field sourced from Crossref and the materialized `age_days`; it does not invent a publication date from the current clock.

## Recovery evidence from actual answers

Cases degraded under corruption: 8; recovered to baseline: 8; unresolved after repair: 0.

Representative sample: `q01-authors` (authors)

- Ground-truth document ID: ["10.1111/exsy.70341"]
- Retrieval hit (baseline/corrupted/repaired): {"baseline": true, "corrupted": false, "repaired": true}
- Token F1 (baseline/corrupted/repaired): {"baseline": 1.0, "corrupted": 0.0, "repaired": 1.0}
- Judge score (baseline/corrupted/repaired): {"baseline": 5, "corrupted": 1, "repaired": 5}
- Baseline answer: Wei Tian, Yuhao Zhou
- Corrupted answer: Khoa Pham, Jiacheng Li, Hassan S. Al Khatib, Shahram Rahimi, Noorbakhsh Amiri Golilarz, Andy Perkins
- Repaired answer: Wei Tian, Yuhao Zhou

## Honest demo hit and miss

- Repaired hit: `q01-authors` retrieved its ground-truth ID ["10.1111/exsy.70341"]; token F1 1.0000.
- Corrupted miss: `q01-authors` did not retrieve ["10.1111/exsy.70341"]; token F1 0.0000.
- There is no repaired-state miss in this run; labeling a corrupted miss as repaired would misrepresent the evidence.

## Recovery conclusion

Within the measured scope, recovery is complete: repaired metrics and monitored signals equal baseline, repaired quality/freshness/index audits pass, and no repaired sample uses a recorded judge fallback.

This statement is limited to the monitored fields and the frozen test set; it is not a claim that the RAG system is generally perfect.

## Evaluator integrity and limitations

Recorded fallback sample IDs: {"baseline": [], "corrupted": [], "repaired": []}.
Repaired index audit: pass; collection `papers-repaired`; documents 24.
Repaired index audit warnings: ["manifest persist_path differs from the runtime Chroma path; the runtime path was used for collection audit"].

- `q01-summary` in `corrupted`: `empty_answer_marked_correct`; judge score 5. This is a measured judge false positive.

- The fixed test set has 16 questions over 4 papers, so it is not a broad benchmark.
- Questions include an exact paper ID and title, which makes retrieval easier than open-ended RAG.
- Several corruption types were applied together; this run cannot isolate every type's causal effect.
- The structured LLM judge produced an observed false positive for an empty corrupted answer.
- Ragas was skipped, and this single run provides no variance or confidence interval.

The false-positive judge example is why retrieval hit and deterministic token F1 are reported beside LLM-judge metrics instead of treating judge score as ground truth.

## Artifact lineage

- Fixed questions: `data/eval/test_set.json`
- Per-state answers/metrics: `data/results/{baseline,corrupted,repaired}_{answers,metrics}.json`
- Per-state quality/freshness: `data/quality/`
- Repaired manifest: `data/embeddings/papers_embeddings_repaired.json`
- Machine-readable comparison: `data/quality/recovery_checkpoint.json`
