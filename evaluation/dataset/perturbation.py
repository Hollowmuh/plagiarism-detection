"""Rule-based text perturbation for generating near-verbatim plagiarism samples.

Applies controlled modifications to source texts:
  - WordNet synonym replacement (10-20% of content words)
  - Active/passive voice conversion via dependency parsing
  - Punctuation and formatting changes
"""

import random
import re
from dataclasses import dataclass

import nltk
from nltk.corpus import wordnet

# Ensure required NLTK data is available.
for pkg in ("wordnet", "averaged_perceptron_tagger", "punkt_tab", "omw-1.4"):
    nltk.download(pkg, quiet=True)


@dataclass
class PerturbationResult:
    original: str
    perturbed: str
    changes: list[str]
    change_ratio: float


# ── Synonym replacement ──────────────────────────────────────────

def _get_synonym(word: str, pos_tag: str) -> str | None:
    """Get a WordNet synonym for a word given its POS tag."""
    wn_pos = {
        "NN": wordnet.NOUN, "NNS": wordnet.NOUN,
        "JJ": wordnet.ADJ, "JJR": wordnet.ADJ, "JJS": wordnet.ADJ,
        "RB": wordnet.ADV, "RBR": wordnet.ADV, "RBS": wordnet.ADV,
        "VB": wordnet.VERB, "VBD": wordnet.VERB, "VBG": wordnet.VERB,
        "VBN": wordnet.VERB, "VBP": wordnet.VERB, "VBZ": wordnet.VERB,
    }.get(pos_tag)

    if wn_pos is None:
        return None

    synsets = wordnet.synsets(word, pos=wn_pos)
    synonyms = set()
    for syn in synsets:
        for lemma in syn.lemmas():
            name = lemma.name().replace("_", " ")
            if name.lower() != word.lower():
                synonyms.add(name)

    return random.choice(list(synonyms)) if synonyms else None


def synonym_replace(text: str, ratio: float = 0.15, seed: int | None = None) -> tuple[str, list[str]]:
    """Replace a fraction of content words with WordNet synonyms.

    Args:
        text: Input text.
        ratio: Fraction of content words to replace (0.10-0.20).
        seed: Random seed for reproducibility.

    Returns:
        (modified_text, list of "old -> new" change descriptions).
    """
    if seed is not None:
        random.seed(seed)

    words = nltk.word_tokenize(text)
    tagged = nltk.pos_tag(words)

    # Identify content word indices (nouns, verbs, adjectives, adverbs).
    content_tags = {"NN", "NNS", "JJ", "JJR", "JJS", "RB", "RBR", "RBS",
                    "VB", "VBD", "VBG", "VBN", "VBP", "VBZ"}
    content_indices = [i for i, (_, tag) in enumerate(tagged) if tag in content_tags]

    n_replace = max(1, int(len(content_indices) * ratio))
    replace_indices = set(random.sample(content_indices, min(n_replace, len(content_indices))))

    changes: list[str] = []
    result = []

    for i, (word, tag) in enumerate(tagged):
        if i in replace_indices:
            syn = _get_synonym(word, tag)
            if syn:
                # Preserve capitalization.
                if word[0].isupper():
                    syn = syn.capitalize()
                result.append(syn)
                changes.append(f"'{word}' -> '{syn}'")
                continue
        result.append(word)

    # Reconstruct text preserving spacing (approximate).
    modified = " ".join(result)
    # Fix spacing before punctuation.
    modified = re.sub(r"\s+([.,;:!?])", r"\1", modified)

    return modified, changes


# ── Punctuation perturbation ─────────────────────────────────────

def punctuation_perturb(text: str, seed: int | None = None) -> tuple[str, list[str]]:
    """Apply random punctuation and formatting changes.

    Changes: semicolons <-> periods, double <-> single quotes,
    comma insertion/removal around conjunctions.
    """
    if seed is not None:
        random.seed(seed)

    changes: list[str] = []
    result = text

    # Semicolons to periods (50% chance each).
    semicolons = [(m.start(), m.end()) for m in re.finditer(r";", result)]
    for start, end in reversed(semicolons):
        if random.random() < 0.5:
            result = result[:start] + "." + result[end:]
            next_char_idx = end
            if next_char_idx < len(result) and result[next_char_idx] == " ":
                next_word_idx = next_char_idx + 1
                if next_word_idx < len(result):
                    result = result[:next_word_idx] + result[next_word_idx].upper() + result[next_word_idx + 1:]
            changes.append("semicolon -> period")

    # Swap quote styles.
    if random.random() < 0.5:
        if '\u201c' in result:
            result = result.replace('\u201c', '"').replace('\u201d', '"')
            changes.append("smart quotes -> straight quotes")
        elif '"' in result:
            result = result.replace('"', "'")
            changes.append('double quotes -> single quotes')

    # Oxford comma insertion/removal.
    pattern = r"(\w+),\s+(and|or)\s+"
    if random.random() < 0.4:
        result, n = re.subn(pattern, r"\1 \2 ", result)
        if n > 0:
            changes.append(f"removed {n} Oxford comma(s)")

    return result, changes


# ── Combined perturbation ────────────────────────────────────────

def perturb_text(
    text: str,
    synonym_ratio: float = 0.15,
    seed: int | None = None,
) -> PerturbationResult:
    """Apply all perturbation strategies to produce a near-verbatim variant.

    Args:
        text: Original source text.
        synonym_ratio: Fraction of content words to replace.
        seed: Random seed.

    Returns:
        PerturbationResult with original, perturbed text, and change log.
    """
    all_changes: list[str] = []

    # Step 1: Synonym replacement.
    result, syn_changes = synonym_replace(text, ratio=synonym_ratio, seed=seed)
    all_changes.extend(syn_changes)

    # Step 2: Punctuation changes.
    result, punct_changes = punctuation_perturb(result, seed=seed + 1 if seed else None)
    all_changes.extend(punct_changes)

    # Compute change ratio (word-level edit distance approximation).
    orig_words = text.lower().split()
    new_words = result.lower().split()
    max_len = max(len(orig_words), len(new_words))
    diffs = sum(1 for a, b in zip(orig_words, new_words) if a != b)
    diffs += abs(len(orig_words) - len(new_words))
    change_ratio = diffs / max_len if max_len > 0 else 0.0

    return PerturbationResult(
        original=text,
        perturbed=result,
        changes=all_changes,
        change_ratio=change_ratio,
    )
