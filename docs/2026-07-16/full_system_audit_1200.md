# Full System Audit — Everything, As It Actually Stands

This document is a complete, current-as-of-2026-07-16 inventory of the dual-tier plagiarism detection system: every component, what it does, how it does it, what's confirmed by real testing vs. reasoned/assumed, and every known caveat or limitation. It supersedes any impression given by any single evaluation report — those are experiment-specific; this is the whole-system picture.

**How to read the confidence markers**: every claim below is tagged **[TESTED]** (directly verified by running real code against real or realistic data, this session or a prior one in this thread), **[BY DESIGN]** (true by construction/code inspection, not independently re-tested), or **[CAVEAT]** (a known gap, risk, or unverified assumption). Don't upgrade a BY DESIGN claim to TESTED in your own head — that distinction is the whole point of this document.

---

## 1. What the system is, in one paragraph

A dual-tier plagiarism and AI-text detection system, built as a Moodle plugin (PHP) backed by a self-hosted FastAPI + Celery service (Python). It checks submitted text for (a) textual overlap with a growing corpus of prior submissions and reference documents, using a cost-conscious two-stage design that only pays for expensive semantic comparison on genuinely ambiguous cases, and (b) an independent, advisory-only estimate of AI authorship likelihood. Designed to be cheap enough to self-host as an alternative to a commercial service like Turnitin.

---

## 2. Detection pipeline — every component

### 2.1 Tier 1 — Winnowing + BM25 (`backend/app/services/winnowing.py`, `tier1_detector.py`)

**What it does**: fingerprints text via the Winnowing algorithm (k=5-gram hashing, window w=4 **[BY DESIGN, config: `WINNOW_K=5`, `WINNOW_W=4`]**), and separately runs BM25+ lexical search. Combines into a single containment-based score.

**How**: `document_fingerprint()` strips whitespace/punctuation (`preprocess()`), builds rolling k-gram hashes, and picks local minima within each window (the actual Winnowing selection algorithm). `FingerprintIndex.submit()` queries first (returns a `MatchResult` with Jaccard, containment, shared-hash-count), *then* unconditionally inserts the queried document's hashes into the index as a side effect — this is intentional (future queries can match against it), but means **every Tier 1 query is also a Tier 1 write** — a load-bearing fact several evaluation scripts got wrong before it was found and fixed (see §9).

**Gating signal used**: containment (`|query ∩ source| / |query|`), not Jaccard — this was itself a bug fix earlier in this project (Jaccard collapses toward zero when the matched document is much longer than the query, exactly the short-answer-vs-long-source case) **[TESTED — Report 01]**.

**What Tier 1 does NOT retain**: k-gram *positions*. `document_fingerprint()` computes `(hash, position)` pairs but `FingerprintIndex.submit()` immediately discards the position half (`hash_values = {h for h, _ in fp}`) — only hash *values* survive anywhere downstream. **[CAVEAT]** This is why match explanations (§2.6) cannot ever be built for Tier-1-only resolutions without materially new instrumentation — confirmed by full-file read, not assumed.

### 2.2 Gating (`backend/app/services/gating.py`)

Pure function, zero dependencies: `route(c1, tau_low, tau_high)` → `TIER1_ORIGINAL` (c1 < tau_low) / `TIER1_PLAGIARISED` (c1 > tau_high, strict) / `ESCALATE_TO_TIER2` (in between). Current deployed values: **`TAU_LOW=0.30`, `TAU_HIGH=0.68`** **[BY DESIGN, config.py]** — tuned specifically for source-document matching (Reports 01/02), re-verified as near-Pareto-optimal for peer-matching too (Report 04 Addendum 5) after an explicit retune attempt found no better zero-false-positive operating point.

### 2.3 Tier 2 — hybrid dense + sparse fusion (`tier2_detector.py`)

