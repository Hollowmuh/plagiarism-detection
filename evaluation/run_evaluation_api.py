"""Run evaluation against the running API (E2E test).

Uses a batch approach: submit all test documents first, then poll for
all results with a generous timeout. This avoids timeouts with the
solo-pool Celery worker.

Usage:
    python evaluation/run_evaluation_api.py [--split test] [-v]
    python evaluation/run_evaluation_api.py --skip-sources --split test -v

Requires: the docker-compose dev stack running on localhost:8000
"""

import csv
import os
import sys
import time
import argparse
import requests
from pathlib import Path

DATA_DIR = Path(__file__).parent / "dataset" / "data"
SOURCES_DIR = DATA_DIR / "sources"
SUBMISSIONS_DIR = DATA_DIR / "submissions"
SPLITS_DIR = DATA_DIR / "splits"

API_URL = "http://localhost:8000/api/v1"
API_KEY = "dev-secret-key-change-in-production"
HEADERS = {"Authorization": f"Bearer {API_KEY}"}


def submit_file(filepath: Path, course_id="eval", assignment_id="eval", user_id="eval") -> str:
    """Submit a file and return submission_id."""
    with open(filepath, "rb") as f:
        resp = requests.post(
            f"{API_URL}/submissions/",
            headers=HEADERS,
            files={"file": (filepath.name, f, "text/plain")},
            data={"course_id": course_id, "assignment_id": assignment_id, "user_id": user_id},
        )
    resp.raise_for_status()
    return resp.json()["submission_id"]


def get_status(submission_id: str) -> dict:
    """Get submission status."""
    resp = requests.get(f"{API_URL}/submissions/{submission_id}/status", headers=HEADERS)
    return resp.json()


def get_results(submission_id: str) -> dict | None:
    """Get detection results for a completed submission."""
    resp = requests.get(f"{API_URL}/submissions/{submission_id}/results", headers=HEADERS)
    if resp.status_code == 200:
        return resp.json()
    return None


def wait_for_all(submission_ids: list[str], timeout: float = 600.0, poll_interval: float = 2.0, verbose: bool = False) -> dict[str, dict]:
    """Wait for all submissions to complete, polling periodically.

    Returns dict of submission_id -> status dict.
    """
    pending = set(submission_ids)
    completed = {}
    start = time.time()

    while pending and (time.time() - start) < timeout:
        still_pending = set()
        for sid in pending:
            try:
                data = get_status(sid)
                if data["status"] in ("completed", "failed"):
                    completed[sid] = data
                else:
                    still_pending.add(sid)
            except Exception:
                still_pending.add(sid)

        pending = still_pending
        if pending:
            if verbose:
                elapsed = time.time() - start
                print(f"    ... {len(completed)} done, {len(pending)} pending ({elapsed:.0f}s elapsed)")
            time.sleep(poll_interval)

    # Mark remaining as timeout
    for sid in pending:
        completed[sid] = {"status": "timeout"}

    return completed


