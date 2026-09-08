# AI-detection additions to Chapter 3 (§3.10.4) and Chapter 4 — ready to paste

Now that AI-authorship detection is confirmed in scope (§3.4.5, already drafted in `docs/2026-08-12/section_3_4_to_3_6_replacement_1430.md`), it needs one addition to Chapter 3's experimental design and one new results section in Chapter 4. Real numbers below are from `evaluation/reports/08_ai_detection_accuracy.md`, run 2026-09-02.

---

## Chapter 3 addition: §3.10.4 (new, appended after §3.10.3)

### 3.10.4 Experiment 4: AI-Authorship Detection Accuracy

No hypothesis in §1.4 targets the AI-authorship signal specifically, since it is an advisory, secondary feature (§3.4.5) rather than part of the plagiarism-detection claims this thesis's hypotheses address. This experiment characterises its accuracy empirically rather than testing it against a pass/fail target, consistent with its advisory-only design intent.

**Ground truth.** The existing evaluation corpus (§3.7) already contains a usable human-vs-AI label, orthogonal to its plagiarism label, requiring no new data collection: Clough & Stevenson (2011) predates modern large language models and is genuine human authorship; PlagBench (Lee et al., 2025) is machine-generated across all three of its categories, confirmed directly against the corpus's own generator metadata before being relied upon. This gives a 185-item labelled corpus (95 human, 90 AI-generated, with generator identity — GPT-3, GPT-4, or LLaMA — known per AI-generated item).

**Procedure.** The deployed AI-authorship classifier is run against all 185 items (the full corpus, not only the test split — the classifier is fixed and pretrained, never fitted to this data, so no split restriction is methodologically required). Its own three-way verdict (`likely_human` / `uncertain` / `likely_ai`) is scored against ground truth, with `likely_ai` treated as a positive prediction. Precision, recall, and F1 are reported with bootstrap 95% confidence intervals, per §3.11.1, alongside a breakdown by generator and a specific check of the false-positive rate on human-authored text — the risk this component's design (§3.4.5) was built around.

---

## Chapter 4 addition: new section, insert as §4.6 (renumbering the existing §4.6/4.7 in `chapter_4_part3_...` to §4.7/4.8, and §4.8 in `chapter_4_part4_...` to §4.9)

## 4.6 Experiment 4: AI-Authorship Detection Accuracy

Following §3.10.4, the deployed classifier was run against all 185 corpus items.

**Table 4.X: AI-authorship detection accuracy.**

| Metric | Value | 95% CI |
|---|---|---|
| Precision | 0.882 | (0.706, 1.000) |
| Recall | 0.167 | (0.093, 0.242) |
| F1 | 0.280 | (0.168, 0.382) |

Confusion matrix: TN=93, FP=2, FN=75, TP=15 (of 90 truly AI-generated items).

**The result is asymmetric, and both halves matter.** Precision is high: when the classifier flags a submission as likely AI-generated, it is correct 88.2% of the time, and only 2 of 95 genuinely human submissions were misclassified (2.1% false-positive rate on this corpus). Recall is very low: 75 of 90 genuinely AI-generated submissions were missed — and the majority of those were not landing in the model's own cautious "uncertain" band, but were confidently, incorrectly scored as human-written. Only 10 of the 90 true-AI items registered as uncertain; the rest split between 15 correctly caught and 65 confidently missed.

**Recall varies sharply and informatively by generator**: GPT-3-generated text was caught 29.4% of the time; LLaMA-generated text, 11.1%; GPT-4-generated text, only 6.9%. The deployed model (`Hello-SimpleAI/chatgpt-detector-roberta`) is trained specifically on ChatGPT-era output, and this ordering — best on the generator closest to its training distribution, worst on a newer and architecturally different model (GPT-4) — is a direct, measured demonstration of the poor cross-generator generalisation this class of detector is known to exhibit (§2.1, §3.4.5), not merely a cited risk.

**The literature-documented false-positive risk for non-native English writers (§3.4.5) is neither confirmed nor refuted by this result.** The measured 2.1% false-positive rate on this corpus is low, but Clough & Stevenson's respondent population is not labelled by first-language background in this study, so this result establishes only that false positives were rare on this specific, uncharacterised population — not that the general concern is unfounded.

**This result empirically justifies, rather than merely assumes, the system's advisory-only design.** A signal with this precision/recall profile is trustworthy as a prompt for a human conversation when it does fire, and actively unsuitable as a comprehensive detector — it will miss the large majority of genuinely AI-generated submissions, especially from any generator newer than the classifier's own training data. The system's existing design (§3.4.5: separate storage, separate rendering, explicit disclaimer, never gating submission status) was made on literature grounds before this measurement and is now independently confirmed by it.
