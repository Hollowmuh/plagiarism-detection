# CHAPTER FOUR — RESULTS, Part 3 of 4: Cross-Submission Matching and Failure-Mode Analysis

This section reports work beyond the three experiments specified in §3.10, undertaken because Experiment 3's threshold sensitivity result (§4.5) raised a direct follow-on question the original design did not fully resolve: cross-submission (peer-to-peer) matching measured a recall ceiling of 41.7% at the best threshold found — is this fixable, and if so how? This section reports that investigation as a complete result, including two negative findings, rather than stopping at the ceiling itself.

## 4.6 Cross-Submission Matching: Diagnosis and Two Attempted Fixes

### The gap, characterised

Source-document matching (§4.4's corpus: submissions checked against external reference documents) achieves 79.2% recall at the deployed threshold. Peer-to-peer matching (§4.5's corpus: submissions checked against other students' submissions) achieves 41.7% recall at its best threshold — a genuinely harder problem, not a measurement artefact. Two separable causes were identified, each investigated directly rather than assumed:

**A corpus-coverage gap.** Roughly half of the test-split submissions labelled as genuine peer-matches have no matching content anywhere in the searched corpus at all — an artefact of how the underlying benchmark corpus was constructed (§3.7.2), not a detector weakness. This ceiling is real but was found to be smaller than a first, naive check suggested, once the check itself was verified against the actual detector output rather than assumed correct.

**A threshold-calibration gap.** Several genuine peer matches score in the 0.60–0.65 range, just under the deployed τ_high = 0.68 — correctly elevated by real overlapping content, but not high enough to auto-confirm.

### Attempted fix 1: lower the threshold for peer-matching specifically

Tested directly rather than assumed: lowering τ_high recovers some of the near-miss matches, but precision breaks immediately and completely at τ_high = 0.65, where a real, identified false positive appears — a genuinely non-plagiarised submission that independently restates a canonical technical definition in similar terms to a genuine copy, scoring high enough to be wrongly confirmed. **The deployed threshold is already close to the best available zero-false-positive operating point for this task; retuning is not a free improvement.**

### Attempted fix 2: an independent structural confirmation signal

A second, independent signal — comparing function-word sentence structure (stripping content words, comparing the remaining "skeleton" pattern) rather than lexical or semantic content — was implemented specifically to distinguish genuine paraphrase from coincidental topical overlap, on the reasoning that copying preserves sentence structure far more than independently-written same-topic text does.

Built and validated against both corpora, per the same evaluation discipline as the rest of this chapter:
- **Peer-matching**: a real, measurable win — recall improved from 41.7% to 54.2% with precision held at 1.000.
- **Source-matching**: a real regression when tested against the *other* corpus — precision fell from 1.000 to 0.885, traced to the same class of same-topic-convergence false positive found in fix 1, now occurring even more broadly across longer source documents (a multiple-comparisons effect: more candidate sentence pairs in a longer document raise the chance of a coincidental structural match). A targeted refinement (restricting the comparison to only the specific matched passage rather than the whole document) measurably improved this (0.885 → 0.920) but did not fully close the gap to the ~1.000 this system requires everywhere else.

**This signal is fully implemented and tested, and shipped disabled by default.** The decision not to enable it follows directly from this system's design constraint, established in §3.4.2 and held consistently throughout Experiments 1–3: precision is never traded away for recall. A real F1 improvement is available if that constraint were relaxed; it was not.

### Summary for Hypothesis interpretation

No hypothesis in §1.4 specifically targets peer-to-peer recall, so this section reports a characterised, honestly-bounded limitation rather than a hypothesis verdict: cross-submission matching works reliably (perfect measured precision throughout every configuration tested) but with materially lower recall than source-matching, for reasons now understood precisely rather than left as an open question, and with two specific, evaluated remediation paths — one shown not to work for free, one shown to work partially and consistently, at a cost this system's design does not accept without further refinement.

## 4.7 Failure-Mode Analysis

Following §3.12.4, false positives from the corrected Experiment 2 run (§4.4) were sampled and inspected directly.

The initial round of this analysis, conducted before defect 1 (Table 4.1) was found, mischaracterised its own findings: two case studies attributed the observed false positives to short-answer submissions sharing enough domain vocabulary with a genuine reference source to saturate the containment score — a plausible-sounding, literature-consistent explanation that turned out to be built on the wrong evidence. Once the system's actual matched document for each case was checked directly, rather than assuming the most plausible-looking candidate, both cases were found to be matching the leaked duplicate identified as defect 1, not the reference document the original analysis had examined by hand.

With defect 1 corrected, the false-positive class it had produced no longer exists (§4.4: zero false positives in the corrected run). A different, genuine residual limitation was found in its place: at least one false negative was traced to a dataset-completeness issue rather than a detection weakness — the canonical reference text indexed for one task is a partial excerpt of the true source article, missing the specific passage a submission had verbatim-copied from a fuller version of the same source. The detector correctly found no match, because no match was present in what it was given to search.

This episode is reported as a specific methodological lesson: the first, plausible-sounding failure-mode explanation was wrong, and was only shown to be wrong by checking what the system had actually matched against, not by re-examining the explanation itself more carefully. This is the same pattern behind several of the ten defects in Table 4.1 and is discussed as a recurring theme in Chapter 5.
