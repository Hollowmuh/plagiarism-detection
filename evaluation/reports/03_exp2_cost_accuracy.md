# Report 3: Experiment 2 — Cost-Accuracy Trade-offs

**Status:** Corrected 2026-07-04 (see addendum) — original 2026-07-03 numbers below are superseded but preserved for context. **Further corrected 2026-07-14**: cloud-only/hybrid-static's F1 revised 0.828→0.842 after confirming (not just flagging) FAISS-index contamination in the always-escalate baselines; dual-tier's own numbers confirmed unaffected. No conclusion changes, only the exact baseline F1.
**Roadmap step:** Step 3
**Tests:** RQ2, RO3, Hypotheses 2 & 3 (≥90% of cloud-only effectiveness at ≤30% of cost; F1 ≥ 0.84)

## Corrected headline (2026-07-04): dual-tier now has the highest F1 of all four configurations

A dataset-construction bug (leaked submission duplicates in the `sources/` corpus — Report 00's addendum, Report 02's correction) affected all four configurations below, since all of them load their corpus via the same `sources/`-listing code. Fixed and re-run:

| Configuration | Precision | Recall | F1 | Escalation rate |
|---|---|---|---|---|
| (a) Local-only | 0.895 | 0.708 | 0.791 | 0% |
| (b) Cloud-only | 0.706 | 1.000 | 0.828 | 100% |
| (c) Hybrid-static | 0.706 | 1.000 | 0.828 | 100% |
| (d) **Dual-tier (proposed)** | **1.000** | 0.792 | **0.884** | 52.63% |

**Correction (2026-07-14):** rows (b) and (c) above were measured against a contaminated shared FAISS index (see the 2026-07-14 addendum near the end of this file) — the true, clean-index numbers are **P=0.727, R=1.000, F1=0.842** for both cloud-only and hybrid-static. Rows (a) and (d) are unaffected (confirmed identical with and without contamination). This doesn't change the ranking or any hypothesis verdict below, only the exact baseline F1 (0.828→0.842) — use 0.842 if citing an exact number in Chapter 4.

**Dual-tier now strictly dominates on F1** — 0.884 vs. 0.828 for both full-Tier-2 baselines and 0.791 for local-only — while also being the cheapest by a wide margin. This is a stronger, cleaner result than the original 2026-07-03 numbers below: previously dual-tier was framed as "99.1% of cloud-only's F1 at 15.8% of its cost" (a good-but-not-best trade-off); it's now the best-performing configuration *and* the cheapest, because the leaked duplicates were suppressing dual-tier's precision advantage more than the always-escalating baselines' (which could "absorb" some of the false-positive cost via Tier 2's fusion in a way Tier-1-alone or the gate couldn't).

**Hypothesis 3 (F1 ≥ 0.84) is now supported** (0.884 > 0.84) — reversing the original "not quite met" finding. **Hypothesis 2's cost claim needs restating**: escalation rate rose from 15.79% to 52.63% (see Report 02's correction for why — Tier 1 was relying on the leaked duplicates for easy resolutions), so the cost savings figure below (84.2%) is now **47.4%** — still a real, substantial saving, but a smaller margin than before. Full corrected numbers: cost $0.0020 vs. baseline $0.0038 (47.4% savings), latency p50=52ms/p95=209ms/p99=291ms (up from p50=12ms/p95=107ms/p99=118ms, tracking the higher escalation rate directly).

**Statistical significance, re-tested:** dual-tier vs. local-only is now significant at the uncorrected level (p=0.0439) but still not at the Bonferroni-corrected threshold (α=0.0167); vs. cloud-only/hybrid-static, still not significant (p=0.20). The core honest conclusion from the original report — that this sample size (n=38) can't statistically distinguish the configurations' per-submission accuracy even when the point-estimate gap looks meaningful — still holds, and if anything is reinforced: a genuinely *larger* F1 gap (0.884 vs 0.828, an 5.6-point gap, larger than the original 0.7-point gap) is *still* not significant after correction, underscoring how much power this sample size lacks.

See Report 00's addendum and Report 02's correction for the full mechanism and diagnostic evidence. Raw corrected data: `evaluation/reports/raw/03_exp2_results_corrected.json`.

## Addendum (2026-07-04, later same day): re-run at the re-tuned τ_low=0.30, and a needed correction to the Hypothesis 2 claim above

