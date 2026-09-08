# Report 0: Dataset Reconciliation

**Status:** Resolved 2026-07-03 — Option A adopted
**Roadmap step:** Step 0 — blocks all other reports

## Decision needed

Chapter 3 (Section 3.7) describes a self-collected 200-submission corpus. The actual `evaluation/dataset/data/` folder is built from two real external corpora (confirmed via `labels.csv`'s own `dataset` column):

| Source | original | verbatim | near_verbatim | paraphrased | Total |
|---|---|---|---|---|---|
| Clough & Stevenson (2011) | 38 | 19 | 19 | 19 | 95 |
| PlagBench (Lee et al., 2025) | 30 | 30 | 0 | 30 | 90 |
| **Combined** | **68** | **49** | **19** | **49** | **185** |

Splits: 109/38/38 (train/val/test) per `evaluation/dataset/data/splits/*.csv`.

**Decision (record supervisor sign-off separately when confirmed in person — proceeding on this basis for now):**
- [x] Option A: Correct Chapter 3 to describe the real sourcing (recommended)
- [ ] Option B: Build the originally-described custom corpus before Chapter 4

All downstream reports (02-06) and the Chapter 4/5 write-up proceed on the basis that "the test split" = the real 38-submission reconciled test split described below (Clough & Stevenson + PlagBench, 109/38/38 train/val/test). If your supervisor later requires Option B instead, the actual system/evaluation code doesn't change — only the corpus and Chapter 3's prose would need redoing.

## If Option A: replacement text for Chapter 3

### Replacement Table 3.1

| Category | Count | Description | Source |
|---|---|---|---|
| Verbatim | 49 | Exact copy-paste from a single source | Clough & Stevenson (2011); PlagBench (Lee et al., 2025) |
| Near-verbatim | 19 | Light/heavy paraphrase of verbatim (Clough & Stevenson only — PlagBench has no near-verbatim category) | Clough & Stevenson (2011) |
| Paraphrased | 49 | Systematic rewording, meaning preserved | Clough & Stevenson (2011); PlagBench (LLM-generated) |
| Original | 68 | Non-plagiarised responses | Clough & Stevenson (2011); PlagBench (LLM-generated) |
| Total | 185 | | |

### Replacement citations (add to References list)
- Clough, P., & Stevenson, M. (2011). Developing a corpus of plagiarised short answers. *Language Resources and Evaluation*, 45(1), 5-24.
- Lee, J., Agrawal, T., Uchendu, A., Le, T., Chen, J., & Lee, D. (2025). PlagBench: Exploring the duality of large language models in plagiarism generation and detection. *Proceedings of NAACL 2025*. arXiv:2406.16288.

### Section 3.7.2 (Collection Procedure) replacement text — draft, needs your review

> The evaluation corpus combines two established, peer-reviewed sources rather than custom collection, prioritising external validity and independent verifiability over bespoke data. Clough and Stevenson's (2011) corpus of plagiarised short answers contributes 95 submissions across 5 Wikipedia-sourced questions, each with cut-and-paste, light-paraphrase, heavy-paraphrase, and non-plagiarised response variants from multiple respondents. PlagBench (Lee et al., 2025) contributes a further 90 submissions, an LLM-generated benchmark covering verbatim, paraphrased, and original text pairs. The combined corpus totals 185 labelled submissions, split 109/38/38 into train/validation/test sets.

### Section 3.7.3 (Labelling Protocol) — likely needs removing or rescoping
Original text describes a second-pass review with 2-week separation and Cohen's kappa on a 20-item audit — this applies to *self-collected, self-labelled* data. Since labels here come from the original corpus authors (Clough & Stevenson's respondent instructions; PlagBench's construction methodology), this section should either be removed or rewritten to describe reliance on the source corpora's own published labelling methodology instead.

## If Option B
Not scoped in this roadmap — would need a separate plan (ethics approval process, GPT-4 generation + review pipeline, timeline). Flag to supervisor if this path is chosen; the roadmap in `docs/2026-07-03/outstanding_steps_roadmap_0528.md` assumes Option A.

## Addendum (2026-07-04): a second, more consequential dataset-construction bug found in `sources/`

Separately from the Chapter 3 provenance question above, a genuine data-leakage bug was found in how `evaluation/dataset/data/sources/` was built: **all 95 Clough & Stevenson submissions are also present in `sources/` under their bare filename** (e.g. `submissions/cs_g0pC_taskc.txt` and `sources/g0pC_taskc.txt` are the same content, differing only in the `cs_` prefix). Verified exhaustively: 95/95 C&S submissions have this duplicate; 0/90 PlagBench submissions do (PlagBench's own source files use a distinct `pb_source_*` naming, so they were never at risk of this).

**Why this matters:** every evaluation script that indexes `sources/` as "the corpus" (`run_evaluation.py`, and `exp2_cost_accuracy.py`'s `local_only`/`cloud_only`/`hybrid_static` baselines) was therefore checking every C&S submission against a corpus that already contained an exact copy of itself. This is the actual mechanism behind the `original`-category false positives documented in Report 02 and analyzed (misattributed, see Report 05's correction) as "short-answer/source-article vocabulary overlap" — the real cause is simpler and more mechanical: a submission matching its own leaked duplicate, not a genuine ambiguous vocabulary-sharing case.

**Fix:** `run_evaluation.py`'s `load_source_texts()` and `exp2_cost_accuracy.py`'s `load_sources()` now both exclude any `sources/` file whose bare (prefix-stripped) name matches a real submission's filename, via a new `_leaked_submission_basenames()` helper in each script. This drops the indexed corpus from 190 files to 95 (97 genuine sources — the 5 `orig_taskX.txt` Wikipedia articles plus ~92 `pb_source_*.txt` PlagBench references — minus the ones already correctly excluded elsewhere).

**How this was found:** while implementing the *different*, previously-planned fix (a minimum absolute shared-hash-count floor, from Report 02's follow-up note), a diagnostic script revealed every one of the 10 false positives had `shared_hashes == query_total == matched_document_total` — the signature of an exact-duplicate match, not a partial vocabulary overlap. The originally-planned fix would not have touched these cases at all (they have *high* absolute shared-hash counts, not low), which is what prompted checking the corpus construction itself rather than the algorithm.

**Impact on downstream reports:** substantial and mostly positive — see Reports 02, 03, and 05's own 2026-07-04 corrections for full before/after numbers. Headline: dual-tier F1 rose from 0.807 to **0.884** (now the highest F1 of all four configurations tested, not just the cheapest), precision rose from 0.697 to **1.000** (zero false positives), but escalation rate rose from 15.79% to **52.63%**, meaning Hypothesis 1 (≥80% Tier-1-alone resolution) is **no longer supported** — Report 02 has the full corrected analysis. Report 04 (exp3) is unaffected: it builds its corpus from the train-split submissions directly, never from `sources/`.

Related: [[tier2-detection-quality]].
