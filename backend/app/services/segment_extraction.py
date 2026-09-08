"""Extracts the specific matched text span behind a Tier 2 detection.

Tier2Detector.detect() already knows which submission chunk and which
source chunk index produced the winning dense score (Tier2Result's
best_submission_chunk/best_source_chunk_index), but the submission chunk
is the only side with its text/offsets already in hand -- the source
chunk has to be recovered by re-chunking the source document's text the
same deterministic way it was chunked at index time.

This is deliberately a separate module from tier2_detector.py (scoring)
and structural_detector.py (which has no chunking dependency of its own)
-- both detection_pipeline.py's match-explanation field and its
chunk-anchored structural-confirmation call site need this same
extraction, so it lives where both can import it without coupling those
two otherwise-independent modules to each other.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.services.embedding_service import chunk_text, TextChunk


@dataclass
class MatchedSegmentData:
    """Field names mirror app.schemas.result.MatchedSegment exactly, so
    detection_tasks.py can serialize this with dataclasses.asdict() and
    have it validate directly against that Pydantic model."""
    source_text: str
    submitted_text: str
    source_offset: list[int]
    submitted_offset: list[int]


def extract_matched_segment(
    submission_chunk: TextChunk,
    source_text: str,
    source_chunk_index: int,
) -> MatchedSegmentData | None:
    """Recover the exact matched text/offsets for one Tier 2 match.

    submission_chunk already carries correct text/offsets from the
    original chunk_text(submission_text) call in Tier2Detector.detect() --
    no rework needed for that side. source_text is re-chunked here via the
    same deterministic chunk_text() used at index time (tier2_detector.py's
    index_chunks()); this reproduces identical chunk boundaries as long as
    source_text and CHUNK_SIZE/CHUNK_OVERLAP haven't changed since
    indexing. If they have (or source_chunk_index is otherwise out of
    range), returns None rather than raising -- a display feature failing
    open, not a pipeline correctness issue.
    """
    source_chunks = chunk_text(source_text)
    if source_chunk_index < 0 or source_chunk_index >= len(source_chunks):
        return None

    source_chunk = source_chunks[source_chunk_index]

    return MatchedSegmentData(
        source_text=source_chunk.text,
        submitted_text=submission_chunk.text,
        source_offset=[source_chunk.char_start, source_chunk.char_end],
        submitted_offset=[submission_chunk.char_start, submission_chunk.char_end],
    )