Report 02's threshold re-sweep found `τ_low=0.30` (up from 0.25) gives identical accuracy at lower escalation, and it was adopted as the deployed value (`settings.TAU_LOW`). Re-ran both `run_evaluation.py` and this script against the new deployed threshold to get an exact, non-extrapolated figure rather than estimating it:

| | τ_low=0.25 (previous) | τ_low=0.30 (now deployed) |
|---|---|---|
| Precision / Recall / F1 | 1.000 / 0.792 / 0.884 | **identical** — 1.000 / 0.792 / 0.884 |
| Escalation rate | 52.63% (20/38) | **47.37% (18/38)** |
| Cost | $0.0020 | **$0.0018** |
| Savings vs. cloud-only | 47.4% | **52.6%** |
| Latency | p50=52ms, p95=209ms, p99=291ms | p50=21ms, p95=261ms, p99=351ms |

Accuracy is confirmed identical (verified, not assumed) — this is a pure cost improvement from the re-tuning, exactly as Report 02 found.

**Correction to the Hypothesis 2 claim above:** the "Hypothesis 2's cost claim needs restating... still a real, substantial saving" language above did not go far enough. Hypothesis 2 has two parts — ≥90% of cloud-only's effectiveness **and** ≤30% of its cost — and they now need to be scored separately, not blended into one "still supported, just smaller" statement:
- **Effectiveness part: not just met but exceeded.** Dual-tier's F1 (0.884) is *higher* than cloud-only's (0.828), i.e. 106.8% of cloud-only's effectiveness, not merely ≥90%.
- **Cost part: not met.** Even at the improved 52.6% savings, dual-tier's cost is 47.4% of cloud-only's — above the ≤30% target. This was true at the original 47.4%-savings figure too (52.6% of cost) and remains true after the re-tuning improvement; the gap narrowed but the target isn't cleared.

**Correct, honest statement of H2: partially supported** — the effectiveness bar is cleared comfortably, the cost bar is not, at either threshold tested. This is a real, legitimate finding, not a failure to hide: the dominant cost driver is the escalation rate itself (47-53% of submissions needing Tier 2), and Report 02 already establishes that this reflects Tier 1's genuine (uninflated) resolving power on this corpus, not a threshold-tuning shortfall — the same underlying fact that makes Hypothesis 1 unsupported also caps how much the cost side of Hypothesis 2 can improve through threshold tuning alone. Report both halves of H2 distinctly in Chapter 4 rather than a single pass/fail verdict.

## Addendum (2026-07-14): the FAISS-contamination caveat below was actually tested, not just flagged — it's real, and it materially affects the two always-escalate baselines

The "Methodological caveat: FAISS index contamination" section below (written 2026-07-04) flagged that `FAISSIndex()`'s default auto-load of a shared, persisted index file *could* affect results, but hedged: "this should not materially affect the reported scores." That claim was never actually verified against a clean, isolated index — it was reasoned, not tested. This addendum tests it.

**Method:** re-ran `run_evaluation.py` (dual-tier) and `exp2_cost_accuracy.py` (all 4 configs) with `FAISS_INDEX_PATH` pointed at a freshly-created, isolated index file (`/tmp/clean_eval_faiss*.faiss`) instead of the default shared path (`/data/faiss/index.faiss`, confirmed to resolve to a real, persisted local file that had accumulated vectors from every evaluation run and pipeline test across this entire multi-week session — a much larger contamination than the "recent Moodle test submissions" scope originally flagged).

**Result: the hedge was wrong for the two always-escalate baselines, correct for dual-tier.**

| Configuration | Precision/Recall/F1 (contaminated, previously reported) | Precision/Recall/F1 (clean index) |
|---|---|---|
| Local-only | 0.895 / 0.708 / 0.791 | **identical** (never touches FAISS) |
| Cloud-only | 0.706 / 1.000 / 0.828 | **0.727 / 1.000 / 0.842** |
| Hybrid-static | 0.706 / 1.000 / 0.828 | **0.727 / 1.000 / 0.842** |
| **Dual-tier** | 1.000 / 0.792 / 0.884 | **identical** (1.000 / 0.792 / 0.884) |

