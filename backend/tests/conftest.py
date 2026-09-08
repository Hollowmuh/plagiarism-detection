"""Pytest configuration and shared fixtures."""

import os
import sys

import pytest

# Ensure backend app is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Set test environment variables before importing app modules
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost:5432/test")
os.environ.setdefault("DATABASE_URL_SYNC", "postgresql://test:test@localhost:5432/test")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("CELERY_BROKER_URL", "redis://localhost:6379/0")
os.environ.setdefault("CELERY_RESULT_BACKEND", "redis://localhost:6379/1")
os.environ.setdefault("API_SECRET_KEY", "test-secret-key")
# Force-override (not setdefault): the container already has FAISS_INDEX_PATH
# set to the shared production path, so setdefault would silently no-op and
# tests would load/pollute live production/eval vector data.
os.environ["FAISS_INDEX_PATH"] = "/tmp/test_faiss_index.faiss"
os.environ.setdefault("UPLOAD_DIR", "/tmp/test_uploads")


def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line("markers", "slow: marks tests as slow (embedding model required)")
