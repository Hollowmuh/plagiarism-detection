"""Unit tests for the stopword-skeleton structural confirmation signal.

See evaluation/reports/04_exp3_threshold_sensitivity.md Addendums 4-6 for
the motivation: lowering tau_high to recover missed peer-matching genuine
copies was found to immediately introduce false positives from same-topic,
independently-written answers. This module is the confirmation signal
meant to distinguish the two without simply lowering tau_high globally.
"""

import os

from app.services.structural_detector import (
    maybe_structural_confirm,
    sentence_skeleton_score,
    skeleton_containment,
    skeleton_ngrams,
)

SUBMISSIONS_DIR = os.path.join(
    os.path.dirname(__file__), "..", "..", "evaluation", "dataset", "data", "submissions"
)


def load_submission(filename: str) -> str:
    path = os.path.join(SUBMISSIONS_DIR, filename)
    with open(path, encoding="utf-8", errors="replace") as f:
        return f.read()


class TestSkeletonNgrams:
    def test_identical_text_full_containment(self):
        text = "The quick brown fox jumps over the lazy dog in the park."
        a = skeleton_ngrams(text, n=3)
        b = skeleton_ngrams(text, n=3)
        assert skeleton_containment(a, b) == 1.0

    def test_completely_different_structure_low_containment(self):
        a = skeleton_ngrams("The cat sat on the mat by the door.", n=3)
        b = skeleton_ngrams("Photosynthesis converts light energy into chemical energy.", n=3)
        assert skeleton_containment(a, b) < 0.3

    def test_short_text_below_n_returns_empty(self):
        assert skeleton_ngrams("The cat.", n=10) == set()

    def test_empty_text_returns_empty(self):
        assert skeleton_ngrams("", n=4) == set()

    def test_content_word_substitution_preserves_skeleton(self):
        # Same function-word structure, different content words -- this is
        # exactly the "synonym-substitution paraphrase" case Stamatatos's
        # method is designed to catch that raw content-word overlap misses.
        a = skeleton_ngrams("The algorithm calculates the importance of each page.", n=3)
        b = skeleton_ngrams("The formula determines the significance of each node.", n=3)
        assert skeleton_containment(a, b) > 0.5


class TestSkeletonContainment:
    def test_empty_set_a_returns_zero(self):
        assert skeleton_containment(set(), {("a", "b")}) == 0.0

    def test_is_asymmetric(self):
        # a is a subset of b's n-grams but not vice versa -> containment(a,b) high, containment(b,a) lower
        a = {("x", "y", "z")}
        b = {("x", "y", "z"), ("p", "q", "r"), ("m", "n", "o")}
        assert skeleton_containment(a, b) == 1.0
        assert skeleton_containment(b, a) == 1 / 3


class TestSentenceSkeletonScore:
    def test_identical_texts_score_one(self):
        # Sentences must be >= MIN_SENTENCE_WORDS (15) to be compared at
        # all -- see sentence_skeleton_score's docstring for why short
        # sentences are excluded (spurious matches from too few n-grams).
        text = (
            "The algorithm calculates the relative importance of each page "
            "by counting the number and quality of links pointing to it "
            "from other pages in the network."
        )
        assert sentence_skeleton_score(text, text) == 1.0

    def test_sentences_shorter_than_minimum_are_excluded(self):
        short = "This is a short test sentence with few words."
        assert sentence_skeleton_score(short, short) == 0.0

    def test_empty_text_returns_zero(self):
        assert sentence_skeleton_score("", "Some real text here.") == 0.0
        assert sentence_skeleton_score("Some real text here.", "") == 0.0

    # ── Regression fixtures: real cases from Addendum 5's threshold retune ──
    # Confirmed by running the real pipeline (tier1.detect + tier2.detect)
    # against evaluation/dataset/data/ on 2026-07-09 -- these are the exact
    # (submission, best_match) pairs the fused Tier2 score actually picked,
    # not an assumed/plausible pairing.

    def test_known_false_positive_has_low_skeleton_score(self):
        # cs_g0pB_taskb.txt is genuinely non-plagiarised (category=original,
        # is_plagiarised=0) but scored t2=0.6788 against cs_g2pC_taskb.txt
        # purely from shared technical vocabulary -- the exact case that
        # motivated this feature (Addendum 5). 0.25 here is a conservative
        # bound well under the deployed STRUCTURAL_SKELETON_THRESHOLD=0.30
        # (Addendum 6 found 0.25 alone let through 4 same-task "canonical
        # definition" false positives -- see that addendum).
        sub = load_submission("cs_g0pB_taskb.txt")
        match = load_submission("cs_g2pC_taskb.txt")
        score = sentence_skeleton_score(sub, match)
        assert score < 0.25, f"known false positive scored {score:.3f}, expected < 0.25"

    def test_known_true_positive_paraphrased_has_high_skeleton_score(self):
        # cs_g0pA_taskd.txt is genuinely plagiarised (category=paraphrased)
        # but scored t2=0.6054, just under tau_high=0.68 -- a real miss
        # this feature is meant to recover.
        sub = load_submission("cs_g0pA_taskd.txt")
        match = load_submission("cs_g0pC_taskd.txt")
        score = sentence_skeleton_score(sub, match)
        assert score >= 0.25, f"known true positive scored {score:.3f}, expected >= 0.25"

    def test_known_true_positive_near_verbatim_has_high_skeleton_score(self):
        # cs_g4pE_taskb.txt (category=near_verbatim) scored t2=0.6508, also
        # just under tau_high.
        sub = load_submission("cs_g4pE_taskb.txt")
        match = load_submission("cs_g0pA_taskb.txt")
        score = sentence_skeleton_score(sub, match)
        assert score >= 0.25, f"known true positive scored {score:.3f}, expected >= 0.25"


