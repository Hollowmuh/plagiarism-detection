from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.core.exceptions import AppError, app_error_handler
from app.core.logging import setup_logging


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    setup_logging()
    # Startup: verify DB connectivity
    from app.db.session import engine
    async with engine.begin() as conn:
        await conn.execute(__import__("sqlalchemy").text("SELECT 1"))
    yield
    # Shutdown: dispose engine
    await engine.dispose()


app = FastAPI(
    title="Plagiarism Detection API",
    description="Dual-tier plagiarism detection system for Moodle LMS",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Exception handlers
app.add_exception_handler(AppError, app_error_handler)

# Mount API routes
from app.api.v1 import api_router  # noqa: E402

app.include_router(api_router)
