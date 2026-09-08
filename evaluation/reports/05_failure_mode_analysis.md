# Report 5: Failure Mode Analysis

**Status:** Corrected 2026-07-04 — the two case studies below were misdiagnosed; see the correction section at the end before citing this report
**Roadmap step:** Step 5
**Depends on:** Report 03's dual-tier confusion matrix (10 false positives, all `original`-category, all Clough & Stevenson) — this confusion matrix is itself superseded, see Report 03's 2026-07-04 correction

## Correction (2026-07-04): both case studies below compared the wrong documents

While implementing a different, unrelated fix, a diagnostic script checked what `cs_g0pC_taskc.txt` (Case 2 below) actually matched against in the live system, rather than the plausible-looking document assumed at the time. The system's real `best_match_id` was `g0pC_taskc.txt` — a duplicate of the submission itself, accidentally present in the evaluation corpus's `sources/` folder (see Report 00's addendum for the full mechanism: all 95 Clough & Stevenson submissions were duplicated into `sources/` under their bare filename). **`orig_taskc.txt`, which the analysis below quotes and compares against, was never the document the system actually matched.** The same applies to Case 1 (`cs_g4pE_taske.txt`) — both submissions were matching their own leaked duplicate, not showing a genuine ambiguous-vocabulary-overlap case.

This was a real methodological lapse in the original analysis: `orig_taskX.txt` was assumed to be the relevant comparison document because it was the *plausible* canonical source for the task, without first checking what the pipeline's own `best_match_id` field actually returned. The lesson generalizes and is worth stating in Chapter 4/5: when writing a textual case study of a detection result, always verify against the system's own reported match, not the document that seems like it *should* be the match.

**With the leaked duplicates removed from the corpus (Report 00/02's fix), both of these submissions now correctly resolve as non-plagiarised** (`cs_g0pC_taskc.txt`: escalates to Tier 2, final score 0.600, below the 0.68 threshold; `cs_g4pE_taske.txt`: escalates, final score 0.637, also below threshold) — this specific failure mode (leaked-duplicate self-matches) is now fully eliminated, not merely reduced: the corrected confusion matrix has **zero** false positives (Report 02/03's corrections).

### A real replacement case study: the fix traded false positives for a small number of new false negatives, and at least one has a clear, distinct explanation

Removing the artificial duplicate-match boost revealed that a few genuine positives were resolving above threshold *only because of it* — 5 submissions (previously true positives) now score 0.60-0.6549, just under `tau_high=0.68`. One was examined directly: `cs_g4pD_taskb.txt` (labelled `verbatim`, task b — PageRank).

**Submission excerpt:** "...Simplified algorithm / How PageRank Works / Assume a small universe of four web pages: A, B, C and D. The initial approximation of PageRank would be evenly divided between these four documents. Hence, each document would begin with an estimated PageRank of 0.25..."

**This dataset's canonical source, `orig_taskb.txt`, excerpt:** covers PageRank's definition, the Google patent history, and Google's own description of the algorithm as a "ballot" among pages — it does **not** contain the "four web pages A, B, C, D" worked example the submission quotes almost verbatim (this specific passage is recognizable as a real, separate section of Wikipedia's actual PageRank article).

**Interpretation:** the ground-truth `verbatim` label is very plausibly still correct — the respondent likely did copy directly from Wikipedia's PageRank article — but `orig_taskb.txt`, the specific canonical-source excerpt captured in this dataset, appears to be a **partial excerpt** of the real article that happens not to include the section this particular respondent copied from. This is a distinct, legitimate limitation from the one originally (incorrectly) diagnosed: it's not a vocabulary-overlap/containment-threshold problem, it's that the reference corpus's source documents may not comprehensively cover everything a genuinely-verbatim submission could have copied from the same real-world source. Tier 1's score (0.4286) and Tier 2's fused score (0.6124) are both consistent with "genuinely low overlap with *this specific* reference document" rather than a detection failure against the passage that's actually present.

**For Chapter 4/5:** report the corrected mechanism plainly — the original "short-answer shares source-article vocabulary" story (below) does not hold up under verification and should not be cited. The real, corrected story is twofold: (1) a data-leakage bug caused all 10 original-category false positives, now fully fixed; (2) the fix's side effect (5 new false negatives) surfaces a distinct, legitimate limitation — canonical source excerpts in this dataset may be incomplete relative to the full real-world source, which is a dataset-completeness limitation worth naming as future work (e.g., re-scraping fuller versions of each task's Wikipedia source article) rather than an algorithmic one.

