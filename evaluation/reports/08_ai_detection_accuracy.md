# Report 8: AI-Authorship Detection Accuracy

**Status:** Done (2026-09-02)
**Roadmap step:** Not in original roadmap — added after confirming AI-authorship detection is in scope for the thesis

## Ground truth, verified before building the experiment

The evaluation corpus (Report 00) merges two sources with different, verifiable authorship: Clough & Stevenson (2011, 95 submissions) predates modern LLMs entirely and its `task` column holds plain question letters (a–e) — genuine human authorship. PlagBench (Lee et al., 2025, 90 submissions) is LLM-generated **across all three of its categories, including "original"** — confirmed directly via `labels.csv`'s `task` column, which holds `Input.gpt3` / `Input.gpt4` / `Input.llama` for every PlagBench row without exception. This was checked empirically before designing the experiment, not assumed from the paper's description alone — PlagBench's "original" (non-plagiarised) category being *also* machine-generated was the one point worth verifying directly, since it's easy to wrongly assume "original" means "human."

This gives a real, already-available 185-item human-vs-AI labelled corpus at zero additional data-collection cost: 95 human-authored, 90 AI-generated (with generator identity known per item). No new data was collected for this experiment.

## Method

`evaluation/experiments/exp5_ai_detection_accuracy.py`. Ran the real `ai_detector.detect()` (the deployed model, `Hello-SimpleAI/chatgpt-detector-roberta`, loaded exactly as in production) against all 185 items — the full corpus, not just the 38-item test split, since the classifier is fixed and pretrained, never fitted to any split of this data, so there is no train/test leakage risk in using every labelled item.

Two framings reported: (a) the system's own three-way verdict (`likely_human` / `uncertain` / `likely_ai`), with `likely_ai` treated as the positive prediction — this matches how the signal is actually used in the deployed system; (b) a conventional raw-score-at-0.5 threshold, ignoring the uncertain band, for comparison.

## Result

**Table 8.1: Binary accuracy (verdict = likely_ai as positive prediction).**

| Metric | Value | 95% CI |
|---|---|---|
| Precision | 0.882 | (0.706, 1.000) |
| Recall | 0.167 | (0.093, 0.242) |
| F1 | 0.280 | (0.168, 0.382) |

Confusion matrix (rows = true, cols = predicted; 0 = human, 1 = AI):

```
         pred human   pred AI
true human    93          2
true AI       75         15
```

At the raw 0.5 threshold (ignoring the uncertain band): precision 0.900, recall 0.200, F1 0.327 — the same pattern, marginally less conservative.

**Table 8.2: Recall by generator, among the 90 true-AI items.**

| Generator | Caught (likely_ai) | Recall |
|---|---|---|
| GPT-3 | 10/34 | 29.4% |
| GPT-4 | 2/29 | 6.9% |
| LLaMA | 3/27 | 11.1% |

**False-positive risk on human-authored text**: 2/95 (2.1%) of genuinely human submissions were misclassified as `likely_ai`; a further 2/95 (2.1%) landed in the `uncertain` band. 91/95 (95.8%) were correctly, confidently classified `likely_human`.

## Interpretation

**High precision, very low recall — and the two are not symmetric findings.** When this classifier flags something as likely AI-generated, it is usually right (88.2% precision, tight enough that a false accusation is genuinely rare on this corpus — only 2 of 95 human submissions). But it misses the overwhelming majority of AI-generated text: 75 of 90 genuinely AI-generated submissions were not flagged, and critically, most of these were not even landing in the cautious "uncertain" band — only 10 of the 90 true-AI items did. The other 65 missed items were confidently, incorrectly classified as `likely_human`.

**The recall failure is not uniform across generators, and the pattern is exactly what the model's own name predicts.** `Hello-SimpleAI/chatgpt-detector-roberta` — a detector trained specifically on ChatGPT-era output — catches GPT-3-style text nearly three times more often (29.4%) than GPT-4 text (6.9%), with LLaMA-generated text in between (11.1%). This is a direct, corpus-specific demonstration of the exact risk flagged in the design research behind this component (`docs/2026-07-01/ai_detection_tier_1426.md`): supervised classifiers "degrade hard on domain shift / unseen generators" — here shown as a concrete, measured 4x recall gap between the generator the model was built to catch and a newer model it generalises poorly to.

**The documented ESL/false-positive risk did not manifest strongly on this specific corpus** — 2.1% is a low false-positive rate, not the 61%+ misclassification rate reported for TOEFL essays in the literature review behind this component. This should not be read as the literature's concern being wrong; Clough & Stevenson's specific respondent population (a UK university's computer-science short-answer takers) is not characterised in this study by first-language background, so this corpus cannot confirm or rule out the ESL-specific claim either way — it can only report that, on this particular population, false positives were rare.

## For Chapter 3/4

This is a genuine, informative negative-leaning result, and should be reported as precisely as measured rather than rounded toward either "it works" or "it doesn't": the signal is trustworthy when it fires (high precision) but should never be relied upon to catch AI-generated text reliably (very low recall, and sharply worse against generators newer than its training data). This is the direct, empirical justification for the system's existing design choice (§3.4.5) to treat this signal as advisory-only, shown in visually distinct rendering with an explicit disclaimer, never as a plagiarism-style verdict — a design decision made in advance of this measurement, on literature grounds, and now independently confirmed by this thesis's own data rather than only by citation.