def load_split(split_name: str) -> list[dict]:
    path = SPLITS_DIR / f"{split_name}.csv"
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def wait_for_queue_drain(max_wait: float = 300.0, verbose: bool = False):
    """Wait for Redis task queues to drain."""
    import subprocess
    start = time.time()
    while time.time() - start < max_wait:
        try:
            result = subprocess.run(
                ["docker", "compose", "-f", "docker-compose.dev.yml",
                 "exec", "-T", "redis", "redis-cli",
                 "llen", "extraction"],
                capture_output=True, text=True, cwd=str(DATA_DIR.parent.parent.parent)
            )
            extraction_len = int(result.stdout.strip()) if result.stdout.strip().isdigit() else 0

            result2 = subprocess.run(
                ["docker", "compose", "-f", "docker-compose.dev.yml",
                 "exec", "-T", "redis", "redis-cli",
                 "llen", "detection"],
                capture_output=True, text=True, cwd=str(DATA_DIR.parent.parent.parent)
            )
            detection_len = int(result2.stdout.strip()) if result2.stdout.strip().isdigit() else 0

            if extraction_len == 0 and detection_len == 0:
                return
            if verbose:
                print(f"    Queues: extraction={extraction_len} detection={detection_len}")
        except Exception:
            pass
        time.sleep(3)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--split", default="test", choices=["train", "val", "test", "all"])
    parser.add_argument("--verbose", "-v", action="store_true")
    parser.add_argument("--skip-sources", action="store_true", help="Skip source indexing (if already done)")
    parser.add_argument("--timeout", type=float, default=600.0, help="Max wait time for all results (seconds)")
    args = parser.parse_args()

    print("=" * 60)
    print("PLAGIARISM DETECTION — API EVALUATION (Batch Mode)")
    print("=" * 60)

    # Step 1: Submit source documents to build corpus
    if not args.skip_sources:
        print("\n[1/4] Submitting source documents to build corpus...")
        source_files = sorted(f for f in os.listdir(SOURCES_DIR) if f.endswith(".txt"))
        source_count = 0
        for i, fname in enumerate(source_files):
            filepath = SOURCES_DIR / fname
            if filepath.stat().st_size < 50:
                continue
            try:
                submit_file(filepath, course_id="corpus", assignment_id="source", user_id="system")
                source_count += 1
                if args.verbose and source_count % 20 == 0:
                    print(f"    Submitted {source_count}/{len(source_files)} sources...")
            except Exception as e:
                if args.verbose:
                    print(f"    SKIP {fname}: {e}")
                continue

        print(f"    Submitted {source_count} source documents.")
        print("    Waiting for corpus to be fully indexed...")
        wait_for_queue_drain(max_wait=300, verbose=args.verbose)
        # Extra buffer for the last indexing tasks
        time.sleep(5)
        print("    Corpus ready.")
    else:
        print("\n[1/4] Skipping source indexing (--skip-sources)")

    # Step 2: Submit ALL test documents (fast, don't wait for each)
    if args.split == "all":
        split = load_split("train") + load_split("val") + load_split("test")
    else:
        split = load_split(args.split)

    print(f"\n[2/4] Submitting {len(split)} test documents (split={args.split})...")

    submissions = []  # (submission_id, row_data, submit_time)
    for i, row in enumerate(split):
        filename = row["filename"]
        filepath = SUBMISSIONS_DIR / filename
        if not filepath.exists():
            if args.verbose:
                print(f"    SKIP {filename} (file not found)")
            continue
        try:
            sid = submit_file(filepath, course_id="eval", assignment_id=args.split, user_id=row["category"])
            submissions.append((sid, row, time.time()))
            if args.verbose and (i + 1) % 10 == 0:
                print(f"    Submitted {i+1}/{len(split)}")
        except Exception as e:
            if args.verbose:
                print(f"    ERROR submitting {filename}: {e}")
            continue

    print(f"    All {len(submissions)} submitted. Waiting for processing...")

    # Step 3: Wait for ALL to complete
    print(f"\n[3/4] Waiting for results (timeout={args.timeout:.0f}s)...")
    all_sids = [s[0] for s in submissions]
    statuses = wait_for_all(all_sids, timeout=args.timeout, poll_interval=3.0, verbose=args.verbose)

    # Collect results
    results = []
    for sid, row, submit_time in submissions:
        filename = row["filename"]
        category = row["category"]
        is_plag_true = int(row["is_plagiarised"])

        status = statuses.get(sid, {})
        if status.get("status") == "completed":
            det = get_results(sid)
            if det:
                is_plag_pred = 1 if det["is_plagiarised"] else 0
                score = det["final_score"]
                escalated = det.get("escalated", False)
                tier1 = det.get("tier1_score", 0.0)
                tier2 = det.get("tier2_score")
            else:
                is_plag_pred = 0
                score = 0.0
                escalated = False
                tier1 = 0.0
                tier2 = None
        elif status.get("status") == "failed":
            is_plag_pred = 0
            score = 0.0
            escalated = False
            tier1 = 0.0
            tier2 = None
            if args.verbose:
                print(f"    FAILED: {filename}")
            continue
        else:
            if args.verbose:
                print(f"    TIMEOUT: {filename}")
            continue

        results.append({
            "filename": filename,
            "category": category,
            "true": is_plag_true,
            "pred": is_plag_pred,
            "score": score,
            "tier1": tier1,
            "tier2": tier2,
            "escalated": escalated,
        })

    # Step 4: Compute metrics
    print(f"\n[4/4] Computing metrics ({len(results)} processed)...")

    if not results:
        print("No results to compute metrics on.")
        return

    y_true = [r["true"] for r in results]
    y_pred = [r["pred"] for r in results]
    categories = [r["category"] for r in results]
    escalated_flags = [r["escalated"] for r in results]

    # Basic metrics
    tp = sum(1 for t, p in zip(y_true, y_pred) if t == 1 and p == 1)
    fp = sum(1 for t, p in zip(y_true, y_pred) if t == 0 and p == 1)
    fn = sum(1 for t, p in zip(y_true, y_pred) if t == 1 and p == 0)
    tn = sum(1 for t, p in zip(y_true, y_pred) if t == 0 and p == 0)

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0
    accuracy = (tp + tn) / len(results) if results else 0

    # Per-category
    cat_metrics = {}
    for cat in set(categories):
        cat_true = [t for t, c in zip(y_true, categories) if c == cat]
        cat_pred = [p for p, c in zip(y_pred, categories) if c == cat]
        cat_tp = sum(1 for t, p in zip(cat_true, cat_pred) if t == 1 and p == 1)
        cat_fp = sum(1 for t, p in zip(cat_true, cat_pred) if t == 0 and p == 1)
        cat_fn = sum(1 for t, p in zip(cat_true, cat_pred) if t == 1 and p == 0)
        cat_tn = sum(1 for t, p in zip(cat_true, cat_pred) if t == 0 and p == 0)
        cat_p = cat_tp / (cat_tp + cat_fp) if (cat_tp + cat_fp) > 0 else 0
        cat_r = cat_tp / (cat_tp + cat_fn) if (cat_tp + cat_fn) > 0 else 0
        cat_f = 2 * cat_p * cat_r / (cat_p + cat_r) if (cat_p + cat_r) > 0 else 0
        cat_metrics[cat] = {
            "precision": cat_p, "recall": cat_r, "f1": cat_f,
            "n": len(cat_true), "tp": cat_tp, "fp": cat_fp, "fn": cat_fn, "tn": cat_tn,
        }

    # Cost
    n_escalated = sum(1 for e in escalated_flags if e)
    esc_rate = n_escalated / len(results) if results else 0

    # Print report
    print("\n" + "=" * 60)
    print("EVALUATION RESULTS")
    print("=" * 60)
    print(f"\nSamples: {len(results)}")
    print(f"\nOverall:")
    print(f"  Accuracy:  {accuracy:.3f}")
    print(f"  Precision: {precision:.3f}")
    print(f"  Recall:    {recall:.3f}")
    print(f"  F1-score:  {f1:.3f}")
    print(f"\nConfusion Matrix:")
    print(f"  TN={tn:3d}  FP={fp:3d}")
    print(f"  FN={fn:3d}  TP={tp:3d}")
    print(f"\nPer-category:")
    for cat in ["verbatim", "near_verbatim", "paraphrased", "original"]:
        if cat in cat_metrics:
            m = cat_metrics[cat]
            print(f"  {cat:14s}: P={m['precision']:.3f} R={m['recall']:.3f} F1={m['f1']:.3f} (n={m['n']}, TP={m['tp']} FP={m['fp']} FN={m['fn']} TN={m['tn']})")
    print(f"\nTier Resolution:")
    print(f"  Escalation rate: {esc_rate:.1%} ({n_escalated}/{len(results)})")
    print(f"  Tier 1 resolved: {(1-esc_rate)*100:.1f}%")
    print(f"  Cost savings vs cloud-only: {(1-esc_rate)*100:.1f}%")

    # Score distribution
    plag_scores = [r["score"] for r in results if r["true"] == 1]
    orig_scores = [r["score"] for r in results if r["true"] == 0]
    if plag_scores:
        print(f"\nScore distribution:")
        print(f"  Plagiarised (n={len(plag_scores)}): mean={sum(plag_scores)/len(plag_scores):.3f} min={min(plag_scores):.3f} max={max(plag_scores):.3f}")
    if orig_scores:
        print(f"  Original    (n={len(orig_scores)}): mean={sum(orig_scores)/len(orig_scores):.3f} min={min(orig_scores):.3f} max={max(orig_scores):.3f}")

    print("=" * 60)

    # Save results CSV
    output_path = Path(__file__).parent / "results.csv"
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=results[0].keys())
        writer.writeheader()
        writer.writerows(results)
    print(f"\nDetailed results saved to: {output_path}")

    # Print per-submission details if verbose
    if args.verbose:
        print(f"\n{'='*80}")
        print("DETAILED RESULTS")
        print(f"{'='*80}")
        for r in results:
            correct = "OK  " if r["true"] == r["pred"] else "MISS"
            esc = " [T2]" if r["escalated"] else "     "
            print(
                f"  {correct} {r['filename']:40s} cat={r['category']:14s} "
                f"true={r['true']} pred={r['pred']} score={r['score']:.3f}"
                f" t1={r['tier1']:.3f}{esc}"
            )


if __name__ == "__main__":
    main()
