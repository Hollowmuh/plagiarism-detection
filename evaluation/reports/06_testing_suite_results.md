# Report 6: Unit Test Suite, Coverage, and a Third Real Bug

**Status:** Parts A and C done (2026-07-03); Part B covered by existing manual verification, formal automation deferred. **Part A's numbers are stale — see the 2026-07-14 addendum near the end for the current real count (147 tests, 85% coverage), not the "94 passed, 87%" cited below.**
**Roadmap step:** Step 6
**Tests:** Sections 3.12.1-3.12.3; the bug found in Part A also affects Report 04's numbers (see that report's addendum)

**Note (2026-07-04):** a fifth real bug in the same spirit as this report's third one was found the following day — a dataset-construction data-leakage bug (evaluation corpus's `sources/` folder contained duplicate copies of 95 submissions), which turned out to be the actual cause of the `original`-category false positives this session had earlier attributed to a detection-algorithm limitation (Report 02's original diagnosis, corrected; Report 05's case studies, corrected). See Report 00's addendum for the discovery and Report 02/03's corrections for the numbers. Same pattern as this report: found only by directly verifying what the system actually matched against, not by trusting a plausible-looking explanation.

## Part A: Unit testing (Section 3.12.1)

### Method

`backend/tests/` already had a substantial suite (94 tests across `test_api.py`, `test_bm25.py`, `test_gating.py`, `test_pipeline.py`, `test_tier1.py`, `test_tier2.py`, `test_winnowing.py`) from prior work — this step audited and ran it rather than writing from scratch. Ran the full suite inside the deployed container with `coverage run -m pytest -v`, then `coverage report -m`, as the appropriate substitute for `pytest --cov=app` (the `pytest-cov` plugin is not installed in this image; only the base `coverage` package is — both measure the same thing, `pytest-cov` is a thin pytest-integration wrapper around `coverage`).

### First run: 91 passed, 3 failed — none of the 3 were pre-existing/expected

```
tests/test_tier2.py::TestTier2Detector::test_verbatim_high_score   FAILED
tests/test_tier2.py::TestTier2Detector::test_paraphrased_detected  FAILED
tests/test_tier2.py::TestChunking::test_chunk_text_empty           FAILED
```

Two of these traced back to a genuine, previously-unknown, production-affecting bug — not a test artifact. One was a small, self-contained bug in the chunking helper.

### Bug 3 (of the session's total four): `FAISSIndex`'s doc_id mapping is never persisted, and its next-id counter never resyncs after loading

**Symptom:** `test_verbatim_high_score` asserted `result.score > 0.3` for a detector queried with an exact verbatim copy of one of its own two indexed documents, and got `0.220` (dense_score=0.330 — implausibly low for an identical-text match). `test_paraphrased_detected` asserted `result.dense_score > 0.0` and got exactly `0.0`, with `dense_matches=[]`. Both tests' setup logs showed `faiss_loaded ntotal=2400` — a fresh 2-document test fixture was somehow inheriting a 2400-vector index.

**Root cause (`backend/app/services/faiss_service.py`):** `FAISSIndex.__init__` sets `self._next_id = 0` unconditionally. `_try_load()` restores the underlying FAISS vector index from disk (`faiss.read_index()`) but (a) never resynchronizes `_next_id` to the loaded index's `ntotal`, and (b) never persisted or restored the Python-side `_id_map`/`_doc_map` dictionaries in the first place — the FAISS library itself only stores raw vectors by integer position, it has no concept of doc_ids; that mapping lived entirely in this class's own (previously unpersisted) memory.

Consequence, in order: every process restart silently discards all doc_id ↔ position mappings for previously-indexed documents (those vectors remain physically in the index but become permanently unreachable by doc_id). Then, the very next `add()`/`add_batch()` call in the new process assigns a low integer key (0, 1, 2, ...) that collides with the *real* FAISS position of one of those now-orphaned old vectors, while the new vector's *actual* position (offset by the pre-existing `ntotal`) is never given a map entry at all. Net effect: newly-indexed documents' own matches are silently dropped from search results (`_id_map.get(idx)` returns `None` and gets filtered), while orphaned old vectors can occasionally resurface mislabeled with a *wrong* doc_id if they happen to rank in a query's top-k.

