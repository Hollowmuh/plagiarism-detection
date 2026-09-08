"""Structural (stopword-skeleton n-gram) confirmation signal.

Motivation (2026-07-09, evaluation/reports/04_exp3_threshold_sensitivity.md
Addendums 4-5): lowering tau_high to recover missed peer-matching genuine
copies was found to immediately introduce false positives -- independently
-written, same-topic answers scoring almost as high as genuine copies
purely from shared technical vocabulary. This module implements Stamatatos
(2011) "Plagiarism detection using stopword n-grams": strip content words,
keep only the function-word/stopword sequence ("skeleton"), and compare
n-gram overlap of the skeletons. Genuine copying/paraphrase preserves
function-word sentence structure far more than independent same-topic
writing does, even after synonym substitution -- so it's a signal that
should be largely orthogonal to the topical-vocabulary-convergence
confound fooling the existing dense/sparse scores.

This is a CONFIRMATION signal only: it never runs on its own, only to
double-check a Tier 2 score that's suspicious (above a lower "verify"
bound) but not yet confident enough to auto-confirm (below tau_high).
"""

from __future__ import annotations

import re

from app.services.embedding_service import split_sentences

# A curated list of common English function words (articles, prepositions,
# conjunctions, pronouns, auxiliary/modal verbs). Deliberately excludes
# domain/content words -- the whole point is that this list stays fixed
# regardless of subject matter, so its n-gram "skeleton" reflects sentence
# structure, not topic.
STOPWORDS: frozenset[str] = frozenset("""
a about above after again against all am an and any are aren't as at be
because been before being below between both but by can can't cannot
could couldn't did didn't do does doesn't doing don't down during each
few for from further had hadn't has hasn't have haven't having he he'd
he'll he's her here here's hers herself him himself his how how's i i'd
i'll i'm i've if in into is isn't it it's its itself let's me more most
mustn't my myself no nor not of off on once only or other ought our ours
ourselves out over own same shan't she she'd she'll she's should
shouldn't so some such than that that's the their theirs them themselves
then there there's these they they'd they'll they're they've this those
through to too under until up very was wasn't we we'd we'll we're we've
were weren't what what's when when's where where's which while who who's
whom why why's with without won't would wouldn't you you'd you'll you're
you've your yours yourself yourselves
""".split())

_WORD_RE = re.compile(r"[a-zA-Z']+")
_PLACEHOLDER = "\0"  # cannot collide with any real token


def skeleton_tokens(text: str) -> list[str]:
    """Tokenize text, replacing every non-stopword token with a fixed
    placeholder. The resulting sequence reflects function-word structure
    only, independent of topic/content vocabulary."""
    tokens = _WORD_RE.findall(text.lower())
    return [t if t in STOPWORDS else _PLACEHOLDER for t in tokens]


def skeleton_ngrams(text: str, n: int = 4) -> set[tuple[str, ...]]:
    """N-grams of the skeleton token sequence."""
    tokens = skeleton_tokens(text)
    if len(tokens) < n:
        return set()
    return {tuple(tokens[i:i + n]) for i in range(len(tokens) - n + 1)}


def skeleton_containment(a: set[tuple[str, ...]], b: set[tuple[str, ...]]) -> float:
    """Asymmetric containment |a ∩ b| / |a| -- matches this codebase's
    established containment-over-Jaccard convention (winnowing.py's
    FingerprintIndex.submit() gate, tier1_detector.py's score selection),
    which avoids Jaccard collapsing toward zero when one side is much
    longer/shorter than the other."""
    if not a:
        return 0.0
    return len(a & b) / len(a)


MIN_SENTENCE_WORDS = 15


def sentence_skeleton_score(
    text_a: str, text_b: str, n: int = 4, min_sentence_words: int = MIN_SENTENCE_WORDS
) -> float:
    """Best-sentence-pair skeleton containment between two texts.

    Splits both texts into sentences (reusing embedding_service's
    split_sentences, the same splitter chunk_text() uses, so this stays
    single-source-of-truth for sentence boundaries) and returns the
    maximum containment across all (sentence_a, sentence_b) pairs --
    mirroring Tier2Detector's own "best chunk pair wins" aggregation for
    architectural consistency.

    Sentence-level (not chunk_text()'s coarser word-budget-level)
    granularity matches Stamatatos's original method: comparing whole
    documents or large multi-sentence chunks risks skeleton n-grams
    spanning unrelated sentence boundaries, diluting the signal.

    Sentences shorter than min_sentence_words are excluded from
    comparison on BOTH sides. Found empirically (2026-07-09, real-pipeline
    peer-matching validation, evaluation/experiments/exp4_structural_signal_
    validation.py): short, generic sentences (e.g. "Design technique, like
    divide-and-conquer method.") have so few n-grams that a single
    coincidental skeleton match against an unrelated short sentence
    elsewhere produces a spuriously high (sometimes literally 1.0)
    containment score with zero genuine relationship -- a classic
    denominator-too-small artifact. All four false positives this
    surfaced were driven by 5-14 word sentences; all three genuine
    recoveries came from 16-31 word sentences on both sides. 15 was
    chosen as a clean separator with margin on both sides of that gap,
    not tuned tighter than the evidence supports.
    """
    sents_a = [s for s in split_sentences(text_a) if len(s.split()) >= min_sentence_words]
    sents_b = [s for s in split_sentences(text_b) if len(s.split()) >= min_sentence_words]
    if not sents_a or not sents_b:
        return 0.0

    ngrams_b = [skeleton_ngrams(s, n) for s in sents_b]

    best = 0.0
    for sa in sents_a:
        ng_a = skeleton_ngrams(sa, n)
        if not ng_a:
            continue
        for ng_b in ngrams_b:
            score = skeleton_containment(ng_a, ng_b)
            if score > best:
                best = score
    return best


def maybe_structural_confirm(
    tier2_score: float,
    submission_text: str,
    match_text: str | None,
    tau_high: float,
    tau_verify: float,
    skeleton_threshold: float,
    ngram_n: int = 4,
) -> tuple[bool, float | None]:
    """Decide whether a Tier 2 score that fell short of tau_high should be
    reclassified as plagiarised based on structural (skeleton) evidence.

    Only runs the (relatively expensive, O(sentences_a * sentences_b))
    comparison when tier2_score is in the "verify band" [tau_verify,
    tau_high] -- clearly-low scores are left alone, and clearly-high
    scores already auto-confirmed by tier2_score > tau_high upstream.

    Returns (confirmed, skeleton_score). skeleton_score is None if the
    check didn't run at all (score outside the verify band, or match_text
    unavailable -- e.g. BM25Index's in-memory text cache was cleared by a
    worker restart since the match was indexed; this is a graceful skip,
    not an error, since Tier 1 already fully depends on and tolerates the
    same in-memory-only limitation today).
    """
    if match_text is None:
        return False, None
    if not (tau_verify <= tier2_score <= tau_high):
        return False, None

    score = sentence_skeleton_score(submission_text, match_text, n=ngram_n)
    return score >= skeleton_threshold, score
