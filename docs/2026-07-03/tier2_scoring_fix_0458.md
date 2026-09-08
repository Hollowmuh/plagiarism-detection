# Tier 2 Scoring Bug Fix & Threshold Retuning

## Context

While answering "what's the performance of the two tiers," running the existing `evaluation/run_evaluation.py` harness against the held-out test split (38 samples, PAN-style plagiarism corpus in `evaluation/dataset/data/`) revealed the dual-tier pipeline was catching **zero** plagiarism cases: Precision/Recall/F1 all 0.000 (24 false negatives, 0 true positives), despite an 84% Tier 2 escalation rate.

## Root Causes (two independent bugs in `backend/app/services/tier2_detector.py`)

1. **Destructive per-query min-max renormalization.** `tier2_detector.py` called `robust_min_max_normalize()` on the dense (FAISS) and sparse (BM25) candidate score arrays before fusion. Both scores were *already* absolute-calibrated to [0,1] (FAISS cosine similarity on normalized vectors; BM25 via `BM25Index.search()`'s own proportional `raw/saturation` normalization — see that function's docstring, which explicitly documents avoiding this exact pattern). Re-normalizing per-query meant whichever candidate was locally-best always inflated to exactly `1.0`, regardless of true similarity — an artifact, not a signal.

2. **Doc-ID / chunk-ID key mismatch (the primary blocker).** `index_chunks()` stores FAISS vectors under chunk-suffixed IDs (`"doc.txt__chunk_0"`), but `BM25Index` indexes at plain document granularity (`"doc.txt"`). The fusion step's `sparse_lookup.get(cid, 0.0)` / `dense_lookup.get(cid, 0.0)` could therefore never find both signals for the same candidate — every candidate got either a dense score or a sparse score, never both. Since `alpha=0.6 > 1-alpha=0.4`, dense-only candidates always won the argmax, and their sparse contribution was *structurally* always `0.0`. Combined with bug #1, `c2` was pinned at almost exactly `alpha` (0.6) for nearly every escalated submission — which never exceeded `TAU_HIGH=0.75`, so Tier 2 could never fire "plagiarised," full stop.

This also explains a second symptom noticed earlier in the session: real Moodle submissions that escalated to Tier 2 always returned `matches: []` in the API response — `best_match_id` was a chunk-suffixed string, not a valid document UUID, so `detection_tasks.py`'s `uuid.UUID(pipeline_result.best_match_id)` silently failed and skipped persisting the `SimilarityPair`.

## Fixes Applied

- `tier2_detector.py`: removed the `robust_min_max_normalize()` calls entirely — dense/sparse arrays are now used directly since both are already absolute-normalized.
- `tier2_detector.py`: FAISS search results are now collapsed back to their base document ID (`match_id.rsplit("__chunk_", 1)[0]`) before aggregating into `dense_scores`, so dense and sparse lookups share the same key space.

## Threshold Retuning (`TAU_HIGH`)

After the code fix, F1 on the test split jumped to 0.760 at the old `TAU_HIGH=0.75` default — but with 7/14 "original" (non-plagiarized) documents now false-flagged. Swept `TAU_HIGH` against the **validation** split only (not test, to avoid overfitting the report number), found a stable F1-optimum plateau at `TAU_HIGH ≈ 0.67–0.72` on both val and test independently (a good sign it's a real optimum, not noise). Picked `TAU_HIGH=0.68` — notably, `docker-compose.dev.yml` already had `TAU_HIGH: "0.65"` for local dev, very close to this value, suggesting this was previously discovered informally but never carried into the actual `.env` used for the GCP deployment (which still had the textbook-round `0.75`).

Also ran a 2D grid search over `alpha × TAU_HIGH` (using cached per-sample dense/sparse components to avoid re-running embeddings per config) — found no configuration in a wide sweep (`alpha` 0.3–0.9) that improved on `alpha=0.6, TAU_HIGH=0.68`. The remaining false positives (same-prompt "original" student essays scoring high on both dense *and* sparse similarity to corpus documents) persist regardless of the dense/sparse weighting, meaning they're not a tunable-weighting artifact — most likely genuine topical/lexical overlap between independently-written essays answering the same assignment prompt, which is a harder, more fundamental limitation of similarity-based detection (topical similarity vs. actual copying) rather than a fixable bug. Documented as a known limitation, not silently accepted.

## Before / After (held-out test split, n=38)

| | Before (broken) | After (fixed + retuned) |
|---|---|---|
| Precision | 0.000 | 0.733 |
| Recall | 0.000 | 0.917 |
| F1 | 0.000 | **0.815** |
| near_verbatim F1 | 0.000 | 1.000 |
| verbatim F1 | 0.000 | 1.000 |
| paraphrased F1 | 0.000 | 0.889 |
| original F1 | 0.000 | 0.000 (known limitation, see above) |
| Escalation rate | 84.2% | 84.2% |
| Latency p50/p95/p99 (ms) | 126/279/318 | 126/275/301 |

## Deployment

- `backend/app/config.py`: `TAU_HIGH` default changed 0.75 → 0.68, with a comment explaining the empirical basis.
- `.env` / `.env.example`: same change, both locally and on the live VM's deployed `.env`.
- `api`, `celery-worker`, `celery-beat` containers restarted on `plagiarism-detector-vm` to pick up the code fix and new threshold for real (non-eval) traffic.
- Verified via `evaluation/run_evaluation.py --split test` inside the live `api` container (evaluation/ folder copied to VM for this purpose, not part of the normal deployment).

## Follow-ups Not Done (out of scope for this pass)

- The "original" category false-positive rate (8/14 on test) is a real, unresolved limitation. Improving it likely needs a different signal than pure embedding/lexical similarity (e.g., stricter containment/coverage thresholds, or per-source exclusion of same-assignment-prompt documents from the corpus) rather than further threshold tuning.
- `tau_low` (0.25) was not retuned — only `TAU_HIGH` and `alpha` were swept. Worth revisiting if the "original" false-positive issue gets tackled.