## Original analysis (2026-07-03) — preserved below for the record, but superseded by the correction above

## Method

Read the actual submission text and its matched source text side by side for 2 of the 10 false positives, rather than relying on the statistical pattern alone (all-FP-is-C&S, all-TN-is-PlagBench) as sufficient evidence.

## Case 1: `cs_g4pE_taske.txt` (task e, "dynamic programming")

**Submission (labelled `original` — respondent instructed to answer independently):**
> "Dynamic programming is a method for efficiently solving a broad range of search and optimization problems which exhibit the characteristics of overlappling."

**Source article (`orig_taske.txt`, the Wikipedia text the question was built from):**
> "...dynamic programming is a method of solving problems that exhibit the properties of overlapping subproblems and optimal substructure..."

The opening sentence's structure and several specific words ("a method... of solving problems which/that exhibit the... overlapping...") closely track the source. This is genuinely ambiguous: it could be the respondent recalling the standard textbook phrasing for a well-known CS term independently (arguably legitimate for a concise technical definition), or it could reflect the source having been consulted despite the "original" label. Winnowing correctly detected real, close phrase-level overlap here — this is closer to a **defensible flag** than a pure false positive, even though the corpus's ground-truth label says "original."

## Case 2: `cs_g0pC_taskc.txt` (task c, "vector space model")

**Submission:** explains vector space model, dimensions, and **cosine similarity with weighting schemes and inverted indexes** — content and terminology that **does not appear in the source article at all**.

**Source article (`orig_taskc.txt`):** covers vector space model, dimensions, and tf-idf weighting, but never mentions cosine similarity, inverted indexes, or the specific computational trade-offs the submission discusses.

This submission is **substantially different content** from the source — clearly independent, arguably more technically sophisticated than the source it supposedly "copied." Yet Winnowing still returned containment=1.0. This is a genuine false positive with no reasonable copying interpretation.

## Interpretation

The two cases together narrow the root cause more precisely than Report 02's initial hypothesis. It's not that these submissions are topically similar to their sources in a vague sense — it's that **short technical answers about well-defined, narrowly-scoped CS concepts share enough standard domain vocabulary and boilerplate phrasing with their topic's canonical definition that Winnowing's k=5 fingerprinting saturates at or near full containment**, regardless of whether the surrounding content is genuinely independent (Case 2) or arguably closer to unattributed paraphrase of a standard definition (Case 1). Because these are *short* answers, a handful of shared 5-gram hashes can constitute the entirety of the submission's own (small) fingerprint set, even though those same 5-grams are a tiny fraction of the (much longer) source article's fingerprint set — this is a structural property of applying an asymmetric containment threshold to short-vs-long document pairs, not a defect in the Winnowing implementation itself (see Report 01's fix, which correctly restored containment-gating; this failure mode exists *because* that fix works correctly, not despite it).

PlagBench's `original` submissions don't show this pattern (0/4 false positives) because PlagBench's construction methodology doesn't tie "original" responses to a specific, shared pre-existing reference document the way Clough & Stevenson's short-answer methodology does.

## External corroboration

This is not a corpus-specific curiosity — PAN 2025 (arXiv:2510.06805, cited in `docs/2026-07-03/chapter_four_five_0521.md`) reports the same category of problem: embedding/similarity-based plagiarism detectors systematically conflate topical or domain-vocabulary closeness with actual copying, and don't generalise cleanly across datasets built with different methodologies. The specific mechanism here (short-answer + shared-reference-document corpora) is a concrete instance of that broader, independently-documented limitation.

## For Chapter 4/5

- Report both cases plainly: one is a defensible edge case (arguable whether "original" is the right ground truth at all for Case 1), the other is a clear false positive with no reasonable copying interpretation (Case 2). Don't flatten this into a single "the algorithm is wrong" or "the algorithm is right" claim — the honest finding is that the *containment threshold* doesn't distinguish these two situations, and arguably shouldn't be expected to on short technical text alone.
- Candidate future work (Report 02 already flagged the technical fix: a minimum absolute shared-hash count, not just a containment fraction, before triggering `TIER1_PLAGIARISED`): this would likely fix Case 2 without meaningfully affecting Case 1, since Case 2's overlap is a handful of generic terms while genuine near-verbatim/verbatim copies (which correctly score 1.0 across this corpus, per Report 02) share far more absolute fingerprint overlap.
