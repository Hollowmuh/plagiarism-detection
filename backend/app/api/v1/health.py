import asyncio

import redis.asyncio as aioredis
from fastapi import APIRouter
from sqlalchemy import text

from app.config import settings
from app.db.session import engine
from app.schemas.health import HealthResponse

router = APIRouter()


async def _check_db() -> str:
    try:
        async with engine.begin() as conn:
            await conn.execute(text("SELECT 1"))
        return "ok"
    except Exception as e:
        return f"error: {e}"


async def _check_redis() -> str:
    try:
        r = aioredis.from_url(settings.REDIS_URL)
        await r.ping()
        await r.aclose()
        return "ok"
    except Exception as e:
        return f"error: {e}"


def _check_workers_sync() -> str:
    """Check if at least one Celery worker is responding (sync, runs in thread)."""
    try:
        from app.tasks.celery_app import celery_app

        inspector = celery_app.control.inspect(timeout=2.0)
        ping = inspector.ping()
        if ping:
            return f"ok ({len(ping)} workers)"
        return "no workers"
    except Exception as e:
        return f"error: {e}"


@router.get("/health", response_model=HealthResponse)
async def health_check():
    """Full health check: database, Redis, Celery workers."""
    db_status, redis_status = await asyncio.gather(
        _check_db(),
        _check_redis(),
    )
    # Worker check is sync (celery inspect), run in thread
    worker_status = await asyncio.to_thread(_check_workers_sync)

    overall = "healthy"
    if "error" in db_status or "error" in redis_status:
        overall = "degraded"

    return HealthResponse(
        status=overall,
        database=db_status,
        redis=redis_status,
        workers=worker_status,
    )


@router.get("/health/live")
async def liveness():
    """Liveness probe — is the process alive?"""
    return {"status": "alive"}


@router.get("/health/ready")
async def readiness():
    """Readiness probe — can we serve traffic?"""
    db_status = await _check_db()
    if "error" in db_status:
        from fastapi.responses import JSONResponse
        return JSONResponse(
            status_code=503,
            content={"status": "not_ready", "database": db_status},
        )
    return {"status": "ready"}
