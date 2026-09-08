# LLM-Generated Content Detection — Plan

**Date:** 2026-05-17 22:09
**Goal:** Add AI-written-content detection alongside the existing dual-tier plagiarism detector, so the Moodle plugin can show *both* a similarity score and an AI-likelihood score for each submission.

---

## 1. What we already have

| Component | Role | Where it lives |
|---|---|---|
| Tier 1 (winnowing + BM25) | Detects *lexical* copying — student copied passages from another submission. | [backend/app/services/tier1_detector.py](../../backend/app/services/tier1_detector.py) |
| Tier 2 (sentence-transformers + FAISS) | Detects *semantic* copying — paraphrased plagiarism. | [backend/app/services/tier2_detector.py](../../backend/app/services/tier2_detector.py) |
| Moodle plugin | Submits files, polls, renders badge. | [moodle-plugin/plagiarism/dualtier/](../../moodle-plugin/plagiarism/dualtier/) |

Both tiers answer **"is this similar to something else we've seen?"** Neither answers **"was this written by a model?"**

---

## 2. Detection landscape (May 2026)

### 2a. The dominant approaches

| Approach | How it works | Best accuracy | False-positive rate | Cost | Strength |
|---|---|---|---|---|---|
| **Perplexity + burstiness** (DetectGPT, original GPTZero) | Sliding-window perplexity over a base LM; "burstiness" = variance across sentences. Humans are uneven; LLMs are smooth. | ~70-80% | 3-12% | CPU, fast | Cheap, interpretable. Loses to paraphrasers. |
| **Fine-tuned RoBERTa classifier** (SuperAnnotate, Originality.ai) | Supervised binary classifier on labelled corpus. | ~87% in-domain, drops to ~60% out-of-domain | 1-5% in-domain | Single forward pass on RoBERTa-large (~350M) | Strong if trained on the domain you care about. Poor generalisation across new LLMs and domains. |
| **Binoculars** (ICML 2024 — current SOTA) | Run two LMs (an "observer" and a "performer") side by side; compare perplexity ratios. Zero-shot, no training. | **>90%** | **0.01%** | Two LMs in memory (~14B parameters with Falcon-7B pair); needs GPU for production speed but works on CPU for short docs | Best published FPR. Robust across models and domains because it doesn't memorise patterns. |
| **Stylometry + XGBoost** | Hand-crafted features (POS frequencies, sentence-length variance, function-word ratios) fed to a tabular classifier. | ~80% | 5-10% | CPU, ms-scale | Interpretable. Often matches transformers on benchmarks but degrades on adversarial paraphrase. |
| **Watermarking** | Embed cryptographic markers at generation time. | ~99% if watermarks exist | ~0% | Trivial check | Only works for cooperating model providers. Most students won't use watermarked models. |
| **Behavioural signals** (keystroke cadence, paste, edit history) | Track how the document was *written* in Moodle's editor. | Very high when applicable | Low | Cheap | Bypassed by file upload (which we use). |

### 2b. Critical caveats

1. **No detector exceeds ~90% accuracy** across all model families. Detection is an arms race; new LLMs evade old detectors.
2. **False positives on non-native English writers are catastrophic.** Studies report **61.3% FPR** on TOEFL essays by Chinese students. For West African or other ESL students this is a real risk for our userbase.
3. **At low FPR thresholds (<0.5%), most detectors collapse to near-zero true-positive rate** (RAID Benchmark 2024). Binoculars is the published exception.
4. **In-distribution scores look great; out-of-distribution collapses.** A RoBERTa classifier trained on GPT-3.5 essays may report 90% accuracy in tests but 50% on Claude-written ones.
5. **Detection should NEVER be the sole basis for an academic penalty.** It must surface "look closer" signals to a human grader, not pass/fail by itself. Major providers (Turnitin, Copyleaks) explicitly state this.

---

## 3. Recommendation for this project

**Add a third detector — "AI-likelihood" — that runs in parallel with Tier 1/Tier 2 and is reported as a separate dimension, not folded into the plagiarism score.**

### 3a. Choice of model

