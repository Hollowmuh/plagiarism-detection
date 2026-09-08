# §3.3, §3.8, §3.12, §3.13 replacement/patch prose, plus final consistency pass

---

## 3.3 Case Study Context — patch

Keep the first sentence (Moodle 4.x, medium-sized university target). Replace the hardware sentence:

> ~~The system is designed for a medium-sized university processing 1,000-50,000 essay submissions per academic year, on institutional server hardware with 16-64 GB RAM, 4-8 CPU cores, and 100 GB available storage.~~
>
> The system is designed for a medium-sized university processing 1,000–50,000 essay submissions per academic year. 16–64GB RAM and 4–8 CPU cores represent a comfortable target range for institutions of that size; the live deployment used for evaluation deliberately targeted the lower end of institutional capacity rather than this comfortable range, to stress-test the affordability claim directly (see below).

Keep the GPU-optional sentence and the platform-agnostic sentence unchanged. Replace the final paragraph:

> ~~Experiments run on a single development workstation with 16 GB RAM, an Intel Core i5 processor, and a 256 GB SSD. This intentionally modest specification mirrors the lower bound of expected institutional capacity and functions as a latency stress test.~~
>
> Two environments were used. Threshold tuning and offline evaluation experiments (§3.10) ran on a local development workstation. The live system — full Docker Compose stack (FastAPI backend, two Celery workers, Redis, two PostgreSQL instances, and the complete Moodle stack) — was deployed on a Google Cloud Platform `e2-standard-2` instance: 2 vCPUs and approximately 7.8GB RAM, below even the stated institutional-capacity floor. This was a deliberate choice, not a constraint accepted reluctantly: demonstrating the full stack running comfortably on a smaller instance than the target range makes a stronger affordability claim than testing only within a comfortable margin. The live real-time demonstration reported in Chapter 4 (§3.10.3) ran entirely on this instance.

---

## 3.8 Tools and Technologies — patch

Keep the table's existing rows for Python, FastAPI, rank-bm25, sentence-transformers, FAISS, Celery+Redis, Moodle, PHP, PostgreSQL, Docker, and SciPy — all confirmed in use.