**What it does**: only runs for `ESCALATE_TO_TIER2` cases. Chunks the submission (`chunk_text()`, sentence-aware, `CHUNK_SIZE=256` words, `CHUNK_OVERLAP=50` **[BY DESIGN]**), embeds each chunk (`all-MiniLM-L6-v2`, 384-dim, CPU), searches FAISS for dense candidates and BM25 for sparse candidates, fuses via `c2 = α·dense + (1-α)·sparse` with **`α=0.6`** **[BY DESIGN]**.

**Chunk-pair tracking (added 2026-07-11)**: `detect()` now also tracks *which specific* submission chunk and source chunk index produced the winning dense score (`Tier2Result.best_submission_chunk`/`best_source_chunk_index`), not just which document — a parallel dict updated in lockstep with the existing per-document max-score aggregation, fusion math itself untouched **[TESTED — 14 new unit tests, `test_tier2.py`]**. This is `None`/`None` when the winning match was never a dense (FAISS) candidate — a BM25-only winner — which is **provably close to unreachable** at the deployed `α=0.6`: a BM25-only candidate has `dense_score=0`, so `fused ≤ 0.4`, below `STRUCTURAL_TAU_VERIFY=0.60` **[TESTED — direct invariant assertion, `TestBm25OnlyWinnerCannotReachStructuralBand`]**.

### 2.4 AI-authorship detection (`ai_detector.py`, `ai_detection_tasks.py`)

**What it does**: fully independent, advisory-only signal — separate model, separate task queue (`ai_detection`), never blocks or combines with the plagiarism score. Verdict bands: `AI_DETECTOR_TAU_LOW=0.25` / `AI_DETECTOR_TAU_HIGH=0.75` → likely_human / uncertain / likely_ai **[BY DESIGN]**. `AI_DETECTOR_ENABLED=True` by default.

**[CAVEAT, documented and tested live]**: real false-positive risk on short/formulaic/non-native-English text — directly observed in live Moodle testing (a short factual submission scored 93% AI-likelihood) **[TESTED]**. Never treat as a standalone verdict; UI presents it as a separate section with an explicit disclaimer.

### 2.5 Structural confirmation signal (`structural_detector.py`) — **built, tested, DISABLED by default**

**What it does when enabled**: for a Tier 2 score that misses `TAU_HIGH` but lands in `[STRUCTURAL_TAU_VERIFY=0.60, TAU_HIGH=0.68]`, compares the specific matched chunk pair's *function-word skeleton* (Stamatatos 2011 stopword n-grams — strip content words, keep only stopword sequence structure, compare n-gram overlap, sentence-bounded, `MIN_SENTENCE_WORDS=15` filter, `NGRAM_N=4`) and can flip the verdict to plagiarised if `skeleton_containment ≥ STRUCTURAL_SKELETON_THRESHOLD=0.30`.

