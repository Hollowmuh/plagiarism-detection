"""Indices must be rebuildable from stored documents after a worker restart."""

import pytest

from app.services import detection_pipeline as pipeline
from app.services.bm25_service import BM25Index
from app.services.faiss_service import FAISSIndex
from app.services.winnowing import FingerprintIndex

SOURCE = (
    "The tidal energy laboratory measures current speed with acoustic profilers "
    "mounted on the seabed. Engineers calibrate each profiler before the spring "
    "tide and store raw readings with a timestamp for later comparison. "
) * 3


@pytest.fixture
def fresh_pipeline(tmp_path, monkeypatch):
    """Simulate a just-restarted worker: every singleton empty, FAISS on disk in tmp."""
    monkeypatch.setattr(pipeline, "_fingerprint_index", FingerprintIndex())
    monkeypatch.setattr(pipeline, "_bm25_index", BM25Index())
    monkeypatch.setattr(pipeline, "_faiss_index", FAISSIndex(index_path=str(tmp_path / "i.faiss")))
    monkeypatch.setattr(pipeline, "_tier1", None)
    monkeypatch.setattr(pipeline, "_tier2", None)
    return pipeline


def test_copy_is_detected_after_restore(fresh_pipeline):
    assert fresh_pipeline.run_detection("before", SOURCE + " unused").is_plagiarised is False
    fresh_pipeline.get_fingerprint_index().remove("before")

    fresh_pipeline.restore_indices([("original", SOURCE)])
    result = fresh_pipeline.run_detection("copy", SOURCE)

    assert result.is_plagiarised is True
    assert result.best_match_id == "original"


def test_restore_is_idempotent_and_skips_empty(fresh_pipeline):
    docs = [("a", SOURCE), ("empty", "   ")]
    first = fresh_pipeline.restore_indices(docs)
    second = fresh_pipeline.restore_indices(docs)

    assert first["documents"] == 1
    assert first["faiss_vectors_added"] > 0
    assert second["faiss_vectors_added"] == 0
    assert fresh_pipeline.get_bm25_index().document_count == 1
