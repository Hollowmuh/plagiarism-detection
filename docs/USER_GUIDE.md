# Dual-Tier Plagiarism Detection System — User Guide

This guide covers every feature of the system from each user's perspective (student, teacher, administrator, API integrator), how to use it, and what to expect. Every feature described here was verified working against a live deployment on 2026-07-04 — see the "Verification" note under each section for what was actually tested and how.

## 1. What this system does

A dual-tier plagiarism and AI-content detection system, deployed as a Moodle plugin backed by a self-hosted FastAPI service. It checks student submissions for:
1. **Plagiarism / textual similarity** — against a growing corpus of previously-submitted work and known reference documents, using a cost-conscious two-tier design (cheap local checks first, escalating to more expensive checks only when genuinely ambiguous).
2. **Likely AI-generated authorship** — an independent, advisory-only signal, never used to gate or auto-fail a submission.

It is designed to be affordable to self-host (no per-submission cloud API cost for the majority of submissions) rather than relying on a commercial service like Turnitin.

## 2. How detection works (what happens after you submit)

1. **Tier 1 (local, fast, free):** the submission's text is fingerprinted (Winnowing algorithm) and checked against BM25 lexical search over the existing corpus. If the resulting confidence score is clearly low (below `τ_low`) or clearly high (above `τ_high`), the submission is resolved immediately — no further processing.
2. **Escalation (only for ambiguous cases):** if Tier 1's score falls in between the two thresholds, the submission escalates to **Tier 2** — a hybrid dense (FAISS semantic embeddings) + sparse (BM25) similarity search, fused into a single confidence score.
3. **AI-detection (parallel, independent):** at the same time, a separate signal estimates the likelihood the text was AI-generated. This never blocks or delays the plagiarism result, and is never combined into the same score — it's shown as a separate, clearly-labelled advisory badge.
4. **Indexing:** once resolved, the submission's own content is added to the corpus, so it can be matched against by future submissions (this is what "cross-submission" checking means — catching students copying from each other, not just from external sources).

**Verification:** the full pipeline (Tier 1 → escalation → Tier 2 → AI-detection → indexing) was re-verified end-to-end on 2026-07-04 via a genuine Moodle submission (see §3below) and via direct API calls; per-tier accuracy numbers are in `evaluation/reports/02_exp1_tier_resolution.md` and `03_exp2_cost_accuracy.md`.

## 3. For students

### Submitting work
Submit normally through the Moodle assignment — either as a file (PDF, DOCX, or TXT) or as online text, whichever the assignment allows. Nothing extra is required; submission triggers detection automatically in the background.

### The disclosure notice
Before submitting, you'll see a notice on the assignment page:
> *"Your submission will be checked for originality using the Dual-Tier plagiarism detection system. Submitted files are analysed and compared against other submissions."*

This is shown automatically whenever the plugin is enabled for an assignment — you don't need to do anything, it's informational.

### Seeing your own result
After your submission is processed (usually **under a minute**, see §7 for the exact timing breakdown), a colored badge appears on your submission page:
- **Green** — low similarity score.
- **Orange** — moderate score.
- **Red** — high score.
- The badge text shows the percentage and which tier resolved it, e.g. `12% (tier1)` or `68% (tier2)`.

A second, visually distinct badge may appear alongside it: **`AI: NN%`** — the advisory AI-authorship likelihood. This is a separate signal from the similarity score and is never combined with it. **Read this with caution**: AI-detectors are documented in the literature to have real false-positive risk, especially on short, formulaic, or non-native-English text — this badge is a conversation-starter for a teacher, not proof of anything on its own.

Clicking either badge takes you to the same detailed report page (visible to teachers; see §4 for what it shows — students see the badge but the detailed report requires the `viewreport` capability, which is not granted to the student role by default).

