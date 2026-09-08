"""Dataset construction pipeline for the plagiarism detection evaluation.

Generates a 200-submission dataset:
  - 40 verbatim (copy-paste from sources)
  - 40 near-verbatim (rule-based perturbation)
  - 60 paraphrased (GPT-4 + semantic verification)
  - 60 original (distinct, no plagiarism)

Usage:
    python generate_dataset.py --sources-dir data/sources --output-dir data
    python generate_dataset.py --step verbatim
    python generate_dataset.py --step split --seed 42
"""

import argparse
import csv
import json
import os
import random
from pathlib import Path

import numpy as np

from perturbation import perturb_text
from quality_control import run_quality_control, find_near_duplicates


CATEGORIES = {
    "verbatim": {"count": 40, "plagiarism": True},
    "near_verbatim": {"count": 40, "plagiarism": True},
    "paraphrased": {"count": 60, "plagiarism": True},
    "original": {"count": 60, "plagiarism": False},
}

SPLIT_RATIOS = {"train": 0.6, "validation": 0.2, "test": 0.2}


def load_sources(sources_dir: str) -> list[dict]:
    """Load source documents from a directory.

    Each file should be .txt with the text content.
    Filename (without extension) is used as the source ID.
    """
    sources = []
    for path in sorted(Path(sources_dir).glob("*.txt")):
        text = path.read_text(encoding="utf-8", errors="replace").strip()
        if text:
            sources.append({"id": path.stem, "text": text, "path": str(path)})
    print(f"Loaded {len(sources)} source documents")
    return sources


def extract_paragraphs(text: str, min_words: int = 50) -> list[str]:
    """Split text into paragraphs, filtering out short ones."""
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    return [p for p in paragraphs if len(p.split()) >= min_words]


def generate_verbatim(
    sources: list[dict],
    count: int = 40,
    seed: int = 42,
) -> list[dict]:
    """Generate verbatim plagiarism samples by inserting source paragraphs.

    Each sample contains 1-3 paragraphs copied directly from a source,
    inserted into otherwise filler context.
    """
    random.seed(seed)
    samples = []

    all_paragraphs = []
    for source in sources:
        for para in extract_paragraphs(source["text"]):
            all_paragraphs.append({"text": para, "source_id": source["id"]})

    if not all_paragraphs:
        print("WARNING: No paragraphs found in sources")
        return []

    for i in range(count):
        n_paras = random.randint(1, 3)
        selected = random.sample(all_paragraphs, min(n_paras, len(all_paragraphs)))
        plagiarised_text = "\n\n".join(p["text"] for p in selected)
        source_refs = list({p["source_id"] for p in selected})

        samples.append({
            "id": f"verbatim_{i:03d}",
            "text": plagiarised_text,
            "category": "verbatim",
            "plagiarism": True,
            "source_refs": source_refs,
        })

    print(f"Generated {len(samples)} verbatim samples")
    return samples


def generate_near_verbatim(
    verbatim_samples: list[dict],
    count: int = 40,
    synonym_ratio: float = 0.15,
    seed: int = 42,
) -> list[dict]:
    """Generate near-verbatim samples by perturbing verbatim copies."""
    samples = []

    for i, orig in enumerate(verbatim_samples[:count]):
        result = perturb_text(orig["text"], synonym_ratio=synonym_ratio, seed=seed + i)

        samples.append({
            "id": f"near_verbatim_{i:03d}",
            "text": result.perturbed,
            "category": "near_verbatim",
            "plagiarism": True,
            "source_refs": orig.get("source_refs", []),
            "change_ratio": result.change_ratio,
            "changes": result.changes,
        })

    print(f"Generated {len(samples)} near-verbatim samples")
    return samples


def generate_originals(
    originals_dir: str,
    count: int = 60,
) -> list[dict]:
    """Load original (non-plagiarised) submissions.

    These should be anonymised past course submissions or purpose-written texts.
    """
    samples = []
    paths = sorted(Path(originals_dir).glob("*.txt"))

    for i, path in enumerate(paths[:count]):
        text = path.read_text(encoding="utf-8", errors="replace").strip()
        if text:
            samples.append({
                "id": f"original_{i:03d}",
                "text": text,
                "category": "original",
                "plagiarism": False,
                "source_refs": [],
            })

    print(f"Loaded {len(samples)} original samples")
    return samples


def run_quality_checks(samples: list[dict]) -> list[dict]:
    """Run quality control on all samples, filtering failures."""
    passed = []
    failed = 0

    for sample in samples:
        qc = run_quality_control(sample["text"])
        if qc.passed:
            sample["word_count"] = qc.word_count
            passed.append(sample)
        else:
            print(f"  QC FAIL [{sample['id']}]: {qc.rejection_reason}")
            failed += 1

    print(f"QC: {len(passed)} passed, {failed} failed")
    return passed


def check_duplicates(samples: list[dict], max_hamming: int = 3) -> list[dict]:
    """Remove near-duplicates within the original category."""
    originals = [s for s in samples if s["category"] == "original"]
    others = [s for s in samples if s["category"] != "original"]

    duplicates = find_near_duplicates(
        [{"id": s["id"], "text": s["text"]} for s in originals],
        max_hamming=max_hamming,
    )

    if duplicates:
        remove_ids = {d[1] for d in duplicates}  # Remove the second of each pair.
        print(f"Removing {len(remove_ids)} near-duplicates: {remove_ids}")
        originals = [s for s in originals if s["id"] not in remove_ids]

    return others + originals


