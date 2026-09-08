"""Confirms the exact JSONB write shape detection_tasks.py produces for
matched_segments validates against SimilarityPairResponse -- the same
explicit-kwarg construction path app/api/v1/submissions.py:219-227 uses
to read it back out.

No real database is involved -- there is no DB-backed test infrastructure
anywhere in this project (a known, documented gap for the whole Celery
task-orchestration layer; see evaluation/reports/07_full_pipeline_audit.md
and the coverage note in Report 06). detection_tasks.py's tier1_detect
itself is untestable without that infrastructure, which is out of scope
here. What actually matters for the "does this round-trip" question --
and what could realistically break silently (a field-name typo, wrong
nesting depth) -- is the Python-level shape contract between
dataclasses.asdict(MatchedSegmentData) and MatchedSegment/
SimilarityPairResponse, which this test exercises directly.
"""

import dataclasses

from app.schemas.result import MatchedSegment, SimilarityPairResponse
from app.services.segment_extraction import MatchedSegmentData


class TestMatchedSegmentsSchemaRoundtrip:
    def test_asdict_matches_matched_segment_schema(self):
        segment = MatchedSegmentData(
            source_text="the matched source passage",
            submitted_text="the matched submission passage",
            source_offset=[100, 150],
            submitted_offset=[20, 70],
        )

        # Exactly what detection_tasks.py's SimilarityPair(...) call does.
        matched_segments = [dataclasses.asdict(segment)]

        parsed = MatchedSegment(**matched_segments[0])
        assert parsed.source_text == segment.source_text
        assert parsed.submitted_text == segment.submitted_text
        assert parsed.source_offset == segment.source_offset
        assert parsed.submitted_offset == segment.submitted_offset

    def test_similarity_pair_response_accepts_the_write_shape(self):
        """Exercises the same explicit-kwarg construction path
        submissions.py:219-227 uses to read a SimilarityPair row back out
        as an API response."""
        import uuid

        segment = MatchedSegmentData(
            source_text="source passage",
            submitted_text="submitted passage",
            source_offset=[0, 15],
            submitted_offset=[0, 18],
        )
        matched_segments = [dataclasses.asdict(segment)]

        response = SimilarityPairResponse(
            source_document_id=uuid.uuid4(),
            similarity_score=0.75,
            match_type="tier2",
            matched_segments=matched_segments,
        )

        assert response.matched_segments is not None
        assert len(response.matched_segments) == 1
        assert response.matched_segments[0].source_text == "source passage"

    def test_none_matched_segments_still_valid(self):
        """The existing (pre-feature) no-segment case must keep working
        unchanged -- matched_segments=None is a valid, expected value, not
        just the new list-of-dicts shape."""
        import uuid

        response = SimilarityPairResponse(
            source_document_id=uuid.uuid4(),
            similarity_score=0.9,
            match_type="tier1",
            matched_segments=None,
        )
        assert response.matched_segments is None