class TestMaybeStructuralConfirm:
    def test_score_above_tau_high_does_not_run(self):
        confirmed, score = maybe_structural_confirm(
            tier2_score=0.90, submission_text="anything", match_text="anything",
            tau_high=0.68, tau_verify=0.60, skeleton_threshold=0.25,
        )
        assert confirmed is False
        assert score is None

    def test_score_below_tau_verify_does_not_run(self):
        confirmed, score = maybe_structural_confirm(
            tier2_score=0.40, submission_text="anything", match_text="anything",
            tau_high=0.68, tau_verify=0.60, skeleton_threshold=0.25,
        )
        assert confirmed is False
        assert score is None

    def test_match_text_none_gracefully_skips(self):
        # Simulates BM25Index's in-memory text cache missing the match
        # (e.g. a worker restart since the match was indexed) -- must not
        # raise, must not confirm.
        confirmed, score = maybe_structural_confirm(
            tier2_score=0.65, submission_text="anything", match_text=None,
            tau_high=0.68, tau_verify=0.60, skeleton_threshold=0.25,
        )
        assert confirmed is False
        assert score is None

    def test_in_band_high_skeleton_confirms(self):
        text = "The algorithm ranks pages by counting the links that point to them from other pages."
        confirmed, score = maybe_structural_confirm(
            tier2_score=0.65, submission_text=text, match_text=text,
            tau_high=0.68, tau_verify=0.60, skeleton_threshold=0.25,
        )
        assert confirmed is True
        assert score == 1.0

    def test_in_band_low_skeleton_does_not_confirm(self):
        confirmed, score = maybe_structural_confirm(
            tier2_score=0.65,
            submission_text="The cat sat quietly on the warm windowsill all afternoon.",
            match_text="Photosynthesis is the process plants use to convert light into energy.",
            tau_high=0.68, tau_verify=0.60, skeleton_threshold=0.25,
        )
        assert confirmed is False
        assert score is not None
        assert score < 0.25

    def test_boundary_at_tau_verify_runs(self):
        # tau_verify is inclusive per maybe_structural_confirm's docstring.
        text = "The formula computes the total based on the given inputs."
        confirmed, score = maybe_structural_confirm(
            tier2_score=0.60, submission_text=text, match_text=text,
            tau_high=0.68, tau_verify=0.60, skeleton_threshold=0.25,
        )
        assert score is not None

    def test_boundary_at_tau_high_runs(self):
        # tau_high is inclusive per maybe_structural_confirm's docstring
        # (the caller only invokes this when result.is_plagiarised is
        # already False, i.e. tier2_score <= tau_high given gating.route's
        # strict '>' -- so the boundary case is real and must be handled).
        text = "The formula computes the total based on the given inputs."
        confirmed, score = maybe_structural_confirm(
            tier2_score=0.68, submission_text=text, match_text=text,
            tau_high=0.68, tau_verify=0.60, skeleton_threshold=0.25,
        )
        assert score is not None
