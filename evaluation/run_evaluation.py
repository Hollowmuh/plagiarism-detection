"""Run the full evaluation pipeline against the dataset.

Processes all submissions through the detection pipeline (directly, no HTTP)
and compares predictions against ground truth labels.

Usage:
    python -m evaluation.run_evaluation [--split test] [--verbose]
"""

import csv
import os
import sys
import time
import argparse
from pathlib import Path

import numpy as np

# Add backend to path so we can import the services
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from app.services.detection_pipeline import (
    run_detection,
    index_document,
    get_fingerprint_index,
    get_bm25_index,
)
from app.services.text_extraction import extract_text_from_file
from evaluation.metrics import (
    compute_metrics,
    compute_cost,
    compute_latency,
    per_category_f1,
    format_report,
)

DATA_DIR = Path(__file__).parent / "dataset" / "data"
SOURCES_DIR = DATA_DIR / "sources"
SUBMISSIONS_DIR = DATA_DIR / "submissions"
SPLITS_DIR = DATA_DIR / "splits"


def load_split(split_name: str) -> list[dict]:
    """Load a split CSV (train/val/test) and return rows."""
    path = SPLITS_DIR / f"{split_name}.csv"
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _leaked_submission_basenames() -> set[str]:
    """Filenames in sources/ that are actually duplicates of real submissions
    (same content, bare filename with the cs_/pb_ split-prefix stripped)
    rather than genuine independent reference documents.

    Every Clough & Stevenson submission was, by a dataset-construction bug,
    also copied into sources/ under its bare filename -- e.g. submissions/
    cs_g0pC_taskc.txt and sources/g0pC_taskc.txt are the same content. This
    means every C&S submission trivially matches a duplicate of itself when
    "sources" is indexed as the evaluation corpus, which is what actually
    caused the original-category false positives previously misattributed
    to short-answer/source-article vocabulary overlap (see Report 00's
    addendum and Report 02's correction). PlagBench's sources use a distinct
    "pb_source_*" naming and are not affected.
    """
    leaked = set()
    for fname in os.listdir(SUBMISSIONS_DIR):
        for prefix in ("cs_", "pb_"):
            if fname.startswith(prefix):
                leaked.add(fname[len(prefix):])
                break
    return leaked


def load_source_texts() -> dict[str, str]:
    """Load all genuine source reference texts, excluding files that are
    actually duplicates of real submissions (see _leaked_submission_basenames)."""
    leaked = _leaked_submission_basenames()
    sources = {}
    for fname in os.listdir(SOURCES_DIR):
        if fname.endswith(".txt") and fname not in leaked:
            path = SOURCES_DIR / fname
            with open(path, encoding="utf-8", errors="replace") as f:
                sources[fname] = f.read()
    return sources


def index_sources(sources: dict[str, str], verbose: bool = False):
    """Index all source documents so the detection pipeline has a corpus.

    index_document() only populates BM25 + FAISS: it assumes the Winnowing
    fingerprint was already inserted as a side effect of tier1.detect() (true
    for real submissions, which always go through detect() before indexing --
    see backend/tests/test_pipeline.py's indexed_corpus fixture for the same
    workaround). Source documents here never go through detect(), so the
    fingerprint index must be populated explicitly or Winnowing silently sees
    an empty corpus for the entire run.
    """
    fp_idx = get_fingerprint_index()
    count = 0
    for doc_id, text in sources.items():
        if not text.strip():
            continue
        fp_idx.submit(doc_id, text)
        index_document(doc_id, text)
        count += 1
    if verbose:
        fp_idx = get_fingerprint_index()
        bm25_idx = get_bm25_index()
        print(f"Indexed {count} source documents")
        print(f"  Fingerprint index: {fp_idx.document_count} docs")
        print(f"  BM25 index: {bm25_idx.document_count} docs")


