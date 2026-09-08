"""Unit tests for the API endpoints.

Uses httpx async test client to test FastAPI routes.
DB-dependent endpoints mock the session dependency.
"""

import uuid
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from unittest.mock import patch, AsyncMock, MagicMock

from app.main import app
from app.config import settings
from app.db.session import get_db


class MockAsyncSession:
    """Mock async DB session that returns None for queries."""
    async def get(self, *args, **kwargs):
        return None

    async def execute(self, *args, **kwargs):
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        result.scalars.return_value.all.return_value = []
        return result

    async def commit(self):
        pass

    async def rollback(self):
        pass

    async def close(self):
        pass


async def mock_get_db():
    yield MockAsyncSession()


@pytest_asyncio.fixture
async def client():
    # Override DB dependency with mock
    app.dependency_overrides[get_db] = mock_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest.fixture
def auth_headers():
    return {"Authorization": f"Bearer {settings.API_SECRET_KEY}"}


@pytest.mark.asyncio
class TestHealthEndpoints:
    async def test_live(self, client):
        resp = await client.get("/api/v1/health/live")
        assert resp.status_code == 200
        assert resp.json()["status"] == "alive"

    async def test_health_no_auth_required_for_live(self, client):
        resp = await client.get("/api/v1/health/live")
        assert resp.status_code == 200


@pytest.mark.asyncio
class TestSubmissionEndpoints:
    async def test_submit_requires_auth(self, client):
        resp = await client.post("/api/v1/submissions/")
        assert resp.status_code in (401, 403, 422)

    async def test_submit_invalid_file_type(self, client, auth_headers):
        files = {"file": ("test.exe", b"binary content", "application/octet-stream")}
        data = {"course_id": "CS101", "assignment_id": "A1", "user_id": "student1"}
        resp = await client.post(
            "/api/v1/submissions/",
            headers=auth_headers,
            files=files,
            data=data,
        )
        assert resp.status_code in (400, 422)

    async def test_get_nonexistent_submission_status(self, client, auth_headers):
        fake_id = str(uuid.uuid4())
        resp = await client.get(
            f"/api/v1/submissions/{fake_id}/status",
            headers=auth_headers,
        )
        assert resp.status_code == 404

    async def test_get_results_nonexistent(self, client, auth_headers):
        fake_id = str(uuid.uuid4())
        resp = await client.get(
            f"/api/v1/submissions/{fake_id}/results",
            headers=auth_headers,
        )
        assert resp.status_code == 404

    async def test_delete_nonexistent(self, client, auth_headers):
        fake_id = str(uuid.uuid4())
        resp = await client.delete(
            f"/api/v1/submissions/{fake_id}",
            headers=auth_headers,
        )
        assert resp.status_code == 404

    async def test_invalid_uuid_returns_422(self, client, auth_headers):
        resp = await client.get(
            "/api/v1/submissions/not-a-uuid/status",
            headers=auth_headers,
        )
        assert resp.status_code == 422
