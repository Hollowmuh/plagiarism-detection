# Report 1: Tier 2 Bug Fix & Threshold Retuning

**Status:** Done (2026-07-03)
**Roadmap step:** Step 1

## Summary

Tier 2 was silently non-functional (0.000 F1 — zero recall) from initial deployment until 2026-07-02/03. Two independent bugs in `backend/app/services/tier2_detector.py`: a destructive per-query min-max renormalization that discarded absolute similarity, and a doc-ID/chunk-ID key mismatch that prevented the dense and sparse fusion from ever combining both signals for the same candidate.

Fixed both, then retuned `TAU_HIGH` (0.75→0.68) via val-then-test methodology. Result: test-split F1 0.000 → **0.815** (P=0.733, R=0.917).

## Full writeup

See `docs/2026-07-03/tier2_scoring_fix_0458.md` for the complete technical detail: root-cause diagnosis, before/after numbers by category, the alpha×tau_high grid search showing the "original" false-positive rate doesn't respond to reweighting, and deployment notes.

## Note on dataset reconciliation

The numbers above were measured against the (now confirmed, per Report 00) real 38-item test split — Report 00's reconciliation didn't change the split itself, only its documented provenance, so no numbers here needed revision.

## Addendum 2026-07-03: a second, independent bug found while investigating Report 02

While computing the per-category escalation breakdown for Report 02, `winnow=0.0` showed up for nearly every submission in the verbose eval logs — including labelled *verbatim* copies, which Winnowing should trivially catch. Two real, independent bugs, found by tracing the actual code paths rather than assuming the algorithm was just "not great at this":

1. **`backend/app/services/winnowing.py`, `FingerprintIndex.submit()`:** candidate matches were gated on Jaccard similarity (`if jacc >= self.threshold`) instead of containment, even though `tier1_detector.py`'s own comment explicitly documents containment as the correct signal ("Jaccard is symmetric and inflated by topical overlap... Use CONTAINMENT"). Jaccard collapses toward zero whenever the matched source document is much longer than the copied excerpt — exactly the case for a short answer copying part of a longer reference — so genuine full-containment matches were silently discarded before `tier1_detector.py` ever got to read them. Fixed: gate on `cont >= self.threshold` instead. All 35 existing unit tests still pass (`backend/tests/test_winnowing.py`, `test_tier1.py`) — none of them exercised the "short excerpt in long source" case, which is why this wasn't caught earlier.

2. **`evaluation/run_evaluation.py`, `index_sources()` (the bigger cause):** `detection_pipeline.index_document()` only populates BM25 + FAISS — its docstring says "Called AFTER detection," meaning it assumes the Winnowing fingerprint was already inserted as a side effect of `tier1.detect()`. That assumption holds for real submissions (which always go through `detect()` before indexing in production). It does **not** hold for the eval harness's `index_sources()`, which indexes the 190 static source documents directly, never running `detect()` on them. Result: the Winnowing index was essentially empty of the entire pre-existing corpus for the whole evaluation run — `backend/tests/test_pipeline.py`'s own `indexed_corpus` fixture already documents this exact gap and works around it (`# For testing, we also call fp_index.submit() to populate the fingerprint index`), but the eval script never applied the same workaround. Fixed: `index_sources()` now calls `fp_idx.submit(doc_id, text)` explicitly before `index_document()`.

### Impact (test split, same 38 items, after both fixes)

| Metric | Before this fix | After this fix |
|---|---|---|
| Escalation rate | 84.21% (32/38) | **15.79% (6/38)** |
| Precision | 0.733 | 0.697 |
| Recall | 0.917 | 0.958 |
| F1 | 0.815 | 0.807 |
| Latency p50/p95/p99 (ms) | 131/284/362 | **12/107/118** |
| Cost savings vs. cloud-only | 15.8% | **84.2%** |

Escalation rate and latency improved dramatically — most submissions now resolve instantly at Tier 1 via Winnowing rather than needing Tier 2's embedding computation. F1 dipped slightly (0.815→0.807): precision dropped because Winnowing's newly-correct containment scoring now aggressively flags a specific, well-evidenced failure case in the `original` category — see Report 02 and Report 05 for the full breakdown. This is a genuinely different, better-supported result than the prior state, not a regression to hide.