**Mechanism, confirmed not just theorized:** cloud-only and hybrid-static send *every* submission through Tier 2's FAISS search — every query is exposed to whatever extra, unrelated candidate vectors happen to be sitting in the shared index. Dual-tier only escalates ambiguous cases (52.63% here), and a genuine best-match tends to dominate the fused score regardless of a few extra contaminating candidates in the pool — confirmed by testing, not assumed: dual-tier's numbers are bit-for-bit identical with and without contamination. The same robustness was independently confirmed for Report 04's exp3 methodology (also gated/tiered, also FAISS-dependent) — its F1 values were unaffected by the same contamination, for the same structural reason.

**This does not change any qualitative conclusion.** Dual-tier (F1=0.884) is still clearly the best of all four configurations even against the corrected, higher baseline F1 (0.842) — the margin narrows slightly (0.042 vs. the previously-reported 0.056) but the ranking and the cost story are unchanged. Hypothesis 3 (F1≥0.84) is still supported by dual-tier. **The corrected numbers above are now the authoritative ones** — update the "Corrected headline" table earlier in this report if citing exact baseline precision/recall/F1 in Chapter 4; the qualitative narrative in that section still holds.

**Fix applied, not just diagnosed:** re-generated `evaluation/reports/raw/03_config_comparison.png` from the clean run (the old version, like every plot in this report before 2026-07-14, was rendered from the original 2026-07-03 run and had never been regenerated after *any* subsequent correction — a separate, broader staleness issue found and fixed the same day across the whole `reports/` folder). Clean-index raw results: `evaluation/reports/raw/03_exp2_results_clean_index.json`.

**Remaining, deliberately out of scope:** the *production/Moodle-facing* FAISS index is expected to be shared and cumulative by design (that's the whole point — cross-submission matching needs a growing corpus) — this contamination finding is specific to *evaluation* runs incorrectly sharing that same index path instead of using an isolated one, not a flaw in the production architecture. A permanent fix (e.g. all evaluation scripts defaulting to a temp path unless explicitly told to share) is worth doing but wasn't applied to the scripts themselves in this pass — only re-run with an environment-variable override. Future evaluation runs should set `FAISS_INDEX_PATH` to an isolated path explicitly rather than relying on the default.

## Original report (2026-07-03), preserved below for context — numbers superseded by the corrections above

## Method note: `evaluation/experiments/exp2_cost_accuracy.py` was fixed and committed

The script had two real bugs that made it unsafe to run as-is: its `load_data()` expected a `labels.csv` schema (`id`, `plagiarism` columns) that doesn't match our real dataset (`filename`, `is_plagiarised`, per Report 00's reconciliation), and its built-in "dual-tier" configuration **re-simulated gating inline with hardcoded `tau_low=0.25`/`tau_high=0.75`** rather than calling the real, fixed pipeline — meaning it would have silently used the stale pre-retuning threshold (0.75, not our tuned 0.68) and produced numbers inconsistent with Reports 01/02.

