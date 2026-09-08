# Chapter 4 & 5 Action Plan

## ⚠️ Read this first: a discrepancy that shapes everything below

Chapter 3, Section 3.7 ("Dataset Construction") describes the evaluation corpus as **self-collected**: 40 verbatim (Wikipedia + open-access papers inserted into essays), 40 near-verbatim (rule-based WordNet synonym swap), 60 paraphrased (GPT-4 generated, manually reviewed), 60 original (anonymised past course submissions), 200 total, with a 60/20/20 train/val/test split.

The actual `evaluation/dataset/data/` folder in the repository does not match this. Its filenames (`cs_g1pA_taskb.txt`, `cs_g4pE_taske.txt`, ...) are the exact naming convention of **Clough & Stevenson (2011)**, *"Developing a corpus of plagiarised short answers,"* *Language Resources and Evaluation*, 45(1), 5-24 — a well-known, citable, real academic corpus (5 tasks × ~19 respondents, cut-and-paste/light-paraphrase/heavy-paraphrase/non-plagiarised categories). The `pb_` prefixed files match **PlagBench** (Lee, Agrawal, Uchendu, Le, Chen & Lee, 2025, NAACL — *"PlagBench: Exploring the Duality of Large Language Models in Plagiarism Generation and Detection,"* arXiv:2406.16288), a 46.5K-pair synthetic benchmark covering verbatim/paraphrase/summarisation plagiarism.

Splits are also 110/38/38 (train/val/test), not the stated 60/20/20 of 200 total — close, but not what Chapter 3 claims.

**This is not a small citation fix.** It means either:
- **(A)** Chapter 3 gets corrected to accurately describe the real data sources (Clough & Stevenson + PlagBench — both are *more* citable/defensible than home-grown data, so this is a clean fix, just needs the text and Table 3.1 rewritten and the two references added), **or**
- **(B)** the actual 200-submission custom corpus described in Chapter 3 gets built for real before Chapter 4 is written, so the results chapter reports on what the methodology chapter promised.

**Recommendation: (A).** Rebuilding a real, IRB-adjacent, department-approved 200-submission corpus with anonymised past student essays is weeks of separate work (ethics approval, GPT-4 generation + manual review at ~15% discard rate, inter-rater kappa on a 20-item audit) that doesn't change what the system does — it only changes what you evaluate it against. Using established, peer-reviewed corpora is standard practice and arguably *strengthens* external validity (a marker/examiner can independently verify Clough & Stevenson's properties; they can't verify your private essay collection). Flag this explicitly to your supervisor before proceeding — this is a decision they should sign off on, not one to make silently.