**Primary:** **Binoculars** with **Falcon-7B / Falcon-7B-Instruct** as the observer/performer pair.
- Highest published accuracy + lowest FPR.
- Zero-shot — no labelled training set to maintain as new LLMs ship.
- Apache 2.0 licensed.
- ~14B parameters in RAM; CPU inference takes ~5-15 s per 500-word submission, GPU brings it to <1 s.

**Fallback (CPU-constrained mode):** **SuperAnnotate/roberta-large-llm-content-detector** (HuggingFace, Apache 2.0).
- ~350M parameters, ~200 ms per submission on CPU.
- 87% benchmark accuracy.
- Run this when the host has no GPU; gate Binoculars behind a config flag.

### 3b. What the scores mean (and what we tell the user)

The result will gain two new fields:
- `ai_score` — float 0–1, raw confidence that the text was machine-generated.
- `ai_verdict` — categorical `human | mixed | likely_ai`, computed as:
  - `< 0.30` → `human`
  - `0.30 – 0.85` → `mixed` (could be edited AI, could be a strong non-native writer — needs human review)
  - `≥ 0.85` → `likely_ai`

Threshold deliberately conservative — we'd rather miss some AI-written content than wrongly accuse an ESL student. The teacher sees the score, makes the call.

### 3c. Why NOT fold into the plagiarism score

Plagiarism and AI-generation are conceptually independent:
- A student can paraphrase ChatGPT output (high AI score, low similarity score).
- A student can copy a Wikipedia article (low AI score, high similarity score).
- Mixing them into one number erases that distinction. The teacher needs to see both.

---

## 4. Architecture

```
                                ┌── Tier 1 (winnow+BM25) ──┐
                                │                          │
upload ──► extract_text ──► tier1_detect ──┬── (gate) ──► tier2_detect (escalate)
                                           │                          │
                                           └── ai_detect  ◄────────────┘
                                                  │
                                           DetectionResult
                                                  │
                                  ┌───────────────┼───────────────┐
                                  │               │               │
                            similarity_score   ai_score     similarity_pairs[]
                                  │               │
                                  └───── Moodle plugin shows BOTH badges
```

`ai_detect` is a new Celery task on a new `ai` queue, fired *in parallel* with `tier1_detect`. Two badges on the Moodle row:
- Left: similarity badge (existing, % green/orange/red)
- Right: new AI badge (`H` / `M` / `AI`, also colour-coded)

---

## 5. Implementation steps

### Phase 1 — Backend (1-2 days)
1. **New service** `backend/app/services/ai_detector.py`
   - `class AIDetector` with `detect(text: str) -> AIResult` (score, verdict, model_used, elapsed_ms).
   - Two implementations: `BinocularsDetector` (preferred) and `RoBERTaDetector` (fallback).
   - Pick which based on `settings.AI_DETECTOR_MODE` env var (`binoculars` / `roberta` / `off`).
2. **Pre-load at worker startup** — add to existing `@worker_ready` signal in [celery_app.py](../../backend/app/tasks/celery_app.py:50) so we don't repeat Bug 1.
3. **New Celery task** `backend/app/tasks/ai_tasks.py::detect_ai_content` on a new `ai` queue. Triggered alongside `tier1_detect` (extraction task fans out to both).
4. **DB schema** — add columns to `detection_results`:
   - `ai_score: float | None`
   - `ai_verdict: str | None`
   - `ai_model: str | None`
   - `ai_processing_time_ms: int | None`
   - Alembic migration `0003_add_ai_detection.py`.
5. **API schema** — extend `DetectionResultResponse` in [schemas/result.py](../../backend/app/schemas/result.py) with the same four fields.
6. **Worker queue** — update [docker-compose.yml](../../docker-compose.yml) so the worker subscribes to `ai` alongside the existing queues. Bump worker memory limit to 16 GB if running Binoculars.

### Phase 2 — Moodle plugin (half a day)
7. **DB column** in `mdl_plagiarism_dualtier_files`:
   - `ai_score` (float)
   - `ai_verdict` (varchar 20)
   - Add an `upgrade.php` step.