def create_splits(
    samples: list[dict],
    seed: int = 42,
) -> dict[str, list[dict]]:
    """Create stratified train/validation/test splits (60/20/20).

    Stratified by category to maintain class balance in each split.
    """
    random.seed(seed)

    by_category: dict[str, list[dict]] = {}
    for s in samples:
        by_category.setdefault(s["category"], []).append(s)

    splits: dict[str, list[dict]] = {"train": [], "validation": [], "test": []}

    for cat, cat_samples in by_category.items():
        random.shuffle(cat_samples)
        n = len(cat_samples)
        n_train = int(n * SPLIT_RATIOS["train"])
        n_val = int(n * SPLIT_RATIOS["validation"])

        splits["train"].extend(cat_samples[:n_train])
        splits["validation"].extend(cat_samples[n_train:n_train + n_val])
        splits["test"].extend(cat_samples[n_train + n_val:])

    for name, items in splits.items():
        print(f"  {name}: {len(items)} samples")

    return splits


def save_dataset(
    samples: list[dict],
    splits: dict[str, list[dict]],
    output_dir: str,
):
    """Save the dataset to disk.

    Outputs:
      - data/submissions/<id>.txt  (one file per sample)
      - data/labels.csv            (id, category, plagiarism, source_refs, word_count)
      - data/splits/<split>.csv    (id list per split)
    """
    submissions_dir = os.path.join(output_dir, "submissions")
    splits_dir = os.path.join(output_dir, "splits")
    os.makedirs(submissions_dir, exist_ok=True)
    os.makedirs(splits_dir, exist_ok=True)

    # Write submission files.
    for sample in samples:
        path = os.path.join(submissions_dir, f"{sample['id']}.txt")
        with open(path, "w", encoding="utf-8") as f:
            f.write(sample["text"])

    # Write labels.
    labels_path = os.path.join(output_dir, "labels.csv")
    with open(labels_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "id", "category", "plagiarism", "source_refs", "word_count",
        ])
        writer.writeheader()
        for s in samples:
            writer.writerow({
                "id": s["id"],
                "category": s["category"],
                "plagiarism": int(s["plagiarism"]),
                "source_refs": json.dumps(s.get("source_refs", [])),
                "word_count": s.get("word_count", len(s["text"].split())),
            })

    # Write split files.
    for split_name, split_samples in splits.items():
        path = os.path.join(splits_dir, f"{split_name}.csv")
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["id"])
            for s in split_samples:
                writer.writerow([s["id"]])

    print(f"Dataset saved to {output_dir}")
    print(f"  {len(samples)} submissions, {len(splits)} splits")


def main():
    parser = argparse.ArgumentParser(description="Generate plagiarism detection evaluation dataset")
    parser.add_argument("--sources-dir", default="data/sources", help="Directory of source documents")
    parser.add_argument("--originals-dir", default="data/sources", help="Directory of original submissions")
    parser.add_argument("--output-dir", default="data", help="Output directory")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    parser.add_argument("--step", choices=["all", "verbatim", "near_verbatim", "split"],
                        default="all", help="Run a specific step only")
    args = parser.parse_args()

    random.seed(args.seed)
    np.random.seed(args.seed)

    print("=== Plagiarism Detection Dataset Generator ===\n")

    # Load sources.
    sources = load_sources(args.sources_dir)

    if args.step in ("all", "verbatim"):
        print("\n--- Generating verbatim samples ---")
        verbatim = generate_verbatim(sources, count=40, seed=args.seed)

        print("\n--- Generating near-verbatim samples ---")
        near_verbatim = generate_near_verbatim(verbatim, count=40, seed=args.seed)
    else:
        verbatim, near_verbatim = [], []

    print("\n--- Loading original samples ---")
    originals = generate_originals(args.originals_dir, count=60)

    # NOTE: Paraphrased samples require GPT-4 API access.
    # Run paraphrase_generator.py separately, then place results in
    # data/submissions/paraphrased_*.txt before running the split step.
    paraphrased_dir = os.path.join(args.output_dir, "submissions")
    paraphrased = []
    if os.path.exists(paraphrased_dir):
        for path in sorted(Path(paraphrased_dir).glob("paraphrased_*.txt")):
            text = path.read_text(encoding="utf-8").strip()
            if text:
                paraphrased.append({
                    "id": path.stem,
                    "text": text,
                    "category": "paraphrased",
                    "plagiarism": True,
                    "source_refs": [],
                })
    print(f"Found {len(paraphrased)} paraphrased samples")

    all_samples = verbatim + near_verbatim + paraphrased + originals

    print(f"\n--- Quality control ({len(all_samples)} samples) ---")
    all_samples = run_quality_checks(all_samples)

    print("\n--- Duplicate detection ---")
    all_samples = check_duplicates(all_samples)

    print(f"\n--- Creating splits ({len(all_samples)} samples) ---")
    splits = create_splits(all_samples, seed=args.seed)

    print("\n--- Saving dataset ---")
    save_dataset(all_samples, splits, args.output_dir)

    # Summary.
    print("\n=== Summary ===")
    by_cat = {}
    for s in all_samples:
        by_cat.setdefault(s["category"], 0)
        by_cat[s["category"]] += 1
    for cat, count in sorted(by_cat.items()):
        print(f"  {cat}: {count}")
    print(f"  TOTAL: {len(all_samples)}")


if __name__ == "__main__":
    main()