If you go with (A), the following need updating before Chapter 4 is written:
- Section 3.7 rewritten to describe Clough & Stevenson + PlagBench sourcing and composition (actual category counts, actual split sizes — pull these directly from `evaluation/dataset/data/labels.csv` and `splits/*.csv`, don't estimate)
- Table 3.1 replaced with real numbers
- References list: add Clough & Stevenson (2011) and Lee et al. (2025) — full citations at the bottom of this doc
- Section 3.7.3 (labelling protocol / Cohen's kappa / 2-week-separated second-pass review) either removed or re-scoped, since these categories were labelled by the original corpus authors, not by you

---

## What's already real, from this session's work

You have genuine, already-executed experimental results — not projections. This is unusual and valuable: most of Chapter 4 is normally written *after* a clean final run, but you're starting from a documented bug-fix narrative that itself satisfies Hevner's DSR guideline 6 ("design as a search process" — Section 3.2, item 11).

**A real bug was found and fixed mid-project:** Tier 2 was scoring 0.000 F1 (zero recall) due to two independent bugs — a destructive per-query min-max renormalization, and a doc-ID/chunk-ID key mismatch that silently prevented the sparse and dense fusion from ever combining both signals for the same candidate. Full writeup: `docs/2026-07-03/tier2_scoring_fix_0458.md`. Fixing both, then retuning `TAU_HIGH` (0.75→0.68) via proper val-then-test methodology, took test-split F1 from 0.000 to **0.815** (P=0.733, R=0.917).

This is a legitimate, citable methodological finding in its own right (silent scoring corruption with no thrown errors, only caught by actually running the evaluation harness rather than trusting the pipeline "working") — Chapter 4 should report it, not bury it. It also directly demonstrates RO1 (architecture design) and the DSR "search process" guideline.

**What you already have data for:**
- Test-split F1 = 0.815, P = 0.733, R = 0.917 (n=38)
- Per-category F1: near_verbatim 1.000, verbatim 1.000, paraphrased 0.889, **original 0.000** (see limitation below)
- Latency: p50=126ms, p95=275ms, p99=301ms — comfortably inside the 5-second p95 budget (Hypothesis 4 / RQ3)
- Escalation rate: 84.2% (test), 89.5% (val)
- A 2D grid search over `alpha × tau_high` confirming the "original" false-positive rate doesn't respond to reweighting (see limitation below)

**What contradicts the thesis's own hypothesis, and must be reported honestly, not hidden:**
Section 3.4.2 and RO2 (Hypothesis 1) require escalation rate ≤ 25% ("80% resolve at Tier 1 alone"). Your actual measured escalation rate is **84.2%** — almost the exact inverse. This is the single most important number to address in Chapter 4. It doesn't mean the system failed; it means `tau_low`/`tau_high` as currently set don't satisfy the stated design constraint, and that's a real, reportable finding with a real, fixable cause (see Action 3 below).

**Known, externally-corroborated limitation:** the "original" (non-plagiarised) category has a 0.000 F1 — roughly half of true-original documents in the Clough & Stevenson set are false-flagged. A 2D grid search across a wide `alpha`/`tau_high` range found no configuration that fixes this without sacrificing recall elsewhere — same-prompt student essays share genuine topical/lexical overlap that isn't distinguishable from copying by pure similarity. This is independently corroborated by **PAN 2025** (arXiv:2510.06805): even their embedding-based approaches, evaluated on a purpose-built dataset, top out around 0.5 precision, and the same approaches *"underperform significantly"* when cross-validated against the older PAN 2015 benchmark — the paper's stated conclusion is exactly your finding: embedding similarity conflates topical closeness with copying, and this doesn't fully resolve with tuning. This gives you a real, citable anchor for the "known limitation, not a bug" framing in both Chapter 4 (discussion) and Chapter 5 (future work).

---

## Chapter 4 Action Plan: Results and Discussion

Structure Chapter 4 around the 3 experiments and 5 research questions already defined in Section 3.10 — don't invent a new structure. Standard guidance for this chapter (see references) is to organise around research questions/hypotheses, use tables/figures for quantitative results, and discuss *every* reported number, not just the favourable ones.

### 4.1 Chapter Introduction
One paragraph restating the 3 experiments and what each tests (mirror Section 3.10). State the actual dataset used (post dataset-discrepancy resolution above) and its final composition/split sizes pulled directly from the repo's `labels.csv`/`splits/*.csv`.

### 4.2 Experiment 1: Tier Resolution Analysis (RQ1, RO1/RO2, Hypothesis 1)
**Action needed:** you have escalation-rate data (84.2%/89.5%) but not yet broken down per-category as Section 3.10.1 specifies ("verbatim and original near-fully resolved at Tier 1, paraphrased predominantly escalated"). Re-run `evaluation/run_evaluation.py --split test --verbose` and tabulate escalation rate by category from the per-sample CSV output (already captures `category` and `escalated` columns — just needs a groupby, no new code).

**Report honestly:** Hypothesis 1 (≥80% Tier 1 resolution) is **not supported** by current thresholds (84.2% escalate, i.e. only ~16% resolve at Tier 1 alone). Present the actual number, then discuss why: `tau_low=0.25` is unchanged from the original design, but `TAU_HIGH` was lowered from 0.75→0.68 specifically to fix the Tier 2 scoring bug's downstream precision problem (Section 3.4.2's constraint that Tier 1 plagiarism precision ≥0.95 pulls in the opposite direction from a low escalation rate — document this tension explicitly, it's a genuine architectural trade-off, not an oversight).

**Optional strengthening action, time permitting:** re-run the `alpha × tau_high` grid search (script already used this session, was in `evaluation/experiments/` conceptually — see `docs/2026-07-03/tier2_scoring_fix_0458.md` for the exact methodology) but this time optimise jointly for F1 subject to the ≤25% escalation constraint, as Section 3.10.3's threshold-sensitivity sweep was designed to do. Report whether *any* point on the Pareto frontier satisfies both the ≤25% escalation and reasonable F1 — if not, that's itself a finding worth stating plainly: the stated 80/20 hypothesis may be incompatible with acceptable precision on this corpus, which is a legitimate, defensible conclusion for a final-year project to reach.

### 4.3 Experiment 2: Cost-Accuracy Trade-offs (RQ2, RO3, Hypotheses 2 & 3)
**Not yet done — this is the biggest remaining gap.** Section 3.10.2 requires comparing **4 configurations**: local-only, cloud-only, hybrid-static, and dual-tier. You currently only have dual-tier numbers. The repo already has `evaluation/baselines/local_only.py`, `cloud_only.py`, and `hybrid_static.py` — these exist but (as far as this session's work went) were never run against the corrected tier2 code.

**Action:** run all three baseline scripts + `run_evaluation.py` (dual-tier) against the same test split, tabulate P/R/F1/cost/latency for all 4 side by side (this is Table 4.X, the centrepiece of Chapter 4). Compute cost via Section 3.5.5's formula using the *actual* escalation rate you measured, not a projected one.

**Statistical test:** Section 3.10.2 specifies a paired t-test (dual-tier vs. cloud-only per-submission F1, Bonferroni-corrected across 3 pairwise comparisons, α=0.05). `evaluation/metrics.py`'s `paired_comparison()` function already implements this — it just needs per-sample score arrays from all 4 configurations fed in. Do not skip the significance test and just report point estimates; Section 3.2's DSR guideline 4 (rigour) commits you to it.

**Honest framing:** with dual-tier F1=0.815 against a target of ≥0.84 (Hypothesis 3), state plainly whether the hypothesis is supported (it's close but not quite met on this measurement) and discuss why — likely the same "original" category limitation. Don't round 0.815 up to sound like it hit 0.84.

### 4.4 Experiment 3: Threshold Sensitivity & Real-Time Demonstration (RQ3/RQ4, Hypotheses 4 & 5)
**Latency (Hypothesis 4):** already done — p95=275-299ms is well inside the 5-second budget, comfortably supported. Report as-is, this is a clean win, but note it was measured in-process (no Celery/HTTP overhead) — see limitations below.

**Threshold sensitivity heatmap:** not yet done at the 3×3 grid specified in Section 3.10.3 (`tau_low ∈ {0.20,0.25,0.30}`, `tau_high ∈ {0.70,0.75,0.80}`). The 2D sweep this session did was wider but different-shaped (single-tau_low, finer tau_high granularity, plus an alpha dimension). Either re-run the exact 3×3 grid as specified for a clean heatmap figure, or explicitly amend Section 3.10.3 to describe the wider sweep you actually ran (more informative, but needs the methodology chapter to match).

**Real-time cross-submission demonstration:** not yet done. This requires actually driving the deployed Moodle instance — submit Student B's essay, wait 15 minutes (or fake the clock), submit a paraphrased Student D copy, verify detection within 5 seconds and that the dashboard shows the cross-reference. You already proved the *underlying mechanism* works in a previous session (student1/student2 cross-submission test on the live Moodle deployment, tier1→tier2 escalation, badge rendering) — this experiment is largely a formalisation/re-run of that with timing instrumentation added, not new engineering. Repeat 5× per Section 3.10.3, log actual latency each time.

### 4.5 Confusion Matrices & Failure Mode Analysis (Section 3.12.4)
You have the confusion matrix (TN=6, FP=8, FN=2, TP=22 on test). Section 3.12.4 requires manually inspecting sampled false positives to characterise failure modes — do this for a handful of the 8 false-positive "original" documents: read the actual matched passages, confirm/refute the "same-prompt topical overlap" hypothesis with real textual evidence rather than just asserting it. This turns a plausible guess into a documented finding.

### 4.6 Unit/Integration/Performance Testing (Sections 3.12.1-3.12.3)
Not addressed this session. Needs: pytest suite with `coverage.py` ≥80% (Section 3.12.1), Behat integration test against the Dockerised Moodle instance (3.12.2 — you have a working Moodle deployment already, this formalises what's been manually verified), and Locust load test ramping 1→50 concurrent users (3.12.3). These are real engineering tasks, not writing tasks — budget time accordingly, likely the largest remaining time cost in this chapter.

### 4.7 Chapter Summary
One page synthesising: which hypotheses were supported (H3 latency: yes; H1 escalation rate: no, with explanation; H2/H3 cost-accuracy: pending Section 4.3's baseline runs), and a forward pointer into Chapter 5.

---

## Chapter 5 Action Plan: Summary, Conclusion, and Recommendations

Standard structure (see references): Summary → Summary of Findings → Conclusions → Recommendations, with recommendations split between practical/deployment recommendations and future-research recommendations — conventionally one future-research recommendation per original research question (you have 5 RQs, so aim for around 5).

### 5.1 Summary
Half a page restating the research aim, the 5 objectives (RO1-RO5), and the DSR methodology — no new content, purely orientation for a reader who skips straight to Chapter 5 (which examiners often do).

### 5.2 Summary of Findings
Map directly onto the 5 research questions from Section 1.4, one paragraph each, each citing the specific Chapter 4 number:
- RQ1 (80% Tier 1 resolution?) → No, 84.2% escalated, not ≤20-25%. State the actual number and the precision/escalation-rate tension identified in 4.2.
- RQ2 (dual-tier vs. 3 baselines) → pending Section 4.3's runs; report P/R/F1/cost/latency comparison table result once available.
- RQ3 (5s p95 latency budget) → Yes, comfortably (275-299ms measured).
- RQ4 (optimal α, τ_low, τ_high, and sensitivity) → report the actual tuned values (α=0.6, τ_low=0.25, τ_high=0.68) and the sensitivity finding that the "original" false-positive rate doesn't respond to retuning within a wide range — this is itself an answer to "how sensitive is the system," just not the answer originally expected.
- RQ5 (open-source reproducibility) → straightforward if the repo, dataset composition (once corrected), and evaluation harness are published under the stated licences.

### 5.3 Conclusions
Distinct from the findings summary — this is where you state what the findings *mean*. Suggested framing: the dual-tier architecture is real and functional (proven via actual Moodle deployment + real bug fixes + real evaluation), it clearly satisfies the latency and cost-reduction goals, but the specific 80/20 escalation-rate hypothesis as originally stated doesn't hold at the precision level the architecture also requires — meaning the "impossible trinity" framed in Section 1.2.1 isn't fully broken, it's *relocated*: the trade-off shifted from "accuracy vs. cost" to "escalation-rate vs. Tier-1 precision," which is a more precise, more honest characterisation of the actual trade-off surface than the thesis originally hypothesised. That reframing is itself a legitimate contribution — negative/partial results that sharpen the research question are standard, valid science, not a failure of the project.

### 5.4 Recommendations
**Practical/deployment recommendations** (for institutions adopting this): document the actual tuned thresholds, note that the "original" false-positive rate means results should be presented to instructors as advisory (mirrors the same design principle you already applied to the AI-detection tier in this codebase — cross-reference it, it's a consistent design philosophy worth naming explicitly).

**Future-research recommendations**, roughly one per RQ, grounded in what's actually been learned:
1. Investigate features beyond pure lexical/semantic similarity to separate "same-topic original work" from "copying" — cite the PAN 2025 (arXiv:2510.06805) finding that this exact confusion is a known open problem, not unique to this system.
2. Test generalisation across corpora (PAN 2025's own headline finding: embedding-based methods that do well on one dataset can fail badly on another) — evaluate this system against a second corpus beyond Clough & Stevenson/PlagBench to check whether F1=0.815 holds up, directly extending the "search process" the thesis already documents.
3. Explore whether a 3-region gating function (rather than 2 thresholds) or a learned classifier over `(c1, dense, sparse)` rather than fixed linear interpolation could resolve the escalation-rate/precision tension identified in 4.2/5.3.
4. Extend the AI-generated-text detection tier (already built in this codebase, separate from the plagiarism pipeline) with a proper validated corpus and ESL-bias-aware calibration, per your own project's documented caveats.
5. Complete cross-lingual and multi-LMS (Canvas/Blackboard) support, explicitly deferred in Section 1.6.2's delimitations.

---

## Suggested order of operations

1. **Resolve the dataset discrepancy first** (decision + Chapter 3 correction) — everything else in Chapter 4 depends on knowing what corpus you're actually reporting against.
2. Run the 3 baseline comparisons (Section 4.3) — this is the single highest-value missing piece, since RQ2/H2/H3 are unaddressed without it.
3. Run the proper 3×3 threshold heatmap + statistical significance tests.
4. Do the manual false-positive inspection (4.5) — cheap, and turns a hypothesis into a documented finding.
5. Write Chapter 4 sections in the order above, citing real numbers only.
6. Write Chapter 5, which is largely synthesis once Chapter 4 exists — should be fast once 4 is solid.
7. Testing suite (4.6) and real-time demo (4.4) can run in parallel with writing, since they don't block the narrative — but budget real time for them, they're not paperwork.

## References for this planning doc

- Clough, P., & Stevenson, M. (2011). Developing a corpus of plagiarised short answers. *Language Resources and Evaluation*, 45(1), 5-24.
- Lee, J., Agrawal, T., Uchendu, A., Le, T., Chen, J., & Lee, D. (2025). PlagBench: Exploring the duality of large language models in plagiarism generation and detection. *Proceedings of NAACL 2025*. arXiv:2406.16288.
- [Overview of the Plagiarism Detection Task at PAN 2025](https://arxiv.org/abs/2510.06805) — arXiv:2510.06805. Cross-dataset generalisation finding directly relevant to Chapter 4 discussion and Chapter 5 future work.
- [How to Write Chapter 4 of a Dissertation: Results Guide](https://www.assignnmentinneed.com/blog/how-to-write-chapter-4-of-a-dissertation)
- [Results and Discussion — Writing the Dissertation, University of Southampton Library Guides](https://library.soton.ac.uk/writing_resultsanddiscussion)
- [Chapter 5: Summary, Conclusions, and Recommendations, VTech](https://vtechworks.lib.vt.edu/bitstream/handle/10919/30772/ch5-src.PDF)
- [The Purpose of Chapter 5 in a Dissertation, Statistics Solutions](https://www.statisticssolutions.com/the-purpose-of-chapter-5-in-a-dissertation/)
- `docs/2026-07-03/tier2_scoring_fix_0458.md` (this repo) — full technical writeup of the bug fix and evaluation results referenced throughout this plan.