**Verification:** both the disclosure notice and both badge types were confirmed rendering correctly on a live assignment page on 2026-07-04 (file submission scored 0%/tier1, AI-detection showed 93% on the same short factual text — a real, useful illustration of the AI-detector's documented false-positive risk on short text, not a system malfunction).

## 4. For teachers

### Viewing results
The same colored badge (and AI badge, if present) appears on the assignment grading page for every student's submission. Click through to the **report page** for the full breakdown:
- Overall status, similarity score, tier resolved, and plagiarised/not-plagiarised verdict.
- Tier 1 score, Tier 2 score (if escalated), final fused score, and processing time.
- **Matched passages** — side-by-side comparison of the submitted text against the specific source/peer text it matched, when available.
- A separate **AI-authorship section** (score, verdict, model used, and a disclaimer) if AI-detection is enabled.

**Report page access is restricted** to `editingteacher`, `teacher`, and `manager` roles by default (`plagiarism/dualtier:viewreport` capability) — students cannot view the detailed report even for their own submission, only the summary badge.

**Verification (2026-07-04):** confirmed the report page renders all three sections correctly for an authorized teacher request. Also specifically verified a security fix: the report page checks that the record you're requesting actually belongs to the course module you have permission for — requesting a real record with a *different*, mismatched (but otherwise valid) module id correctly returns "Report record does not belong to the specified course module" rather than leaking another module's data.

### Enabling/disabling per assignment
In the assignment settings, under "Dual-Tier Plagiarism Detection," toggle "Enable for this activity." This is per-module — you can run detection on some assignments and not others in the same course.

**Verification:** confirmed live — disabling per-module config immediately hides the badge on that assignment (verified by direct toggle + page re-fetch); re-enabling restores it.

**Operational note:** Moodle caches plugin configuration. If you change the *global* enable/disable setting (admin-level, not per-assignment) and don't see it take effect immediately, purge Moodle's caches (Site administration → Development → Purge caches). Per-assignment toggles do not have this issue — they took effect immediately in testing.

## 5. For administrators

### Global configuration
Under **Site administration → Plugins → Plagiarism → Dual-Tier Plagiarism Detection**:
- **Enable plugin** — global on/off switch. Must be on *and* the per-module setting enabled for detection to run on a given assignment.
- **API URL** — the backend FastAPI service's base URL (Docker service name internally, e.g. `http://api:8000/api/v1`).
- **API key** — must match the backend's `API_SECRET_KEY`.
- Moodle's own master switch, `$CFG->enableplagiarism`, must also be on for any plagiarism-plugin badges to render anywhere in Moodle (this is a Moodle-core setting, separate from this plugin's own enable switch).