8. **check_results task** ([classes/task/check_results.php](../../moodle-plugin/plagiarism/dualtier/classes/task/check_results.php)) — after fetching `/results`, store the four new fields.
9. **get_links()** in [lib.php](../../moodle-plugin/plagiarism/dualtier/lib.php) — emit *two* spans: existing similarity badge + new AI badge.
10. **report.php** ([report.php](../../moodle-plugin/plagiarism/dualtier/report.php)) — display the AI score, model used, processing time, and a clear disclaimer: *"This is a signal, not a verdict. ESL student writing can be misclassified — please review the document yourself."*
11. **Language strings** in `lang/en/plagiarism_dualtier.php` for the new badges, verdicts, and disclaimer.

### Phase 3 — Verification (half a day)
12. **Verification script** `verify_ai_detector.py`:
    - Submit a human-written sample → expect `verdict=human`.
    - Submit a known ChatGPT/Claude paragraph → expect `verdict=likely_ai`.
    - Submit an ESL student sample (proxy: pick a paragraph from a non-native English academic essay) → confirm score is below 0.85 (false-positive guard).
13. **End-to-end Moodle test** — extend the existing 3-student test to 5: add `student4` (submits AI-generated essay) and `student5` (submits ESL-style human essay). Confirm dashboards correctly distinguish them.

### Phase 4 — Operational (ongoing)
14. **Audit log** — record every submission's AI score in a separate `ai_detection_log` table for the academic-integrity board to review false-positive claims.
15. **Calibration job** — quarterly: re-test the detector against samples of the *latest* LLMs (Claude N+1, GPT N+1, etc.). Adjust thresholds if drift is detected.

---

## 6. Risks and open questions

| Risk | Mitigation |
|---|---|
| Binoculars eats 14 GB RAM — workstation may OOM | Default to RoBERTa mode in `.env`; require explicit `AI_DETECTOR_MODE=binoculars` to enable. |
| ESL false positives → wrongly accused student | Threshold ≥0.85 for `likely_ai`; teacher-facing copy *explicitly* says it's a signal not a verdict; never block submission. |
| Detector becomes obsolete as new LLMs ship | Quarterly calibration. Binoculars is more robust here than fine-tuned classifiers. |
| First Binoculars load downloads ~14 GB from HuggingFace | Bake model into Docker image at build time (same approach we'd want for `all-MiniLM-L6-v2` after Bug 1). |
| Detection adds 5-15 s to submission processing | Run as a parallel Celery task on its own queue; doesn't block the similarity result from appearing. |

### Open before we start

- Are we OK with the additional resource cost (14 GB RAM for Binoculars, or accept ~75% accuracy with RoBERTa fallback)?
- What's the policy if `verdict=likely_ai` but the student disputes? — needs a written process before deployment.
- Do we want the AI badge visible to *students* on their own submission page, or teacher-only?

---

## 7. Effort estimate

- Backend implementation + migration + verification: **2 days** of focused work.
- Moodle plugin UI: **0.5 day**.
- Documentation + calibration plan: **0.5 day**.
- **Total: ~3 days** to ship a Phase-1 (RoBERTa fallback) version; **+0.5 day** to add Binoculars mode.

## Sources
- [Spotting LLMs With Binoculars: Zero-Shot Detection of Machine-Generated Text (arxiv:2401.12070)](https://arxiv.org/abs/2401.12070)
- [Binoculars implementation (GitHub)](https://github.com/ahans30/Binoculars)
- [SuperAnnotate/roberta-large-llm-content-detector (HuggingFace)](https://huggingface.co/SuperAnnotate/roberta-large-llm-content-detector)
- [LLM-generated text detection: enhancing accuracy using XLM-RoBERTa & DistilBERT (PeerJ CS, 2026)](https://peerj.com/articles/cs-3672/)
- [Detecting the Machine: comprehensive benchmark (arxiv:2603.17522, 2026)](https://arxiv.org/abs/2603.17522)
- [GPTZero AI Detector accuracy benchmarks 2026 (EyeSift comparison)](https://www.eyesift.com/blog/ai-detector-accuracy-benchmarks-2026/)
- [False positives on non-native English writers (PMC review)](https://pmc.ncbi.nlm.nih.gov/articles/PMC12331776/)
- [AI Detector Accuracy Leaderboard 2026 (HumanizeAI)](https://thehumanizeai.pro/articles/ai-detector-accuracy-leaderboard-2026)
- [What Educators Should Know About AI Detection in 2026 (Copyleaks)](https://copyleaks.com/blog/what-educators-should-know-about-ai-detection-in-2026)
