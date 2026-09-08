import uuid

from sqlalchemy import select

from app.tasks.celery_app import celery_app
from app.db.sync_session import get_sync_session
from app.core.logging import get_logger

log = get_logger("extraction")


@celery_app.task(
    bind=True,
    name="app.tasks.extraction_tasks.extract_text",
    max_retries=3,
    default_retry_delay=30,
    queue="extraction",
)
def extract_text(self, submission_id: str) -> dict:
    """Extract text from all documents attached to a submission."""
    from app.models.submission import Submission, SubmissionStatus
    from app.models.document import Document
    from app.services.text_extraction import extract_text_from_file

    session = get_sync_session()
    try:
        sub = session.get(Submission, uuid.UUID(submission_id))
        if not sub:
            log.error("submission_not_found", submission_id=submission_id)
            return {"error": "Submission not found"}

        sub.status = SubmissionStatus.EXTRACTING
        session.commit()

        documents = (
            session.execute(
                select(Document).where(Document.submission_id == sub.id)
            )
            .scalars()
            .all()
        )

        results = []
        for doc in documents:
            try:
                text = extract_text_from_file(doc.file_path, doc.mime_type)
                doc.extracted_text = text
                doc.word_count = len(text.split()) if text else 0
                results.append({
                    "document_id": str(doc.id),
                    "word_count": doc.word_count,
                    "status": "ok",
                })
                log.info(
                    "text_extracted",
                    document_id=str(doc.id),
                    word_count=doc.word_count,
                )
            except Exception as e:
                results.append({
                    "document_id": str(doc.id),
                    "status": "error",
                    "error": str(e),
                })
                log.error(
                    "extraction_failed",
                    document_id=str(doc.id),
                    error=str(e),
                )

        session.commit()

        # Transition to detection phase
        sub.status = SubmissionStatus.DETECTING
        session.commit()

        # Chain to detection pipeline
        from app.tasks.detection_tasks import tier1_detect
        tier1_detect.delay(submission_id)

        # AI-authorship detection runs independently and in parallel: it's a
        # separate advisory signal, not a stage of the plagiarism pipeline,
        # so it must not block or gate submission completion.
        from app.config import settings
        if settings.AI_DETECTOR_ENABLED:
            from app.tasks.ai_detection_tasks import ai_detect
            ai_detect.delay(submission_id)

        return {
            "submission_id": submission_id,
            "documents_processed": len(results),
            "results": results,
        }

    except Exception as exc:
        session.rollback()
        log.error("extraction_task_failed", error=str(exc))
        raise self.retry(exc=exc)
    finally:
        session.close()