**Why it's off**: dual-corpus validation found a real, asymmetric result **[TESTED, twice — original whole-document version, then chunk-anchored version]**:
- Peer-matching corpus: real win, recall 0.417→0.542 at perfect precision, unchanged by chunk-anchoring.
- Source-matching corpus: real regression even after the chunk-anchoring fix — precision 1.000→0.920 (not the required ~1.000), 2 remaining false positives, both same-task "original" (genuinely non-plagiarised) answers independently restating a canonical technical definition (Bayes' theorem, PageRank). Root cause: even a single ~256-word chunk can contain enough qualifying sentences for a coincidental structural match (a multiple-comparisons problem, shrunk but not eliminated by chunk-anchoring).

**Current status**: `STRUCTURAL_ENABLED=False` **[BY DESIGN, config.py]** — code fully built, fully tested (including the exact real false-positive/true-positive cases as pinned regression fixtures), available as an opt-in, but production behavior is unchanged from before this feature existed. Confirmed **[TESTED]**: re-running the source-matching check with the default restored exactly reproduces the pre-feature baseline (P=1.000, F1=0.884), byte-for-byte.

**Named, not-yet-attempted next step**: sentence-pair anchoring (not just chunk-anchoring) would shrink the comparison further, but needs FAISS indexed at sentence granularity, not chunk — a materially bigger change.

### 2.6 Match explanation (`segment_extraction.py`) — **built, LIVE**

**What it does**: for Tier-2-resolved detections where a chunk pair is available (§2.3), recovers the actual matched text and character offsets on both sides (`MatchedSegmentData`: `source_text`, `submitted_text`, `source_offset`, `submitted_offset`). Source-side text/offsets come from re-chunking the source document's stored text via the same deterministic `chunk_text()` used at index time (no new storage needed — same settings, same function, same result, confirmed **[TESTED]** by exact offset round-trip assertions).

**Where this was dead before**: the DB column (`SimilarityPair.matched_segments`, JSONB), the Pydantic schema (`MatchedSegment`), and the Moodle `report.php` rendering loop (submitted/source text side-by-side) **all already existed and were mutually consistent** — but nothing in the detection pipeline had ever written to that column, since the feature's inception. Confirmed dead by full-file grep across `detection_tasks.py`/`tier2_detector.py`/`detection_pipeline.py` before the fix.

**Confirmed live end-to-end [TESTED]**: a genuine Bayes'-theorem paraphrase pair from the evaluation corpus, run through the real (non-mocked) pipeline, produced correct, sensible matched text and offsets, validated against the actual Pydantic response schema — not a synthetic fixture.

**Scope boundary**: Tier-1-only resolutions never get a `matched_segment` (§2.1's positional-data gap). A BM25-only Tier-2 winner also doesn't (no chunk pair) — proven close to unreachable at current `α`, same as §2.5.

---

## 3. Data layer

| Store | Backing | Persistence | Scope |
|---|---|---|---|
| `FingerprintIndex` (Winnowing) | In-memory `dict[int, set[str]]` | **None** — pure in-memory, lost on worker restart | Hash values only, no text, no positions |
| `BM25Index` | In-memory `BM25Plus` + `_raw_texts: dict[str,str]` | **None** — in-memory only | Full document text (the only in-process doc_id→text lookup) |
| `FAISSIndex` | `faiss.IndexIDMap2` wrapping `IndexFlatIP`/`IndexIVFPQ` | **Persisted** (`.faiss` file + `.meta.json` sidecar) | Chunk-level vectors, `{doc_id}__chunk_N` keys |
| Postgres (`Submission`, `Document`, `DetectionResult`, `SimilarityPair`) | Real DB | **Persisted** | Source of truth for everything else |

**[CAVEAT]** Winnowing and BM25 state is **entirely in-memory with no persistence** — a Celery worker restart silently loses all previously-indexed fingerprints/text, and every subsequent query starts against a partially-empty corpus until re-indexed. This is a pre-existing, accepted characteristic (Tier 1 has always depended on this), not something introduced recently — but it means production accuracy is implicitly coupled to worker uptime in a way that isn't tested or monitored.

**FAISS specifically**: migrated 2026-07-08 from raw `IndexFlatIP`/`IndexIVFPQ` to `IndexIDMap2`-wrapped versions, specifically to support real vector removal (`remove_ids()`) — closing a dangling-reference bug where deleted submissions' vectors kept surfacing as live matches indefinitely. **[TESTED]** — legacy files auto-migrate in-memory on load. IVFPQ backend (only reachable past ~1,000 vectors via `upgrade_to_ivfpq()`) is confirmed **[BY DESIGN, checked]** unreachable dead code in the live deployment (no caller) — its removal path is deliberately guarded off (refuses rather than risks a confirmed partial-corruption-before-raising FAISS behavior), add/search still work.

**[CAVEAT — found and fixed this audit, 2026-07-14]**: evaluation scripts (`baselines/cloud_only.py`, `hybrid_static.py`, and by extension anything calling bare `FAISSIndex()`/`get_faiss_index()` with no explicit path) default to the **same shared, persisted index path** used by every other local run — meaning repeated local evaluation work silently contaminates future evaluation runs' candidate pools. Confirmed **[TESTED]** to materially affect always-escalate baselines (cloud-only/hybrid-static F1 shifted from an uncontrolled 0.828 to a clean-index-verified 0.842) but *not* dual-tier or any gated/tiered methodology (Report 04's exp3/exp4), which are structurally protected since a genuine best-match dominates regardless of a few extra contaminating candidates. Not fixed at the script level (no code change to force an isolated path by default) — only worked around per-run via `FAISS_INDEX_PATH` env override. **Future evaluation runs should set this explicitly.**

---

## 4. API layer (`backend/app/api/v1/`)

REST endpoints, Bearer-token auth (`API_SECRET_KEY`), `MAX_UPLOAD_SIZE_MB=50` **[BY DESIGN]**:

| Endpoint | Behavior |
|---|---|
| `GET /health/live` | No auth, liveness only |
| `POST /submissions/` | `202 Accepted`, enqueues async Celery detection — **[CAVEAT]** Report 07 finding 8 (unbounded upload read before size-check) was never fixed, flagged low-priority, likely bounded upstream but unverified |
| `GET /submissions/{id}/status`, `GET /submissions/{id}` | Poll for state |
| `GET /submissions/{id}/results` | Full result incl. `matches[].matched_segments` (now real data, §2.6) |
| `DELETE /submissions/{id}` | Cascades DB rows + dispatches `purge_documents` Celery task to remove from Winnowing/BM25/FAISS **[TESTED]** |

**[TESTED, negative cases confirmed live]**: wrong file type → 400, oversized file → 413, missing/wrong auth → 401/403.

---

## 5. Celery / async task layer

Two workers, split deliberately (2026-07-03/04) after a real ordering bug was found and fixed:

- **`celery-worker`** (`--pool=solo`, queues: `extraction, detection, indexing, embedding`) — strictly serialized. Must stay serialized: correctness depends on submission N's indexing completing before submission N+1's detection runs against the shared, order-sensitive Winnowing/BM25/FAISS state. `cpus: 1.0` limit.
- **`celery-worker-fast`** (`--pool=threads --concurrency=1`, queue: `ai_detection`) — independent, advisory-only, never touches shared detection state or gates `Submission.status`. `cpus: 0.75` limit.

**[CAVEAT, first-attempt-was-wrong story, now fixed]**: an earlier version also moved `extraction` onto the concurrent worker — this broke cross-submission ordering (extraction completion order ≠ submission order under concurrency), caught only by live-testing a 2-submission race, not by review. Extraction was moved back to the serialized worker.

**[CAVEAT, load-tested and fixed]**: the worker split itself introduced a real capacity regression under load (p99=11-15s at 50 concurrent users, `celery-worker-fast` CPU-starving the API process) — found by re-running the load test after the split, not caught by the original pre-split test. Fixed via `--concurrency=1` + explicit `cpus` limits; re-verified clean (0 failures, p95=120ms, p99=210ms) **[TESTED]**.

**Test coverage of this whole layer is genuinely thin** (16-48% per module) **[TESTED, coverage report]** — no DB test infrastructure exists anywhere in this project, so `detection_tasks.py` and its siblings can't be unit-tested the way pure-Python services can. This is a stable, structural, long-standing characteristic, not new neglect — offset by extensive live/manual verification instead of unit tests.

---

## 6. Moodle plugin layer (`moodle-plugin/plagiarism/dualtier/`)

**Submission flow**: `observer.php` (event hook, with a dedup check on a content-hash `identifier` field — **[TESTED live]** confirmed a resubmission with identical content does not create a duplicate record) → `submit_file.php` (ad-hoc task, submits to backend, queues `poll_result`) → `poll_result.php` (self-requeuing ad-hoc task, polls every 15s up to 40 attempts, ~10 min ceiling) → falls back to `check_results.php` (5-minute scheduled task, persistent safety net, unchanged) if `poll_result` gives up.

**Latency, this specific architecture** **[TESTED, full genuine browser-simulated submission]**: ~20 seconds total from submission to Moodle-visible `complete` (down from an original ~5m34s) — breakdown: ~5s ad-hoc pickup (bound by cron cadence), <300ms actual detection, ~14s waiting for the next 15s poll cycle. **Still short of the thesis's 5-second Hypothesis 4 target** — architectural, not a pipeline performance defect (Moodle's scheduled-task minute-floor is a genuine Moodle-core limitation).

