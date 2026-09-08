import time
import uuid

from sqlalchemy import select

from app.tasks.celery_app import celery_app
from app.db.sync_session import get_sync_session
from app.core.logging import get_logger

log = get_logger("ai_detection")


@celery_app.task(
    bind=True,
    name="app.tasks.ai_detection_tasks.ai_detect",
    max_retries=2,
    default_retry_delay=60,
    queue="ai_detection",
)
def ai_detect(self, submission_id: str) -> dict:
    """Score a submission for likely AI authorship.

    Runs independently of (and in parallel with) tier1_detect: this is a
    separate advisory signal, not a stage in the plagiarism pipeline. Never
    touches Submission.status -- the main COMPLETED gate stays driven solely
    by the plagiarism detection pipeline so existing pollers (the Moodle
    plugin's check_results task) are unaffected if this fails or lags.
    """
    from app.config import settings
    from app.models.submission import Submission
    from app.models.document import Document
    from app.models.ai_detection import AIDetectionResult
    from app.services.ai_detector import detect

    if not settings.AI_DETECTOR_ENABLED:
        return {"skipped": "AI_DETECTOR_ENABLED is false"}

    session = get_sync_session()
    start = time.perf_counter()

    try:
        sub = session.get(Submission, uuid.UUID(submission_id))
        if not sub:
            return {"error": "Submission not found"}

        documents = (
            session.execute(
                select(Document).where(Document.submission_id == sub.id)
            )
            .scalars()
            .all()
        )

        full_text = "\n\n".join(
            d.extracted_text for d in documents if d.extracted_text
        )
        if not full_text.strip():
            log.info("ai_detect_skipped_no_text", submission_id=submission_id)
            return {"skipped": "No extracted text available"}

        outcome = detect(full_text)
        elapsed_ms = int((time.perf_counter() - start) * 1000)

        existing = session.execute(
            select(AIDetectionResult).where(
                AIDetectionResult.submission_id == sub.id
            )
        ).scalar_one_or_none()

        if existing:
            existing.ai_score = outcome.score
            existing.verdict = outcome.verdict
            existing.model_name = outcome.model_name
            existing.processing_time_ms = elapsed_ms
        else:
            session.add(AIDetectionResult(
                submission_id=sub.id,
                ai_score=outcome.score,
                verdict=outcome.verdict,
                model_name=outcome.model_name,
                processing_time_ms=elapsed_ms,
            ))

        session.commit()

        log.info(
            "ai_detect_complete",
            submission_id=submission_id,
            ai_score=outcome.score,
            verdict=outcome.verdict,
            elapsed_ms=elapsed_ms,
        )

        return {
            "submission_id": submission_id,
            "ai_score": outcome.score,
            "verdict": outcome.verdict,
            "processing_time_ms": elapsed_ms,
        }

    except Exception as exc:
        session.rollback()
        log.error("ai_detect_failed", submission_id=submission_id, error=str(exc))
        raise self.retry(exc=exc)
    finally:
        session.close()
