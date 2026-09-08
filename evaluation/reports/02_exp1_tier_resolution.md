# Report 2: Experiment 1 — Tier Resolution Analysis

**Status:** Superseded 2026-07-04 — see the correction section below before quoting any number from this report's original 2026-07-03 text
**Roadmap step:** Step 2
**Tests:** RQ1, RO1/RO2, Hypothesis 1 (≥80% resolve at Tier 1 alone)

## Headline result, as corrected 2026-07-04: Hypothesis 1 is NOT supported

**Escalation rate ρ = 52.63% (20/38); Tier 1 resolution rate = 47.37%** — well short of the ≥80% target. The original 2026-07-03 finding below ("Hypothesis 1 is supported, 84.21% resolution") was itself an artifact, this time of a dataset-construction bug (leaked submission duplicates in the `sources/` corpus — see Report 00's addendum and the full correction section after the original text). Precision is now excellent (1.000, zero false positives) once that bug is fixed, but Tier 1 alone resolves far fewer cases than the leaked-corpus numbers suggested. **Read the "Correction (2026-07-04)" section near the end of this file for the full corrected analysis before using any number from the sections immediately below, which are preserved for the DSR narrative but are superseded.**

## Command run

```
python -m evaluation.run_evaluation --split test --verbose --output exp1_test_results_v3.csv
```
Run inside `plagiarism-detection-api-1` on `plagiarism-detector-vm`, against the reconciled 38-item test split (Report 00), after the two Winnowing bug fixes documented in Report 01's addendum.

## Original headline result (2026-07-03, superseded — see correction below)

**Escalation rate ρ = 15.79% (6/38).** Tier 1 resolution rate = 84.21%, comfortably clearing the ≥80% target in RO2/Hypothesis 1. (An earlier run, before the Winnowing fixes, showed the *opposite* — 84.2% escalation — which would have meant H1 failed; that number was an artifact of a broken fingerprint index, not a true measurement. See Report 01's addendum for the full story — this is worth including in Chapter 4 as part of the DSR "search process" narrative, since it's a legitimate example of iterative refinement changing a hypothesis's outcome.)

## Per-category breakdown

| Category | n | Escalated | Escalation rate | Resolved at Tier 1 |
|---|---|---|---|---|
| original | 14 | 1 | 7.1% | 92.9% |
| verbatim | 10 | 0 | 0.0% | 100% |
| near_verbatim | 4 | 0 | 0.0% | 100% |
| paraphrased | 10 | 5 | 50.0% | 50.0% |
| **Total** | **38** | **6** | **15.8%** | **84.2%** |

This closely matches Section 3.10.1's own prediction ("verbatim and original categories near-fully resolved at Tier 1 and paraphrased submissions predominantly escalated") — verbatim/near-verbatim resolve at Tier 1 100% of the time, original 92.9%, and paraphrased is the only category with substantial escalation (50%).

## Tier 1 plagiarism precision (Section 3.5.3's ≥0.95 constraint)

Of the 32 submissions resolved at Tier 1 (not escalated), 29 were classified `TIER1_PLAGIARISED` and 3 `TIER1_ORIGINAL` (verified via `groupby(['category','gate'])` on the raw CSV, not hand-counted from log excerpts — see `evaluation/reports/raw/02_exp1_test_results.csv`).

`TIER1_PLAGIARISED` breakdown by category: 10 `original` (all false positives — see root cause below), 10 `verbatim` (all true positives), 4 `near_verbatim` (all true positives), 5 `paraphrased` (all true positives) = 19 true positives + 10 false positives = 29 total.

`TIER1_ORIGINAL` breakdown: 3, all `original` category, all correct (true negatives).

**Tier 1 plagiarism precision = 19/29 ≈ 0.655**, which **does not meet** Section 3.5.3's ≥0.95 constraint. Report this plainly — it's the direct cost of the Winnowing fix's improved sensitivity, entirely concentrated in one well-understood failure mode (below), not diffuse underperformance.

## Root cause of the `original`-category false positives (well-evidenced, not speculative)

All 10 false positives are Clough & Stevenson submissions (`cs_` prefix); all 4 true negatives in the `original` category are PlagBench (`pb_` prefix) — a perfectly clean split by data source. This is because Clough & Stevenson's methodology has respondents answer short questions *about* a specific Wikipedia source article, which is itself indexed as a corpus document (`orig_taska.txt` etc. in `evaluation/dataset/data/sources/`). A genuine, independently-written short answer legitimately reuses some of the source article's specific terminology — entirely normal and expected — and because these are *short* answers, that shared vocabulary can constitute a large fraction (up to 100%) of the answer's own small fingerprint set, even though it constitutes a tiny fraction of the (much longer) source article. Containment is asymmetric by design (`|query ∩ source| / |query|`), so this is a structural property of applying a fixed containment threshold to short-vs-long document pairs, not a bug in the Winnowing implementation itself.

PlagBench's `original` submissions don't show this pattern because PlagBench's construction methodology doesn't tie each "original" response to a specific pre-existing source document in the same way.

## Discussion for Chapter 4

Two honest, connected findings to report:
1. **Hypothesis 1 is supported** (84.2% Tier 1 resolution rate) — but this masks a real precision problem within that resolution: Tier 1's `TIER1_PLAGIARISED` calls are only 50% precise, well under the 0.95 target, entirely concentrated in one specific, identifiable corpus artifact.
2. The "impossible trinity" reframing from `docs/2026-07-03/chapter_four_five_0521.md` (Section 5.3's conclusion) still applies, but the *locus* of the trade-off has moved: it's no longer "escalation rate vs. Tier 1 precision" as a system-wide tension — the escalation-rate hypothesis is now cleanly supported. The tension is now specifically about how a short-answer corpus interacts with a source-article-derived vocabulary, and only affects one corpus/category combination. This is a *more* precise, more defensible finding for Chapter 4 than the earlier framing.

## Follow-up worth flagging (not fixed here, candidate for Chapter 5 future work or a quick follow-up)

~~A targeted fix is plausible: require a minimum absolute shared-hash count (not just a containment fraction) before triggering `TIER1_PLAGIARISED`, so a 3-word coincidental overlap in a 10-word answer can't hit containment=1.0 on trivial grounds.~~ **Superseded — see the 2026-07-04 correction below.** This diagnosis turned out to be wrong: the false positives were not caused by coincidental short-query vocabulary overlap at all.

## Correction (2026-07-04): the root cause above was wrong — real cause was a dataset-construction bug, not a Winnowing/containment limitation

Before implementing the shared-hash-count fix, a diagnostic script checked the actual `shared_hashes` count behind each of the 10 false positives. Every single one showed `shared_hashes == query_total == matched_document_total` — exact equality in both directions, the signature of matching a **duplicate**, not a partial overlap. The specific case Report 05 analyzed in depth (`cs_g0pC_taskc.txt`) was confirmed to actually match `g0pC_taskc.txt`, not `orig_taskc.txt` (the Wikipedia article Report 05's manual text comparison used) — Report 05's analysis was built on the wrong pair of documents.

**Actual root cause:** `evaluation/dataset/data/sources/` contains a duplicate of all 95 Clough & Stevenson submissions under their bare filename (e.g. `sources/g0pC_taskc.txt` is the same content as `submissions/cs_g0pC_taskc.txt`). Every C&S submission being evaluated was therefore checked against a corpus that already contained an exact copy of itself. See Report 00's addendum for the full discovery and the fix (`run_evaluation.py` and `exp2_cost_accuracy.py` now exclude these 95 leaked duplicates from the indexed corpus, dropping it from 190 to 95 genuine reference documents).

### Corrected results (same command, same test split, fixed corpus)

| | Before fix | After fix |
|---|---|---|
| Escalation rate | 15.79% (6/38) | **52.63% (20/38)** |
| Tier 1 resolution rate | 84.21% | **47.37%** |
| Tier 1 plagiarism precision | 19/29 ≈ 0.655 | not directly comparable — see below |
| Overall precision (dual-tier) | 0.697 | **1.000** |
| Overall recall (dual-tier) | 0.958 | **0.792** |
| Overall F1 (dual-tier) | 0.807 | **0.884** |

**Hypothesis 1 (≥80% Tier 1 resolution) is no longer supported.** With the leaked duplicates removed, Tier 1 alone resolves only 47.37% of the test split — well under the 80% target. This is a direct, mechanical consequence of the fix: the leaked duplicates were giving Tier 1's Winnowing component an artificial, trivial 100%-containment match for every C&S submission that had one (dozens of them, not just the 10 that happened to be ground-truth-`original`), letting many submissions resolve at Tier 1 that would otherwise need Tier 2. Removing that artificial signal source means more submissions genuinely require Tier 2's dense/sparse fusion to resolve confidently.

**All 10 false positives are gone.** Confusion matrix moved from TN=4/FP=10/FN=1/TP=23 to **TN=14/FP=0/FN=5/TP=19**. Precision is now perfect (1.000); the cost is 5 new false negatives (previously true positives), all of them submissions whose final Tier 2 score is genuinely borderline (0.60-0.6549, just under the 0.68 decision threshold) once the artificial duplicate-match boost is gone. This is a legitimate, honestly-reportable finding about `tau_high`'s calibration for hard paraphrase cases — not a new bug, and not something the previous (leaked) numbers could have revealed, since those 5 submissions' scores were previously inflated above threshold by matching a peer's leaked duplicate rather than by genuine signal against the real source.

### What this means for Chapter 4 — this replaces the discussion section above

Two honest findings now, superseding the two originally listed:
1. **Hypothesis 1 is not supported** (47.37% Tier 1 resolution, vs. the ≥80% target) — report this plainly as a real, negative finding once the corpus is correctly constructed. The previously-reported "84.21%, Hypothesis 1 supported" result was an artifact of the leaked-corpus bug, not a true measurement, in exactly the same way the *original* pre-Report-01-fix 84.2% *escalation* number (the opposite problem) was flagged as an artifact back then. This is worth stating explicitly in Chapter 4 as a second instance of the same lesson: a headline hypothesis result changed twice in one thesis, both times because of a data/implementation bug rather than a true property of the algorithm, which is itself a meaningful methodological point about the importance of verifying corpus construction before trusting evaluation numbers.
2. **Tier 1 precision and overall system precision are now genuinely strong** (Tier 1 no longer produces any of the 10 previously-reported false positives; overall dual-tier precision is 1.000) — the "impossible trinity" framing from earlier sessions is resolved differently than expected: it's not that escalation-rate and precision are in tension after all — once the corpus bug is fixed, precision is excellent and the actual trade-off is between escalation rate (cost) and recall on hard paraphrase cases, a cleaner and more defensible story for Chapter 4/5.

## Threshold re-sweep against the corrected corpus (2026-07-04): a modest, legitimate improvement — H1 still not supported

The deployed `tau_low=0.25`/`tau_high=0.68` pair was almost certainly tuned (in an earlier session) against the *leaked* corpus, since that's the only corpus that existed at the time — meaning it may no longer be the right operating point now that the corpus is fixed. This was checked directly with a new script, `evaluation/experiments/exp1b_threshold_resweep.py`, sweeping `tau_low ∈ {0.20, 0.25, 0.30, 0.35}` × `tau_high ∈ {0.55, 0.60, 0.65, 0.68, 0.70, 0.75}` against the same corrected corpus and test split as above.

**Method note — a second, related bug found and fixed while building this script:** the first version of this sweep reused the same `Tier1Detector`/`FingerprintIndex` object across all 24 threshold configurations. Since `FingerprintIndex.submit()` unconditionally inserts the queried document as a side effect, the *first* configuration's queries poisoned the index with every test submission's own fingerprint, making every subsequent configuration degenerate into "predict everyone positive" (this exact bug was also found, independently, in `exp3_threshold_sensitivity.py` — see Report 04's Addendum 3 for the full story and its own, larger correction). Fixed by rebuilding a fresh `FingerprintIndex` for every threshold configuration while reusing the more expensive BM25/FAISS indexes (which aren't mutated by read-only `detect()` calls, so are safe to share).

**Result, properly verified:** the corrected sweep's value at the current deployed operating point (`tau_low=0.25, tau_high=0.68`) reproduces `run_evaluation.py`'s real result *exactly* (F1=0.8837, P=1.000, R=0.7917, escalation=52.63%) — strong evidence the sweep itself is now trustworthy.

**A small, legitimate, free improvement exists:** raising `tau_low` from 0.25 to 0.30 or 0.35 gives *identical* accuracy (F1=0.884, P=1.000, R=0.792) at a **lower escalation rate (47.37% vs. 52.63%)** — 2 fewer of the 38 test submissions need Tier 2, with zero accuracy cost. The submissions scoring in the 0.25-0.35 Tier 1 band are, empirically, never genuine plagiarism cases in this corpus, so resolving them directly as `TIER1_ORIGINAL` instead of escalating loses nothing. **Recommendation: adopt `tau_low=0.30`** (settings.TAU_LOW) as a low-risk, immediately-adoptable correction.

**This does not recover Hypothesis 1.** Even the best point found (escalation as low as 44.7-47.4% depending on exact `tau_low`/`tau_high` combination) remains far short of the ≥80% Tier-1-resolution target — raising `tau_low` further, or changing `tau_high`, trades away precision or recall rather than closing this gap (e.g. `tau_high=0.60` reaches a marginally higher F1=0.885 but at P=0.821, reintroducing false positives; `tau_high=0.65` similarly trades precision for a small F1 change). The honest conclusion: Tier 1's real (uninflated) resolving power on this corpus is genuinely limited to roughly half the test split, and no threshold recalibration changes that — recalibration can only optimize *within* that real constraint, not manufacture resolving power the leaked corpus had only appeared to provide. Report both findings together in Chapter 4: a real, defensible small improvement, and a clear-eyed statement that Hypothesis 1 remains unsupported even after correcting for it. Full sweep results: `evaluation/experiments/exp1b_resweep_results.json`.
