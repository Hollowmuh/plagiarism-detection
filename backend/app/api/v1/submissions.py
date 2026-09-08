import os
import uuid

import aiofiles
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.core.auth import verify_api_key
from app.core.exceptions import NotFoundError
from app.db.session import get_db
from app.models.ai_detection import AIDetectionResult
from app.models.document import Document
from app.models.result import DetectionResult, SimilarityPair
from app.models.submission import Submission, SubmissionStatus
from app.schemas.result import (
    AIDetectionResultResponse,
    DetectionResultResponse,
    SimilarityPairResponse,
)
from app.schemas.submission import (
    SubmissionAccepted,
    SubmissionResponse,
    SubmissionStatusResponse,
)
from app.services.text_extraction import compute_file_hash

router = APIRouter()


@router.post(
    "/",
    response_model=SubmissionAccepted,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(verify_api_key)],
)
async def create_submission(
    file: UploadFile = File(...),
    course_id: str | None = Form(None),
    assignment_id: str | None = Form(None),
    user_id: str | None = Form(None),
    db: AsyncSession = Depends(get_db),
):
    """Upload a document for plagiarism detection.

    Returns 202 Accepted immediately. Processing runs asynchronously.
    """
    # Validate file type
    allowed_extensions = {".pdf", ".docx", ".txt"}
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {ext}. Allowed: {', '.join(allowed_extensions)}",
        )

    # Validate file size
    max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
    content = await file.read()
    if len(content) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Max: {settings.MAX_UPLOAD_SIZE_MB} MB",
        )

    # Create submission record
    submission = Submission(
        course_id=course_id,
        assignment_id=assignment_id,
        user_id=user_id,
        status=SubmissionStatus.PENDING,
    )
    db.add(submission)
    await db.flush()  # Get the ID

    # Save file to disk
    upload_dir = os.path.join(settings.UPLOAD_DIR, str(submission.id))
    os.makedirs(upload_dir, exist_ok=True)
    file_path = os.path.join(upload_dir, file.filename or "document")

    async with aiofiles.open(file_path, "wb") as f:
        await f.write(content)

    # Compute hash for dedup
    file_hash = compute_file_hash(file_path)

    # Create document record
    document = Document(
        submission_id=submission.id,
        filename=file.filename or "document",
        file_path=file_path,
        file_hash=file_hash,
        mime_type=file.content_type,
        file_size_bytes=len(content),
    )
    db.add(document)
    await db.flush()

    # Commit BEFORE queuing — otherwise the worker can dequeue and look up
    # the submission_id before the API request commits, producing
    # "submission_not_found" and silently dropping the task.
    await db.commit()

    # Queue extraction task
    from app.tasks.extraction_tasks import extract_text

    task = extract_text.delay(str(submission.id))
    submission.celery_task_id = task.id
    await db.commit()

    return SubmissionAccepted(
        submission_id=submission.id,
        status="pending",
        message="Submission queued for processing",
    )


@router.get(
    "/{submission_id}/status",
    response_model=SubmissionStatusResponse,
    dependencies=[Depends(verify_api_key)],
)
async def get_submission_status(
    submission_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Lightweight status poll (no joins)."""
    sub = await db.get(Submission, submission_id)
    if not sub:
        raise NotFoundError("Submission not found")

    # Get processing time if result exists
    processing_time = None
    if sub.status == SubmissionStatus.COMPLETED:
        result = await db.execute(
            select(DetectionResult.processing_time_ms).where(
                DetectionResult.submission_id == submission_id
            )
        )
        processing_time = result.scalar_one_or_none()

    return SubmissionStatusResponse(
        id=sub.id,
        status=sub.status,
        tier_resolved=sub.tier_resolved,
        processing_time_ms=processing_time,
    )


@router.get(
    "/{submission_id}",
    response_model=SubmissionResponse,
    dependencies=[Depends(verify_api_key)],
)
async def get_submission(
    submission_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Get full submission details."""
    sub = await db.get(Submission, submission_id)
    if not sub:
        raise NotFoundError("Submission not found")
    return sub


@router.get(
    "/{submission_id}/results",
    response_model=DetectionResultResponse,
    dependencies=[Depends(verify_api_key)],
)
async def get_submission_results(
    submission_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Get detection results for a submission."""
    # Check submission exists
    sub = await db.get(Submission, submission_id)
    if not sub:
        raise NotFoundError("Submission not found")

    if sub.status != SubmissionStatus.COMPLETED:
        raise HTTPException(
            status_code=409,
            detail=f"Results not ready. Current status: {sub.status.value}",
        )

    # Fetch result with similarity pairs
    stmt = (
        select(DetectionResult)
        .where(DetectionResult.submission_id == submission_id)
        .options(selectinload(DetectionResult.similarity_pairs))
    )
    result = (await db.execute(stmt)).scalar_one_or_none()
    if not result:
        raise NotFoundError("Detection result not found")

    # Best-effort: AI detection runs independently and in parallel with the
    # plagiarism pipeline, so it may not have finished yet even though the
    # main submission is COMPLETED. Omit rather than block/error on it.
    ai_result = (
        await db.execute(
            select(AIDetectionResult).where(
                AIDetectionResult.submission_id == submission_id
            )
        )
    ).scalar_one_or_none()

    return DetectionResultResponse(
        submission_id=result.submission_id,
        tier1_score=result.tier1_score,
        tier2_score=result.tier2_score,
        final_score=result.final_score,
        is_plagiarised=result.is_plagiarised,
        escalated=result.escalated,
        escalation_reason=result.escalation_reason,
        processing_time_ms=result.processing_time_ms,
        matches=[
            SimilarityPairResponse(
                source_document_id=pair.source_document_id,
                similarity_score=pair.similarity_score,
                match_type=pair.match_type,
                matched_segments=pair.matched_segments,
            )
            for pair in result.similarity_pairs
        ],
        ai_detection=(
            AIDetectionResultResponse(
                ai_score=ai_result.ai_score,
                verdict=ai_result.verdict.value,
                model_name=ai_result.model_name,
                processing_time_ms=ai_result.processing_time_ms,
            )
            if ai_result
            else None
        ),
        created_at=result.created_at,
    )


@router.delete(
    "/{submission_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(verify_api_key)],
)
async def delete_submission(
    submission_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Delete a submission and all associated data.

    Also purges the submission's documents from the in-memory Winnowing and
    BM25 detection indices, which are entirely separate from the database
    and would otherwise keep "deleted" content permanently matchable by
    future submissions (see evaluation/reports/07_full_pipeline_audit.md,
    finding 2). Dispatched as a Celery task rather than called in-process:
    get_fingerprint_index()/get_bm25_index() are per-process singletons
    with no IPC, and the actual populated indices live in the
    celery-worker process, not this API process -- calling .remove()
    directly here would silently mutate an unused, separate copy and do
    nothing to the real index (an earlier version of this fix made exactly
    that mistake; verified wrong by testing, not caught by inspection).
    FAISS vectors are NOT purged -- IndexFlatIP doesn't support removing
    individual vectors without a full index rebuild; this is a known,
    documented limitation, not an oversight in this fix.
    """
    sub = await db.get(Submission, submission_id)
    if not sub:
        raise NotFoundError("Submission not found")

    documents = (
        await db.execute(
            select(Document).where(Document.submission_id == submission_id)
        )
    ).scalars().all()

    if documents:
        from app.tasks.purge_tasks import purge_documents
        purge_documents.delay([str(doc.id) for doc in documents])

    await db.delete(sub)
