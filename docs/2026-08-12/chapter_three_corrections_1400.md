# Chapter 3 (Methodology) — full correction dossier

Source: `C:\Users\olomu\Downloads\fyp\uploads\190407042.docx`, extracted and cross-checked section by section against the actual codebase and the evaluation reports in `evaluation/reports/`. Chapter 3 already exists in full (sections 3.1–3.14) — this is not a "write from scratch" job, it's a correction pass. **Chapter 4 does not exist yet** — the document goes straight from Chapter 3 to References.

Format per section: **What it currently says** → **What's actually true** → **Evidence** → **Fix needed**.

---

## Pre-existing structural issue (not caused by any of this session's work)

§3.2 says implementation ran in "**5 phases**: problem identification, requirements specification, design and development, evaluation, and communication." §3.9 then lists **six** numbered phases (3.9.1–3.9.6: Foundation, Tier 1, Dataset+Tier2, Moodle Plugin, Evaluation, Communication). These don't match each other. Needs reconciling regardless of anything else — pick one enumeration and use it in both places.

---

## §3.2 Research Design

**Says**: "validate through 3 controlled experiments... on a **200-submission** labelled corpus."
**Actually**: 185 submissions (95 Clough & Stevenson + 90 PlagBench), split 109/38/38. See §3.7 below — this number appears in at least four places in the chapter (§3.2, §3.7.1, §3.9.3, §3.14) and needs correcting in all of them consistently.

