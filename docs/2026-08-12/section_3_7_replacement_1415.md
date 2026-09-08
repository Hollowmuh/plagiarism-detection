# §3.7 Dataset Construction — replacement prose, ready to paste

Matches the existing chapter's register (impersonal, third-person, technical) and subsection numbering. Replaces the current 3.7.1–3.7.4 in full.

---

## 3.7 Dataset Construction

### 3.7.1 Composition

The evaluation corpus draws on two established, peer-reviewed sources rather than purpose-built collection, prioritising external validity and independent reproducibility over bespoke data. It contains 185 labelled submissions across four plagiarism categories, summarised in Table 3.1.

**Table 3.1: Evaluation dataset composition.**

| Category | Count | Description | Source |
|---|---|---|---|
| Verbatim | 49 | Exact copy-paste from a single source | Clough & Stevenson (2011); PlagBench (Lee et al., 2025) |
| Near-verbatim | 19 | Light-to-heavy paraphrase of a verbatim copy | Clough & Stevenson (2011) only — PlagBench has no near-verbatim category |
| Paraphrased | 49 | Systematic rewording, meaning preserved | Clough & Stevenson (2011); PlagBench (LLM-generated) |
| Original | 68 | Non-plagiarised responses | Clough & Stevenson (2011); PlagBench (LLM-generated) |
| **Total** | **185** | | |

The corpus is split 109/38/38 (train/validation/test) by submission, stratified by category to preserve class balance across all three splits.

### 3.7.2 Collection Procedure

The corpus combines two independently published, peer-reviewed benchmarks. Clough and Stevenson's (2011) corpus of plagiarised short answers contributes 95 submissions across five short-answer computer-science questions, each with cut-and-paste, light-revision, heavy-revision, and non-plagiarised response variants collected from multiple student respondents against a single Wikipedia-derived reference answer per question. PlagBench (Lee et al., 2025) contributes a further 90 submissions, a large-language-model-generated benchmark covering verbatim, paraphrased, and original text pairs, each sample paired with its own individually-generated source passage rather than a source shared across the sample.

Using two established corpora rather than self-collected data was a deliberate methodological choice: it removes researcher bias from label assignment, allows direct comparability with prior published work using the same corpora, and avoids the consent and anonymisation burden of collecting fresh student submissions (see §3.13). The trade-off, made explicit rather than left implicit, is that the two corpora are not structurally identical — Clough & Stevenson's design has multiple students sharing one canonical source per task, which makes genuine cross-submission (peer-to-peer) matching structurally possible for that half of the corpus; PlagBench's per-sample source design does not share this property. This distinction becomes directly relevant to the cross-submission matching results reported in Chapter 4.

### 3.7.3 Labelling Protocol

Each submission carries the category and binary plagiarism label assigned by its originating corpus's own published construction methodology, rather than a label independently re-derived for this study. Clough and Stevenson (2011) describe their own collection and labelling procedure in full in the source publication; PlagBench's labels follow directly from its controlled generation process (each sample is generated under an explicit verbatim/paraphrased/original instruction, so category and plagiarism status are known by construction rather than assigned by a second-pass human reviewer). No independent inter-rater reliability exercise was run for this thesis, since doing so would duplicate rather than validate the source corpora's own established labelling.

### 3.7.4 Quality Control

Quality control took the form of verifying the corpus as assembled, rather than filtering raw collected text for length, language, or near-duplication (the SimHash/language-identification/length-bound controls appropriate for freshly-collected data do not apply to two already-published, already-curated corpora). This verification surfaced one genuine construction defect, found and corrected during evaluation rather than assumed absent: all 95 Clough & Stevenson submissions were found to also be present, under a different bare filename, in the directory used as the external reference-document corpus for source-matching experiments — meaning every Clough & Stevenson submission was originally being evaluated against a corpus that already contained an exact copy of itself. This was diagnosed by inspecting the anomalously high shared-hash counts behind an unexpected cluster of false positives, traced to its root cause, and fixed by excluding the 95 leaked duplicates from the indexed source corpus before any results were finalised. Its discovery and correction are documented in full, including the before/after impact on every affected result, in the accompanying technical evaluation record and are reported plainly in Chapter 4 rather than silently absorbed into the final numbers.

---

## Replacement citations (add to the References list)

Clough, P., & Stevenson, M. (2011). Developing a corpus of plagiarised short answers. *Language Resources and Evaluation*, 45(1), 5–24.

Lee, J., Agrawal, T., Uchendu, A., Le, T., Chen, J., & Lee, D. (2025). PlagBench: Exploring the duality of large language models in plagiarism generation and detection. *Proceedings of NAACL 2025*. arXiv:2406.16288.

---

## Consistency updates needed elsewhere in the chapter once this lands

Replace "200-submission" / "200 labelled submissions" with "185-submission" / "185 labelled submissions" in: §3.2 (guideline 3), §3.9.3, §3.14. Replace "60/20/20" with "109/38/38" in §3.9.3. These are the only other places the old dataset figures recur.