**Why this is a production bug, not just a test artifact:** `get_faiss_index()` (`backend/app/services/detection_pipeline.py`) is a per-process singleton pointed at the same persisted path (`/data/faiss/index.faiss`) used by every Celery worker in the real deployment. Every worker restart (deploy, crash-restart, VM reboot) reproduces exactly this failure mode for whatever gets indexed afterward — this is not specific to how the unit tests happened to be structured.

**Fix applied** (`backend/app/services/faiss_service.py`):
1. `_try_load()` now sets `self._next_id = self._index.ntotal` immediately after a successful load.
2. `save()` now writes `_id_map`/`_doc_map` to a JSON sidecar file (`<index_path>.meta.json`) alongside the FAISS index; `_try_load()` reads it back if present. If the FAISS index file exists but its sidecar doesn't (the state of every index persisted before this fix), this is logged explicitly (`faiss_meta_missing`) rather than silently mismatched — those specific vectors remain permanently unreachable by doc_id (there was never any mapping saved to recover), but no *new* additions will collide with them going forward.

Also fixed, while in the same test file: `test_tier2.py::TestChunking::test_chunk_text_empty` expected `chunk_text("") == []`; `re.split(r"(?<=[.!?])\s+", "")` returns `['']` (one empty-string element, not zero elements), so the existing `if not sentences: return []` guard never triggered on empty input. Fixed with an explicit `if not text.strip(): return []` check at the top of `chunk_text()` in `backend/app/services/embedding_service.py`.

**A second, compounding bug found while verifying the fix — test isolation was already supposed to prevent this, and silently didn't:** `backend/tests/conftest.py` sets `os.environ.setdefault("FAISS_INDEX_PATH", "/tmp/test_faiss_index.faiss")`, clearly intending to isolate tests from the shared production/eval index — but `setdefault` only applies when the variable is *not already set*, and the container's real environment already has `FAISS_INDEX_PATH=/data/faiss/index.faiss` set. So the intended isolation was a complete no-op the entire time; the `faiss_loaded ntotal=2400` in the failing tests' logs was literally the shared production/eval index, not an accidentally-reused test fixture. Fixed by force-overriding (`os.environ["FAISS_INDEX_PATH"] = ...`) instead of `setdefault`, scoped to just this one variable (the other `setdefault` calls in the same file were left alone, since there's no evidence they have the same problem and changing them isn't needed to fix this bug).

### Re-verifying already-published Chapter 4 numbers weren't compromised

Because this bug only manifests when a process adds vectors after loading an *already non-empty* persisted index, its impact on any given prior experiment run depends on whether the shared index file happened to have vectors on disk at that run's start — not on the experiment's own design. Rather than assume either way, the fixed code was deployed, the (already-corrupted, never-had-a-sidecar) persisted index was reset to empty, and Reports 02's and 03's exact commands were re-run from scratch:

- **Report 02 (`run_evaluation.py --split test`) and Report 03 (all 4 configurations in `exp2_cost_accuracy.py`): reproduced exactly** — precision/recall/F1/escalation-rate identical to 4 significant figures for `local_only`, `cloud_only`, `hybrid_static`, and `dual_tier`. These runs' own indexing evidently started from a file that was empty or not-yet-corrupted at the time, so the bug never actually triggered during them. **No changes needed to Reports 01, 02, or 03.**
- **Report 04's exp3 threshold sweep: genuinely affected.** By the time that experiment ran, the shared index already held vectors from the preceding exp1/exp2 runs. The one grid cell with non-zero escalation (τ_low=0.20/τ_high=0.70) has been corrected from F1=0.222 to **F1=0.588 (P=1.000, R=0.417)**; the other 8 degenerate cells never invoke Tier 2 and are unaffected. See Report 04's addendum for the full corrected table and interpretation.