Fixed in place and committed: corrected schema loading, corpus now loads from `sources/` (matching what Report 02's `run_evaluation.py` indexes, so the comparison is apples-to-apples), and dual-tier is loaded from a `run_evaluation.py` output CSV via a new `--dual-tier-csv` flag rather than re-simulated a second, less-trustworthy way. Run as:
```
python -m evaluation.run_evaluation --split test --output <path>   # produces the dual-tier CSV first
python -m evaluation.experiments.exp2_cost_accuracy --data-dir evaluation/dataset/data --dual-tier-csv <path>
```
Verified to reproduce identical numbers across 3 separate runs (an ad-hoc version written first, then the committed fix, run twice). Also generates `evaluation/figures/config_comparison.png` (saved to `evaluation/reports/raw/03_config_comparison.png`) and `evaluation/experiments/exp2_results.json` (saved to `evaluation/reports/raw/03_exp2_results.json`).

**Note if re-running in a container:** if files were transferred via `docker cp` rather than a live bind mount, the destination directory may end up owned by a different UID than the container's runtime user, causing a `PermissionError` when the script tries to save `exp2_results.json` — fix with `docker exec -u root <container> chown -R <user>:<user> <path>` before running. This bit me once this session; not a bug in the script itself.

## Results (test split, n=38)

| Configuration | Precision | Recall | F1 | Escalation rate | Cost (per 38 subs) | p50 (ms) | p95 (ms) | p99 (ms) |
|---|---|---|---|---|---|---|---|---|
| (a) Local-only | 0.677 | 0.875 | 0.764 | 0% | $0.0000 | 10 | 18 | 22 |
| (b) Cloud-only | 0.686 | 1.000 | 0.814 | 100% | $0.0038 | 123 | 274 | 351 |
| (c) Hybrid-static | 0.686 | 1.000 | 0.814 | 100% | $0.0038 | 135 | 282 | 330 |
| (d) **Dual-tier (proposed)** | 0.697 | 0.958 | **0.807** | **15.79%** | **$0.0006** | **12** | **107** | **118** |

(Cost figures use `c_cloud = $0.0001` per Tier-2-processed submission, per Section 3.11.3's rate; scale by `1000/38` for a per-1000-submissions figure if quoting alongside commercial pricing — e.g. dual-tier ≈ $0.016/1000 vs. cloud-only ≈ $0.10/1000.)

## Hypothesis 2: supported

Dual-tier reaches **0.807/0.814 = 99.1% of cloud-only's F1** at **0.0006/0.0038 = 15.8% of cloud-only's cost** — comfortably clears both the ≥90% effectiveness and ≤30% cost targets. Latency is also dramatically better (p95 107ms vs. 274-282ms for the two full-Tier-2 baselines), because most submissions resolve instantly at Tier 1 (12ms) rather than needing the ~250-300ms round trip through embedding + FAISS.

## Hypothesis 3: not quite met, with a specific, known cause

F1 = 0.807 falls short of the ≥0.84 target. This is not diffuse underperformance — Report 02 already identifies the exact cause: 10 of 38 test submissions (all `original`-category, all Clough & Stevenson) are false positives due to short-answer/source-article vocabulary overlap. Every other category (verbatim, near-verbatim, paraphrased) scores at or near perfect F1 across all 4 configurations. If those 10 false positives were resolved (see Report 02's flagged follow-up), F1 would rise substantially — this is worth explicitly modeling in Chapter 4 as a "what if" alongside the honest as-measured number.

## Statistical test: paired t-test, dual-tier vs. each baseline (Bonferroni-corrected, α=0.05, corrected α=0.0167)

| Comparison | Mean diff | 95% CI | t | p | Significant? |
|---|---|---|---|---|---|
| Dual-tier vs. local-only | +0.053 | (0.000, 0.132) | 1.434 | 0.160 | No |
| Dual-tier vs. cloud-only | 0.000 | (−0.079, 0.079) | 0.000 | 1.000 | No |
| Dual-tier vs. hybrid-static | 0.000 | (−0.079, 0.079) | 0.000 | 1.000 | No |

**Report this honestly:** at n=38, dual-tier's per-submission correctness is not statistically distinguishable from any of the 3 baselines — including local-only, despite a 4-point F1 gap in the point estimate. The real, defensible claim from this experiment is about **cost and latency**, which are near-deterministic given the escalation rate (not something that needs a significance test the way accuracy does) — dual-tier's cost/latency advantage over cloud-only and hybrid-static is real and large, while its accuracy is statistically equivalent to all three baselines at this sample size. Don't claim a significant accuracy advantage that the test doesn't support; the cost/latency story is the genuinely strong, supportable result here.

## Methodological caveat: FAISS index contamination

`FAISSIndex()` auto-loads a persisted index from `/data/faiss/index.faiss` by default, and this file is shared with the *live production* Moodle deployment (real student1/student2 test submissions from earlier sessions) plus every prior evaluation run this session. Candidate pool sizes in the verbose logs show 100-103 candidates per query (expected corpus size for a clean run: ~190 source docs, but candidate counts here reflect FAISS top-k retrieval limits, not raw corpus size contamination directly) — the persisted file was not reset before this run, to avoid destructively affecting real production embeddings. This should not materially affect the reported scores (Tier 2's fusion score is computed directly from the top-matching candidate, not renormalized against the full candidate pool, per the Report 01 fix), but could affect which document is reported as `best_match_id` in edge cases. Worth isolating with a dedicated eval-only FAISS index path in future work (Report 05/future work).

## Answer to RQ2

*"How does the confidence-gated dual-tier system compare against local-only, cloud-only, and hybrid-static baselines on precision, recall, F1-score, latency, and per-1,000-submission cost?"* — Table above answers this directly. Dual-tier trades a small, not-statistically-significant amount of accuracy for a large, real reduction in cost (84.2% savings vs. cloud-only) and latency (p95 ~2.5-2.6× faster than cloud-only/hybrid-static).
