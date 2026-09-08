# Introducing the 2026-07-04 fix and the 3 additive features into Chapters 1-3

This is writing guidance, not a Chapter draft — it tells you *where* and *how* to fold two pieces of new work into the already-written Chapters 1-3, without needing to restructure them. Chapters 1-3 are otherwise untouched by this document.

## Part A: the dataset-leakage fix (already implemented, real result — write this in as fact)

This is not speculative future work — it happened, it's tested, and the corrected numbers are in `evaluation/reports/00_dataset_reconciliation.md`, `02_exp1_tier_resolution.md`, and `03_exp2_cost_accuracy.md`. It belongs in the thesis as a real methodological correction, the same way Report 01's Winnowing bug fixes already do.

### Chapter 1 (Introduction)
No structural change needed. If Chapter 1 has a paragraph enumerating the thesis's contributions or research rigor (commonly near the end of the Introduction, alongside RO1-RO5), add one sentence along these lines:

> Beyond the system's design and implementation, this thesis also demonstrates a disciplined empirical evaluation practice: several implementation and dataset-construction defects were identified and corrected during evaluation itself, including a data-leakage bug in the benchmark corpus (Section 3.7) that had produced a misleading precision result, illustrating the importance of verifying evaluation infrastructure with the same rigor as the system under test.

This doesn't need its own paragraph or subsection in Ch1 — one sentence positions it as evidence of rigor, not as an admission of a flaw to apologize for.

### Chapter 2 (Literature Review)
Add a short new subsection (or fold into wherever Ch2 discusses evaluation methodology / related work) citing the general ML-evaluation-leakage literature — this makes the finding look like a recognized, well-studied class of problem rather than an ad hoc mistake:

> **Data leakage in ML-based evaluation.** Kapoor and Narayanan (2023) survey 294 papers across 17 scientific disciplines and find data leakage — broadly, any violation of the separation between what a model is evaluated against and what it has effectively already seen — to be a widespread and often silent failure mode, proposing an eight-category taxonomy spanning "textbook" errors to subtle, discipline-specific pitfalls. Plagiarism-detection evaluation is particularly exposed to one specific variant: if a benchmark's "reference corpus" (the documents a submission is checked against) inadvertently contains the submission itself, or a near-duplicate of it, detection results are inflated in a way that is easy to miss unless the corpus construction is audited directly, not just the detection algorithm. Section 3.7.4 and Chapter 4 report an instance of exactly this pattern found during this thesis's own evaluation.

Citation to add: Kapoor, S., & Narayanan, A. (2023). Leakage and the reproducibility crisis in machine-learning-based science. *Patterns*, 4(9). https://doi.org/10.1016/j.patter.2023.100804

### Chapter 3 (Methodology)
This is where the real content addition belongs. Two options depending on how much Ch3 restructuring you're willing to do:

**Minimal-touch option (recommended):** add a new **Section 3.7.4: Corpus Integrity Validation** immediately after Section 3.7.3 (labelling protocol). Draft text:

> Following construction of the combined evaluation corpus (Section 3.7), a corpus-integrity check was performed to confirm that the "source" reference documents used for detection (Section 3.9) are independent of the submissions being evaluated against them. This check found that all 95 Clough and Stevenson (2011) submissions had also been included, unintentionally, in the source-reference set under their original (unprefixed) filenames — meaning each such submission's evaluation would trivially match an exact duplicate of itself. This was corrected by excluding any reference-set file whose content duplicates a submission (Section 4.X reports the corrected results; the original, leakage-affected results are documented for transparency in the evaluation reports repository). PlagBench (Lee et al., 2025) submissions were unaffected, as their reference documents use a distinct naming convention that does not collide with submission filenames.

**Alternative (if you'd rather not touch the numbered section structure):** fold the same content into Section 3.9 (wherever the evaluation *procedure*, as opposed to corpus *construction*, is described) as a paragraph titled "Evaluation corpus validation," with identical content.

Either way, Chapter 3 should describe this as **methodology** ("this is how the corpus was validated"), not as a finding — the finding and its numeric impact belong in Chapter 4.

## Part B: the 3 additive features (not yet implemented — introduce as motivated future-facing scope, not as built system components)

Unlike Part A, none of tortured-phrase detection, AI-detector calibration, or match-explanation generation exist in the codebase yet. Introducing them prematurely as if built would misrepresent the thesis. The right way to introduce them now is as **forward-looking scope**: named, cited, and justified, but clearly framed as extensions this thesis's architecture is designed to accommodate rather than has already delivered.

### Chapter 1 (Introduction) — Research Objectives / Scope and Limitations
If Ch1 has a "Scope and Limitations" or "Delimitations" subsection (common right after RO1-RO5), add three bullet points naming these as identified, deliberately-scoped-out extensions, e.g.:

> This thesis's dual-tier architecture is designed to be extensible along three directions identified during evaluation but not implemented within the current scope: (i) detection of adversarially-paraphrased ("tortured phrase") submissions that evade lexical/embedding similarity while preserving meaning; (ii) calibrated, ensemble-based AI-authorship detection to reduce the false-positive risk this thesis's own advisory AI-detection feature was found to carry for non-standard English writing; (iii) generated natural-language rationales accompanying similarity reports, to assist human reviewers in judging the ambiguous cases this thesis's own failure-mode analysis (Section 4.X) identified. Chapter 5 discusses each as future work, with references to the specific literature motivating them.

If Ch1 doesn't have such a subsection, it's fine to introduce these purely in Ch2 (literature) and Ch5 (future work) without touching Ch1 at all — don't force a structural change Ch1 doesn't already support.

### Chapter 2 (Literature Review) — three new subsections
Each should be short (2-4 sentences), cite 1-2 sources, and end by explicitly connecting the gap to this thesis's own system. Suggested placement: as three subsections under wherever Ch2 currently discusses "Limitations of Current Approaches" or "Emerging Challenges," likely right after the existing PAN 2025 discussion.

**2.X.1 Adversarial paraphrasing and tortured phrases.** Cabanac, Labbé, and Magazinov (2021) first documented "tortured phrases" — recognized technical terms replaced by synonym-substituted equivalents (e.g. "counterfeit consciousness" for "artificial intelligence") — as a forensic signature of machine-paraphrased text used to evade plagiarism/similarity detection. Martel, Lentschat, and Labbé (2024) show that masked-token-prediction-based detection (flagging phrases a domain language model finds locally implausible) outperforms embedding-similarity approaches for this specific evasion pattern, achieving recall=0.87/precision=0.61 for previously-undocumented tortured phrases. The overview of PAN 2026 (Sharma et al., forthcoming) names generative/adversarial paraphrase evasion as a live, unresolved challenge for plagiarism detection broadly — directly relevant to this thesis's Winnowing/embedding-based dual-tier design, which (per Report 05's corrected failure-mode analysis) has no dedicated defense against this specific evasion pattern today.