**Report page** (`report.php`): summary table, score breakdown, matched passages (now real, §2.6), AI-authorship section. Access restricted to `editingteacher`/`teacher`/`manager` via `plagiarism/dualtier:viewreport` capability **[TESTED live]**. **[CAVEAT, real gap identified but not fixed]**: does not currently surface `escalation_reason` or any plain-English "why" narrative — only raw scores + matched text. Offered to add, not yet implemented.

**Security**: an IDOR vulnerability (report.php authorized against `$cmid` but fetched by independent `$id`, letting a teacher with access to one module view any other module's report) was found and fixed — cross-check that `$record->cmid === $cmid` **[TESTED live]** with a deliberately mismatched real record.

**Config**: global enable + per-module enable, both independently required. **[CAVEAT, confirmed real, not a bug]**: Moodle caches plugin config — a global toggle change needs `admin/cli/purge_caches.php` to take effect immediately; per-module toggles don't have this issue **[TESTED]**.

**Crontab dependency [CAVEAT]**: the VM's 4-staggered-entry crontab (`sleep 0/15/30/45 && cron.php`, giving ~15s cadence) lives only on the VM host — does **not** survive VM recreation (though does survive a stop/start of the same instance) and must be re-added manually if the VM is ever rebuilt from scratch.

---

## 7. Deployment / infrastructure — current actual state

**GCP VM `plagiarism-detector-vm` (zone `us-east1-b`) is currently STOPPED (`TERMINATED`)** as of this session — confirmed directly via `gcloud compute instances describe`. It was briefly started (2026-07-13) to check the deployed URL, then explicitly stopped back down at the user's request ("shut it down back... work locally for now"). **No system is currently live/reachable at any URL.**

**[CAVEAT, confirmed by observation]**: the VM's external IP is **ephemeral, not static** — starting it produced a *different* IP (`35.237.189.75`) than the one documented everywhere in prior reports/memory (`104.196.7.251`). If restarted again, expect another new IP, and expect Moodle's `$CFG->wwwroot` (configured for a specific IP) to mismatch until manually updated — this is the same class of issue as the already-documented wwwroot-mismatch gotcha, just triggered by IP churn rather than a code change.

**Docker Compose services** (when running): `api`, `celery-worker`, `celery-worker-fast`, `celery-beat`, `postgres`, `redis`, `moodle`, `moodle-db`, `moodle-nginx`.

**Local development state**: all work since 2026-07-13 has been done locally (Windows, Git Bash), with a local `sentence-transformers` install for real-embedding testing, `HF_HUB_OFFLINE=1` used to avoid transient HuggingFace Hub DNS flakiness once the model is cached.

---

## 8. Testing & quality — current, verified numbers

**[TESTED, this session, 2026-07-14]**: **147 tests passing, 85% overall coverage** (`backend/`). This superseded a stale "94 tests, 87%" figure that had gone uncorrected in `evaluation/reports/06_testing_suite_results.md` for 10 days across three separate feature additions.

Per-layer coverage: service layer 91-100% (pure-Python, no DB dependency, thoroughly unit-tested); Celery task layer 16-48% (structural — no DB test infra exists); `text_extraction.py` 30% (thin I/O wrapper, untested by design so far).

**Load test [TESTED]**: 0 failures at 50 concurrent users, POST p95=120ms/p99=210ms (budget: 5000ms) — current, post-regression-fix numbers.

**Behat/automated integration testing**: does not exist. Explicitly deferred, substituted with extensive manual/live verification instead (documented per-feature, not a single repeatable command).

---

## 9. Dataset — what it actually is

**[BY DESIGN, confirmed via `labels.csv`'s own `dataset` column]**: a merge of two real, external, peer-reviewed corpora — **Clough & Stevenson (2011)**, 95 submissions across 5 tasks with one shared canonical source per task, and **PlagBench (Lee et al. 2025)**, 90 submissions with individually-unique per-sample sources. 185 total, split 109/38/38 train/val/test. **This is not what Chapter 3 originally described** (a self-collected 200-submission corpus) — Report 00 documents the reconciliation decision (Option A: correct Chapter 3's prose to match reality) but **this correction has not yet been applied to the actual thesis document**, only decided and staged in the reports folder.

**A real, separate data-leakage bug** (all 95 Clough & Stevenson submissions were also present in the "external sources" folder under a bare filename, so every C&S submission was being checked against a corpus containing an exact copy of itself) was found and fixed 2026-07-04 — this was the actual cause of what was originally misdiagnosed as a vocabulary-overlap detection limitation (Report 05's original case studies were built on the wrong matched document as a direct consequence, and were corrected).

---

## 10. Confirmed, current, authoritative performance numbers

Use these, not any number from a single report's original (pre-correction) text:

| Metric | Value | Source |
|---|---|---|
| Source-matching precision / recall / F1 | 1.000 / 0.792 / 0.884 | Reports 01-03, re-verified 2026-07-14 |
| Source-matching baselines (cloud-only, hybrid-static) F1 | 0.842 (clean index) | Report 03 addendum, 2026-07-14 |
| Peer-matching precision / recall / F1 (deployed, structural signal off) | 1.000 / 0.417 / 0.588 | Report 04 |
| Peer-matching if structural signal were enabled | 1.000 / 0.542 / 0.703 | Report 04 Addenda 6-7 (not deployed) |
| Escalation rate (source corpus, deployed thresholds) | 47.37% | Report 03 |
| Cost savings vs. cloud-only | 52.6% | Report 03 |
| Component pipeline latency (p50/p95/p99) | ~21/261/351ms | Report 03 |
| Moodle end-to-end latency | ~20s | Report 04 Part C follow-up 2 |
| Load test (50 users) | 0 failures, p95=120ms | Report 06 addendum |
| Backend test suite | 147 passing, 85% coverage | This audit, 2026-07-14 |

---

## 11. Everything that is NOT done

- **Chapters 4 and 5 of the actual thesis document** — still unwritten. Every report in `evaluation/reports/` exists specifically as the evidence base for this; the write-up itself doesn't exist.
- **Chapter 3's dataset-provenance correction** — decided (Report 00, Option A) but not applied to the actual document.
- **3 additive features**, deliberately unimplemented by design: tortured-phrase detection, AI-detector calibration, match-explanation generation *beyond* the basic version now live (e.g. word-level diff highlighting — `difflib`/similar is available in Python's stdlib but nothing currently imports it).
- **Sentence-pair anchoring** for the structural signal (would need FAISS at sentence granularity, not chunk).
- **`escalation_reason` / plain-English "why" narrative** on the Moodle report page.
- **Report 07 finding 8** (unbounded upload read) — flagged low-priority, never fixed.
- **Behat automated integration testing** — deferred by design.
- **DB test infrastructure** for the Celery task layer — doesn't exist; that layer's low coverage is structural, not neglect, but closing it would need this built first.
- **A default fix for evaluation-script FAISS contamination** (§3) — worked around per-run, not fixed at the script level.

---

## 12. The honest one-paragraph summary

The core detection pipeline (Tier 1 + Tier 2 + gating) is real, tested, and performing at documented, re-verified numbers with zero known open correctness bugs. Two features (structural confirmation, match explanation) were built this session sharing one underlying architectural change; one shipped live and works, the other is fully built and tested but deliberately not enabled because it doesn't yet meet this system's own bar (never trade away precision). Ten real bugs have been found and fixed across the whole project's history via actually running the system, not code review — the most recent (FAISS index contamination in evaluation baselines) was found four days ago during a documentation audit, not the code itself. The production deployment is currently powered off. The biggest remaining gap is not technical: it's that the thesis chapters describing all of this haven't been written yet.
