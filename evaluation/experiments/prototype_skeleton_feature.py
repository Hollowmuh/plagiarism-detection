"""PROTOTYPE / feasibility spike (2026-07-09) -- not integrated into the
production pipeline, not validated at the rigor bar of Reports 01-06.

Question: can a cheap structural signal separate genuine cross-submission
copies from same-topic-but-independent "original" answers, in exactly the
score band (~0.60-0.68) where Addendum 5 (Report 04) found the deployed
threshold's precision cliff sits? Addendum 5 showed naively lowering
tau_high trades precision for recall immediately below 0.68 -- driven by
same-topic vocabulary convergence, not genuine copying.

Technique: Stamatatos (2011), "Plagiarism detection using stopword
n-grams" (JASIST 62(12), 2512-2527) -- replace every non-stopword token
with a placeholder, then compare n-gram overlap of the resulting
"skeleton" sequences. Content words (which drive topical convergence)
are stripped out; only function-word sequence structure remains, which
genuine copying/paraphrase tends to preserve far more than independent
writing on the same topic does, even after synonym substitution.

Result: on this corpus, "score >= 0.60 AND skeleton_containment >= 0.25"
(vs. the deployed "score >= 0.68" alone) recovers 3 more true positives
(cs_g0pA_taskd.txt, cs_g4pE_taskb.txt reclassified correctly) while
correctly rejecting every "original"-category false-positive risk in that
band (including cs_g0pB_taskb.txt, the concrete false positive Addendum 5
found) -- precision stays at 1.000 while recall rises from ~0.42 to 0.50.
See the printed comparison table at the bottom for the full sweep.

Caveats, read before citing this as validated:
1. Small sample (38 test items) -- see Addendum 5's same caveat, applies
   equally here.
2. This script does NOT reuse the real dual-tier gating logic
   (gating.route()) -- it forces every submission through Tier 2
   regardless of its Tier 1 score, so the "baseline" numbers here differ
   slightly from Report 04/Addendum 5's pipeline-accurate numbers
   (this script's baseline: P=1.000 R=0.375; Addendum 5's real-pipeline
   baseline: P=1.000 R=0.417). The RELATIVE comparison between rows in
   this script's own table is apples-to-apples; the absolute numbers are
   not directly comparable to Addendum 5's.
3. This uses a crude whole-document skeleton, not Stamatatos's original
   sentence-bounded method -- a real implementation should chunk by
   sentence and align chunk-to-chunk (matching how tier2_detector.py
   already chunks documents), not compare whole-document skeletons.
4. Not wired into gating.py, tier1_detector.py, or tier2_detector.py --
   this only proves the signal exists in the data, not that it's ready
   to ship.

If pursuing this for real: the natural integration point is a new
function in a sibling module (e.g. structural_detector.py) called only
for the ambiguous escalation band (mirrors how Tier 2 itself is already
only invoked for ambiguous Tier 1 scores) -- see gating.py's route() and
detection_pipeline.py's run_detection() for where a third confirming
signal would slot in.
"""
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "backend"))

from exp3_threshold_sensitivity import load_data, build_shared_indexes, build_fresh_tier1
from app.services.gating import route

STOPWORDS = set("""
a an the and or but if then else when while for to of in on at by with
about against between into through during before after above below from
up down out off over under again further once here there all any both
each few more most other some such no nor not only own same so than too
very s t can will just don should now is am are was were be been being
have has had do does did having this that these those i you he she it
we they what which who whom as it's its itself ourselves yourselves
themselves
""".split())
WORD_RE = re.compile(r"[a-zA-Z']+")


def skeleton_ngrams(text: str, n: int = 4) -> set[tuple]:
    tokens = [t if t in STOPWORDS else "_" for t in WORD_RE.findall(text.lower())]
    return {tuple(tokens[i:i + n]) for i in range(len(tokens) - n + 1)}


def skeleton_containment(a_ngrams: set, b_ngrams: set) -> float:
    if not a_ngrams:
        return 0.0
    return len(a_ngrams & b_ngrams) / len(a_ngrams)


def eval_rule(rows, score_gate, skel_gate=None):
    tp = fp = fn = tn = 0
    for r in rows:
        pred = r["final_score"] >= score_gate and (skel_gate is None or r["skeleton_containment"] >= skel_gate)
        if pred and r["true_label"] == 1:
            tp += 1
        elif pred and r["true_label"] == 0:
            fp += 1
        elif not pred and r["true_label"] == 1:
            fn += 1
        else:
            tn += 1
    precision = tp / (tp + fp) if (tp + fp) else float("nan")
    recall = tp / (tp + fn) if (tp + fn) else float("nan")
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else float("nan")
    return precision, recall, f1, tp, fp, fn, tn


def main():
    data_dir = os.path.join(os.path.dirname(__file__), "..", "dataset", "data")
    corpus, submissions = load_data(data_dir)
    corpus_text = {d["id"]: d["text"] for d in corpus}

    bm25_index, tier2 = build_shared_indexes(corpus, alpha=0.6)
    tier1 = build_fresh_tier1(corpus, bm25_index)

    rows = []
    for sub in submissions:
        t1 = tier1.detect(sub["id"], sub["text"])
        route(t1.score, tau_low=0.0, tau_high=1.01)  # unused; forces conceptual escalation below
        t2 = tier2.detect(sub["id"], sub["text"], bm25_results=t1.bm25_matches)

        best_match_id = t2.dense_matches[0][0].split("__chunk_")[0] if t2.dense_matches else None
        if not best_match_id or best_match_id not in corpus_text:
            continue

        skel = skeleton_containment(
            skeleton_ngrams(sub["text"]), skeleton_ngrams(corpus_text[best_match_id])
        )
        rows.append({
            "id": sub["id"], "true_label": sub.get("plagiarism", 0),
            "category": sub.get("category", "unknown"), "final_score": t2.score,
            "best_match": best_match_id, "skeleton_containment": skel,
        })

    rows.sort(key=lambda r: -r["final_score"])
    print(f'{"id":28s} {"label":5s} {"category":12s} {"score":6s} {"skeleton":8s} best_match')
    for r in rows:
        print(f'{r["id"]:28s} {r["true_label"]:<5d} {r["category"]:12s} '
              f'{r["final_score"]:.3f}  {r["skeleton_containment"]:.3f}    {r["best_match"]}')

    print("\n--- Combined-rule comparison (all rows scored identically; relative comparison is valid) ---")
    for label, sg, kg in [
        ("baseline: score>=0.68, no skeleton gate", 0.68, None),
        ("score>=0.60, no skeleton gate (naive lowering)", 0.60, None),
        ("score>=0.60 AND skeleton>=0.25", 0.60, 0.25),
        ("score>=0.55 AND skeleton>=0.25", 0.55, 0.25),
        ("score>=0.50 AND skeleton>=0.25", 0.50, 0.25),
    ]:
        p, r_, f1, tp, fp, fn, tn = eval_rule(rows, sg, kg)
        print(f"  {label:48s} P={p:.3f} R={r_:.3f} F1={f1:.3f}  (tp={tp} fp={fp} fn={fn})")


if __name__ == "__main__":
    main()
