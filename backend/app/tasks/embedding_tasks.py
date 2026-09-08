"""Embedding generation tasks.

Pre-computes and stores document chunk embeddings in the database
and indexes them in FAISS for Tier 2 semantic search.
"""

import uuid

from sqlalchemy import select

from app.tasks.celery_app import celery_app
from app.db.sync_session import get_sync_session
from app.core.logging import get_logger

log = get_logger("embedding")


@celery_app.task(
    bind=True,
    name="app.tasks.embedding_tasks.generate_embeddings",
    max_retries=2,
    default_retry_delay=60,
    queue="embedding",
)
def generate_embeddings(self, submission_id: str) -> dict:
    """Generate 384-dim embeddings for all chunks of a submission.

    Chunks the extracted text, encodes with all-MiniLM-L6-v2,
    stores DocumentChunk records in the DB, and indexes in FAISS.
    """
    from app.models.document import Document, DocumentChunk
    from app.services.embedding_service import chunk_text, encode_texts
    from app.services.detection_pipeline import get_faiss_index

    session = get_sync_session()
    try:
        documents = (
            session.execute(
                select(Document).where(
                    Document.submission_id == uuid.UUID(submission_id)
                )
            )
            .scalars()
            .all()
        )

        if not documents:
            return {"error": "No documents found", "submission_id": submission_id}

        total_chunks = 0
        faiss_index = get_faiss_index()

        for doc in documents:
            if not doc.extracted_text:
                continue

            # Chunk the text
            chunks = chunk_text(doc.extracted_text)
            if not chunks:
                continue

            chunk_texts = [c.text for c in chunks]

            # Generate embeddings (batch, CPU-optimized)
            embeddings = encode_texts(chunk_texts)

            # Store chunks in DB
            for chunk in chunks:
                db_chunk = DocumentChunk(
                    document_id=doc.id,
                    chunk_index=chunk.index,
                    chunk_text=chunk.text,
                    char_start=chunk.char_start,
                    char_end=chunk.char_end,
                )
                session.add(db_chunk)

            # Index embeddings in FAISS
            chunk_ids = [f"{doc.id}__chunk_{c.index}" for c in chunks]
            faiss_index.add_batch(chunk_ids, embeddings)

            total_chunks += len(chunks)

        session.commit()

        log.info(
            "embeddings_generated",
            submission_id=submission_id,
            documents=len(documents),
            chunks=total_chunks,
        )

        return {
            "submission_id": submission_id,
            "status": "completed",
            "chunks_generated": total_chunks,
        }

    except Exception as exc:
        session.rollback()
        log.error("embedding_failed", submission_id=submission_id, error=str(exc))
        raise self.retry(exc=exc)
    finally:
        session.close()
