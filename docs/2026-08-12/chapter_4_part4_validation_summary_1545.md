# CHAPTER FOUR — RESULTS, Part 4 of 4: System Validation, Hypothesis Summary, Chapter Summary

---

## 4.8 System Validation

Following §3.12.

### 4.8.1 Unit Testing

147 tests pass across the backend test suite, with 85% overall line coverage — exceeding the 80% target stated in §3.12.1. Coverage is not uniform: the core detection services (Winnowing, BM25, Tier 1/Tier 2 scoring, gating, and the structural-signal and match-explanation modules introduced in §4.6) reached 91–100%; the asynchronous task-orchestration layer, for which no database test infrastructure was built, reached 16–48%. The latter layer's correctness assurance came instead from repeated live, end-to-end verification against the deployed system rather than from automated unit tests, documented per feature as each was verified.

### 4.8.2 Integration Testing

End-to-end submission-to-verdict tests passed via the FastAPI endpoint directly. Automated Moodle-side integration testing via Behat, specified in §3.12.2, was deferred as the lowest-priority item under the project's time budget and substituted with extensive manual, live verification against the deployed Moodle instance: the full submission flow from event capture to badge display, badge rendering for both the similarity and AI-authorship signals, report-page access control (including a deliberately mismatched-module request, confirming defect 7 in Table 4.1 stays fixed), per-assignment and global enable/disable behaviour, and duplicate-submission handling. This verification is real, specific, and repeatable manually, but not automated as a single command the way the originally-scoped Behat suite would have been.

### 4.8.3 Performance Testing

Load testing followed §3.12.3 with an adapted profile — fixed 20-user and 50-user plateaus held for three minutes each, rather than a single ten-minute 1→50-user ramp, for practicality against the deployment's own resource ceiling (§3.3). **Result: zero failed requests at 50 concurrent users** (exceeding the 20-user target in §3.12.3), with p95 latency of approximately 120 milliseconds — two orders of magnitude inside the 5-second budget. Memory was verified directly against the live deployment rather than profiled offline, confirming the full stack (backend, two Celery workers, Redis, two PostgreSQL instances, and the complete Moodle stack) operates comfortably within the actual ~7.8GB deployment instance described in §3.3.

One real regression was found and fixed during this testing, not before it: an architectural change made to resolve defect 6 (Table 4.1) — splitting detection processing across two Celery workers — introduced CPU contention that only appeared under the 50-user load, and was caught only by re-running this exact test after that change, not anticipated in advance. It was resolved by tuning worker concurrency and setting explicit CPU limits before the measurement reported above.

### 4.8.4 Accuracy Validation

Reported in §4.7.

---

## 4.9 Summary of Hypothesis Outcomes

**Table 4.4: Hypothesis outcomes.**

| # | Hypothesis | Target | Result | Verdict |
|---|---|---|---|---|
| H1 | Tier 1 resolution rate | ≥ 80% | 52.63% | **Not supported** |
| H2 | ≥90% of cloud-only effectiveness at ≤30% of its cost | Both halves | Effectiveness 105% (met); cost 47.4% of cloud-only, above the ≤30% target (not met) | **Partially supported** |
| H3 | F1 ≥ 0.84 | ≥ 0.84 | 0.884, highest of 4 configurations | **Supported** |
| H4 | End-to-end latency p95 < 5 seconds | < 5s | Component: 247ms (supported). True end-to-end: ~20s (not supported), down from ~5m34s | **Supported (component) / Not supported (end-to-end)** |
| H5 | Real-time detection feasibility | Qualitative | Genuine cross-submission match detected and delivered live within ~20s; sub-300ms detection itself | **Supported in substance** |

Every hypothesis result above reflects the corrected figures from Table 4.1; none would be reportable as-is from a first, uncorrected measurement.

---

## 4.10 Chapter Summary

The dual-tier system was evaluated against five hypotheses across three specified experiments, plus a supplementary cross-submission matching investigation undertaken because Experiment 3 raised a question the original design left open. Of the five hypotheses, one is clearly supported (F1), one is clearly not supported (Tier 1 resolution rate), one is supported only at the component level and not at the true end-to-end level (latency), one is supported in substance despite a strict literal target not being met (real-time feasibility), and one requires reporting its two halves separately because they diverge (cost-effectiveness).

Two findings recur across this chapter and are treated as connected rather than coincidental. First, the escalation rate this corpus genuinely requires under this system's precision constraint (≈47%) is the single root cause behind both Hypothesis 1's shortfall and the cost half of Hypothesis 2's shortfall — not two independent weaknesses. Second, ten real implementation defects were found and corrected specifically because results were checked against ground truth at every stage rather than trusted once produced, and in three cases a first, plausible-looking fix was itself wrong and only caught by the same discipline. This pattern — measure, distrust the first result enough to check it, find the real cause, fix it, re-measure — is the central methodological finding of this chapter and is taken up directly in Chapter 5's discussion of the project's contribution and limitations.
