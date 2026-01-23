import pytest
import json
import itertools
from fastapi import FastAPI, Request
from starlette.testclient import TestClient
from unittest.mock import patch, MagicMock
from app.core.logging_middleware import StructuredLoggingMiddleware

# Setup a simple app for testing middleware
app = FastAPI()
app.add_middleware(StructuredLoggingMiddleware)


@app.get("/normal")
async def normal_request():
    return {"message": "ok"}


@app.get("/slow")
async def slow_request():
    import time

    time.sleep(0.6)  # > 500ms
    return {"message": "slow"}


@app.get("/error")
async def error_request():
    raise ValueError("planned error")


client = TestClient(app)


@pytest.fixture
def mock_logger():
    with patch("app.core.logging_middleware.structured_logger") as mock:
        yield mock


def test_logs_error_request(mock_logger):
    # Rule 1: Always log errors
    # TestClient raises exceptions by default, we need to suppress that to let middleware handle it
    # However, BaseHTTPMiddleware re-raises exceptions.
    # In a real app, an exception handler would catch it, but the middleware sees the exception.
    # We expect the middleware to log AND re-raise.

    with pytest.raises(ValueError):
        client.get("/error")

    assert mock_logger.info.called
    log_call = mock_logger.info.call_args[0][0]
    log_data = json.loads(log_call)

    # Status code might be 500 effectively if unhandled, but middleware sets it default 500
    assert log_data["status_code"] == 500
    assert "planned error" in log_data["error"]


def test_logs_slow_request(mock_logger):
    # Rule 2: Always log slow requests
    # Patch time MODULE in the middleware file, so we control it completely
    with patch("app.core.logging_middleware.time") as mock_time:
        mock_time.perf_counter.side_effect = [1000.0, 1000.6, 1001.0, 1002.0]
        mock_time.time.return_value = 1700000000.0

        client.get("/slow")

    assert mock_logger.info.called
    log_call = mock_logger.info.call_args[0][0]
    log_data = json.loads(log_call)

    # 1000.6 - 1000.0 = 0.6s = 600ms
    assert log_data["duration_ms"] >= 500


def test_logs_authenticated_user(mock_logger):
    # Test that user info is logged when present in request.state
    # We need a custom route or just rely on middleware inspecting state
    # Since client.get() creates a fresh request, we can't easily set state beforehand
    # unless we add a middleware that runs usage or we mock the request object in the middleware.

    # Easier approach: Define a route that sets the state, simulating auth dependency
    @app.get("/authenticated")
    async def authenticated_request(request: Request):
        # Simulate what auth dependency does
        user = MagicMock()
        user.id = "123-uuid"
        user.email = "test@example.com"
        user.first_name = "Test"
        user.last_name = "User"
        request.state.user = user
        return {"message": "authenticated"}

    # Force sampling or slow request to ensure it logs
    with patch("app.core.logging_middleware.time") as mock_time:
        # Slow request to force log
        mock_time.perf_counter.side_effect = [1000.0, 1000.6]
        mock_time.time.return_value = 1700000000.0

        client.get("/authenticated")

    assert mock_logger.info.called
    log_call = mock_logger.info.call_args[0][0]
    log_data = json.loads(log_call)

    assert log_data["user_id"] == "123-uuid"
    assert log_data["user_email"] == "test@example.com"
    assert log_data["user_name"] == "Test User"


def test_samples_normal_request(mock_logger):
    # Rule 3: Randomly sample 5%
    # Force random to be < 0.05
    # Force time to be fast
    with (
        patch("random.random", return_value=0.01),
        patch("app.core.logging_middleware.time") as mock_time,
    ):
        mock_time.perf_counter.side_effect = [100.0, 100.1]  # 100ms
        mock_time.time.return_value = 1700000000.0

        client.get("/normal")

    assert mock_logger.info.called


def test_ignores_normal_request(mock_logger):
    # Rule 3: Ignore majority
    # Force random to be > 0.05
    # Force time to be fast
    with (
        patch("random.random", return_value=0.10),
        patch("app.core.logging_middleware.time") as mock_time,
    ):
        # Use iterator to avoid StopIteration if framework makes extra calls
        mock_time.perf_counter.side_effect = itertools.count(start=100.0, step=0.1)
        mock_time.time.return_value = 1700000000.0

        client.get("/normal")

    assert not mock_logger.info.called
