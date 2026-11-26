import os

from celery import Celery

# Allow importing config when running as standalone celery worker
broker_url = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
result_backend = os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/1")

celery_app = Celery(
    "plagiarism_detection",
    broker=broker_url,
    backend=result_backend,
)

celery_app.conf.update(
    # Serialization
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,

    # Reliability
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_reject_on_worker_lost=True,
    result_expires=86400,  # 24h

    # Timeouts
    task_soft_time_limit=600,   # 10 min soft
    task_time_limit=900,        # 15 min hard

    # Memory management — recycle workers to prevent ML model leaks
    worker_max_tasks_per_child=50,

    # Queue routing
    task_routes={
        "app.tasks.extraction_tasks.*": {"queue": "extraction"},
        "app.tasks.detection_tasks.*": {"queue": "detection"},
        "app.tasks.embedding_tasks.*": {"queue": "embedding"},
        "app.tasks.indexing_tasks.*": {"queue": "indexing"},
        "app.tasks.ai_detection_tasks.*": {"queue": "ai_detection"},
        "app.tasks.purge_tasks.*": {"queue": "indexing"},
    },

    # Default queue
    task_default_queue="default",
)

# Explicitly import task modules so they register with Celery
import app.tasks.extraction_tasks  # noqa: F401, E402
import app.tasks.detection_tasks  # noqa: F401, E402
import app.tasks.embedding_tasks  # noqa: F401, E402
import app.tasks.indexing_tasks  # noqa: F401, E402
import app.tasks.ai_detection_tasks  # noqa: F401, E402
import app.tasks.purge_tasks  # noqa: F401, E402


# Pre-load Tier-1 + Tier-2 services (sentence-transformers model) at worker
# startup. Without this, the first task that triggers indexing holds a DB
# session open during the ~8 min Hugging Face download, leaving a stale
# transaction snapshot that makes subsequent submissions invisible until
# the worker recycles.
from celery.signals import worker_ready  # noqa: E402


def _restore_detection_indices() -> None:
    """Rebuild the detection indices from completed submissions in the database."""
    from sqlalchemy import select

    from app.db.sync_session import get_sync_session
    from app.models.document import Document
    from app.models.submission import Submission, SubmissionStatus
    from app.services.detection_pipeline import restore_indices

    session = get_sync_session()
    try:
        rows = session.execute(
            select(Document.id, Document.extracted_text)
            .join(Submission, Document.submission_id == Submission.id)
            .where(
                Submission.status == SubmissionStatus.COMPLETED,
                Document.extracted_text.is_not(None),
            )
            .order_by(Document.created_at)
        ).all()
    finally:
        session.close()

    restore_indices((str(doc_id), text) for doc_id, text in rows)


@worker_ready.connect
def _preload_detection_services(sender=None, **kwargs):
    from app.core.logging import get_logger
    log = get_logger("worker_init")
    log.info("preloading_detection_services")
    try:
        from app.services.detection_pipeline import (
            get_tier1_detector,
            get_tier2_detector,
        )
        get_tier1_detector()
        get_tier2_detector()

        # get_tier2_detector() only constructs the detector object -- it
        # never touches the underlying sentence-transformers model, which
        # embedding_service.get_model() loads lazily on first use. Without
        # this explicit warmup, the model load cost (several seconds) lands
        # on whichever real submission happens to be first after a worker
        # restart, which is the actual explanation for the ~3.5-4s
        # "cold start" extraction/indexing latency spikes observed earlier
        # (see evaluation/reports/07_full_pipeline_audit.md, finding 7).
        from app.services.embedding_service import encode_texts
        encode_texts(["warmup"])

        from app.config import settings
        if settings.AI_DETECTOR_ENABLED:
            from app.services.ai_detector import _get_model as _get_ai_model
            _get_ai_model()

        # Only the worker that owns the indices (it consumes the "indexing"
        # queue) restores them. Runs before the solo pool takes any task.
        if sender is not None and "indexing" in sender.app.amqp.queues.consume_from:
            _restore_detection_indices()

        log.info("detection_services_preloaded")
    except Exception as exc:
        log.error("preload_failed", error=str(exc))
