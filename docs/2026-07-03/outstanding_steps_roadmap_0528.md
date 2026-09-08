# Outstanding Steps Roadmap (Chapter 4 & 5)

Sequenced execution plan for the work identified in `docs/2026-07-03/chapter_four_five_0521.md`. Each step below writes its outcome to a numbered file in `evaluation/reports/` (structure created alongside this doc) — Chapter 4 gets written *from* those reports, not the other way around.

Real, verified figures used throughout this roadmap (pulled directly from `evaluation/dataset/data/labels.csv`, not estimated):

| Source | original | verbatim | near_verbatim | paraphrased | Total |
|---|---|---|---|---|---|
| Clough & Stevenson (2011) | 38 | 19 | 19 | 19 | 95 |
| PlagBench (Lee et al., 2025) | 30 | 30 | 0 | 30 | 90 |
| **Combined** | **68** | **49** | **19** | **49** | **185** |

(185, not the 200 Chapter 3 currently claims; splits are 109/38/38 train/val/test per the existing `splits/*.csv`, not 60/20/20 of 200.) PlagBench has no near-verbatim category (it only covers verbatim/paraphrase/summarisation), which is why that column is 0 for it — worth noting explicitly in the corrected Chapter 3, since it explains an otherwise-odd asymmetry in Table 3.1.

---

## Step 0 — Dataset reconciliation decision (blocks everything else)

**Owner:** you + supervisor, not something I should decide unilaterally.
**Output:** `evaluation/reports/00_dataset_reconciliation.md`

Confirm with your supervisor: correct Chapter 3 to describe the real Clough & Stevenson + PlagBench sourcing (recommended), or commit to building the originally-described custom 200-submission corpus first. Once decided, this report records the decision, the rationale, and — if correcting Chapter 3 — the exact replacement text for Section 3.7 and Table 3.1 using the real numbers above, ready to paste in.

**Do this first.** Every experiment below reports against "the test split," and that phrase needs to mean one specific, correctly-described thing before Chapter 4 is written, or you'll need to redo the write-up later.

---

## Step 1 — Tier 2 bug fix & retuning (already done)

**Output:** `evaluation/reports/01_tier2_bugfix_and_retuning.md` (copy of `docs/2026-07-03/tier2_scoring_fix_0458.md`, cross-referenced rather than duplicated)

Nothing to do here except link it in — already complete, already has before/after numbers (F1 0.000→0.815). Placed first in the reports sequence because Chapter 4 should present this as the opening result: the system didn't work out of the box, here's what was found and fixed, here's what it does now. That's a legitimate DSR "search process" narrative (Section 3.2, guideline 6), not something to hide as embarrassing.

---

## Step 2 — Experiment 1: Tier Resolution Analysis

**Output:** `evaluation/reports/02_exp1_tier_resolution.md`
**Depends on:** Step 0

