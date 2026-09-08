"""Unit tests for FAISSIndex, in particular its vector-removal support
(remove_document()) and the legacy-format (pre-IndexIDMap2) migration path.

Added 2026-07-08 alongside the IndexIDMap2 migration -- previously there
was no removal support at all, and no dedicated test file for this class.
Every scenario here mirrors a real behavior confirmed empirically against
the actual faiss-cpu package before being written into faiss_service.py
(see docs/2026-07-08/faiss_vector_removal_1223.md); the trickiest ones
(IndexIDMap2 requiring an empty index on construction, IVF-family removal
being unsafe) were only discovered by running real FAISS calls, not by
reading docs, so these tests pin that empirically-verified behavior.

Uses isolated per-test index files (pytest's tmp_path) rather than the
shared conftest.py FAISS_INDEX_PATH, since these tests specifically need
independent save/reload cycles.
"""

import json

import faiss
import numpy as np
import pytest

from app.services.faiss_service import FAISSIndex

DIM = 8


def _vec(seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    v = rng.random(DIM).astype(np.float32)
    faiss.normalize_L2(v.reshape(1, -1))
    return v


class TestAddAndSearch:
    def test_add_and_search_roundtrip(self, tmp_path):
        idx = FAISSIndex(dimension=DIM, index_path=str(tmp_path / "idx.faiss"))
        v = _vec(1)
        idx.add("doc1", v)

        results = idx.search(v, top_k=5)
        assert results[0][0] == "doc1"
        assert results[0][1] == pytest.approx(1.0, abs=1e-4)

    def test_add_batch_skips_existing_doc_ids(self, tmp_path):
        idx = FAISSIndex(dimension=DIM, index_path=str(tmp_path / "idx.faiss"))
        vecs = np.stack([_vec(1), _vec(2)])
        idx.add_batch(["doc1", "doc2"], vecs)
        assert idx.total_vectors == 2

        idx.add_batch(["doc1", "doc3"], np.stack([_vec(1), _vec(3)]))
        assert idx.total_vectors == 3  # doc1 skipped, only doc3 added


class TestRemoveDocument:
    def test_remove_exact_doc_id(self, tmp_path):
        idx = FAISSIndex(dimension=DIM, index_path=str(tmp_path / "idx.faiss"))
        idx.add("doc1", _vec(1))
        assert idx.total_vectors == 1

        removed = idx.remove_document("doc1")
        assert removed == 1
        assert idx.total_vectors == 0

    def test_remove_removes_all_chunks(self, tmp_path):
        idx = FAISSIndex(dimension=DIM, index_path=str(tmp_path / "idx.faiss"))
        idx.add_batch(
            ["doc1__chunk_0", "doc1__chunk_1", "doc1__chunk_2"],
            np.stack([_vec(1), _vec(2), _vec(3)]),
        )
        assert idx.total_vectors == 3

        removed = idx.remove_document("doc1")
        assert removed == 3
        assert idx.total_vectors == 0

    def test_remove_leaves_other_docs_with_shared_prefix_intact(self, tmp_path):
        idx = FAISSIndex(dimension=DIM, index_path=str(tmp_path / "idx.faiss"))
        idx.add_batch(
            ["a__chunk_0", "a2__chunk_0"],
            np.stack([_vec(1), _vec(2)]),
        )

        removed = idx.remove_document("a")
        assert removed == 1
        assert idx.total_vectors == 1
        assert idx.search(_vec(2), top_k=5)[0][0] == "a2__chunk_0"

    def test_remove_nonexistent_doc_id_is_noop(self, tmp_path):
        idx = FAISSIndex(dimension=DIM, index_path=str(tmp_path / "idx.faiss"))
        assert idx.remove_document("never_indexed") == 0

    def test_removed_doc_id_never_returned_as_dangling_reference(self, tmp_path):
        """The actual bug this change fixes: search() must never surface a
        doc_id that's been removed, even when queried with its own vector."""
        idx = FAISSIndex(dimension=DIM, index_path=str(tmp_path / "idx.faiss"))
        v = _vec(1)
        idx.add("doc1", v)
        assert any(r[0] == "doc1" for r in idx.search(v, top_k=5))

        idx.remove_document("doc1")

        assert not any(r[0] == "doc1" for r in idx.search(v, top_k=5))


class TestPersistence:
    def test_save_and_reload_preserves_ids_and_removals(self, tmp_path):
        path = str(tmp_path / "idx.faiss")
        idx = FAISSIndex(dimension=DIM, index_path=path)
        idx.add_batch(["doc1", "doc2", "doc3"], np.stack([_vec(1), _vec(2), _vec(3)]))
        idx.remove_document("doc2")
        idx.save()

        reloaded = FAISSIndex(dimension=DIM, index_path=path)
        assert reloaded.total_vectors == 2
        assert reloaded.search(_vec(1), top_k=5)[0][0] == "doc1"
        assert not any(r[0] == "doc2" for r in reloaded.search(_vec(2), top_k=5))

    def test_next_id_persisted_no_collision_after_reload_and_remove(self, tmp_path):
        path = str(tmp_path / "idx.faiss")
        idx = FAISSIndex(dimension=DIM, index_path=path)
        idx.add_batch(["doc1", "doc2", "doc3"], np.stack([_vec(1), _vec(2), _vec(3)]))
        idx.remove_document("doc2")  # creates a gap
        idx.save()

        reloaded = FAISSIndex(dimension=DIM, index_path=path)
        prior_max_fid = max(reloaded._id_map.keys())
        reloaded.add("doc4", _vec(4))
        new_fid = reloaded._doc_map["doc4"]

        assert new_fid > prior_max_fid  # never reuses the gap left by doc2


class TestLegacyMigration:
    def _write_legacy_flat_index(self, tmp_path, n=3):
        path = str(tmp_path / "idx.faiss")
        legacy = faiss.IndexFlatIP(DIM)
        vecs = np.stack([_vec(i) for i in range(n)])
        legacy.add(vecs)
        faiss.write_index(legacy, path)

        id_map = {i: f"doc{i}" for i in range(n)}
        doc_map = {f"doc{i}": i for i in range(n)}
        with open(path + ".meta.json", "w", encoding="utf-8") as f:
            json.dump({"id_map": id_map, "doc_map": doc_map}, f)  # no next_id: pre-migration format

        return path, vecs

    def test_legacy_flat_index_migrates_and_becomes_removable(self, tmp_path):
        path, vecs = self._write_legacy_flat_index(tmp_path, n=3)

        idx = FAISSIndex(dimension=DIM, index_path=path)
        assert isinstance(idx._index, faiss.IndexIDMap2)
        assert idx.total_vectors == 3
        assert idx.search(vecs[1], top_k=5)[0][0] == "doc1"

        removed = idx.remove_document("doc1")
        assert removed == 1
        assert idx.total_vectors == 2

    def test_migration_is_memory_only_does_not_write_until_next_save(self, tmp_path):
        path, _ = self._write_legacy_flat_index(tmp_path, n=2)
        before_bytes = open(path, "rb").read()

        idx = FAISSIndex(dimension=DIM, index_path=path)
        assert isinstance(idx._index, faiss.IndexIDMap2)  # migrated in memory
        after_construct_bytes = open(path, "rb").read()
        assert before_bytes == after_construct_bytes  # but not saved yet

        idx.save()
        reloaded_raw = faiss.read_index(path)
        assert isinstance(reloaded_raw, faiss.IndexIDMap2)

    def test_migration_skipped_on_id_map_mismatch(self, tmp_path, caplog):
        path, _ = self._write_legacy_flat_index(tmp_path, n=3)
        # Corrupt the meta.json to simulate a prior non-atomic-save crash:
        # fewer id_map entries than vectors actually in the index.
        with open(path + ".meta.json", "w", encoding="utf-8") as f:
            json.dump({"id_map": {"0": "doc0"}, "doc_map": {"doc0": 0}}, f)

        idx = FAISSIndex(dimension=DIM, index_path=path)
        assert not isinstance(idx._index, faiss.IndexIDMap2)
        assert idx.remove_document("doc0") == 0  # refuses rather than risk a bad mapping


class TestIVFPQMigrationAndSafety:
    def _write_legacy_ivfpq_index(self, tmp_path, n=5):
        path = str(tmp_path / "idx.faiss")
        rng = np.random.default_rng(42)
        quantizer = faiss.IndexFlatIP(DIM)
        legacy = faiss.IndexIVFPQ(quantizer, DIM, 2, 4, 8)
        train_data = rng.random((10000, DIM)).astype(np.float32)
        faiss.normalize_L2(train_data)
        legacy.train(train_data)

        vecs = np.stack([_vec(i) for i in range(n)])
        legacy.add(vecs)
        faiss.write_index(legacy, path)

        id_map = {i: f"doc{i}" for i in range(n)}
        doc_map = {f"doc{i}": i for i in range(n)}
        with open(path + ".meta.json", "w", encoding="utf-8") as f:
            json.dump({"id_map": id_map, "doc_map": doc_map}, f)

        return path, vecs

    @pytest.mark.slow
    def test_legacy_ivfpq_migrates_and_search_works(self, tmp_path):
        path, vecs = self._write_legacy_ivfpq_index(tmp_path, n=5)

        idx = FAISSIndex(dimension=DIM, index_path=path)
        assert isinstance(idx._index, faiss.IndexIDMap2)
        assert idx.total_vectors == 5
        assert idx.search(vecs[2], top_k=5)[0][0] == "doc2"

    @pytest.mark.slow
    def test_ivfpq_backed_index_refuses_removal_instead_of_risking_corruption(self, tmp_path):
        """remove_ids() on an IVF-family IndexIDMap2 was confirmed to
        partially mutate the index before raising -- not a clean failure.
        remove_document() must detect this and refuse up front."""
        path, vecs = self._write_legacy_ivfpq_index(tmp_path, n=5)

        idx = FAISSIndex(dimension=DIM, index_path=path)
        before = idx.total_vectors

        removed = idx.remove_document("doc2")

        assert removed == 0
        assert idx.total_vectors == before  # untouched, not partially corrupted
        assert idx.search(vecs[2], top_k=5)[0][0] == "doc2"  # still fully intact