### Deployment architecture
Docker Compose services:
- `api` — FastAPI backend, handles submission intake, status/results queries.
- `celery-worker` — handles extraction → detection → indexing, deliberately single-threaded (`--pool=solo`). This is not a performance oversight: detection reads and indexing writes the same shared in-memory search indices, so this chain must stay serialized to guarantee correctness (a submission is always fully indexed before the next one's detection runs). Capped to 1 CPU.
- `celery-worker-fast` — handles the independent AI-detection signal only, with light concurrency (1 thread, capped to 0.75 CPU) — safe to parallelize because it never touches the shared detection state and never blocks anything.
- `celery-beat` — Celery's own scheduler (for the `check_results` fallback task, see §7).
- `postgres`, `redis` — application database and Celery broker.
- `moodle`, `moodle-db`, `moodle-nginx` — the Moodle instance itself.

**Do not increase `celery-worker`'s concurrency or move `extraction`/`detection`/`indexing` onto a concurrent worker** — this was tried and reverted after live testing showed it breaks cross-submission ordering (a later submission could be checked before an earlier one finishes indexing, missing a genuine match). See `evaluation/reports/04_exp3_threshold_sensitivity.md`'s Addendum 2 for the full story.

### Thresholds and tuning
Key settings (`backend/app/config.py`):
- `TAU_LOW` (default 0.30) / `TAU_HIGH` (default 0.68) — the Tier 1 gating thresholds. Below `TAU_LOW`: resolved as original. Above `TAU_HIGH`: resolved as plagiarised. In between: escalates to Tier 2.
- `ALPHA` (default 0.6) — Tier 2's dense/sparse fusion weight (`final = α·dense + (1-α)·sparse`).
- `AI_DETECTOR_TAU_LOW` / `AI_DETECTOR_TAU_HIGH` (0.25/0.75) — AI-detection's own three-way verdict bands (`likely_human` / `uncertain` / `likely_ai`).

These were empirically re-tuned on 2026-07-04 after a dataset-construction bug was fixed in evaluation — see `evaluation/reports/02_exp1_tier_resolution.md` for the full methodology if re-tuning again in future (don't guess new values without re-running the threshold sweep script, `evaluation/experiments/exp1b_threshold_resweep.py`).

## 6. API reference (for direct integration, outside Moodle)

Base path: `/api/v1`. All endpoints except the health check require `Authorization: Bearer <API_SECRET_KEY>`.

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/health/live` | Liveness check, no auth required. Returns `{"status": "alive"}`. |
| `POST` | `/submissions/` | Submit a document. Multipart form: `file` (PDF/DOCX/TXT, ≤50MB), optional `course_id`/`assignment_id`/`user_id`. Returns `202 Accepted` with a `submission_id` immediately; processing is async. |
| `GET` | `/submissions/{id}/status` | Lightweight poll: `status` (`pending`/`extracting`/`detecting`/`completed`/`failed`), `tier_resolved`, `processing_time_ms`. |
| `GET` | `/submissions/{id}` | Full submission record: status, course/assignment/user ids, timestamps, error message if failed. |
| `GET` | `/submissions/{id}/results` | Full detection results (only available once `status=completed`, else `409`): scores, tier, plagiarised verdict, matched passages, AI-detection. |
| `DELETE` | `/submissions/{id}` | Deletes the submission and purges it from the detection indices (see below) so it's no longer matchable by future submissions. `204 No Content`. |

**Verification (2026-07-04):** every endpoint above was directly tested against the live deployment, including the negative cases: unsupported file type → `400`, oversized file (tested at 51MB against the 50MB limit) → `413`, missing auth → `401`, wrong API key → `403`.

### A note on deletion and data removal
Deleting a submission removes it from the database *and* from the in-memory Winnowing/BM25/FAISS search indices (dispatched as a background task so this happens in the same process that holds the real, populated indices — a subtlety worth knowing if you're extending this: the indices are per-process singletons with no shared memory between the API and worker containers, so index mutations must happen inside a Celery task, not directly in an API route handler). FAISS (dense embedding) vectors are removed via `faiss.IndexIDMap2`'s native `remove_ids()` (as of 2026-07-08 — previously not possible without a full index rebuild, which meant a deleted submission's dense vector kept surfacing as a live match candidate indefinitely; see `evaluation/reports/07_full_pipeline_audit.md`'s follow-up for the fix).

**Verification:** confirmed directly — submitted two duplicate documents, confirmed they matched each other, deleted both, then confirmed a fresh third duplicate no longer matched anything (this predates the FAISS fix and only exercised the Winnowing/BM25 path). The FAISS-specific removal path is covered by `backend/tests/test_faiss_service.py`, including a direct test that a removed doc_id can never again be returned by `search()`, even when queried with its own former embedding.

## 7. Timing: what to expect

Two different numbers matter here, and they're not the same thing:

- **Component/pipeline latency** (how long detection itself takes, once it starts running): typically **well under 300ms**, even when escalating to Tier 2.
- **Moodle-visible end-to-end latency** (from clicking "Save changes" to the badge appearing): **~20 seconds typical**, verified via a real, complete submission on 2026-07-04. This is dominated by two polling delays, not detection itself:
  1. Up to ~15 seconds for Moodle's cron to pick up the submission and hand it to the backend (an "ad-hoc task," picked up by a cron job that now runs every ~15 seconds).
  2. Up to ~15 seconds for the result to be polled back and written to the Moodle-visible status (a fast, self-repeating background check, not the old 5-minute scheduled fallback).

A slower, 5-minute fallback check (`check_results`) still runs in the background in case the fast path is ever interrupted (e.g. a worker crash mid-submission) — you should never normally see it kick in, but it's there as a safety net.

**Verification:** the original (pre-fix) end-to-end latency was measured at ~5m34s; after the fix described above, a full genuine re-test (real login, file upload, submission, through to Moodle showing `complete`) measured **~20 seconds** — a ~16x improvement, and this is now the expected, normal timing.

## 8. Cost and capacity

- **Cost model:** only submissions that escalate to Tier 2 incur the (self-hosted, still-cheap) cost of dense embedding computation. In the last measured evaluation run, escalation rate was ~47%, giving roughly **half the cost** of always running full Tier 2 analysis on every submission, while achieving *better* accuracy (F1) than always-Tier-2 in the same test — see `evaluation/reports/03_exp2_cost_accuracy.md`.
- **Load capacity:** tested at 20 and 50 concurrent submitting users with zero failures and p95 latency around 100-200ms for the submission-acceptance endpoint (not full detection — see the pipeline-vs-end-to-end distinction in §7) on a 2-vCPU VM. See `evaluation/reports/06_testing_suite_results.md` for the full load-test writeup, including a real capacity regression that was found and fixed on 2026-07-04 (the AI-detection worker's concurrency was originally set too high for this VM's capacity — since fixed).

## 9. Known limitations (stated plainly, not hidden)

- **AI-detection has a documented false-positive risk** on short, formulaic, or non-native-English text. It is advisory-only by design specifically because of this — never treat it as a standalone verdict.
- **Cross-submission (peer-to-peer) matching is a harder problem for this system than source-matching.** Measured recall for genuine peer-submission matches tops out around 42% at the best tuned threshold, versus ~79% for matching against known external sources. This is an honest, measured limitation (see `evaluation/reports/04_exp3_threshold_sensitivity.md`), not a claim the system doesn't work — it means some genuine collusion cases will be missed, particularly in courses with few, narrow assignment topics where many students converge on similar answers independently.
- **Vector-store removal only supports the flat (small-corpus) index backend.** The IVFPQ backend used past ~1,000 vectors (`upgrade_to_ivfpq()`) is not currently wired into the live pipeline at all (no scheduler calls it), so this doesn't affect the deployed system today — but if it's ever activated, removal against an IVFPQ-backed index is deliberately refused rather than attempted, because direct testing found FAISS's IVF-family `remove_ids()` can partially corrupt the index before raising an error. This is a real, empirically-confirmed FAISS behavior (not a hypothetical), documented in `docs/2026-07-08/faiss_vector_removal_1223.md`.
- **The Celery task-orchestration layer has comparatively low automated test coverage** (~15-30% per module) — this is documented, not hidden; the layer has been extensively validated through live, end-to-end testing instead (this whole guide's "Verification" notes), which is a different (and for this kind of integration-heavy code, arguably more relevant) form of assurance than unit test coverage alone.

## 10. Troubleshooting

- **Badge never appears:** check both the global plugin enable switch and the per-assignment toggle. If you just changed the global switch, purge Moodle's caches.
- **Submission stuck in "pending"/"submitted" for more than ~1 minute:** check that the VM's crontab (`crontab -l`) has the 4 staggered `cron.php` entries — this does not survive VM recreation and must be re-added manually after any fresh provision.
- **A resubmission of unchanged content doesn't seem to do anything:** this is expected — the system deduplicates by content hash per assignment+student, so resubmitting identical content is a no-op rather than creating a redundant, cost-incurring duplicate check.
- **Report page shows "Report record does not belong to the specified course module":** this is the security check working as intended — you don't have access to view that specific record from the module you're viewing it from.