1. Re-run `evaluation/run_evaluation.py --split test --verbose --output <path>` against the reconciled dataset.
2. From the output CSV (`category`, `escalated`, `gate` columns already present), compute escalation rate overall and per category — this is a `pandas.groupby`, no new code needed.
3. Report the headline number plainly: **84.2% escalation rate**, not the ≤25% Hypothesis 1 target. State per-category breakdown (expect verbatim/original to resolve at Tier 1 more often than paraphrased, per Section 3.10.1's own prediction — confirm or refute this with the real breakdown).
4. Write the discussion paragraph explaining the Tier-1-precision (≥0.95 constraint) vs. low-escalation-rate tension identified previously — this is the causal explanation for why H1 doesn't hold, not just the fact that it doesn't.

**Stretch goal, time permitting:** re-run the `alpha × tau_high` grid search (methodology already in `docs/2026-07-03/tier2_scoring_fix_0458.md`) with an explicit ≤25% escalation-rate constraint applied, to see if *any* point on the Pareto frontier satisfies both. Report the answer either way — "no configuration satisfies both constraints simultaneously on this corpus" is a valid, useful finding.

---

## Step 3 — Experiment 2: Cost-Accuracy Trade-offs (biggest remaining gap)

**Output:** `evaluation/reports/03_exp2_cost_accuracy.md`
**Depends on:** Step 0

This is the highest-value missing piece — RQ2, H2, and H3 are all unaddressed without it.

1. Confirm `evaluation/baselines/local_only.py`, `cloud_only.py`, `hybrid_static.py` still import cleanly against the current (fixed) `tier2_detector.py`/`bm25_service.py`/`faiss_service.py` — they may reference the same modules I just patched, so check for breakage before trusting their output.
2. Run all 3 baselines + the dual-tier pipeline (`run_evaluation.py`) against the same reconciled test split. Capture per-submission P/R/F1, cost (Section 3.5.5 formula, using the *measured* escalation rate, not a projected one), and latency for all 4 configurations.
3. Build the comparison table (this is Table 4.X, the centrepiece of Chapter 4).
4. Run the paired t-test (dual-tier vs. cloud-only per-submission F1, Bonferroni-corrected across 3 pairwise comparisons, α=0.05) using `evaluation/metrics.py`'s existing `paired_comparison()` — don't skip this, Section 3.2 commits you to it.
5. State plainly whether H2 (≥90% of cloud-only effectiveness at ≤30% of cost) and H3 (F1≥0.84) are supported. Current dual-tier F1=0.815 is close to but under 0.84 — report the real number, don't round up.

---

## Step 4 — Experiment 3: Threshold Sensitivity & Real-Time Demo

**Output:** `evaluation/reports/04_exp3_threshold_sensitivity.md`
**Depends on:** Step 0

1. **Threshold heatmap:** run the exact 3×3 grid specified in Section 3.10.3 (`tau_low ∈ {0.20,0.25,0.30}`, `tau_high ∈ {0.70,0.75,0.80}`) — `evaluation/experiments/exp3_threshold_sensitivity.py` already exists for this, confirm it runs against the reconciled dataset and the fixed tier2 code, generate the heatmap figure via `evaluation/plots.py`.
2. **Latency:** already have p50/p95/p99 from Step 2/3's runs — reuse rather than re-measure, but note explicitly that these are in-process measurements (no Celery/HTTP overhead), which is a real caveat worth stating in the report, not glossing over.
3. **Real-time cross-submission demo:** drive the actual deployed Moodle instance (`plagiarism-detector-vm`, `http://104.196.7.251:8080`) — submit an essay as one student, wait (or fake the clock via direct DB manipulation like earlier sessions did), submit a paraphrased near-duplicate as a second student, verify detection completes within 5 seconds of the second submission and the badge/report renders correctly. Repeat 5× with different pairs per Section 3.10.3, log actual wall-clock timing each run. You already proved the underlying mechanism works (student1/student2 cross-submission test, prior session) — this formalizes it with timing instrumentation, it's not new engineering.

---

## Step 5 — Failure Mode Analysis

**Output:** `evaluation/reports/05_failure_mode_analysis.md`
**Depends on:** Step 3 (needs the confusion matrix / false-positive list from the dual-tier run)

Manually inspect a sample of the false-positive "original" documents (previously 8/14 on the un-reconciled test split — number may shift slightly once Step 0 lands). For each: read the actual matched passage pair, note whether it's genuine same-prompt topical overlap (the working hypothesis, independently corroborated by PAN 2025's finding that embedding similarity conflates topical closeness with copying) or something else. Turns a plausible guess into a documented finding with textual evidence — this is Section 3.12.4's requirement, and it directly feeds Chapter 4's discussion and Chapter 5's "known limitation" framing.

---

## Step 6 — Testing Suite (largest remaining time cost)

**Output:** `evaluation/reports/06_testing_suite_results.md`
**Independent of Steps 0-5** — can run in parallel with the write-up.

1. **Unit tests** (Section 3.12.1): pytest suite per module (Winnowing, BM25, embedding pipeline, FAISS wrapper, fusion, gating), `coverage.py` ≥80% enforced. Check what already exists in `backend/tests/` (saw `test_bm25.py` referenced earlier) before writing from scratch.
2. **Integration tests** (Section 3.12.2): Behat test against the Dockerised Moodle instance — you already have a working Moodle deployment (`plagiarism-detector-vm`), this formalizes manual verification already done in prior sessions into an automated, re-runnable test.
3. **Performance/load testing** (Section 3.12.3): Locust, ramp 1→50 concurrent users over 10 minutes, assert p95 <5s and zero failures at 20 concurrent users, profile memory with `memory_profiler` against the 16GB budget. This tests the *deployed* system (via HTTP), which will surface any Celery-queue/network overhead the in-process eval numbers from Steps 2-4 don't capture — good complementary data point.

---

## Step 7 — Write Chapter 4

**Depends on:** Steps 0-6 (or at least 0, 1, 2, 3, 5 — Step 6 and the stretch goals in Step 2/4 can trail if time is tight)

Write directly from the reports folder, section by section, per the structure in `docs/2026-07-03/chapter_four_five_0521.md`'s Chapter 4 plan (4.1 through 4.7). Each report file maps to one subsection — this should be close to transcription-plus-interpretation once the reports exist, not fresh analysis.

## Step 8 — Write Chapter 5

**Depends on:** Step 7

Synthesis chapter, should move fast once Chapter 4 is solid. Structure and the 5 suggested future-work recommendations already drafted in `docs/2026-07-03/chapter_four_five_0521.md`'s Chapter 5 plan — mostly needs the real Chapter 4 numbers substituted into the RQ-by-RQ findings summary.

---

## Suggested critical path

Step 0 blocks everything → Step 3 (biggest gap, unlocks RQ2/H2/H3) and Step 2 can run in parallel once Step 0 lands → Step 5 depends on Step 3's output → Step 4 can run anytime after Step 0 → Step 6 is fully parallel, start it early since it's the largest time sink → Steps 7-8 last.

If time is genuinely tight and something has to be cut: Step 6 (formal test suites) is the most cuttable — you have substantial *manual* verification already from deploying and testing the live system across prior sessions, which can be cited as evidence even without formal pytest/Behat/Locust automation, with an explicit note in Chapter 4 that automated test coverage is future work rather than pretending it exists.
