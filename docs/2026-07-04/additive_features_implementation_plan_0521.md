# Implementation plan: 3 additive features (tortured-phrase detection, AI-detector calibration, match-explanation generation)

Informed by web research completed 2026-07-04 (citations inline). Each feature is scoped as: motivation (with evidence), concrete technical design fitting this codebase's existing architecture, integration points, evaluation plan, effort estimate, and risks. Priority ordering and a recommendation on what to actually build before submission are at the end.

---

## Feature 1: Adversarial-paraphrase ("tortured phrase") detection

### Motivation
Cabanac, Labbé, and Magazinov (2021, arXiv:2107.06751) documented "tortured phrases" — recognized technical terms replaced by synonym-substituted equivalents that are grammatically intact but semantically off (e.g. "counterfeit consciousness" for "artificial intelligence", "profound learning" for "deep learning") — as a forensic signature of automated paraphrasing tools used specifically to evade similarity/plagiarism detectors. This is a documented, live evasion pattern: publishers (IEEE, Wiley, Elsevier) have retracted 1,400+ papers on this basis since 2024-2026. Martel, Lentschat, and Labbé (2024, arXiv:2402.03370) show a masked-token-prediction approach (does a domain language model find this word implausible in context?) outperforms embedding-similarity for finding *novel*, undocumented tortured phrases (recall=0.87, precision=0.61). The PAN 2026 overview (arXiv:2602.09147) names generative/adversarial paraphrase evasion as a live, unresolved area. **This system currently has no defense against this evasion pattern** — Winnowing's k-gram fingerprinting and Tier 2's embedding similarity both assume the paraphraser preserves enough surface or semantic similarity to be caught; a tortured-phrase-style attack is specifically designed to defeat exactly that assumption while still reading as (barely) grammatical.

### Technical design
Two-tier approach, cheapest-first, matching this system's own "confidence-gated escalation" philosophy:

