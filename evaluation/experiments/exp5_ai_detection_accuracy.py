"""Experiment 5: AI-Authorship Detection Accuracy.

Tests the AI-authorship advisory signal (backend/app/services/ai_detector.py)
against real, already-available ground truth in the existing evaluation
corpus -- no new data collection needed.

Ground truth, confirmed against labels.csv's own `dataset`/`task` columns
before building this script (not assumed):
  - Clough & Stevenson (2011), 95 submissions: genuine human authorship.
    `task` column holds plain question letters (a-e), and the corpus
    predates modern LLMs entirely (published 2011).
  - PlagBench (Lee et al., 2025), 90 submissions: LLM-generated, ACROSS
    ALL THREE of its categories including "original" -- `task` column
    holds Input.gpt3 / Input.gpt4 / Input.llama for every PlagBench row,
    confirmed by direct inspection, not inferred from the paper alone.

This is a different label axis than the plagiarism label used elsewhere
(Reports 01-04): authorship (human vs AI) rather than plagiarism status.
Orthogonal and independently meaningful -- Clough & Stevenson's "original"
category is human-authored AND non-plagiarised; PlagBench's "original"
category is AI-generated AND non-plagiarised. Both feed this experiment
as ground truth for authorship regardless of their plagiarism label.

Uses the FULL 185-item corpus, not just the 38-item test split: the
AI-detector is a fixed, off-the-shelf pretrained classifier, never
fitted to any split of this corpus, so there is no train/test leakage
risk in using every labelled item here.
"""

import csv
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "backend"))

import numpy as np

from metrics import compute_metrics

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "dataset", "data")
SUBMISSIONS_DIR = os.path.join(DATA_DIR, "submissions")


def load_all_items() -> list[dict]:
    items = []
    with open(os.path.join(DATA_DIR, "labels.csv"), encoding="utf-8") as f:
        for row in csv.DictReader(f):
            path = os.path.join(SUBMISSIONS_DIR, row["filename"])
            if not os.path.exists(path):
                continue
            with open(path, encoding="utf-8", errors="replace") as tf:
                text = tf.read().strip()
            if not text:
                continue
            is_ai = 1 if row["dataset"] == "plagbench" else 0
            generator = row["task"] if is_ai else None
            items.append({
                "filename": row["filename"],
                "category": row["category"],
                "dataset": row["dataset"],
                "generator": generator,
                "is_ai_ground_truth": is_ai,
                "text": text,
            })
    return items


