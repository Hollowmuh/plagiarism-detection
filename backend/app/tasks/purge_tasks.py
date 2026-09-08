"""Task to purge a deleted submission's documents from the in-memory
detection indices (Winnowing fingerprint index, BM25 index, FAISS index).

Must run inside the celery-worker process, where the actual populated
indices live -- calling FingerprintIndex.remove()/BM25Index.remove() from
the API process's own separate copy of these singletons would be a no-op
(they are plain per-process globals with no IPC/shared memory; see
evaluation/reports/07_full_pipeline_audit.md, finding 2, and the
correction to its first fix attempt).
"""

from app.tasks.celery_app import celery_app
from app.core.logging import get_logger

log = get_logger("purge")


@celery_app.task(
    bind=True,
    name="app.tasks.purge_tasks.purge_documents",
    max_retries=2,
    default_retry_delay=30,
    queue="indexing",
)
def purge_documents(self, doc_ids: list[str]) -> dict:
    """Remove the given document IDs from the Winnowing/BM25/FAISS indices.

    Routed to the "indexing" queue (the serialized detection worker), not
    the concurrent ai_detection worker -- this mutates the same shared,
    order-sensitive state that detection/indexing already touch, so it
    needs the same serialization guarantee (see the celery-worker split
    documented in evaluation/reports/04_exp3_threshold_sensitivity.md's
    Addendum 2).

    FAISS removal is chunk-aware (tier2_detector.index_chunks() fans one
    doc_id out into "{doc_id}__chunk_N" keys, see FAISSIndex.remove_document)
    and, unlike the Winnowing/BM25 indices, isn't persisted by every caller
    automatically -- save() is called once here after the loop.
    """
    from app.services.detection_pipeline import get_fingerprint_index, get_bm25_index, get_faiss_index

    fp_index = get_fingerprint_index()
    bm25_index = get_bm25_index()
    faiss_index = get_faiss_index()

    faiss_removed = 0
    for doc_id in doc_ids:
        fp_index.remove(doc_id)
        bm25_index.remove(doc_id)
        faiss_removed += faiss_index.remove_document(doc_id)

    if faiss_removed:
        faiss_index.save()

    log.info("documents_purged", doc_ids=doc_ids, faiss_vectors_removed=faiss_removed)
    return {"purged": len(doc_ids), "faiss_vectors_removed": faiss_removed}
