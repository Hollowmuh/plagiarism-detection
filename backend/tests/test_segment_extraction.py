from app.services.embedding_service import chunk_text
from app.services.segment_extraction import extract_matched_segment, MatchedSegmentData


class TestExtractMatchedSegment:
    def test_correct_offsets(self):
        source_text = "First sentence about apples. Second sentence about oranges. Third sentence about grapes."
        submission_text = "A submission sentence about bananas that copies something."

        submission_chunks = chunk_text(submission_text)
        assert submission_chunks, "fixture text must produce at least one chunk"
        submission_chunk = submission_chunks[0]

        source_chunks = chunk_text(source_text)
        target_index = 0

        result = extract_matched_segment(submission_chunk, source_text, target_index)

        assert isinstance(result, MatchedSegmentData)
        assert result.source_text == source_chunks[target_index].text
        assert result.submitted_text == submission_chunk.text
        assert result.source_offset == [source_chunks[target_index].char_start, source_chunks[target_index].char_end]
        assert result.submitted_offset == [submission_chunk.char_start, submission_chunk.char_end]
        # Offsets must actually slice back to the same text in the originals.
        assert source_text[result.source_offset[0]:result.source_offset[1]] == result.source_text
        assert submission_text[result.submitted_offset[0]:result.submitted_offset[1]] == result.submitted_text

    def test_out_of_range_index_returns_none(self):
        source_text = "A short source document with only one chunk of text."
        submission_text = "A short submission with one chunk too."
        submission_chunk = chunk_text(submission_text)[0]

        result = extract_matched_segment(submission_chunk, source_text, source_chunk_index=99)

        assert result is None

    def test_negative_index_returns_none(self):
        source_text = "A short source document."
        submission_text = "A short submission."
        submission_chunk = chunk_text(submission_text)[0]

        result = extract_matched_segment(submission_chunk, source_text, source_chunk_index=-1)

        assert result is None

    def test_empty_source_text_returns_none(self):
        submission_text = "A short submission."
        submission_chunk = chunk_text(submission_text)[0]

        result = extract_matched_segment(submission_chunk, "", source_chunk_index=0)

        assert result is None

    def test_multi_chunk_source_picks_correct_chunk(self, monkeypatch):
        from app.config import settings
        monkeypatch.setattr(settings, "CHUNK_SIZE", 6)
        monkeypatch.setattr(settings, "CHUNK_OVERLAP", 0)

        source_text = (
            "This is the first chunk of source text about apples and oranges. "
            "This is the second chunk of source text about bananas and grapes. "
            "This is the third chunk of source text about mangoes and kiwis."
        )
        source_chunks = chunk_text(source_text)
        assert len(source_chunks) >= 3, "fixture must produce multiple chunks for this test to be meaningful"

        submission_text = "A submission chunk of text."
        submission_chunk = chunk_text(submission_text)[0]

        result = extract_matched_segment(submission_chunk, source_text, source_chunk_index=2)

        assert result.source_text == source_chunks[2].text
        assert result.source_offset == [source_chunks[2].char_start, source_chunks[2].char_end]
