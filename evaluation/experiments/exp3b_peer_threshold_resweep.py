"""Experiment 3b: Threshold re-sweep for cross-submission (peer) matching.

Motivation (2026-07-09): Report 04's Addendum 4 found the deployed
tau_high=0.68/0.70 (tuned for source-matching, Reports 01-03) is
miscalibrated for peer-matching specifically -- 4 of 12 genuinely
matchable test-positives scored 0.600-0.651, just under tau_high=0.70,
while precision was perfect (1.000) at every tau_high tested so far
(0.70/0.75/0.80). This sweep extends tau_high DOWN, into and below that
0.60-0.65 band, to find where peer-matching recall/precision actually
trades off, and whether a peer-matching-specific threshold pair would be
safe to use.

Same corpus/methodology as exp3_threshold_sensitivity.py (train-split
submissions as corpus, test-split submissions as queries) -- deliberately
NOT modifying that committed script in place, per the exp1b_threshold_
resweep.py precedent for retuning exercises.
"""

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "backend"))

import numpy as np

from exp3_threshold_sensitivity import load_data, build_shared_indexes, build_fresh_tier1, run_with_thresholds
from metrics import compute_metrics


def main():
    print("=" * 60)
    print("EXPERIMENT 3b: Peer-matching threshold re-sweep")
    print("=" * 60)

    data_dir = os.path.join(os.path.dirname(__file__), "..", "dataset", "data")
    corpus, submissions = load_data(data_dir)
    print(f"Corpus (train-split submissions): {len(corpus)}")
    print(f"Test submissions: {len(submissions)}")

    print("\nBuilding shared BM25/FAISS indexes (built once, safe to reuse)...")
    bm25_index, tier2 = build_shared_indexes(corpus, alpha=0.6)

    y_true = np.array([s["plagiarism"] for s in submissions])

    # Wider grid than the original 3x3, extending tau_high DOWN into and
    # below the 0.60-0.65 band where Addendum 4 found real missed matches.
    tau_lows = [0.20, 0.25, 0.30]
    tau_highs = [0.50, 0.55, 0.58, 0.60, 0.62, 0.65, 0.68, 0.70, 0.75, 0.80]

    all_results = {}
    best = None

    print("\n--- Threshold sweep ---")
    for tl in tau_lows:
        for th in tau_highs:
            if th <= tl:
                continue
            tier1 = build_fresh_tier1(corpus, bm25_index)
            results = run_with_thresholds(tier1, tier2, submissions, tl, th)
            y_pred = np.array([r["predicted"] for r in results])
            escalated = np.array([r["escalated"] for r in results])

            m = compute_metrics(y_true, y_pred)
            rho = float(np.mean(escalated))

            key = f"tl={tl:.2f}_th={th:.2f}"
            all_results[key] = {
                "f1": m.f1, "precision": m.precision, "recall": m.recall,
                "escalation_rate": rho,
            }
            print(f"  tau_low={tl:.2f}, tau_high={th:.2f}: "
                  f"F1={m.f1:.3f} P={m.precision:.3f} R={m.recall:.3f} rho={rho:.2%}")

            # "Best": maximize F1 subject to precision staying perfect
            # (1.000) -- i.e. don't trade away the "never a false accusation"
            # property this corpus has shown at every tau_high tested so far.
            if m.precision >= 1.0:
                if best is None or m.f1 > best["f1"] or (
                    m.f1 == best["f1"] and rho < best["escalation_rate"]
                ):
                    best = {"tau_low": tl, "tau_high": th, "f1": m.f1,
                             "precision": m.precision, "recall": m.recall,
                             "escalation_rate": rho}

    print("\n--- Current deployed operating point (tau_low=0.30, tau_high=0.68) ---")
    current = all_results.get("tl=0.30_th=0.68")
    print(json.dumps(current, indent=2))

    print("\n--- Best for peer-matching (subject to precision staying perfect) ---")
    print(json.dumps(best, indent=2))

    output_path = os.path.join(os.path.dirname(__file__), "exp3b_resweep_results.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump({
            "current_operating_point": current,
            "best_peer_matching": best,
            "all_configurations": all_results,
        }, f, indent=2)
    print(f"\nResults saved to {output_path}")


if __name__ == "__main__":
    main()