def run_on_split(
    split: list[dict],
    verbose: bool = False,
) -> dict:
    """Run detection on all submissions in a split.

    Returns dict with predictions, scores, latencies, escalation flags.
    """
    y_true = []
    y_pred = []
    scores = []
    latencies = []
    escalated = []
    categories = []
    details = []

    for i, row in enumerate(split):
        filename = row["filename"]
        category = row["category"]
        is_plag_true = int(row["is_plagiarised"])

        # Read submission text
        filepath = SUBMISSIONS_DIR / filename
        with open(filepath, encoding="utf-8", errors="replace") as f:
            text = f.read()

        if not text.strip():
            if verbose:
                print(f"  [{i+1}/{len(split)}] SKIP {filename} (empty)")
            continue

        # Run detection
        doc_id = f"eval_{filename}"
        start = time.perf_counter()
        result = run_detection(doc_id, text)
        elapsed_ms = (time.perf_counter() - start) * 1000

        # Collect results
        is_plag_pred = 1 if result.is_plagiarised else 0
        y_true.append(is_plag_true)
        y_pred.append(is_plag_pred)
        scores.append(result.final_score)
        latencies.append(elapsed_ms)
        escalated.append(result.escalated)
        categories.append(category)

        details.append({
            "filename": filename,
            "category": category,
            "true": is_plag_true,
            "pred": is_plag_pred,
            "score": result.final_score,
            "tier1": result.tier1_score,
            "tier2": result.tier2_score,
            "escalated": result.escalated,
            "gate": result.gate_decision,
            "latency_ms": elapsed_ms,
        })

        if verbose:
            status = "OK" if is_plag_true == is_plag_pred else "MISS"
            esc = " [T2]" if result.escalated else ""
            print(
                f"  [{i+1}/{len(split)}] {status} {filename:40s} "
                f"cat={category:14s} true={is_plag_true} pred={is_plag_pred} "
                f"score={result.final_score:.3f}{esc} ({elapsed_ms:.0f}ms)"
            )

    return {
        "y_true": np.array(y_true),
        "y_pred": np.array(y_pred),
        "scores": np.array(scores),
        "latencies": np.array(latencies),
        "escalated": np.array(escalated),
        "categories": np.array(categories),
        "details": details,
    }


def main():
    parser = argparse.ArgumentParser(description="Run plagiarism detection evaluation")
    parser.add_argument("--split", default="test", choices=["train", "val", "test", "all"])
    parser.add_argument("--verbose", "-v", action="store_true")
    parser.add_argument("--output", "-o", default=None, help="Output CSV path for detailed results")
    args = parser.parse_args()

    print("=" * 60)
    print("PLAGIARISM DETECTION — EVALUATION")
    print("=" * 60)

    # Load and index source corpus
    print("\n[1/3] Loading source corpus...")
    sources = load_source_texts()
    index_sources(sources, verbose=args.verbose)

    # Load split
    print(f"\n[2/3] Running detection on '{args.split}' split...")
    if args.split == "all":
        split = load_split("train") + load_split("val") + load_split("test")
    else:
        split = load_split(args.split)
    print(f"  {len(split)} submissions to process\n")

    # Run detection
    results = run_on_split(split, verbose=args.verbose)

    # Compute metrics
    print(f"\n[3/3] Computing metrics...")
    metrics = compute_metrics(results["y_true"], results["y_pred"])
    cost = compute_cost(results["escalated"])
    latency = compute_latency(results["latencies"])
    per_cat = per_category_f1(
        results["y_true"], results["y_pred"], results["categories"]
    )

    # Print report
    report = format_report(metrics, cost, latency, per_cat)
    print(f"\n{report}")

    # Save detailed results if requested
    if args.output:
        with open(args.output, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=results["details"][0].keys())
            writer.writeheader()
            writer.writerows(results["details"])
        print(f"\nDetailed results saved to: {args.output}")


if __name__ == "__main__":
    main()