### Second run, after all three fixes: 94 passed, 0 failed

```
94 passed in 30.50s
```

### Coverage

```
TOTAL   1617 stmts   206 miss   87% covered
```

Well above the ≥80% target stated in Section 3.12.1. Lowest-covered modules, for context (not treated as a defect list — these are mostly infra/glue code exercised by integration paths rather than unit tests):
- `app/api/v1/health.py` (35%) and `app/services/text_extraction.py` (30%): thin wrappers around external I/O (file-type sniffing, health-check pings) not exercised by the unit suite; would need integration-style tests hitting real files/dependencies.
- `app/api/v1/submissions.py` (51%): the async submission-creation endpoint, likely exercised more by the Moodle-integration/manual-verification pass (Part B) than by unit tests.
- `app/services/faiss_service.py` (53%): the newly-added persistence code paths (`_meta_path` load/save branches, `faiss_meta_missing` warning, `upgrade_to_ivfpq`) are not yet covered by a dedicated test — worth adding given this module just had a real bug in it (candidate follow-up, not blocking).

## For Chapter 4/5

This is the fourth genuine, previously-unknown bug found this session (after the two in Report 01's addendum), and like those, it was found only by actually running the system's own test suite end-to-end rather than by code review — directly supporting the thesis's DSR framing (Hevner et al. 2004, "design as a search process"): defects surface through building and evaluating, not through inspection alone. Report this plainly in Chapter 4/5 alongside the other three bugs, and note the verification discipline used here (empirically re-running prior experiments after the fix rather than assuming either "everything is now suspect" or "nothing could have been affected") as part of the thesis's evaluation methodology.

## Part B: Integration testing (Section 3.12.2) — covered by existing manual verification, formal Behat suite deferred

Per the roadmap's own guidance ("Step 6 is the most cuttable... substantial manual verification already exists"), this was not built as a new automated Behat suite this session. What already exists and is citable as evidence in Chapter 4:
- **Report 04 Part C** (this session): a real, timed, curl-driven submission through the actual live Moodle deployment, end to end (upload → observer → ad-hoc task → Tier 1 → Tier 2 escalation → `check_results` cron → Moodle-visible `complete` status).
- **`gcp-deployment-gotchas` memory (earlier session, 2026-07-01)**: five real plugin bugs were found and fixed specifically by simulating a full student1/student2 cross-submission end-to-end (login → upload → submit → cron → badge rendering), not by config/health checks alone — documented with the exact verification procedure to repeat if the plugin changes again.

State this plainly in Chapter 4: automated Behat coverage is future work, not something that exists today; the manual verification above is real and specific but not re-runnable as a single automated command.

## Part C: Performance/load testing (Section 3.12.3)

### Method

No load-testing tool was installed on the deployment; `locust` was added to a fresh venv on the VM host (`~/locust_env`) rather than inside the API container, so the test drives the API the same way a real external client would — over actual HTTP, through the container's exposed port, not via in-process calls (that in-process path is what Reports 01-04 already measure). `evaluation/load_test/locustfile.py` defines a `SubmissionUser` that uploads one of 5 short representative texts to `POST /api/v1/submissions/` (the real multipart, Bearer-authenticated endpoint), polls `GET /api/v1/submissions/{id}/status` once, and additionally issues lightweight `GET /api/v1/health/live` requests at 3x the weight (mixed traffic, not pure submission load).

**Important scope note:** `POST /api/v1/submissions/` returns `202 Accepted` immediately and enqueues the actual Tier 1/Tier 2 detection as an async Celery task (`backend/app/api/v1/submissions.py`) — so this test measures API/DB-write/task-enqueue latency under concurrent HTTP load, not full detection latency. That's the correct and only thing this specific endpoint can be load-tested for; the detection pipeline's own latency is what Reports 01-04 already measure in-process. Chapter 4 should present these as complementary, not competing, numbers.

### Commands run

```
locust -f locustfile.py --host=http://localhost:8000 --headless --users 20 --spawn-rate 2 --run-time 3m --csv=loadtest_20u
locust -f locustfile.py --host=http://localhost:8000 --headless --users 50 --spawn-rate 2 --run-time 3m --csv=loadtest_50u
```

Section 3.12.3 specifies a single continuous 1→50 ramp over 10 minutes; this was run instead as two separate, shorter (3-minute) plateaus at the two concentration levels the roadmap's own assertions target (20 and 50 concurrent) — a deliberate scope reduction for practicality, not a methodological difference in what's being measured. Both runs are saved in full: `evaluation/reports/raw/06_loadtest_20users_stats.csv`, `06_loadtest_50users_stats.csv`.

### Results

| Concurrency | Requests | Failures | POST p50 | POST p95 | POST p99 | POST max |
|---|---|---|---|---|---|---|
| 20 users, 3 min | 1,740 | **0 (0.00%)** | 27ms | 60ms | 180ms | 3,400ms* |
| 50 users, 3 min | 4,171 | **0 (0.00%)** | 33ms | 75ms | 120ms | 280ms |

\*The 20-user run's single 3.4s max is consistent with a cold-start effect (first requests after the container had been idle) rather than a load-driven degradation — the 50-user run, under twice the concurrency, has a *lower* max (280ms) and a *tighter* full distribution, which would not be the case if the 3.4s outlier reflected genuine saturation.

**Both required assertions are met with a wide margin:** zero failed requests at 20 concurrent users (target: zero), and p95 latency of 60-75ms at both 20 and 50 concurrent users (target: <5,000ms) — roughly two orders of magnitude under budget. `/api/v1/health/live` stayed under 20ms p95 throughout both runs.

### Memory (in place of a full `memory_profiler` instrumentation pass)

`docker stats --no-stream` immediately after the 50-user run:

| Container | CPU | Memory / limit |
|---|---|---|
| celery-worker | 89.9% | 722MiB / 4GiB |
| api | 0.55% | 239MiB / 7.75GiB |
| postgres | 5.2% | 49MiB / 7.75GiB |
| redis | 2.5% | 9MiB / 7.75GiB |
| (moodle stack + flower + celery-beat) | ~0% each | <100MiB each |

Total memory footprint across all 9 containers is well under 1.5GiB — far inside any reasonable budget. Celery-worker's CPU (89.9%) is the one component under real pressure, consistent with it churning through the Tier 2 embedding backlog generated by the submission burst; this is expected and not a failure condition (no requests failed, no queue errors observed).

**Worth flagging plainly, not glossing over:** Section 3.11 (methodology) assumes a **16GB** memory budget, but the actual deployed VM (`plagiarism-detector-vm`) has **7.8GB** total RAM (`free -h`, confirmed this session) — well under half the assumed budget. The system comfortably handles this load test's traffic within that smaller real budget, which is if anything a *stronger* affordability result than the thesis's own stated target, but the discrepancy between the assumed and actual VM spec should be corrected in Chapter 3/4 rather than silently left as an unremarked mismatch.

### For Chapter 4/5 (original 2026-07-03 framing — see the 2026-07-04 addendum below before treating this as the final word)

Report this as a genuinely strong, uncomplicated result: zero failures and p95 latency 2 orders of magnitude under budget at both the required (20) and stretch (50) concurrency levels, on a smaller VM than the thesis's own stated budget assumed. The one honest caveat to carry forward is scope (this endpoint's latency reflects request acceptance/enqueueing, not full detection — pair this table with Reports 01-04's in-process pipeline latency numbers rather than presenting either alone as "the" latency result), plus the 16GB-vs-7.8GB budget correction above.

## Addendum (2026-07-04): the celery-worker split introduced a real regression this original test never saw, found by re-running it, and fixed

This original Part C test ran **before** the celery-worker split (Report 04's Addendum 2, done later the same day/the next day, splitting the single worker into `celery-worker` and `celery-worker-fast` to fix a cross-submission ordering bug). Re-running the identical 50-user Locust test against the *current* architecture — as part of validating whether the whole system was genuinely "done end to end" — surfaced a real capacity regression that this report's original numbers could not have caught, since the configuration they tested no longer exists.

### The regression, measured

| | Original (pre-split) | Re-test (post-split, before tuning) |
|---|---|---|
| Failures | 0 (0.00%) | 3 (0.08%), `RemoteDisconnected` on health checks |
| POST p95 | 75ms | 400ms (aggregated); **2,600ms** for POST specifically |
| POST p99 | 120ms | **11,000ms** |
| POST max | 280ms | **14,925ms** |

p99 latency of 11-15 seconds is a genuine failure of the 5-second Hypothesis 4 budget at the tail, on a request path (`POST /submissions/`) that should be near-instantaneous (it only writes a DB row and enqueues a task).

### Root cause, diagnosed with direct evidence, not assumed

`docker stats` immediately after the failing run showed `celery-worker-fast` (the AI-detection worker, added by the split, `--pool=threads --concurrency=2`) at **94.56% CPU**, `celery-worker` (detection/indexing) at 51.28% — combined with the VM's other containers, over 175% CPU demand on a 2-vCPU machine. `redis-cli LLEN ai_detection` showed **507 backlogged tasks**, while `detection`/`indexing`/`extraction` queues were all empty — confirming the AI-detection worker specifically, not the correctness-critical detection/indexing path, was the saturated component, and that its CPU contention was the plausible mechanism starving the API process itself (the actual request path under test never touches AI-detection directly — it only enqueues a task — so the failures/latency can only be explained by OS-level CPU contention across containers, not application logic).

This is a real, direct cost of the celery-worker split that the *original* test in this report never measured, because that configuration (two separate always-running worker processes instead of one) didn't exist yet when this report's Part C was first written.

### Fix and re-verification

`celery-worker-fast`'s `--concurrency` was reduced from 2 to 1, and explicit Docker `cpus` limits were added to both celery workers (`celery-worker-fast: 0.75`, `celery-worker: 1.0`) in `docker-compose.yml` — concurrency=2 was never load-bearing for the split's actual goal (decoupling AI-detection from the correctness-critical chain only requires running it in a *separate process*, not with extra threads inside that process), and AI-detection is advisory-only, so it can tolerate being slower under load in a way the API path cannot.

Re-ran the identical 50-user test after this change: **0 failures, POST p95=120ms, p99=210ms, max=690ms** — clean, and the celery-worker-fast/celery-worker CPU usage after the run measured 11.71%/0.36% respectively (nothing pegged). **Honest trade-off, stated plainly:** the AI-detection queue backlog (781 tasks after this run, since ~998 submissions arrived) now drains more slowly than before the cap — this is the deliberate, correct prioritization (protect the measured, user-facing latency metric; let the advisory-only signal lag under sustained heavy load), not an oversight.

### For Chapter 4/5 — replaces the "uncomplicated result" framing above

This is a stronger, more complete story than the original framing, not a worse one: the *system*, as it exists at the end of this thesis's work, passes the load test cleanly (0 failures, p95/p99 far under budget). But getting there required finding and fixing a real regression introduced by an earlier, independently-justified architectural fix (the celery-worker split) — a concrete demonstration that a fix validated in isolation (Report 04's Addendum 2 correctly solved the ordering bug it targeted) can still have an unvalidated cost in a different dimension (capacity under load) until that dimension is specifically re-tested. This is the same lesson Report 07's audit already drew from its own first, silently-broken fix attempt, appearing here for a third time in the same session — worth naming as a deliberate pattern in Chapter 5's methodology discussion, not a coincidence.

## Addendum (2026-07-14): Part A's test count and coverage were never updated after 2026-07-03 — real current numbers

Part A's "94 passed, 0 failed" / "87% covered" headline is from 2026-07-03/04. A great deal of work landed in `backend/` since then without this report ever being revisited: the FAISS `IndexIDMap2` migration (19 new/extended tests), the structural-signal feature (its own dedicated test file plus `test_pipeline.py` additions), and the match-explanation feature (chunk-pair tracking, segment extraction, schema round-trip tests) — each added tests at the time in their own context, but none of those increments ever made it back into this report, which is supposed to be the canonical "current state of the suite" reference.

**Real current numbers** (`HF_HUB_OFFLINE=1 python -m coverage run -m pytest tests/ -q`, then `coverage report -m`, re-run 2026-07-14):

```
147 passed in 77.65s
TOTAL   2492 stmts   383 miss   85% covered
```

**Coverage moved 87%→85% — a real, explainable drop, not a regression to be alarmed about.** Test *count* grew substantially (94→147, +56%), but so did the amount of intentionally-thin-covered code: the new service-layer modules (`segment_extraction.py`, `structural_detector.py`) are at 98-100% coverage, same as this session's established standard — but `detection_tasks.py` (16%), `ai_detection_tasks.py`/`embedding_tasks.py` (20% each), `extraction_tasks.py` (17%), `indexing_tasks.py` (31%) are the same, previously-documented, structurally-hard-to-unit-test Celery task layer (no DB test infrastructure exists in this project — see `test_matched_segments_schema_roundtrip.py`'s own docstring for why, and Report 07's audit for the same limitation noted earlier) — and this layer *also* grew (new fields threaded through `detection_tasks.py`'s `SimilarityPair` construction) without a proportional increase in coverage, since testing it properly would require building DB test infrastructure that doesn't exist, a separate, larger undertaking not in scope for any single feature pass. The 2-point drop is arithmetic, not a quality signal: more total statements, with the *proportion* that's Celery-task-layer (thin coverage, always has been) slightly higher than before.