def main():
    print("=" * 60)
    print("EXPERIMENT 5: AI-Authorship Detection Accuracy")
    print("=" * 60)

    from app.services.ai_detector import detect

    items = load_all_items()
    n_human = sum(1 for i in items if i["is_ai_ground_truth"] == 0)
    n_ai = sum(1 for i in items if i["is_ai_ground_truth"] == 1)
    print(f"\nCorpus: {len(items)} items ({n_human} human-authored / Clough & Stevenson, "
          f"{n_ai} AI-generated / PlagBench)")

    results = []
    for i, item in enumerate(items):
        outcome = detect(item["text"])
        results.append({
            **{k: v for k, v in item.items() if k != "text"},
            "ai_score": outcome.score,
            "verdict": outcome.verdict,
        })
        if (i + 1) % 20 == 0 or (i + 1) == len(items):
            print(f"  {i + 1}/{len(items)} scored")

    y_true = np.array([r["is_ai_ground_truth"] for r in results])
    # Binary prediction: likely_ai counts as predicted-AI; likely_human and
    # uncertain both count as NOT predicted-AI. This matches how the system
    # is actually used -- only a likely_ai verdict is a claim, uncertain is
    # deliberately a non-claim, not a positive prediction.
    y_pred_strict = np.array([1 if r["verdict"] == "likely_ai" else 0 for r in results])
    m_strict = compute_metrics(y_true, y_pred_strict)

    # Also report threshold-at-0.5 (ignoring the uncertain band entirely) as
    # a second, more conventional framing for comparison.
    y_pred_threshold = np.array([1 if r["ai_score"] > 0.5 else 0 for r in results])
    m_threshold = compute_metrics(y_true, y_pred_threshold)

    n_uncertain = sum(1 for r in results if r["verdict"] == "uncertain")
    n_uncertain_human = sum(1 for r in results if r["verdict"] == "uncertain" and r["is_ai_ground_truth"] == 0)
    n_uncertain_ai = sum(1 for r in results if r["verdict"] == "uncertain" and r["is_ai_ground_truth"] == 1)

    # False-positive rate specifically on human-authored text -- this is the
    # literature-documented ESL/false-positive risk (docs/2026-07-01/
    # ai_detection_tier_1426.md), directly testable here since Clough &
    # Stevenson is a UK-university short-answer corpus with a realistic mix
    # of native and non-native English writers.
    human_items = [r for r in results if r["is_ai_ground_truth"] == 0]
    human_fp_strict = sum(1 for r in human_items if r["verdict"] == "likely_ai") / len(human_items)
    human_uncertain_rate = sum(1 for r in human_items if r["verdict"] == "uncertain") / len(human_items)

    # Per-generator recall among true-AI items.
    ai_items = [r for r in results if r["is_ai_ground_truth"] == 1]
    per_generator = {}
    for gen in sorted(set(r["generator"] for r in ai_items)):
        gen_items = [r for r in ai_items if r["generator"] == gen]
        caught = sum(1 for r in gen_items if r["verdict"] == "likely_ai")
        per_generator[gen] = {"n": len(gen_items), "caught_likely_ai": caught, "recall": caught / len(gen_items)}

    print("\n--- Binary metrics (verdict=likely_ai as positive prediction) ---")
    print(f"Precision: {m_strict.precision:.3f}  95% CI {m_strict.precision_ci}")
    print(f"Recall:    {m_strict.recall:.3f}  95% CI {m_strict.recall_ci}")
    print(f"F1:        {m_strict.f1:.3f}  95% CI {m_strict.f1_ci}")
    print(f"Confusion matrix (rows=true, cols=pred, [0,1]=[human,AI]):\n{m_strict.confusion}")

    print("\n--- Binary metrics (raw score > 0.5, ignoring uncertain band) ---")
    print(f"Precision: {m_threshold.precision:.3f}  Recall: {m_threshold.recall:.3f}  F1: {m_threshold.f1:.3f}")

    print(f"\n--- Uncertain-band behaviour ---")
    print(f"Total uncertain: {n_uncertain}/{len(results)} ({n_uncertain/len(results):.1%})")
    print(f"  of which human-authored: {n_uncertain_human}, AI-generated: {n_uncertain_ai}")

    print(f"\n--- False-positive risk on human-authored text (the literature-flagged concern) ---")
    print(f"Human items misclassified as likely_ai: {human_fp_strict:.1%}")
    print(f"Human items landing in uncertain band:   {human_uncertain_rate:.1%}")

    print(f"\n--- Recall by generator (among true-AI items) ---")
    for gen, stats in per_generator.items():
        print(f"  {gen}: {stats['caught_likely_ai']}/{stats['n']} caught as likely_ai ({stats['recall']:.1%})")

    output_path = os.path.join(os.path.dirname(__file__), "exp5_ai_detection_results.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump({
            "n_total": len(results),
            "n_human": n_human,
            "n_ai": n_ai,
            "strict_metrics": {
                "precision": m_strict.precision, "recall": m_strict.recall, "f1": m_strict.f1,
                "precision_ci": m_strict.precision_ci, "recall_ci": m_strict.recall_ci, "f1_ci": m_strict.f1_ci,
                "confusion": m_strict.confusion.tolist(),
            },
            "threshold_0.5_metrics": {
                "precision": m_threshold.precision, "recall": m_threshold.recall, "f1": m_threshold.f1,
            },
            "uncertain_rate_overall": n_uncertain / len(results),
            "human_false_positive_rate": human_fp_strict,
            "human_uncertain_rate": human_uncertain_rate,
            "per_generator_recall": per_generator,
            "per_item_results": results,
        }, f, indent=2)
    print(f"\nResults saved to {output_path}")


if __name__ == "__main__":
    main()