**Tier A — known-phrase dictionary lookup (cheap, ship first).** Maintain a static list of documented tortured-phrase pairs (a public dataset exists: the Problematic Paper Screener / Cabanac's own tortured-phrase database, several hundred entries, freely available). On each submission, run fuzzy string matching (e.g. rapidfuzz, already lightweight enough to add as a dependency) against this dictionary. A match flags the phrase directly — no ML inference needed, near-zero latency cost, catches every *known* tortured phrase immediately.

**Tier B — novel-phrase anomaly detection (optional stretch goal).** For phrases not in the static dictionary, use a masked-language-model approach analogous to Martel et al.: for each candidate technical-sounding noun phrase (extracted via a simple POS-pattern, e.g. spaCy's noun-chunk extraction — spaCy isn't currently a dependency but is a reasonable, well-scoped addition), mask each content word in turn and score the model's predicted probability for the word actually present. A anomalously low probability for a word appearing in an otherwise-technical-sounding phrase is the tortured-phrase signal. This can reuse the AI-detector's existing transformers infrastructure (a small BERT/RoBERTa-family masked-LM, distinct from the classification model already loaded) rather than adding a new heavyweight dependency.

### Integration points
- New file: `backend/app/services/tortured_phrase_detector.py`, following the exact pattern of `ai_detector.py` (module-level singleton for any loaded model, a `detect(text) -> TorturedPhraseResult` function).
- New Celery task: `backend/app/tasks/tortured_phrase_tasks.py`, dispatched the same way `ai_detect` is — independently, in parallel, never gating `Submission.status` (this is an advisory signal, same tier as AI-detection, not a plagiarism-tier decision).
- New DB table (migration): `tortured_phrase_results` (submission_id, phrases_found: JSON list of {original, suspected_original, position}, score).
- Route on the `celery-worker-fast` service (the concurrent AI-detection worker set up 2026-07-03/04) alongside `ai_detection` — it has the same independence properties (no shared cross-submission state) that made ai_detection safe to parallelize.
- Report UI: a new badge/section, "Adversarial Paraphrase Indicators," listing any flagged phrases with the suspected original term, alongside the existing similarity and AI-detection badges.

### Evaluation plan
- Tier A: measure recall/precision against a held-out sample of the public tortured-phrases dataset (should be near-perfect recall for exact/near-exact dictionary matches; precision depends on false-triggering on legitimate unusual phrasing — validate against a sample of genuine "original" category submissions from the existing corpus to check false-positive rate).
- Tier B (if built): construct synthetic test cases by running known paraphrasing tools (e.g. an open-source spinner, or prompting an LLM to "heavily paraphrase while preserving technical meaning") against a sample of the existing corpus's `orig_taskX.txt` source documents, then checking whether the detector flags the resulting text. Compare precision/recall against Martel et al.'s reported baseline (recall=0.87, precision=0.61) as a sanity check, not a target to beat.

### Effort estimate
Tier A: small — 1-2 days (dictionary sourcing/cleaning, fuzzy-match service, Celery task wiring, UI badge, unit tests). Tier B: medium-large — several days to a week (POS extraction, masked-LM scoring pipeline, threshold tuning, synthetic eval set construction). **Recommend Tier A only for this thesis's timeline; document Tier B as future work.**

### Risks
- Static dictionaries age — new tortured phrases are coined continuously as paraphrasing tools evolve; Tier A alone will miss anything not yet documented. State this limitation explicitly.
- Tier B's masked-LM approach can false-positive on genuinely unusual-but-legitimate technical writing (e.g. a paper coining a genuinely new term) — needs careful threshold tuning against real negative examples, not just synthetic attacks.

---

## Feature 2: AI-detector calibration (reducing non-native-English false positives)

### Motivation
This system's existing AI-detection feature (`ai_detector.py`, RoBERTa-based, advisory-only) was found in earlier deployment testing (documented in `gcp-deployment-gotchas` memory) to score >98% "likely AI" on unambiguously human-written encyclopedic text — consistent with a well-documented, active research finding: AI-text detectors trained predominantly on native-English samples misclassify non-native English writing at substantially elevated rates (one widely-cited figure: >60% false-positive rate on non-native writing vs. near-zero on native writing, from the same detector). Recent work (2025 University of Chicago Booth study; 2026 follow-ups, e.g. arXiv:2602.05769) shows detectors achieving near-zero false-positive rates on EFL/TOEFL-style benchmarks do so primarily through diverse, EFL-inclusive training data and calibrated decision thresholds, not fundamentally different architectures — meaning this is addressable without replacing the underlying model.

### Technical design
Two complementary changes, in priority order:

**(1) Threshold recalibration against an EFL-inclusive validation set (cheap, do this first).** The current detector presumably uses its default classification threshold (typically 0.5 on the model's own logits). Construct a small validation set combining (a) genuinely AI-generated text (existing capability, e.g. GPT-output samples) and (b) genuinely human-written but non-native-English text (a public EFL corpus, e.g. ICNALE or a TOEFL-public-sample-style corpus, or simply a sample of this thesis's own PlagBench/Clough & Stevenson `original` category submissions, some of which may already reflect non-native English patterns). Compute an ROC curve and select a threshold that holds false-positive rate on the EFL subset below a stated target (e.g. ≤5%), even if this costs some recall on the AI-generated subset — for an *advisory* signal, minimizing false accusations should be weighted more heavily than maximizing detection, which is the same asymmetric-cost reasoning this thesis already applies to Tier 1's ≥0.95 precision constraint (Section 3.5.3).

**(2) Ensemble with a second, independent signal (larger effort, do second).** Add a lightweight, architecturally-different second signal — e.g. a perplexity/burstiness-based score computed from a small open causal LM (GPT-2-small is sufficient and cheap; low perplexity + low burstiness is the classic statistical AI-text signature, independent of the RoBERTa classifier's own learned features) — and fuse the two scores via a calibrated linear interpolation, structurally identical to Tier 2's existing `alpha`-weighted dense/sparse fusion (`tier2_detector.py`). Two independent, differently-biased signals agreeing is a stronger basis for an "advisory" flag than either alone, and this reuses an architecture pattern already proven in this codebase rather than inventing a new one.

### Integration points
- Modify `backend/app/services/ai_detector.py`: add an optional second model load (a small causal LM for perplexity), a `_compute_perplexity_score()` function, and a fusion step producing the final advisory score. Keep the existing single-model path as a fallback/feature flag (`AI_DETECTOR_ENSEMBLE_ENABLED`) so this can ship incrementally.
- New evaluation script: `evaluation/experiments/exp_ai_detector_calibration.py`, structurally similar to `exp3_threshold_sensitivity.py` — sweep candidate thresholds against the EFL-inclusive validation set, report the ROC curve and chosen operating point.
- No change needed to the Celery task structure (`ai_detection_tasks.py` already calls a single `detect()` entry point; the ensemble logic stays internal to `ai_detector.py`).

### Evaluation plan
Build (or source) an EFL-inclusive validation set as described above. Report false-positive rate on that subset before and after recalibration/ensembling, alongside true-positive rate on a genuinely-AI-generated subset, as a paired before/after table — directly modeled on how this session already reported the FAISS-bug and dataset-leakage-bug corrections (real numbers, not just a description of the fix).

### Effort estimate
Threshold recalibration alone: small — 1-2 days, mostly validation-set sourcing (the hardest part; may require adapting an existing public EFL corpus rather than building one from scratch) and running the sweep. Full ensemble: medium — 3-5 days (second model integration, fusion tuning, re-running the validation).

### Risks
- Sourcing a genuinely representative EFL validation set is the hard part, not the code — a small or unrepresentative one could give a false sense of calibration. Be explicit in Chapter 4/5 about the validation set's size and limitations, following this session's established pattern of not overclaiming from thin evidence.
- This feature touches a genuinely sensitive area (accusing students of AI use) — any change should be framed and tested primarily as *reducing false accusations*, not as improving raw detection accuracy, consistent with the existing advisory-only, non-gating design.

---

## Feature 3: LLM-generated match-explanation

### Motivation
Existing commercial tools (Turnitin, Copyleaks) surface plagiarism via highlighted overlapping passages and an aggregate similarity percentage, but none surveyed generate a natural-language rationale explaining *why* a specific match is or is not likely to represent copying — this is a genuine, unaddressed gap in the current tooling landscape, not just this system. This thesis's own Report 05 (failure-mode analysis, corrected 2026-07-04) found concrete evidence that some flagged cases are genuinely ambiguous even to a careful human reader comparing the two texts side by side (the "dynamic programming" case: is it independent recall of standard phrasing, or unattributed reliance on the source?) — a short, targeted explanation of *what specifically* overlaps (shared claims, structure, terminology) would materially help a teacher reviewing such a case faster than raw scores alone.

### Technical design
On-demand generation (not automatic for every submission) to control cost, consistent with this thesis's cost-consciousness theme:
1. New backend endpoint: `GET /api/v1/submissions/{id}/explanation`, triggered when a teacher clicks "Explain this match" in the report UI (Moodle `report.php`) — not generated proactively for every escalated submission.
2. Backend assembles a prompt containing: the submission's flagged passage, the matched source's corresponding passage (already available via `SimilarityPair`/`matched_segments`), and the tier/score that triggered the flag.
3. Call an LLM (given this thesis's cost/affordability theme, prefer a smaller/cheaper model — e.g. Claude Haiku or an equivalent — over a large frontier model; a single short explanation per manually-requested case is a tiny, bounded cost, unlike running an LLM over every submission) with a constrained prompt: identify specifically which claims, terminology, or structural elements overlap, and explicitly note when the case is genuinely ambiguous rather than forcing a confident-sounding verdict.
4. **Mandatory UI disclaimer**, directly motivated by research on LLM self-explanation reliability (arXiv:2402.04614, "Faithfulness vs. Plausibility"): generated rationales can be fluent and plausible without faithfully reflecting the actual basis for a decision. The UI must present this as "an AI-generated reading aid to help you evaluate the match yourself" — never as a verified account of why the algorithm flagged the case, and never as additional evidence of guilt.

### Integration points
- New file: `backend/app/services/explanation_service.py` — a `generate_explanation(submission_text_excerpt, source_text_excerpt, score, tier) -> str` function wrapping the LLM call.
- New API route in `backend/app/api/v1/submissions.py`: `GET /{submission_id}/explanation`, auth-gated the same way existing routes are (`verify_api_key`), returning the generated text (cache the result in a new `explanation_results` table so repeated clicks don't re-trigger the LLM call).
- Moodle plugin (`moodle-plugin/plagiarism/dualtier/report.php`): add an "Explain this match" button next to each flagged similarity pair, calling the new endpoint via AJAX and rendering the result with the disclaimer prominently above it, not below (so it can't be missed by scrolling past it).

### Evaluation plan
Not a precision/recall evaluation (there's no ground truth for "correct explanation") — instead, a small qualitative user-study-style check: generate explanations for the specific ambiguous cases Report 05 already identified plus a handful of clear true-positive and clear true-negative cases, and manually assess (a) does the explanation correctly identify the actual overlapping content (spot-check against the real texts, the same rigor this session applied throughout), and (b) does it appropriately hedge on genuinely ambiguous cases rather than asserting false confidence either way. Report this as a small, explicitly-qualitative validation, not a quantitative benchmark — overclaiming rigor here would be inconsistent with this thesis's established evidence standards.

### Effort estimate
Medium — 3-5 days (endpoint, prompt design/iteration, caching, Moodle UI button, the qualitative validation pass). The prompt-engineering and validation loop is likely the largest time cost, not the plumbing.

### Risks
- Cost: bounded by on-demand generation, but still a real per-call cost inconsistent with a "self-hosted, affordable" framing if used carelessly — the design deliberately keeps this manual/on-demand rather than automatic for exactly this reason; don't relax that without re-costing it (Report 03's cost-model reasoning applies directly here).
- Over-trust risk: the single biggest risk of this feature is a teacher treating a fluent-sounding generated explanation as authoritative. The UI disclaimer is not optional — deprioritize shipping this feature over shipping it without the disclaimer.

---

## Priority ordering and recommendation for this thesis's remaining timeline

Given typical B.Sc. thesis time constraints, not all three need to be *built* — the thesis is already strengthened by having them researched, cited, and concretely planned (Chapter 2/5 content) even if only one is actually implemented.

1. **If implementing only one:** Feature 2's threshold-recalibration step (not the full ensemble) — smallest code change, directly addresses a risk this thesis's own system already exhibited in testing (not a hypothetical), and produces a clean before/after evaluation table matching this session's established evidence style.
2. **If implementing two:** add Feature 1's Tier A (dictionary lookup) — also small, ships a genuinely new detection capability (not just a fix to an existing one), and is easy to demo live against a known tortured-phrase example for a viva/defense.
3. **Feature 3 (match-explanation)** is the most novel and differentiated but the least essential to implement now — its value is well-argued even as a fully-scoped-but-unimplemented Chapter 5 future-work item with a concrete design (this document), since building it well (prompt iteration, the disclaimer UX, the qualitative validation) is the part that takes real time, not something to rush in the final stretch.

Whichever gets built, follow this session's established evaluation discipline: report exact commands, real before/after numbers or concrete qualitative examples, and state limitations plainly rather than only the favorable result.