**2.X.2 Bias and calibration in AI-generated-text detection.** Multiple studies (e.g. the 2025 University of Chicago Booth study; the TOEFL/EFL-benchmark studies) document that AI-text detectors trained predominantly on native-English text misclassify non-native English writing at substantially elevated rates — one widely-cited figure puts this above 60% for some detectors, against near-zero false-positive rates for native-English text from the same detectors. Detectors achieving near-zero false-positive rates on this benchmark (e.g. Pangram, per the Booth study) do so primarily through diverse, EFL-inclusive training data and calibrated decision thresholds rather than architectural changes. This thesis's own AI-detection feature (an advisory signal, not a plagiarism-tier decision) was found in earlier deployment testing to score >98% "likely AI" on unambiguously human-written encyclopedic text — consistent with this literature's documented risk pattern, not yet independently mitigated in this system.

**2.X.3 Explainability in similarity/plagiarism reporting.** Commercial tools (Turnitin, Copyleaks) surface similarity via highlighted overlapping passages and an aggregate percentage score, but do not generate a natural-language rationale explaining *why* a given match is or is not likely to represent copying. Separately, research on LLM self-explanations (e.g. work on the faithfulness-vs-plausibility gap in LLM-generated rationales) cautions that generated explanations can be fluent and plausible without faithfully reflecting the actual basis for a decision — a caution directly relevant to any future rationale-generation feature added to this thesis's report UI, which should be explicitly framed as a review aid rather than a verified causal account.

Citations to add:
- Cabanac, G., Labbé, C., & Magazinov, A. (2021). Tortured phrases: A dubious writing style emerging in science. arXiv:2107.06751.
- Martel, E., Lentschat, M., & Labbé, C. (2024). Detection of tortured phrases in scientific literature. arXiv:2402.03370.
- Overview of PAN 2026 (2026). arXiv:2602.09147.
- [Whichever specific non-native-speaker AI-detection bias source you prefer to cite by name once you've read the full paper] — candidate: Liang et al.-style "GPT detectors are biased against non-native English writers" line of work, or the 2026 update arXiv:2602.05769 ("Different Time, Different Language: Revisiting the Bias Against Non-Native Speakers in GPT Detectors").
- On LLM self-explanation faithfulness: arXiv:2402.04614 ("Faithfulness vs. Plausibility: On the (Un)Reliability of Explanations from Large Language Models").

### Chapter 3 (Methodology) — Section 3.13 or equivalent "Scope Boundaries"
Add a short closing subsection (or extend an existing limitations/scope section) naming these three as deliberately out of the current implementation's scope, with a one-line pointer to Chapter 5:

> The dual-tier architecture described above does not currently include adversarial-paraphrase detection, AI-detector ensembling/calibration, or generated match rationales. Each was identified as a concrete extension during this thesis's evaluation (Chapter 4) and is discussed as future work, with an implementation plan, in Chapter 5 and `docs/2026-07-04/additive_features_implementation_plan_0521.md`.

This keeps Ch3 honest about what the *built* system does, while still giving the reader (and your supervisor) a clear signal that these aren't afterthoughts — they're identified, cited, and planned.

## Summary of where everything goes

| Item | Ch1 | Ch2 | Ch3 | Ch4/5 |
|---|---|---|---|---|
| Dataset-leakage fix | 1 sentence, rigor framing | New subsection, cite Kapoor & Narayanan (2023) | New Section 3.7.4, corpus validation procedure | Full numbers already in `evaluation/reports/00,02,03` |
| Tortured-phrase detection | Optional scope bullet | New subsection 2.X.1 | Scope-boundary mention | Ch5 future work + implementation plan doc |
| AI-detector calibration | Optional scope bullet | New subsection 2.X.2 | Scope-boundary mention | Ch5 future work + implementation plan doc |
| Match-explanation generation | Optional scope bullet | New subsection 2.X.3 | Scope-boundary mention | Ch5 future work + implementation plan doc |