Everything else in §3.2 (DSR framing, Hevner et al.'s 7 guidelines) is stable and needs no change — it describes the methodology approach, not implementation specifics.

---

## §3.3 Case Study Context

**Says**: target deployment hardware is "16-64 GB RAM, 4-8 CPU cores," and experiments ran on "a development workstation with 16 GB RAM, an Intel Core i5 processor."
**Actually**: the real, live deployment (the one the real-time Moodle demonstration in §3.10.3 actually ran on) is a GCP `e2-standard-2` instance — **2 vCPU, ~7.8GB RAM** (confirmed via `free -h` on the VM) — below the stated 4-8 core / 16GB floor. Evaluation/threshold-tuning scripts ran locally on the researcher's own Windows machine; the live Moodle integration and real-time demo ran on the GCP VM. Neither environment is currently named in this section.

**This is a positive finding, not a weakness** — the system was shown to comfortably run the full stack (Moodle + Postgres ×2 + Redis + FastAPI + 2 Celery workers) on a smaller box than originally scoped, which *strengthens* the affordability argument in Chapter 1. Recommend: state the actual GCP `e2-standard-2` spec as what was used, and reframe the "16-64GB / 4-8 core" language as the *target range for larger institutional deployments*, with the actual demonstration explicitly noted as exercising the *lower* bound.

**Fix needed**: name the actual two environments (local dev machine for evaluation scripts, GCP e2-standard-2 for live deployment/demo), and correct the RAM figure everywhere it recurs (also in §3.4.3 and §3.12.3 below).

---

## §3.4 System Architecture

### §3.4.1 Tier 1
**Says**: "The Tier 1 confidence score is the maximum normalised similarity returned by either component."
**Actually verified** (`backend/app/services/tier1_detector.py`, read in full): the real formula is

```
c1(D) = max( winnow_containment, min(bm25_normalized, 0.6) )
```

**This is a materially more specific and more important detail than what's currently written.** BM25's contribution is deliberately *capped at 0.6* — specifically so that lexical/topical overlap alone can never push `c1` above `τ_high` (0.68) and trigger a direct `TIER1_PLAGIARISED` verdict. BM25 alone can only ever escalate to Tier 2, never auto-confirm plagiarism on its own. This is a genuine, deliberate false-positive safeguard that isn't in the chapter at all right now — it's exactly the kind of design decision a methodology chapter should describe, and it's a stronger, more defensible design than the "plain max" currently written.

### §3.4.2 Gating Function
**Says**: thresholds are "jointly tuned... to maximise overall F1-score subject to 2 constraints: escalation rate must not exceed 25%, and Tier 1 plagiarism precision must be at least 0.95."
**Actually**: neither constraint was met or used as the actual tuning criterion. The real, deployed thresholds are `τ_low = 0.30`, `τ_high = 0.68`, tuned to **maximise F1 while holding overall precision at 1.000** — with no explicit escalation-rate ceiling. Real measured escalation rate is **47.37%**, essentially double the stated 25% ceiling. This is not a minor rounding difference — it's the single biggest quantitative gap between what this chapter says the design targets and what was actually achieved, and it directly explains why Hypothesis 1 (§3.10.1) is **not supported** in the real results (Tier 1 alone resolves 47.37% of submissions, not ≥80%).

**This needs careful, honest handling, not a quiet number-swap.** Recommend stating plainly: the original 25%-escalation design constraint turned out to be unachievable at the precision level the system requires (0.95 constraint retained, escalation ceiling dropped) — and that this is itself a real, reportable finding, not a design failure to hide. It's the same finding Report 02 already reached independently.

### §3.4.3 Tier 2
**Says**: "Embeddings are stored in a FAISS IVFPQ index sized to fit within 16 GB RAM."
**Actually**: the real `FAISSIndex` implementation (`backend/app/services/faiss_service.py`) uses `IndexFlatIP` (exact search) below 1,000 vectors and only switches to `IndexIVFPQ` above that. **Every evaluation corpus used in this thesis (185 items, or 109-document train-split corpora) is well under 1,000 vectors** — meaning IVFPQ was never actually exercised in any reported experiment; only the flat, exact-search path ran. IVFPQ code exists and is tested, but describing it as *the* index used for the reported results is not accurate.

**Also**: "Tier 2 returns... a ranked list of supporting evidence passages for the instructor dashboard" — this is **now** true (as of a fix made 2026-07-11, this session's work) but was **not true** for most of the project's history. The DB column, schema, and Moodle rendering loop for this existed from early on, but nothing in the detection pipeline ever populated them until a specific fix late in the project. If any earlier evaluation screenshots or Chapter 4 draft material reference this feature, confirm they postdate the fix.

**Fix needed**: state that `IndexFlatIP` (exact) was the index actually used for all reported evaluation, with `IndexIVFPQ` as a documented, tested, but unexercised scale-up path for corpora beyond ~1,000 documents; date the match-explanation feature accurately if referenced in Chapter 4.

### §3.4.4 Moodle Integration
**Says**: "Detection runs asynchronously in a Celery background worker queue."
**Actually true but underspecified.** The real system runs **two** Celery worker pools, not one: `celery-worker` (solo pool — extraction, detection, indexing, embedding, deliberately serialized because these steps share order-sensitive in-memory state) and `celery-worker-fast` (thread pool — AI-authorship detection only, independent and safe to parallelize). This split exists because an earlier, simpler single-worker design was found to have a real capacity problem under load, and a first attempt at splitting it *also* introduced a real correctness bug (parallelizing extraction broke submission-ordering guarantees) before landing on the current, correct split. This is a legitimate, evidence-backed design decision worth including if this section is being expanded — it's a stronger methodology story than "runs in a queue."

**Also**: no mention anywhere in §3.4 of AI-authorship detection at all, even though it's a real, built, deployed, independent signal running in parallel with the plagiarism pipeline. Given Chapter 1's stated scope, confirm with your supervisor whether this belongs in Chapter 3 as an implemented-but-secondary feature, or is explicitly out of scope for this thesis's claims — I can draft it either way once you decide.

**Missing entirely**: the real Moodle result-delivery architecture and its measured latency. This is genuinely one of the strongest, most concrete engineering results in the whole project and currently has zero presence in Chapter 3: a self-requeuing ad-hoc Moodle task polls the backend every ~15 seconds (falling back to a 5-minute scheduled task as a safety net), because Moodle's *scheduled* tasks have a hard one-minute floor with no seconds field — a genuine Moodle-core limitation, not a tuning choice. Measured, live, end-to-end: **~20 seconds** from submission to visible result (down from ~5m34s before this was built). Worth a real subsection.

---

## §3.5 Mathematical Model

### §3.5.2 Tier 1 Detection Function
Update to the verified formula from §3.4.1 above: `c1(D) = max(containment(D), min(BM25_norm(D), 0.6))`. Note also: the actual similarity measure feeding this is **containment** (`|query ∩ source| / |query|`), not the "normalised similarity" language currently used, which matters directly for §3.6.1 below.

### §3.5.3 Gating Decision Function
Formula (`route(D) = ...`) is structurally correct and matches the real `gating.py` exactly. Only the deployed numeric values and the tuning criterion need correcting, per §3.4.2 above: **τ_low = 0.30, τ_high = 0.68** (not left as symbolic placeholders — these are the actual shipped values and should be stated explicitly here), tuned for maximum F1 at fixed precision=1.000, not against an escalation-rate ceiling.

### §3.5.4 Tier 2 Hybrid Fusion
**Confirmed exact match** to the real code (`tier2_detector.py`): `c2(D) = α·S_dense + (1−α)·norm(S_sparse)`. The deployed value is **α = 0.6** — state it explicitly (currently left unstated in the chapter, only "tuned on the validation split"). One caveat worth a sentence: I did not find evidence in this session's work that α was re-swept specifically against the *corrected* (leak-fixed) corpus the way τ_low/τ_high were — if you know it was revisited at some point I haven't seen, confirm; otherwise it's honest to say α=0.6 was carried forward from earlier tuning and not independently re-validated post-correction.

**Important, non-obvious correction**: "norm(S_sparse)" in this formula does *not* mean per-query min-max normalization — see §3.6.5 below, this is the same issue as the BM25 normalization correction and the two should be fixed together for consistency.

### §3.5.5 Cost Model
**Confirmed correct and important to keep exactly as-is**: `C_total(N) = ρ·N·c_cloud`, with Hypothesis 2 predicting "ρ ≤ 0.20 typical, ρ ≤ 0.30 worst case." This is *exactly* the target Report 03 measured against — real ρ came out to 44.7–52.6% depending on the tuning round, meaning the cost half of Hypothesis 2 genuinely was not met, exactly as this section's own stated worst-case bound would predict. **No change needed here** — this section is already correct and Chapter 4 should cite it directly when reporting H2 as "partially supported" (effectiveness target exceeded, cost target missed).

---

## §3.6 Algorithms

### §3.6.1 Winnowing Fingerprinting
**Says**: "Similarity between 2 documents is the Jaccard coefficient."
**Actually**: the real system uses **containment** (`|F(Dᵢ) ∩ F(Dⱼ)| / |F(Dᵢ)|`), not Jaccard. This is one of the most consequential corrections in the whole chapter — it was a real bug in an early implementation (gated on Jaccard when the code's own design intent already said containment), found and fixed specifically because Jaccard collapses toward zero when a matched source document is much longer than the query — exactly the short-answer-copies-part-of-a-longer-source case this system handles constantly. Worth explaining *why* containment is correct here (asymmetric measure, appropriate for excerpt-in-larger-document matching), not just swapping the term.

`k=5`, `w=4` — **confirmed exact match** to deployed config (`WINNOW_K=5`, `WINNOW_W=4`). No change needed there.

### §3.6.2 BM25 Sparse Retrieval
**Says**: "Stop words are stripped via SpaCy's standard English list. Lemmatisation merges inflected forms before indexing."
**Actually verified** (`backend/app/services/bm25_service.py`, read in full): **no SpaCy anywhere** — this was an explicit design choice ("avoids SpaCy dependency at runtime for lighter Docker image"). Tokenization is a simple regex (`[a-z0-9]+`) plus a small, hand-curated ~90-word stopword list. **There is no lemmatisation at all.** This needs a real correction, not a citation swap.

**Also**: the library is specifically **`BM25Plus`** (from `rank_bm25`), not generic BM25/BM25Okapi — worth naming precisely. `k1=1.5, b=0.75` are confirmed correct as stated.

**Says**: "BM25 scores are min-max normalised against the calibration distribution."
**Actually verified, and this is architecturally important**: the real system *deliberately does not* use per-query min-max normalization, and says so explicitly in its own source comments. It uses **proportional scaling** instead — `raw_score / saturation_constant`, capped at 1.0, with the saturation constant calibrated so verbatim matches land around 0.7–1.0 and topical overlap lands around 0.2–0.4. The reasoning, verified directly in the code: per-query min-max normalization rescales relative to whatever's in the local candidate pool, which inflates the locally-best candidate to 1.0 *regardless of its true absolute similarity* — a real anti-pattern the team specifically identified and designed around. This is a genuinely stronger and more defensible methodological choice than what's currently written, and the correction should explain the reasoning, not just state the new formula.

### §3.6.3 Dense Embedding Generation
**Says**: "overlapping passages of 256 tokens with a 192-token stride, giving 25% overlap."
**Actually**: the real, deployed chunking (`CHUNK_SIZE=256`, `CHUNK_OVERLAP=50`, both measured in **words**, not tokens) gives a 206-word stride and roughly **19.5% overlap**, not 25%. Also worth noting the real chunker is sentence-aware — it accumulates whole sentences up to the word budget rather than cutting at a fixed token boundary, which is a better-justified design than a fixed-stride window and worth describing that way.

`all-MiniLM-L6-v2`, 384-dimensional — **confirmed exact match**, no change.

### §3.6.4 FAISS Approximate Nearest Neighbour Search
Config values are **mostly confirmed**: `FAISS_NLIST=256` matches "256 inverted lists"; `FAISS_NPROBE=32` matches "top 32 candidate clusters"; `top_k=50` matches "top 50 nearest passages." `FAISS_M=48` (PQ subquantizer count) doesn't map directly onto "8-byte product-quantised codes" as currently phrased — worth double-checking the exact byte-size claim against FAISS's own IVFPQ parameterization before restating it, rather than carrying the number forward unverified.

**More importantly**: per §3.4.3 above, none of this IVFPQ configuration was actually exercised by any reported evaluation run — every real corpus stayed under the 1,000-vector threshold that would trigger it. The "over 95% recall@50... sub-millisecond" performance claim reads as a projected/literature-derived figure, not something measured against this project's own IVFPQ path. Recommend either scoping this subsection explicitly as "the scale-up path, not exercised in the reported evaluation" or removing the specific recall/latency claim unless you have a source for it.

### §3.6.5 Hybrid Fusion
Structurally fine; just apply the same normalization correction as §3.6.2 (proportional scaling, not min-max) for consistency, since this subsection restates the same fusion described in §3.5.4.

---

## §3.7 Dataset Construction — the largest single correction

**Says**: a self-collected, purpose-built 200-submission corpus (40 verbatim / 40 near-verbatim / 60 paraphrased / 60 original), built from Wikipedia + open-access papers + GPT-4 paraphrasing + anonymised past course submissions, with a formal quality-control and inter-rater-reliability protocol (2-week-separated second-pass labelling, Cohen's kappa on a 20-item audit, SimHash near-duplicate removal, fastText language filtering).

**Actually**: the real evaluation corpus is a merge of two established, peer-reviewed, external corpora — confirmed directly via `labels.csv`'s own `dataset` column:

| Source | Original | Verbatim | Near-verbatim | Paraphrased | Total |
|---|---|---|---|---|---|
| Clough & Stevenson (2011) | 38 | 19 | 19 | 19 | 95 |
| PlagBench (Lee et al., 2025) | 30 | 30 | 0 | 30 | 90 |
| **Combined** | **68** | **49** | **19** | **49** | **185** |

Split 109/38/38 (train/validation/test) — not the 60/20/20 ratio stated in §3.9.3, and not 200 total. None of the described collection procedure (own Wikipedia insertion, own GPT-4 paraphrasing, own quality-control pipeline) actually happened — the corpus was sourced pre-built and pre-labelled from these two published sources.

**This exact correction was already resolved and drafted, three weeks before this correction pass, in `evaluation/reports/00_dataset_reconciliation.md`.** That report already contains ready-to-use replacement text: a replacement Table 3.1, replacement citations (Clough & Stevenson 2011, *Language Resources and Evaluation* 45(1), 5-24; Lee et al. 2025, PlagBench, NAACL 2025, arXiv:2406.16288), and a full paragraph of replacement prose for §3.7.2. I can paste that directly into this section rather than redrafting from scratch — it's already been through one round of review.

**§3.7.3 (Labelling Protocol)** and **§3.7.4 (Quality Control)** as currently written describe a *self-labelling* process (second-pass review, Cohen's kappa, SimHash dedup, language filtering) that doesn't apply to using two already-published, already-labelled corpora. These sections should be replaced with a short description of *each source corpus's own* published labelling methodology (cited, not re-derived), per Report 00's addendum recommendation.

**One real, additional, separate bug worth mentioning here regardless of the corpus-identity correction**: a genuine data-leakage bug was found and fixed in how the source-matching corpus was built — all 95 Clough & Stevenson submissions were also present in the external "sources" folder under their bare filename, meaning every C&S submission was originally being evaluated against a corpus that already contained an exact copy of itself. This was found, diagnosed, and fixed mid-project (dropping the indexed source corpus from 190 to 95 genuine documents) — worth a sentence in Chapter 3 or 5 as a methodological lesson, separate from the identity-of-the-corpus correction above.

---

## §3.8 Tools and Technologies

Confirmed accurate: Python, FastAPI, rank-bm25, sentence-transformers, FAISS, Celery+Redis, Moodle, PHP, PostgreSQL, Docker, SciPy.

**Needs removing**: SpaCy — not actually used anywhere in the deployed system (see §3.6.2).

**Needs adding**, all confirmed real, load-bearing dependencies with no current entry in this table:
- **PyTorch** (`torch`) — required by both `sentence-transformers` and the AI-authorship classifier.
- **transformers** (Hugging Face) — loads the AI-authorship model (`Hello-SimpleAI/chatgpt-detector-roberta`), if AI-detection is scoped into this thesis (see §3.4.4 open question above).
- **Google Cloud Platform** (Compute Engine, `e2-standard-2`) — the actual live deployment platform. Currently unnamed anywhere in the chapter despite being where the real-time Moodle demonstration (§3.10.3) actually ran.
- **nginx** — fronts the Moodle container in the real deployment.
- Confirm exact pinned versions for FAISS, Moodle, PostgreSQL, PHP against what's actually in `docker-compose.yml`/`requirements.txt` rather than the "+"-qualified estimates currently in the table, if you want exact-version precision for the write-up.

---

## §3.9 Implementation Plan

Structural 5-vs-6-phase mismatch already noted at the top of this document. Beyond that: this section describes a clean, linear 12-week plan. The real project, as evidenced by the dated addenda across every evaluation report, involved substantially more iterative bug-finding and re-verification than a linear plan implies (roughly ten distinct real bugs found and fixed via live testing, several requiring re-running already-"complete" evaluation passes). Whether to reconcile §3.9's prospective plan against what actually happened is a judgment call — many DSR theses keep the prospective plan in Chapter 3 as-written and reserve the "how it actually went" narrative for Chapter 5's reflection. Flagging this as a structural decision for you, not asserting a fix.

§3.9.3 also repeats the "60/20/20" split figure inconsistent with the real 109/38/38 split — same correction as §3.7.

---

## §3.10 Experimental Design

**Strong alignment overall** — this section matches what was actually built and run more closely than almost any other part of the chapter:

- **Experiment 1** (§3.10.1, Hypothesis 1) — procedure matches `run_evaluation.py` exactly.
- **Experiment 2** (§3.10.2, Hypotheses 2/3) — the 4-configuration comparison (local-only/cloud-only/hybrid-static/dual-tier) and the paired t-test with Bonferroni correction match `exp2_cost_accuracy.py` exactly, including the specific statistical method.
- **Experiment 3 threshold sweep** (§3.10.3) — the exact swept values, `τ_low ∈ {0.20, 0.25, 0.30}` and `τ_high ∈ {0.70, 0.75, 0.80}`, match `exp3_threshold_sensitivity.py` exactly.

**One real deviation, and it's a well-justified one**: the real-time demonstration protocol (§3.10.3) as written calls for "Repeat 5 times with different submission pairs." What actually happened: one genuine, complete, real-browser-simulated repetition was run (not five), with an explicit methodological justification recorded in the reports — the dominant source of latency is a fixed architectural polling interval (Moodle's cron cadence), not per-submission variance, so five repetitions would mostly reproduce the same bound with different phase-alignment noise rather than add new information. Real measured result: **~20 seconds** end-to-end (not <5 seconds — Hypothesis 4/5's literal target was not met, though the *component* pipeline latency, excluding Moodle's polling architecture, was consistently under 300ms). This deviation should be stated plainly in Chapter 4 alongside the result, with the same reasoning given in the reports — it reads as a defensible methodological judgment call, not a shortcut, provided it's explained rather than silently under-delivered.

---

## §3.11 Evaluation Metrics

**Confirmed accurate and consistent** with everything actually measured — precision/recall/F1 definitions, per-category F1, p50/p95/p99 latency, the $0.0001-per-embedding cost rate (§3.11.3, matches Report 03's stated rate exactly), escalation rate ρ, Tier 1 resolution rate, and conditional Tier 1 precision are all real metrics that were actually computed and reported. No corrections needed in this section — it's ready for Chapter 4 to plug real numbers into.

---

## §3.12 Validation and Testing

### §3.12.1 Unit Testing
**Says**: "80% minimum is enforced in CI on every push."
**Actually**: coverage is real and currently measured at **85%** (backend, 147 tests passing as of the last full run) — but there is **no CI pipeline** anywhere in this project enforcing this on every push. All testing was run manually/locally throughout. The 80% target itself was met and slightly exceeded; the *enforcement mechanism* described (automated CI gating) doesn't exist. Correct the claim to describe manual, repeated `pytest`+`coverage` runs rather than continuous integration.

**Also worth noting honestly**: coverage is not uniform. Core detection services (Winnowing, BM25, Tier 1/2, gating, the newer structural-signal and match-explanation modules) sit at 91–100%. The Celery task-orchestration layer sits at 16–48%, because no database test infrastructure exists in this project to unit-test DB-backed tasks in isolation — that layer's assurance instead comes from extensive live/manual verification, documented per-feature rather than as a single automated suite. Worth a sentence distinguishing "well-covered by unit tests" from "well-verified by other means" rather than a single blended coverage number.

### §3.12.2 Integration Testing
**Says**: "A separate Moodle integration test exercises the plugin against a Dockerised Moodle 4.1 instance using Behat."
**Actually**: Behat automation was **explicitly not built** — a deliberate, documented scope decision, substituted with extensive manual/live verification instead (real logins, real submissions, real report-page checks, documented per feature rather than as one repeatable automated command). This needs an honest correction, not a quiet claim that Behat exists. State plainly: automated Behat coverage was deferred as the most cuttable item under the project's time budget; manual verification covered [list what was actually manually verified: submission flow, badge rendering, report-page access control, per-module/global enable toggles, dedup behavior, cross-course access denial, etc.] — this is a real, specific, non-trivial verification effort, just not an automated one.

### §3.12.3 Performance Testing
**Says**: "Locust, ramping from 1 to 50 concurrent users over 10 minutes... p95 <5s and zero failed requests at 20 concurrent users. Memory profiled with memory_profiler to confirm the 16GB RAM budget."
**Actually**: Locust testing did happen, but with a different, explicitly-justified ramp profile — 20-user and 50-user *3-minute plateaus* rather than a single 10-minute 1→50 ramp, for practicality. Real result is *stronger* than the stated target: **zero failures at 50 concurrent users** (not just 20), p95 latency **~120ms** (not just "under 5s" — two orders of magnitude of headroom). Memory was checked via `free -h`/`docker stats` on the real deployed VM, not `memory_profiler`, and confirmed the system fits comfortably within the *actual* ~7.8GB VM — not the 16GB figure stated elsewhere in this chapter (see §3.3). This whole subsection is good news that just needs its numbers and method corrected to match what really happened.

A real regression was also found and fixed mid-project during a *re-run* of this exact test (a Celery worker-split change introduced a capacity problem under the 50-user load, caught only by re-testing after that change, not by the original test) — worth a sentence if you want the testing section to reflect the iterative-verification story rather than a single clean pass.

### §3.12.4 Accuracy Validation
Matches what was actually done — confusion matrices and manual false-positive inspection were both real parts of this project (Report 05's failure-mode analysis). No correction needed, though note Report 05's own case studies were originally misdiagnosed and had to be corrected once the dataset-leak bug (§3.7) was found — another honest methodological-lesson sentence available if wanted.

---

## §3.13 Ethical Considerations

Downstream of the §3.7 dataset correction: the current text describes anonymising "past course essays" and obtaining "departmental approval" for an "original set" of locally-collected student work. Since the real corpus is two already-published, already-anonymised, already-ethically-cleared external research corpora (Clough & Stevenson; PlagBench), this section's actual ethical story is simpler, not more complex: proper citation and licence compliance for reuse of published research datasets, rather than fresh consent/anonymisation of local student data. The data-security and avoidance-of-harm paragraphs (encryption at rest, no real student accusations resulting from the research) remain accurate and need no change — only the "whose data is this and what consent applies" framing needs to follow the §3.7 correction.

---

## §3.14 Chapter Summary

Restates "200-submission labelled dataset" — same correction as §3.2/§3.7/§3.9.3. Everything else in the summary (DSR frame, 2-tier architecture, gating, hybrid fusion, 5 equations, 3 experiments, 5 hypotheses) is structurally accurate and just needs to inherit the corrections made above.

---

## Summary table — every numeric/factual correction in one place

| Item | Chapter 3 currently says | Actually is |
|---|---|---|
| Dataset size | 200 self-collected | 185 (95 Clough & Stevenson + 90 PlagBench) |
| Split | 60/20/20 | 109/38/38 (train/val/test) |
| Tier 1 similarity measure | Jaccard coefficient | Containment |
| Tier 1 formula | `max(norm(winnow), norm(bm25))` | `max(containment, min(bm25_norm, 0.6))` |
| Escalation-rate design target | ≤25% | Not used as a constraint; real escalation is 47.37% |
| Deployed τ_low / τ_high | unstated (symbolic only) | 0.30 / 0.68 |
| Deployed α | unstated (symbolic only) | 0.6 |
| BM25 tokenization | SpaCy stopwords + lemmatisation | Regex tokenizer + small hand-curated stopword list, no lemmatisation |
| BM25 library | "BM25" | `BM25Plus` (rank_bm25) |
| Score normalization | Min-max | Proportional scaling (raw/saturation, capped at 1.0) — deliberately not min-max |
| Chunking | 256 tokens / 192-token stride / 25% overlap | 256 words / 50-word overlap / ~19.5% overlap, sentence-aware |
| FAISS index actually used in evaluation | IVFPQ | IndexFlatIP (corpus never crossed the 1,000-vector IVFPQ threshold) |
| Target/actual RAM | 16GB (stated in 3 places) | ~7.8GB actual VM (e2-standard-2, 2 vCPU) |
| Deployment platform | Unnamed | GCP Compute Engine, e2-standard-2 |
| CI enforcement of coverage | "enforced in CI on every push" | No CI exists; manual local runs only |
| Coverage achieved | 80% minimum | 85% overall (91-100% core services, 16-48% Celery task layer) |
| Behat integration testing | Described as existing | Explicitly deferred; substituted with manual verification |
| Load test profile | 1→50 ramp over 10 min | 20-user and 50-user 3-min plateaus |
| Load test result | p95 <5s, 0 failures @ 20 users (target) | p95 ~120ms, 0 failures @ 50 users (actual, stronger) |
| Memory profiling tool | memory_profiler | `free -h` / `docker stats` on the real VM |
| Match-explanation feature | Described as existing from the start | Built and fixed 2026-07-11 — was dead code for most of the project |
| Real-time demo repetitions | 5 | 1 (explicitly justified — dominant latency source is architectural, not per-submission) |
| Real-time demo latency | <5s target | ~20s actual, ~16x improvement over an earlier ~5m34s measurement |

---

## What I'd suggest as the actual next step

Given the volume above, I'd recommend going section by section rather than one giant rewrite — starting with §3.7 (Dataset Construction) since it's the largest, highest-stakes correction and Report 00 already has ready-to-use replacement prose for it, then §3.4/§3.5/§3.6 (the technical/mathematical corrections, all code-verified above), then §3.3/§3.8/§3.12 (environment and testing corrections), then a final consistency pass on §3.2/§3.9/§3.14 for the recurring "200"/"60-20-20" figure. Say the word and I'll start drafting actual replacement prose for whichever section you want first.
