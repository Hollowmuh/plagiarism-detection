"""Unit tests for the submission-deletion index-purge task.

Added 2026-07-04 after Report 07's audit found this task had zero test
coverage -- the only verification it had was one live manual test against
the deployed VM, run after the *first* attempt at this fix turned out to
be silently broken (it mutated the wrong process's copy of the indices).
These tests exercise the actual task body (via .run(), bypassing the
broker) against the real FingerprintIndex/BM25Index/FAISSIndex singletons,
the same objects app.services.detection_pipeline hands to the detection
services.

FAISS assertions added 2026-07-08 alongside the IndexIDMap2 migration --
purge_documents now also purges FAISS vectors (previously a documented
limitation; see docs/2026-07-08/faiss_vector_removal_1223.md).
"""

import numpy as np
import faiss

from app.services.detection_pipeline import get_fingerprint_index, get_bm25_index, get_faiss_index
from app.tasks.purge_tasks import purge_documents


def _vec(seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    v = rng.random(384).astype(np.float32)
    faiss.normalize_L2(v.reshape(1, -1))
    return v


class TestPurgeDocuments:
    def test_purge_removes_from_fingerprint_and_bm25_index(self):
        fp_index = get_fingerprint_index()
        bm25_index = get_bm25_index()

        doc_id = "test_purge_doc_1"
        text = (
            "This is a unique test document about photosynthesis and "
            "cellular respiration processes in eukaryotic organisms."
        )
        fp_index.submit(doc_id, text)
        bm25_index.add_document(doc_id, text)

        assert fp_index.get_fingerprint(doc_id) is not None
        assert bm25_index.get_text(doc_id) is not None

        purge_documents.run([doc_id])

        assert fp_index.get_fingerprint(doc_id) is None
        assert bm25_index.get_text(doc_id) is None

    def test_purge_removes_faiss_chunk_vectors(self):
        faiss_index = get_faiss_index()
        doc_id = "test_purge_faiss_doc"
        v = _vec(101)
        faiss_index.add_batch([f"{doc_id}__chunk_0", f"{doc_id}__chunk_1"], np.stack([v, _vec(102)]))
        assert any(r[0] == f"{doc_id}__chunk_0" for r in faiss_index.search(v, top_k=5))

        purge_documents.run([doc_id])

        assert not any(r[0].startswith(doc_id) for r in faiss_index.search(v, top_k=5))

    def test_purge_nonexistent_doc_id_is_a_noop(self):
        # Should not raise even if the doc_id was never indexed -- delete
        # requests can race with (or follow a failed) indexing task.
        purge_documents.run(["nonexistent_doc_id_xyz"])

    def test_purge_multiple_documents(self):
        fp_index = get_fingerprint_index()
        bm25_index = get_bm25_index()
        faiss_index = get_faiss_index()

        doc_ids = ["test_purge_multi_1", "test_purge_multi_2"]
        vecs = {}
        for doc_id in doc_ids:
            text = (
                f"Unique content for {doc_id} about quantum mechanics "
                "and particle physics interactions."
            )
            fp_index.submit(doc_id, text)
            bm25_index.add_document(doc_id, text)
            v = _vec(hash(doc_id) % 1000)
            vecs[doc_id] = v
            faiss_index.add(f"{doc_id}__chunk_0", v)

        purge_documents.run(doc_ids)

        for doc_id in doc_ids:
            assert fp_index.get_fingerprint(doc_id) is None
            assert bm25_index.get_text(doc_id) is None
            assert not any(
                r[0] == f"{doc_id}__chunk_0" for r in faiss_index.search(vecs[doc_id], top_k=5)
            )

    def test_purge_empty_list_is_a_noop(self):
        purge_documents.run([])
