import uuid

from sqlalchemy import select

from app.tasks.celery_app import celery_app
from app.db.sync_session import get_sync_session
from app.core.logging import get_logger

log = get_logger("indexing")


@celery_app.task(
    bind=True,
    name="app.tasks.indexing_tasks.index_submission",
    max_retries=2,
    default_retry_delay=30,
    queue="indexing",
)
def index_submission(self, submission_id: str) -> dict:
    """Index a processed submission for future cross-submission detection."""
    from app.models.document import Document
    from app.services.detection_pipeline import index_document

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
            return {"error": "No documents found"}

        indexed = 0
        for doc in documents:
            if doc.extracted_text:
                index_document(str(doc.id), doc.extracted_text)
                indexed += 1

        log.info(
            "submission_indexed",
            submission_id=submission_id,
            documents_indexed=indexed,
        )

        return {
            "submission_id": submission_id,
            "documents_indexed": indexed,
        }

    except Exception as exc:
        log.error("indexing_failed", submission_id=submission_id, error=str(exc))
        raise self.retry(exc=exc)
    finally:
        session.close()
