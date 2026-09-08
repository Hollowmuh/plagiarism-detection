import dataclasses
import time
import uuid

from sqlalchemy import select

from app.tasks.celery_app import celery_app
from app.db.sync_session import get_sync_session
from app.core.logging import get_logger

log = get_logger("detection")


@celery_app.task(
    bind=True,
    name="app.tasks.detection_tasks.tier1_detect",
    max_retries=2,
    default_retry_delay=60,
    queue="detection",
)
def tier1_detect(self, submission_id: str) -> dict:
    """Run full dual-tier detection pipeline on a submission."""
    from app.models.submission import Submission, SubmissionStatus, TierResolved
    from app.models.document import Document
    from app.models.result import DetectionResult
    from app.services.detection_pipeline import run_detection

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

        if not documents or not any(d.extracted_text for d in documents):
            sub.status = SubmissionStatus.FAILED
            sub.error_message = "No extracted text available"
            session.commit()
            return {"error": "No text to analyze"}

        # Concatenate all document texts
        full_text = "\n\n".join(
            d.extracted_text for d in documents if d.extracted_text
        )

        # Use the first document's id as the index key so detection and
        # post-detection indexing (index_submission) share the same key.
        # best_match_id will then be a document_id, which we can resolve
        # to a Document row for SimilarityPair persistence.
        index_key = str(documents[0].id)

        # Run the full dual-tier detection pipeline
        pipeline_result = run_detection(index_key, full_text)

        elapsed_ms = int((time.perf_counter() - start) * 1000)

        # Store result
        result = DetectionResult(
            submission_id=sub.id,
            tier1_score=pipeline_result.tier1_score,
            tier2_score=pipeline_result.tier2_score,
            final_score=pipeline_result.final_score,
            is_plagiarised=pipeline_result.is_plagiarised,
            escalated=pipeline_result.escalated,
            escalation_reason=pipeline_result.escalation_reason,
            processing_time_ms=elapsed_ms,
        )
        session.add(result)
        session.flush()  # populate result.id for SimilarityPair FK

        # Persist match → source document link for the report UI.
        # best_match_id is a document_id (see index_key above). Skip if it
        # points at the current submission's own document (self-match on
        # the very first indexed document).
        if pipeline_result.best_match_id and pipeline_result.best_match_id != index_key:
            from app.models.result import SimilarityPair
            try:
                source_doc_uuid = uuid.UUID(pipeline_result.best_match_id)
                source_doc = session.get(Document, source_doc_uuid)
                if source_doc:
                    matched_segments = (
                        [dataclasses.asdict(pipeline_result.matched_segment)]
                        if pipeline_result.matched_segment else None
                    )
                    session.add(SimilarityPair(
                        result_id=result.id,
                        source_document_id=source_doc.id,
                        similarity_score=pipeline_result.final_score,
                        match_type="tier2" if pipeline_result.escalated else "tier1",
                        matched_segments=matched_segments,
                    ))
            except (ValueError, TypeError):
                # best_match_id wasn't a valid UUID (e.g. legacy submission_id
                # from a pre-fix indexed entry). Skip persistence rather than fail.
                log.warning(
                    "skip_similarity_pair_invalid_id",
                    best_match_id=pipeline_result.best_match_id,
                )

        sub.status = SubmissionStatus.COMPLETED
        sub.tier_resolved = (
            TierResolved.TIER2 if pipeline_result.escalated else TierResolved.TIER1
        )
        session.commit()

        log.info(
            "detection_complete",
            submission_id=submission_id,
            final_score=pipeline_result.final_score,
            escalated=pipeline_result.escalated,
            plagiarised=pipeline_result.is_plagiarised,
            elapsed_ms=elapsed_ms,
        )

        # Index for future cross-submission detection
        from app.tasks.indexing_tasks import index_submission
        index_submission.delay(submission_id)

        return {
            "submission_id": submission_id,
            "final_score": pipeline_result.final_score,
            "escalated": pipeline_result.escalated,
            "is_plagiarised": pipeline_result.is_plagiarised,
            "processing_time_ms": elapsed_ms,
        }

    except Exception as exc:
        session.rollback()
        try:
            sub = session.get(Submission, uuid.UUID(submission_id))
            if sub:
                sub.status = SubmissionStatus.FAILED
                sub.error_message = str(exc)[:500]
                session.commit()
        except Exception:
            pass
        log.error("detection_failed", submission_id=submission_id, error=str(exc))
        raise self.retry(exc=exc)
    finally:
        session.close()
