"""FAISS vector index service for dense retrieval.

Uses IndexFlatIP for small corpora (<10K) and IVFPQ for larger ones,
both wrapped in IndexIDMap2 so individual vectors can be removed via
remove_ids() -- see remove_document() and evaluation/reports/07_full_pipeline_audit.md
for why this matters (removal used to be structurally impossible, which
let a deleted submission's vector keep surfacing as a live match forever).
384-dimensional embeddings from all-MiniLM-L6-v2.
"""

from __future__ import annotations

import json
import os
from threading import RLock

import faiss
import numpy as np

from app.config import settings
from app.core.logging import get_logger

log = get_logger("faiss")

DIMENSION = 384  # all-MiniLM-L6-v2 output dimension
MIN_VECTORS_FOR_IVFPQ = 1000  # Below this, use flat index


class FAISSIndex:
    """Thread-safe FAISS index with automatic flat/IVFPQ selection.

    - Small corpus (<1000 vectors): uses IndexFlatIP (exact search)
    - Large corpus: uses IndexIVFPQ (approximate search, much faster)

    Both are wrapped in IndexIDMap2, which assigns each vector a stable
    external id we control (see _next_id) instead of an implicit FAISS
    position -- this is what makes remove_document() possible. IndexIDMap2
    (not IndexIDMap) is required specifically because it supports
    reconstruct(), which the legacy-format migration in _try_load() needs.

    Vectors must be L2-normalized so inner product equals cosine similarity.
    """

    def __init__(
        self,
        dimension: int = DIMENSION,
        nlist: int | None = None,
        m: int | None = None,
        nprobe: int | None = None,
        index_path: str | None = None,
    ):
        self.dimension = dimension
        self.nlist = nlist or settings.FAISS_NLIST
        self.m = m or settings.FAISS_M
        self.nprobe = nprobe or settings.FAISS_NPROBE
        self.index_path = index_path or settings.FAISS_INDEX_PATH

        self._lock = RLock()
        self._index: faiss.Index | None = None
        self._id_map: dict[int, str] = {}   # faiss_id → doc_id
        self._doc_map: dict[str, int] = {}  # doc_id → faiss_id
        self._next_id = 0
        self._vectors: dict[int, np.ndarray] = {}  # faiss_id → vector, for IVFPQ retraining
        self._trained = False

        # Try to load existing index
        self._try_load()

    @property
    def _meta_path(self) -> str:
        return self.index_path + ".meta.json"

    def _try_load(self) -> None:
        """Attempt to load a persisted FAISS index plus its doc_id mapping.

        The FAISS index only stores vectors by integer id; the doc_id <->
        id mapping lives in Python (_id_map/_doc_map) and must be
        persisted separately (_meta_path) or every doc_id becomes
        unreachable the moment a process restarts and reloads the index.
        _next_id is persisted explicitly too (not derived from ntotal) --
        after a removal, ntotal is legitimately less than the highest id
        ever assigned, so deriving _next_id from ntotal risks a future
        add() reusing an id that's still alive in _id_map for another doc.

        Files written before IndexIDMap2 was introduced hold a bare
        IndexFlatIP/IndexIVFPQ with implicit sequential ids (0..ntotal-1,
        in insertion order -- guaranteed because removal was impossible
        until this class existed). Those are migrated in-memory into an
        IndexIDMap2-wrapped index below. This migration does NOT save the
        result -- see the comment further down for why eager-saving here
        is unsafe.
        """
        if self.index_path and os.path.exists(self.index_path):
            try:
                self._index = faiss.read_index(self.index_path)
                log.info("faiss_loaded", path=self.index_path, ntotal=self._index.ntotal)
            except Exception as e:
                log.warning("faiss_load_failed", error=str(e))
                self._index = None
                return

            if os.path.exists(self._meta_path):
                try:
                    with open(self._meta_path, encoding="utf-8") as f:
                        meta = json.load(f)
                    self._id_map = {int(k): v for k, v in meta["id_map"].items()}
                    self._doc_map = dict(meta["doc_map"])
                    self._next_id = meta.get("next_id", self._index.ntotal)
                    log.info("faiss_meta_loaded", path=self._meta_path, docs=len(self._doc_map))
                except Exception as e:
                    log.warning("faiss_meta_load_failed", error=str(e))
                    self._next_id = self._index.ntotal
            elif self._index.ntotal > 0:
                self._next_id = self._index.ntotal
                log.warning(
                    "faiss_meta_missing",
                    ntotal=self._index.ntotal,
                    detail="doc_id mapping for existing vectors is unrecoverable; "
                    "those vectors remain in the index but cannot be matched by doc_id",
                )
            else:
                self._next_id = self._index.ntotal

            self._migrate_to_idmap2_if_needed()

    def _migrate_to_idmap2_if_needed(self) -> None:
        """One-time, in-memory upgrade of a legacy (pre-IndexIDMap2) index.

        Deliberately does NOT call self.save(). Every Celery worker process
        (including celery-worker-fast, which never mutates the shared
        indices) loads this index at startup via the worker_ready preload
        hook. If this migration saved eagerly, both worker processes would
        race to independently persist the same file on every restart, with
        the risk of a slower save clobbering vectors the other process adds
        in between. Leaving persistence to the next real write (the
        existing periodic save in index_document(), or purge_documents'
        save()) preserves today's invariant that only celery-worker ever
        writes this file, at the cost of re-running this (cheap) in-memory
        migration on every restart until that first real write happens.
        """
        if self._index is None or isinstance(self._index, faiss.IndexIDMap2):
            return

        ntotal = self._index.ntotal
        if ntotal == 0:
            self._index = faiss.IndexIDMap2(self._index)
            return

        if len(self._id_map) != ntotal:
            log.warning(
                "faiss_migration_skipped_mismatch",
                ntotal=ntotal,
                id_map_size=len(self._id_map),
                detail="id_map/ntotal disagree (likely a prior non-atomic save "
                "interrupted mid-write); leaving index unmigrated -- removal "
                "will no-op against it until this is resolved",
            )
            return

        try:
            legacy = self._index
            if isinstance(legacy, faiss.IndexIVFPQ):
                legacy.make_direct_map()  # only valid because legacy ids are sequential 0-based
            vectors = legacy.reconstruct_n(0, ntotal)

            # IndexIDMap2 requires its wrapped index to be empty on
            # construction (confirmed empirically -- it raises otherwise).
            # reset() clears vectors but keeps training (verified for both
            # IndexFlatIP and IndexIVFPQ), so the already-trained legacy
            # index can be reused in place rather than rebuilt from scratch.
            legacy.reset()
            new_index = faiss.IndexIDMap2(legacy)
            ids = np.array(sorted(self._id_map.keys()), dtype=np.int64)
            new_index.add_with_ids(vectors, ids)
            self._vectors = {int(fid): vectors[i] for i, fid in enumerate(ids)}

            self._index = new_index
            log.info("faiss_migrated_to_idmap2", ntotal=ntotal, type=type(legacy).__name__)
        except Exception as e:
            log.warning("faiss_migration_failed", error=str(e))

    def _ensure_index(self) -> None:
        """Create an IndexIDMap2-wrapped flat index if none exists."""
        if self._index is None:
            self._index = faiss.IndexIDMap2(faiss.IndexFlatIP(self.dimension))
            log.info("faiss_created_flat", dimension=self.dimension)

    @property
    def total_vectors(self) -> int:
        if self._index is None:
            return 0
        return self._index.ntotal

    def add(self, doc_id: str, vector: np.ndarray) -> None:
        """Add a single normalized vector to the index.

        Args:
            doc_id: Unique document/chunk identifier.
            vector: 384-dim float32 array, L2-normalized.
        """
        with self._lock:
            self._ensure_index()

            if doc_id in self._doc_map:
                return  # Already indexed

            vec = vector.astype(np.float32).reshape(1, -1)
            faiss.normalize_L2(vec)

            fid = self._next_id
            self._index.add_with_ids(vec, np.array([fid], dtype=np.int64))
            self._id_map[fid] = doc_id
            self._doc_map[doc_id] = fid
            self._next_id += 1
            self._vectors[fid] = vec.flatten()

    def add_batch(self, doc_ids: list[str], vectors: np.ndarray) -> None:
        """Add multiple vectors at once.

        Args:
            doc_ids: List of unique identifiers.
            vectors: (N, 384) float32 array, L2-normalized.
        """
        with self._lock:
            self._ensure_index()

            vecs = vectors.astype(np.float32)
            faiss.normalize_L2(vecs)

            for i, doc_id in enumerate(doc_ids):
                if doc_id in self._doc_map:
                    continue
                fid = self._next_id
                self._index.add_with_ids(vecs[i : i + 1], np.array([fid], dtype=np.int64))
                self._id_map[fid] = doc_id
                self._doc_map[doc_id] = fid
                self._next_id += 1
                self._vectors[fid] = vecs[i]

    def remove_document(self, doc_id: str) -> int:
        """Remove every vector belonging to doc_id, including chunk fan-out.

        tier2_detector.index_chunks() indexes one submission under multiple
        FAISS keys ("{doc_id}__chunk_0", "{doc_id}__chunk_1", ...), not a
        single doc_id-keyed vector like the Winnowing/BM25 indices. Callers
        (purge_tasks.purge_documents) only know the base doc_id, so removal
        must match by exact id or "{doc_id}__chunk_" prefix, not exact key
        alone -- an exact-match-only removal would silently leave every
        chunk's vector behind.

        Returns the number of vectors removed (0 if doc_id was never
        indexed or the index hasn't been migrated to IndexIDMap2 yet).
        """
        with self._lock:
            if self._index is None or not isinstance(self._index, faiss.IndexIDMap2):
                if self._index is not None:
                    log.warning("faiss_remove_skipped_unmigrated", doc_id=doc_id)
                return 0

            # remove_ids() is confirmed safe (atomic, correct) for a Flat
            # backend, but empirically NOT safe for an IVF-family backend
            # (e.g. IndexIVFPQ, reachable only via upgrade_to_ivfpq(), which
            # is unreachable dead code today): it can partially mutate the
            # index -- corrupting search results -- before raising. Refuse
            # up front rather than risk that, since the failure isn't a
            # clean no-op.
            if isinstance(faiss.downcast_index(self._index.index), faiss.IndexIVF):
                log.warning("faiss_remove_unsupported_ivf", doc_id=doc_id)
                return 0

            prefix = f"{doc_id}__chunk_"
            matched = [k for k in self._doc_map if k == doc_id or k.startswith(prefix)]
            if not matched:
                return 0

            fids = [self._doc_map[k] for k in matched]
            self._index.remove_ids(faiss.IDSelectorBatch(np.array(fids, dtype=np.int64)))

            for key, fid in zip(matched, fids):
                del self._doc_map[key]
                del self._id_map[fid]
                self._vectors.pop(fid, None)

            return len(matched)

    def search(
        self, query_vector: np.ndarray, top_k: int = 50
    ) -> list[tuple[str, float]]:
        """Search for nearest neighbors.

        Args:
            query_vector: 384-dim float32 query, L2-normalized.
            top_k: Number of results.

        Returns:
            List of (doc_id, similarity_score) sorted by score descending.
        """
        with self._lock:
            if self._index is None or self._index.ntotal == 0:
                return []

            qvec = query_vector.astype(np.float32).reshape(1, -1)
            faiss.normalize_L2(qvec)

            k = min(top_k, self._index.ntotal)
            distances, indices = self._index.search(qvec, k)

            results = []
            for dist, idx in zip(distances[0], indices[0]):
                if idx == -1:
                    continue
                doc_id = self._id_map.get(int(idx))
                if doc_id:
                    results.append((doc_id, float(dist)))

            return results

    def save(self) -> None:
        """Persist the index to disk, along with its doc_id mapping.

        Both files are written to a temp path then atomically renamed, so a
        crash mid-write leaves either the old or new version intact, never
        a truncated one.
        """
        with self._lock:
            if self._index is None:
                return
            os.makedirs(os.path.dirname(self.index_path), exist_ok=True)

            tmp_index_path = self.index_path + ".tmp"
            faiss.write_index(self._index, tmp_index_path)
            os.replace(tmp_index_path, self.index_path)

            tmp_meta_path = self._meta_path + ".tmp"
            with open(tmp_meta_path, "w", encoding="utf-8") as f:
                json.dump(
                    {"id_map": self._id_map, "doc_map": self._doc_map, "next_id": self._next_id},
                    f,
                )
            os.replace(tmp_meta_path, self._meta_path)

            log.info("faiss_saved", path=self.index_path, ntotal=self._index.ntotal)

    def upgrade_to_ivfpq(self) -> None:
        """Upgrade from flat index to IVFPQ if enough vectors are available.

        Call this periodically when corpus grows past MIN_VECTORS_FOR_IVFPQ.
        """
        with self._lock:
            if not self._vectors or len(self._vectors) < MIN_VECTORS_FOR_IVFPQ:
                log.info("ivfpq_skip", reason="not enough vectors", count=len(self._vectors))
                return

            fids, vecs = zip(*self._vectors.items())
            ids = np.array(fids, dtype=np.int64)
            training_data = np.array(vecs, dtype=np.float32)
            faiss.normalize_L2(training_data)

            quantizer = faiss.IndexFlatIP(self.dimension)
            nlist = min(self.nlist, len(self._vectors) // 40)
            nlist = max(nlist, 1)

            ivfpq = faiss.IndexIVFPQ(quantizer, self.dimension, nlist, self.m, 8)
            ivfpq.train(training_data)
            # nprobe must be set on the raw IVFPQ index before wrapping --
            # IndexIDMap2 doesn't expose it as a settable attribute on the
            # wrapper, but it persists correctly through the wrap once set.
            ivfpq.nprobe = self.nprobe

            # IndexIDMap2 requires its wrapped index to be empty on
            # construction (confirmed empirically) -- wrap the freshly
            # trained-but-still-empty ivfpq first, then add vectors through
            # the wrapper, rather than adding to the raw index beforehand.
            wrapped = faiss.IndexIDMap2(ivfpq)
            wrapped.add_with_ids(training_data, ids)

            self._index = wrapped
            self._trained = True
            log.info(
                "ivfpq_upgraded",
                nlist=nlist,
                ntotal=self._index.ntotal,
                nprobe=self.nprobe,
            )
