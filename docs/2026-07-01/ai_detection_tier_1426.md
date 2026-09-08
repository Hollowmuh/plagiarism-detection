# AI-Generated-Text Detection: Research & Implementation Plan

## Context

This system currently detects **source-matching plagiarism** (a submission copying/paraphrasing an existing document) via a dual-tier pipeline: Tier 1 (Winnowing fingerprints + BM25, fast/cheap) gates into Tier 2 (FAISS dense embeddings + BM25 hybrid, precise/expensive) when the Tier 1 score falls in an ambiguous band (`TAU_LOW=0.25` to `TAU_HIGH=0.75`, `backend/app/config.py:24-25`).

**AI-generated-text detection is a different problem.** A submission can be:
- Copied from a human source (existing plagiarism detection catches this) and *not* AI-written
- Fully original AI-generated prose (nothing to source-match against — Tier 1/Tier 2 would score it near 0% even though a teacher would still want to know) and *not* plagiarised
- Both, or neither

So this is not a third rung on the existing escalation ladder — it needs to run as an **independent, parallel check** whose output is reported alongside the similarity score, not blended into `final_score`/`is_plagiarised`.

## Research Summary

Six broad approaches exist for AI-text detection (source: [arxiv.org/pdf/2507.15286](https://arxiv.org/pdf/2507.15286), [arxiv.org/pdf/2310.05030](https://arxiv.org/pdf/2310.05030)):

| Approach | How it works | Self-hostable? | Notes |
|---|---|---|---|
| **Perplexity/burstiness** | LLM output is more locally predictable and less bursty (sentence-to-sentence variance) than human writing; score via a reference LM's token log-probs | Yes, cheap | What GPTZero originally used; weakest of the modern methods alone |
| **DetectGPT / Fast-DetectGPT** | Perturb the text, compare log-probability curvature of original vs. perturbations — AI text sits in a sharper local maximum | Yes, moderate cost | Fast-DetectGPT is ~340x faster than original DetectGPT, zero-shot (no training data needed) |
| **Binoculars** | Ratio of perplexity from two different-sized LLMs ("observer" vs "performer") from the *same family* | Yes, but needs 2 LLMs loaded (7B-class models typically) | Zero-shot, state-of-the-art: >90% detection at 0.01% false-positive rate, beats DetectGPT/Fast-DetectGPT/Ghostbuster and commercial tools in published benchmarks ([huggingface.co/blog/dmicz/binoculars-text-detection](https://huggingface.co/blog/dmicz/binoculars-text-detection), [arxiv.org/abs/2401.12070](https://arxiv.org/abs/2401.12070)). Reference impl: [github.com/ahans30/Binoculars](https://github.com/ahans30/Binoculars) |
| **Supervised classifiers** | Fine-tuned transformer encoder (e.g. RoBERTa) trained on human-vs-AI labeled pairs | Yes, cheap (single small model) | Fast, but degrades hard on domain shift / unseen generators / paraphrasing attacks |
| **Watermarking** | Bias token sampling at generation time so output is statistically detectable later | No — requires control over the *generating* model, not applicable here (we only see submitted text, not how it was produced) | Not usable for this use case |
| **Commercial APIs** | Originality.ai, GPTZero, Copyleaks, Turnitin, Pangram, etc. | No — hosted, paid per-check | Best raw accuracy in current benchmarks (Originality.ai ~96-97%, Copyleaks ~94%, Turnitin ~92%, GPTZero ~90% per [eyesift.com](https://www.eyesift.com/blog/ai-detector-accuracy-benchmarks-2026/), [gptzero.me/news/best-ai-detectors](https://gptzero.me/news/best-ai-detectors/)) — but costs money per submission and sends student text to a third party |

### The bias/false-positive problem (important for an academic tool)

This is the single biggest risk in this space and must shape the design, not just be a footnote:
- GPT detectors misclassify **61.3% of TOEFL essays by non-native English speakers as AI-generated**, on average, across multiple commercial tools ([pmc.ncbi.nlm.nih.gov/articles/PMC10382961](https://pmc.ncbi.nlm.nih.gov/articles/PMC10382961/), [sciencedirect.com/science/article/pii/S2666389923001307](https://www.sciencedirect.com/science/article/pii/S2666389923001307))
- False-positive rates run up to 3x higher for non-native writers even with newer detectors, because training/baseline corpora skew toward native-English statistical patterns ([hastewire.com](https://hastewire.com/blog/study-reveals-ai-detectors-false-positives-on-non-native-writers), [pangram.com/blog/how-accurate-is-pangram-ai-detection-on-esl](https://www.pangram.com/blog/how-accurate-is-pangram-ai-detection-on-esl))
- Even the best 2026 tools recommend **never using AI-detection score as sole grounds for an academic-misconduct verdict** — treat it as a signal that prompts a conversation/draft-history check, not an automated accusation ([digitalapplied.com](https://www.digitalapplied.com/blog/ai-content-detection-tools-2026-accuracy-pricing-guide))

**Design implication:** this must ship as an advisory score/badge (like the existing similarity badge), never as an auto-block or auto-fail, and the UI copy must say so explicitly.

## Recommendation

Given this deployment is CPU-only (`e2-standard-2`, 2 vCPU / 8GB RAM, already running Postgres ×2, Redis, FastAPI, Celery worker+beat, Moodle stack) and self-hosted-by-default is the existing pattern (sentence-transformers already runs locally for embeddings):

**Phase 1 (recommended default): self-hosted supervised classifier**, not Binoculars.
- Binoculars needs two LLMs resident in memory simultaneously (typically 7B-class each) — not realistic on this box alongside everything else already running. It's the best *accuracy*, but the wrong fit for *this* hardware.
- A single fine-tuned RoBERTa-family detector (e.g. `Hello-SimpleAI/chatgpt-detector-roberta` class of model, ~500MB) runs comfortably CPU-side, similar footprint to the sentence-transformer already in `embedding_service.py`.
- Explicitly accept the accuracy tradeoff and communicate it: lower ceiling than Binoculars/commercial APIs, worse generalization to unseen generators, so the UI must frame this as "possible AI involvement — advisory" not a verdict.

**Phase 2 (optional upgrade path, decision point for you):** either swap in Fast-DetectGPT (still self-hosted, better accuracy, more CPU cost per check — needs benchmarking on this VM) or add an opt-in commercial API (Pangram is worth a look specifically because it publishes ESL-calibration data, unlike most competitors) for institutions that accept the cost/privacy tradeoff for higher accuracy. This should be a pluggable interface from day one so Phase 2 doesn't require re-architecting.

## Architecture

Mirrors the existing `tier1_detector.py` / `tier2_detector.py` pattern:

```
backend/app/services/ai_detector.py       # new: loads classifier once (singleton, like tier1/tier2 in detection_pipeline.py:24-25), exposes detect(text) -> AIDetectionResult
backend/app/tasks/ai_detection_tasks.py   # new Celery task, own queue "ai_detection" (mirrors extraction/detection/embedding/indexing queues in celery_app.py:39-42)
```

- Runs **in parallel** with the existing `run_detection()` call in `detection_pipeline.py`, not inside the `route()` gate in `gating.py` — independent Celery task chained/grouped alongside the existing detection task, not a new branch in `PipelineResult`.
- New DB table `ai_detection_results` (not new columns on `detection_results`, to keep the two concerns cleanly separable and independently nullable/retriable): `submission_id` (FK), `ai_score` (float 0-1), `verdict` (enum: `likely_human` / `uncertain` / `likely_ai`), `model_name`, `processing_time_ms`, timestamps — same `UUIDPrimaryKeyMixin`/`TimestampMixin` pattern as `backend/app/models/result.py`.
- New Pydantic schema `AIDetectionResultResponse`, added as an optional field on the existing `DetectionResultResponse` (`backend/app/schemas/result.py:23-35`) so the Moodle plugin's existing `get_results()` call (`api_client.php`) picks it up without a new endpoint.
- Moodle side: `plagiarism_dualtier/report.php` gets a new "AI-Generated Content Likelihood" section (styled distinctly from the similarity score, with an explicit disclaimer sentence), and `lib.php`'s `get_links()` badge gets a second, visually distinct indicator so the two signals are never visually conflated into one number.

## Open Questions For You

1. **Self-hosted classifier vs. commercial API for Phase 1** — I've recommended self-hosted for cost/privacy/consistency-with-existing-architecture, but if accuracy matters more than those factors for your use case, Phase 1 could start with a commercial API instead (Pangram or Originality.ai) and skip straight to that. Which matters more here?
2. **Advisory-only, confirmed?** — Given the ESL false-positive research above, I'm assuming this should never auto-fail/auto-block a submission, only surface a score. Confirm before I start building the "verdict" enum and any threshold-based UI coloring, since that's a policy decision, not just an engineering one.
3. **Model choice for Phase 1** — want me to benchmark 2-3 specific open-source classifier checkpoints on this VM's actual CPU before committing, or pick one and proceed?

## Sources

- [Beyond Easy Wins: A Text Hardness-Aware Benchmark for LLM-generated Text Detection](https://arxiv.org/pdf/2507.15286)
- [Counter Turing Test CT^2 / AI Detectability Index](https://arxiv.org/pdf/2310.05030)
- [Detecting LLM-Generated Text with Binoculars](https://huggingface.co/blog/dmicz/binoculars-text-detection)
- [Binoculars GitHub repo](https://github.com/ahans30/Binoculars)
- [Spotting LLMs With Binoculars (arXiv)](https://arxiv.org/abs/2401.12070)
- [AI Detector Accuracy Benchmarks 2026 (eyesift.com)](https://www.eyesift.com/blog/ai-detector-accuracy-benchmarks-2026/)
- [10 Best AI Detectors 2026 (gptzero.me)](https://gptzero.me/news/best-ai-detectors/)
- [AI Content Detection Tools 2026: What Works and What Doesn't](https://www.digitalapplied.com/blog/ai-content-detection-tools-2026-accuracy-pricing-guide)
- [GPT detectors are biased against non-native English writers (PMC)](https://pmc.ncbi.nlm.nih.gov/articles/PMC10382961/)
- [GPT detectors are biased against non-native English writers (ScienceDirect)](https://www.sciencedirect.com/science/article/pii/S2666389923001307)
- [Study Reveals AI Detectors' False Positives on Non-Native Writers](https://hastewire.com/blog/study-reveals-ai-detectors-false-positives-on-non-native-writers)
- [How accurate is Pangram AI Detection on ESL?](https://www.pangram.com/blog/how-accurate-is-pangram-ai-detection-on-esl)
