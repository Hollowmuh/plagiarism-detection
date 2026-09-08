"""GPT-4 paraphrase generation for constructing paraphrased plagiarism samples.

Uses OpenAI Batch API for cost efficiency (50% discount).
Includes semantic fidelity verification via embedding cosine similarity.
"""

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np

PARAPHRASE_PROMPT = """Paraphrase the following text. Preserve the full meaning but use
different vocabulary, sentence structures, and phrasing. Do not add or remove information.

TEXT:
{text}

PARAPHRASED VERSION:"""


@dataclass
class ParaphraseResult:
    original: str
    paraphrased: str
    cosine_similarity: float
    accepted: bool
    rejection_reason: str | None = None


def generate_paraphrase_batch_file(
    texts: list[dict],
    output_path: str,
    model: str = "gpt-4o",
) -> str:
    """Create a JSONL batch file for OpenAI Batch API.

    Args:
        texts: List of {"id": str, "text": str} dicts.
        output_path: Path to write the JSONL file.
        model: OpenAI model to use.

    Returns:
        Path to the created batch file.
    """
    with open(output_path, "w", encoding="utf-8") as f:
        for item in texts:
            request = {
                "custom_id": item["id"],
                "method": "POST",
                "url": "/v1/chat/completions",
                "body": {
                    "model": model,
                    "messages": [
                        {"role": "system", "content": "You are a skilled academic writer."},
                        {"role": "user", "content": PARAPHRASE_PROMPT.format(text=item["text"])},
                    ],
                    "temperature": 0.7,
                    "max_tokens": 2048,
                },
            }
            f.write(json.dumps(request) + "\n")

    return output_path


def submit_batch(batch_file_path: str) -> str:
    """Submit a batch file to OpenAI Batch API.

    Returns the batch ID for polling.
    Requires OPENAI_API_KEY environment variable.
    """
    from openai import OpenAI

    client = OpenAI()

    with open(batch_file_path, "rb") as f:
        uploaded = client.files.create(file=f, purpose="batch")

    batch = client.batches.create(
        input_file_id=uploaded.id,
        endpoint="/v1/chat/completions",
        completion_window="24h",
    )

    print(f"Batch submitted: {batch.id}")
    return batch.id


def poll_batch(batch_id: str, poll_interval: int = 60) -> list[dict]:
    """Poll for batch completion and return results.

    Args:
        batch_id: The batch ID from submit_batch().
        poll_interval: Seconds between polls.

    Returns:
        List of {"custom_id": str, "content": str} results.
    """
    from openai import OpenAI

    client = OpenAI()

    while True:
        batch = client.batches.retrieve(batch_id)
        print(f"  Status: {batch.status} ({batch.request_counts})")

        if batch.status == "completed":
            break
        elif batch.status in ("failed", "cancelled", "expired"):
            raise RuntimeError(f"Batch {batch_id} ended with status: {batch.status}")

        time.sleep(poll_interval)

    # Download results.
    content = client.files.content(batch.output_file_id)
    results = []
    for line in content.text.strip().split("\n"):
        data = json.loads(line)
        custom_id = data["custom_id"]
        text = data["response"]["body"]["choices"][0]["message"]["content"]
        results.append({"custom_id": custom_id, "content": text.strip()})

    return results


def verify_semantic_fidelity(
    original: str,
    paraphrased: str,
    threshold: float = 0.76,
) -> tuple[float, bool]:
    """Verify paraphrase preserves meaning via embedding cosine similarity.

    Uses all-MiniLM-L6-v2 (same model as the detection pipeline).

    Args:
        original: Source text.
        paraphrased: Generated paraphrase.
        threshold: Minimum cosine similarity (P-SP threshold from plan).

    Returns:
        (cosine_similarity, accepted).
    """
    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer("all-MiniLM-L6-v2")
    embeddings = model.encode([original, paraphrased], normalize_embeddings=True)
    cosine_sim = float(np.dot(embeddings[0], embeddings[1]))

    return cosine_sim, cosine_sim >= threshold


def verify_batch(
    originals: list[dict],
    paraphrases: list[dict],
    threshold: float = 0.76,
) -> list[ParaphraseResult]:
    """Verify semantic fidelity for a batch of paraphrases.

    Args:
        originals: List of {"id": str, "text": str}.
        paraphrases: List of {"custom_id": str, "content": str}.
        threshold: Minimum cosine similarity.

    Returns:
        List of ParaphraseResult with acceptance status.
    """
    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer("all-MiniLM-L6-v2")

    orig_map = {item["id"]: item["text"] for item in originals}
    results = []

    for para in paraphrases:
        orig_text = orig_map.get(para["custom_id"], "")
        para_text = para["content"]

        if not orig_text or not para_text:
            results.append(ParaphraseResult(
                original=orig_text,
                paraphrased=para_text,
                cosine_similarity=0.0,
                accepted=False,
                rejection_reason="empty text",
            ))
            continue

        embs = model.encode([orig_text, para_text], normalize_embeddings=True)
        cosine_sim = float(np.dot(embs[0], embs[1]))

        accepted = cosine_sim >= threshold
        reason = None if accepted else f"cosine {cosine_sim:.3f} < {threshold}"

        results.append(ParaphraseResult(
            original=orig_text,
            paraphrased=para_text,
            cosine_similarity=cosine_sim,
            accepted=accepted,
            rejection_reason=reason,
        ))

    return results
