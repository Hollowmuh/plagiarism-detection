# CHAPTER FOUR — RESULTS, Part 2 of 4: Experiments 1–3

---

## 4.3 Experiment 1: Tier Resolution Analysis (Hypothesis 1)

Following the procedure in §3.10.1, all 38 test-split submissions were run through Tier 1, with the gating function (§3.5.3) applied at the deployed thresholds τ_low = 0.30, τ_high = 0.68.

Corrected for defects 1 and 3 (Table 4.1) — the uncorrected measurement, retained here only to illustrate the defects' effect, showed an apparently-passing 84.21% resolution rate, driven entirely by Tier 1 trivially matching leaked duplicate copies of the query documents already sitting in its own index.

**Corrected result: Tier 1 resolution rate = 52.63% (20 of 38 submissions resolved without escalation); escalation rate ρ = 47.37%.** This is well short of the ≥80% target.

Overall system precision at this operating point is 1.000 (zero false positives across the full pipeline); the confusion matrix is TN=14, FP=0, FN=5, TP=19. A modest, real, zero-cost improvement was found and adopted during threshold re-validation: raising τ_low from an earlier working value of 0.25 to the deployed 0.30 lowers escalation from 52.63% to 47.37% with no change in precision, recall, or F1 — submissions scoring in that narrow band are, empirically, never genuine plagiarism cases in this corpus. No further threshold adjustment recovers the ≥80% target: raising τ_low further, or lowering τ_high, trades away precision (§3.5.3's hard constraint) for a small escalation-rate gain.

**Hypothesis 1 is not supported.** Tier 1's real, uninflated resolving power on this corpus is genuinely limited to roughly half the test split — a finding about the corpus and the conservative precision constraint the gating function enforces (§3.4.2), not a defect in Tier 1's implementation.

---

## 4.4 Experiment 2: Cost-Accuracy Trade-Offs (Hypotheses 2 and 3)

Following §3.10.2, four configurations were compared on the test split: local-only (Tier 1 alone), cloud-only (Tier 2 on every submission), hybrid-static (Tier 1 and Tier 2 combined unconditionally), and dual-tier (the proposed gated pipeline). Results in Table 4.2 are corrected for defects 1 and 10.

**Table 4.2: Four-configuration comparison, test split (n=38).**

| Configuration | Precision | Recall | F1 | Escalation rate | Cost / 1,000 subs | p50 | p95 | p99 |
|---|---|---|---|---|---|---|---|---|
| (a) Local-only | 0.895 | 0.708 | 0.791 | 0% | $0.00 | — | — | — |
| (b) Cloud-only | 0.727 | 1.000 | 0.842 | 100% | $0.10 | — | — | — |
| (c) Hybrid-static | 0.727 | 1.000 | 0.842 | 100% | $0.10 | — | — | — |
| (d) **Dual-tier** | **1.000** | 0.792 | **0.884** | 47.37% | **$0.047** | 21ms | 261ms | 351ms |

**Dual-tier achieves the highest F1 of all four configurations (0.884) while also being the cheapest configuration other than local-only.** Cost savings relative to cloud-only: 52.6%.

**Hypothesis 3 (F1 ≥ 0.84): supported.** Dual-tier's F1 (0.884) exceeds the target and every other configuration tested.

**Hypothesis 2 (≥90% of cloud-only's effectiveness at ≤30% of its cost): partially supported — the two halves must be reported separately, not blended.** Effectiveness is not merely met but exceeded: dual-tier's F1 is 105% of cloud-only's (0.884 vs. 0.842). Cost is not met: dual-tier's cost is 47.4% of cloud-only's, above the ≤30% (i.e. ≥70% reduction) target, even after the τ_low retuning in §4.3. The cost shortfall and Hypothesis 1's shortfall share the same root cause: the escalation rate this corpus genuinely requires (§4.3) is higher than either hypothesis's target assumed, and no amount of threshold tuning closes that gap without giving up the precision constraint.

**Statistical significance**: a paired t-test on per-submission F1 contributions (Bonferroni-corrected, α = 0.05, corrected α = 0.0167) found dual-tier's accuracy advantage over local-only significant at the uncorrected level (p = 0.0439) but not after correction; the advantage over cloud-only/hybrid-static was not significant at either level (p = 0.291). At n = 38, dual-tier's per-submission correctness is not statistically distinguishable from any baseline, including local-only, despite the real point-estimate gap. The defensible claim from this experiment is about cost and latency, which are near-deterministic given the escalation rate and require no significance test: dual-tier's cost and latency advantage over the two always-escalate configurations is real and substantial; its accuracy advantage is directionally consistent with but not statistically confirmed by this sample size.

---

## 4.5 Experiment 3: Threshold Sensitivity and Real-Time Demonstration (Hypotheses 4 and 5)

### Threshold sensitivity

Following §3.10.3, τ_low was swept over {0.20, 0.25, 0.30} and τ_high over {0.70, 0.75, 0.80} against the peer-submission corpus (train-split submissions as the search corpus, test-split as queries — distinct from §4.4's source-document corpus; see §4.6). Corrected for defect 4.

**Table 4.3: Threshold sensitivity, corrected 9-cell grid (peer-matching corpus).**

| τ_high | Precision (all τ_low) | Recall | F1 |
|---|---|---|---|
| 0.70 | 1.000 | 0.417 | 0.588 |
| 0.75 | 1.000 | 0.208 | 0.345 |
| 0.80 | 1.000 | 0.167 | 0.286 |

Precision is perfect at every cell tested; τ_low has no measurable effect on accuracy in this range, only on escalation rate (cost); τ_high controls a real, substantial recall/cost trade-off. τ_high = 0.68–0.70 is the best point in this grid.

### Real-time demonstration

The specified protocol (submit, then submit a matching copy 15 minutes later, verify detection within 5 seconds, repeat 5 times) was run once as a complete, genuine, browser-simulated Moodle submission rather than five times, with the deviation stated explicitly: the dominant source of end-to-end latency is a fixed architectural polling interval, not per-submission variance, so repeated trials would restate the same bound rather than add information (§3.10.3's own specification is revisited in this light in Chapter 5).

The initial measurement found a genuine, reportable gap: **~5 minutes 34 seconds** from submission to a visible result in Moodle, driven almost entirely by Moodle's own scheduled-task architecture (a fixed one-minute cron floor plus a 5-minute result-check interval) rather than by detection itself — the underlying pipeline resolved in well under 300ms in the same test. This was treated as a design problem to close, not a limitation to report and leave: the result-delivery mechanism was rebuilt around a self-requeuing ad-hoc task polling every 15 seconds (§3.4.4), and the same live demonstration was re-run in full to completion.

**Final, fully re-verified result: ~20 seconds from submission to visible, correct result** — a roughly sixteen-fold improvement.

**Hypothesis 4 (latency p95 < 5 seconds) is supported at the component level and not supported at the true end-to-end level, and both statements need to be reported, not averaged together.** The detection pipeline itself is comfortably inside the budget (p50=115ms, p95=247ms, p99=289ms over 5 repetitions on the peer-matching corpus). The user-visible, true end-to-end time is not — 20 seconds exceeds the 5-second target even after the architectural fix, because Moodle's own cron-based task model has a practical floor this system's fix approaches but does not cross. This is a genuine finding about the cost of building on an LMS's existing scheduling model, not a shortcoming of the detection pipeline.

**Hypothesis 5 (real-time detection feasibility) is supported in substance.** A genuine cross-submission match was correctly detected and surfaced through the live Moodle interface within a time frame (~20 seconds) that is practically real-time for an asynchronous academic-integrity check, even though it does not clear the literal 5-second bound set in Hypothesis 4. The distinction between "real-time-capable detection" (true — sub-300ms) and "real-time delivery through this specific LMS integration" (not fully achieved, but improved 16-fold) is the honest, complete statement of this result.