**Remove**: the SpaCy row — not used anywhere in the deployed system (see §3.6.2's correction).

**Add these rows**, all confirmed load-bearing and currently missing:

| Component | Tool / Library | Role |
|---|---|---|
| Deep learning runtime | PyTorch | Backs both sentence-transformers and the AI-authorship classifier |
| Transformer models | Hugging Face `transformers` | Loads the AI-authorship classifier (§3.4.5) |
| Cloud deployment platform | Google Cloud Platform (Compute Engine, `e2-standard-2`) | Hosts the live deployment used for the real-time demonstration |
| Reverse proxy | nginx | Fronts the Moodle container in the live deployment |

---

## 3.12 Validation and Testing

### 3.12.1 Unit Testing — patch

Keep the module list (Winnowing, BM25, embedding pipeline, FAISS wrapper, fusion, gating). Replace the coverage sentence:

> ~~Line coverage is measured with coverage.py; 80% minimum is enforced in CI on every push.~~
>
> Line coverage is measured with coverage.py; 80% was the working target, and measured coverage reached 85% overall at completion, verified via repeated local test runs (no continuous-integration pipeline was set up to enforce this automatically). Coverage is not uniform across the codebase: the core detection services (Winnowing, BM25, Tier 1/Tier 2 scoring, gating) reached 91–100% line coverage; the asynchronous task-orchestration layer, which requires a live database to test in isolation and for which no test-database infrastructure was built, reached 16–48%. That layer's correctness assurance instead came from repeated live, end-to-end verification against the deployed system, documented per feature rather than captured in a single automated metric.

### 3.12.2 Integration Testing — replace

> End-to-end tests submit known-plagiarism and known-original documents through the FastAPI endpoint and assert correct routing, correct labelling, and latency compliance. Automated Moodle-side integration testing via Behat was scoped originally but deferred as the lowest-priority item under the project's time budget; it was substituted with extensive manual verification against a live, Dockerised Moodle 4.1 instance, covering the full submission flow (event capture through result display), badge rendering for both signals, report-page access control (including a deliberately mismatched-module request to confirm cross-course access is denied), per-assignment and global enable/disable toggles, and duplicate-submission handling. This verification is real and specific, documented per feature as it was performed, but is not repeatable as a single automated command the way the Behat suite originally scoped would have been.

### 3.12.3 Performance Testing — replace

> Load testing used Locust against the live deployed API, at fixed concurrency plateaus of 20 and 50 users held for three minutes each (adapted from an originally-planned single 1→50-user ramp over ten minutes, for practicality against the deployment's own resource ceiling). The system sustained zero failed requests at 50 concurrent users, with p95 latency of approximately 120 milliseconds — two orders of magnitude inside the 5-second budget. Memory was verified directly against the live deployment (`docker stats`/`free -h`) rather than profiled with memory_profiler, confirming the full stack operates comfortably within the actual ~7.8GB deployment instance described in §3.3, not the 16GB figure used as the general institutional-capacity target. One real capacity regression was found and fixed during this testing: an earlier architectural change (splitting detection processing across two Celery workers to resolve a correctness issue) introduced CPU contention that only appeared under the 50-user load; it was caught by re-running this exact test after that change, and resolved by tuning worker concurrency and explicit CPU limits before the final measurement above.

### 3.12.4 Accuracy Validation

No change — confusion matrices and manual false-positive inspection were both genuinely performed (Chapter 4's failure-mode analysis draws directly on this).

---

## 3.13 Ethical Considerations — patch

Keep the four-safeguard structure and the data-security and avoidance-of-harm paragraphs unchanged — both remain accurate. Replace the privacy/consent paragraph:

> ~~Privacy and consent: All past course essays used in the original set are anonymised before ingestion: personal identifiers, course codes, and timestamps stripped. Departmental approval is obtained before reuse. The synthetic plagiarism set is built from publicly available sources and researcher-authored material, so additional consent isn't required.~~
>
> Privacy and consent: the evaluation corpus (§3.7) is drawn entirely from two already-published, peer-reviewed research corpora (Clough & Stevenson, 2011; PlagBench, Lee et al., 2025), each already anonymised and ethically cleared by its original authors for research reuse. No fresh student data was collected, so no new anonymisation or departmental consent process was required for this thesis; reuse is governed by proper citation and each source's stated licence terms rather than by new consent.

Replace the open-science paragraph's second sentence:

> ~~The anonymised original-set essays are not released, since their reuse falls under the limited departmental consent obtained for evaluation only.~~
>
> The evaluation corpus itself is not re-released as a bundled dataset, since it is a derived combination of two externally-licensed sources; researchers wishing to reproduce the evaluation are directed to the original Clough & Stevenson and PlagBench sources directly, cited in full in §3.7.2.

---

## Final consistency pass — the recurring "200" / "60/20/20" figures

Three remaining places to update once §3.7 lands, each a one-line substitution:

- **§3.2**, DSR guideline "Design evaluation": "...validate through 3 controlled experiments with statistical analysis on a **200-submission** labelled corpus" → "**185-submission**".
- **§3.9.3** (Phase 3 description): "Construct the labelled corpus and freeze the **60/20/20** train/validation/test split" → "**109/38/38**".
- **§3.14** (Chapter Summary): "A **200-submission** labelled dataset balanced across 4 plagiarism categories" → "A **185-submission** labelled dataset across 4 plagiarism categories" (drop "balanced" — the real category counts, per Table 3.1, are 68/49/19/49, not balanced quarters).

No other numeric dataset references were found elsewhere in the chapter.

---

## Status: all sections of the original correction dossier now have drafted replacement text

Covered across this document and the two earlier ones (`section_3_7_replacement_1415.md`, `section_3_4_to_3_6_replacement_1430.md`): §3.2 (consistency line), §3.3, §3.4, §3.5, §3.6, §3.7, §3.8, §3.9 (consistency line), §3.12, §3.13, §3.14 (consistency line). Not drafted, left as open decisions for you: the §3.2/§3.9 five-vs-six-phase mismatch (a structural choice, not a factual correction) and whether §3.4.5 (AI-authorship) belongs in this thesis's scope at all.

Next natural step is Chapter 4 — say the word and I'll start pulling the actual results together the same way, report by report.