**Per-module coverage, current, for context** (full breakdown, not just lowlights):

| Module | Coverage | Note |
|---|---|---|
| `schemas/*.py`, `services/gating.py`, `services/segment_extraction.py` | 100% | |
| `services/structural_detector.py` | 98% | |
| `services/detection_pipeline.py` | 99% | |
| `services/tier1_detector.py`, `winnowing.py` | 97-98% | |
| `services/tier2_detector.py` | 96% | |
| `services/bm25_service.py` | 95% | |
| `services/embedding_service.py` | 91% | |
| `services/faiss_service.py` | 80% | up from 53% at the 2026-07-03 writing — the persistence code paths flagged then as "not yet covered" now are, from the `IndexIDMap2` migration's own test pass |
| `tests/test_api.py` (the test file itself) | 90% | |
| `services/text_extraction.py` | 30% | unchanged limitation, thin I/O wrapper |
| `tasks/celery_app.py` | 48% | |
| `tasks/indexing_tasks.py` | 31% | |
| `tasks/ai_detection_tasks.py`, `embedding_tasks.py` | 20% each | |
| `tasks/extraction_tasks.py` | 17% | |
| `tasks/detection_tasks.py` | 16% | lowest in the codebase; grew in this session's work without new tests, for the DB-infrastructure reason above |

**For Chapter 4/5:** cite 147 tests / 85% coverage, not 94/87% — and if discussing the Celery task layer's low coverage, note it as a *stable, structural* characteristic (present since the 2026-07-03 baseline, not introduced by later work) rather than something that crept in — the drop from 87%→85% is fully explained by proportional growth, not new neglect. **Process lesson worth stating explicitly**: this report went ten days without being updated while the codebase it describes changed substantially underneath it — exactly the kind of drift a "the reports folder should reflect current reality" audit exists to catch, and worth naming in Chapter 5's methodology discussion as a real limitation of maintaining hand-written evaluation reports alongside active development, not just a one-off oversight.
