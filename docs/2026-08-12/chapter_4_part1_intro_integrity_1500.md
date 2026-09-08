# CHAPTER FOUR — RESULTS, Part 1 of 4: Preamble and Methodological Integrity

Chapter 4 does not currently exist in the thesis document — this is new content, drafted from the accompanying evaluation reports (`evaluation/reports/00`–`07`), which serve as the primary source per this project's own stated convention. Register matches Chapter 3 (impersonal, third-person, technical). All numbers below are the final, corrected figures — where a report went through multiple rounds of correction, only the last, verified value is used; the correction history itself is treated as a result, not hidden.

---

## 4.1 Preamble

This chapter reports the outcomes of the three experiments specified in §3.10, tested against the five research hypotheses stated in §1.4, followed by a supplementary cross-submission matching analysis, a failure-mode analysis, and system validation results. Section 4.2 first reports a distinct, cross-cutting finding of its own: the evaluation process surfaced ten genuine implementation defects, none apparent from code review alone, each found only by running the system end-to-end and checking its output against ground truth. This is reported as a methodological result in its own right, consistent with Hevner et al.'s (2004) framing of design as an iterative search process, and it directly explains why several results below differ from what a first, uncorrected measurement would have shown.

## 4.2 Methodological Integrity: Defects Found During Evaluation

Ten real defects were found and corrected during the evaluation process described in this chapter, summarised in Table 4.1. Each was found by actually running the system against real data and checking the result, not by static inspection — in three cases (rows 3, 6, and 9), the *first* attempted fix was itself incorrect and was only caught by re-running the same live check used to justify the fix in the first place.

**Table 4.1: Defects found and corrected during evaluation.**

| # | Defect | Effect before correction | How found |
|---|---|---|---|
| 1 | Corpus data leakage | All 95 Clough & Stevenson submissions were also present, under a different filename, in the external source-matching corpus — every one was evaluated against a copy of itself | Anomalously high shared-hash counts behind a cluster of false positives |
| 2 | Winnowing similarity measure | Gated on Jaccard similarity instead of containment, against the code's own documented design intent — collapsed toward zero for short-excerpt-in-long-source matches | Re-reading the module's own comments against its actual gating logic |
| 3 | Evaluation-harness fingerprint indexing | The offline evaluation script never inserted source documents into the Winnowing index (only into BM25/FAISS), silently making Tier 1 blind to the entire corpus during evaluation. First fix attempt addressed the wrong function. | An existing unit-test fixture had already documented and worked around the same gap |
| 4 | Threshold-sweep self-contamination | Two independent threshold-sweep scripts each reused the same stateful fingerprint index across sweep iterations; each query permanently inserted itself, so every configuration after the first degenerated into "predict everyone positive" | Cross-checking one sweep script's results against an independently-written second one |
| 5 | FAISS vector-to-document mapping | The vector index never persisted its integer-ID-to-document mapping across process restarts, silently orphaning and mis-labelling matches after any worker restart | Unit tests against the shared production index returning implausible scores |
| 6 | Cross-submission ordering under concurrency | An initial fix for a Celery worker capacity problem parallelised document extraction; this broke the guarantee that submission N's content is indexed before submission N+1 is checked against it | A live two-submission race test, run specifically to validate the fix |
| 7 | Cross-course report disclosure (IDOR) | The Moodle report page authorised access against one URL parameter but fetched data using a second, independent, attacker-controllable parameter | Deliberate adversarial audit of the reporting layer |
| 8 | Index purge on submission deletion | Deleting a submission removed its database rows but never removed it from the in-memory detection indices; a first fix attempt mutated an empty copy of the index in the wrong process and silently did nothing | Re-running the same live delete-then-resubmit check used to justify the fix |
| 9 | Match-explanation delivery | The database column, API schema, and Moodle rendering logic for showing matched passages to instructors were all present and mutually consistent from early in the project, but nothing in the detection pipeline ever wrote to the column — the feature was silently dead from inception | Direct trace of the write path while building an unrelated feature |
| 10 | Evaluation-script FAISS index contamination | Baseline comparison scripts defaulted to the same shared, persistent vector index used by every other local evaluation run, inflating candidate pools with unrelated vectors and measurably affecting always-escalate baseline configurations | A documented, unverified caveat in an earlier report was tested directly against an isolated index |

Defects 1–2 and 4–5 affected results reported in this chapter directly and are noted at the relevant point below; their corrected values are the ones reported throughout. Defects 6–9 affected system correctness but not the accuracy/cost/latency figures in this chapter, since they concern data integrity and access control rather than detection quality; they are reported here for completeness and are discussed further in Chapter 5. Defect 10 affected only the exact baseline comparison figures in §4.4, with no change to any hypothesis verdict.
