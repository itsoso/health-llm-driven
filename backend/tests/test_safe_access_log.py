import logging
import re

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.middleware.safe_access_log import SafeAccessLogMiddleware
from main import RequestContextMiddleware


LOGGER_NAME = "app.http_access"


def _access_messages(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [
        record.getMessage()
        for record in caplog.records
        if record.name == LOGGER_NAME
    ]


def test_access_log_uses_route_template_without_private_request_target(
    caplog: pytest.LogCaptureFixture,
) -> None:
    app = FastAPI()
    app.add_middleware(SafeAccessLogMiddleware)

    @app.get("/files/{owner_id}/{filename}")
    def get_private_file(owner_id: int, filename: str) -> dict[str, bool]:
        return {"ok": bool(owner_id and filename)}

    private_values = (
        "private-meal-photo.jpeg",
        "private-expiry-value",
        "private-signature-value",
    )
    with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
        response = TestClient(app).get(
            "/files/187/private-meal-photo.jpeg",
            params={
                "expires": "private-expiry-value",
                "signature": "private-signature-value",
            },
        )

    assert response.status_code == 200
    messages = _access_messages(caplog)
    assert len(messages) == 1
    message = messages[0]
    assert message.startswith(
        "http_access method=GET route=/files/{owner_id}/{filename} status=200 "
    )
    assert re.search(r"duration_ms=\d+(?:\.\d{1,2})?$", message)
    assert "/files/187/" not in message
    assert "expires" not in message
    assert "signature" not in message
    for private_value in private_values:
        assert private_value not in message


def test_unmatched_access_log_never_uses_raw_path_or_query(
    caplog: pytest.LogCaptureFixture,
) -> None:
    app = FastAPI()
    app.add_middleware(SafeAccessLogMiddleware)

    with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
        response = TestClient(app).get(
            "/private-user-path",
            params={"signature": "unmatched-private-signature"},
        )

    assert response.status_code == 404
    message = _access_messages(caplog)[0]
    assert "route=<unmatched>" in message
    assert "private-user-path" not in message
    assert "signature" not in message
    assert "unmatched-private-signature" not in message


def test_exception_is_reraised_after_content_free_access_log(
    caplog: pytest.LogCaptureFixture,
) -> None:
    app = FastAPI()
    app.add_middleware(SafeAccessLogMiddleware)

    @app.get("/explode/{private_value}")
    def explode(private_value: str) -> None:
        raise RuntimeError(f"private-exception-{private_value}")

    with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
        with pytest.raises(RuntimeError, match="private-exception-secret-value"):
            TestClient(app).get("/explode/secret-value")

    message = _access_messages(caplog)[0]
    assert "route=/explode/{private_value}" in message
    assert "status=500" in message
    assert "secret-value" not in message
    assert "private-exception" not in message


def test_request_context_error_log_uses_template_without_exception_content(
    caplog: pytest.LogCaptureFixture,
) -> None:
    app = FastAPI()
    app.add_middleware(RequestContextMiddleware)

    @app.get("/context/{private_value}")
    def fail_in_context(private_value: str) -> None:
        raise RuntimeError(f"private-context-{private_value}")

    with caplog.at_level(logging.ERROR, logger="main"):
        response = TestClient(app).get("/context/secret-filename.jpeg")

    assert response.status_code == 500
    messages = [
        record.getMessage()
        for record in caplog.records
        if record.name == "main" and "[ERROR]" in record.getMessage()
    ]
    assert len(messages) == 1
    message = messages[0]
    assert "GET /context/{private_value}" in message
    assert "RuntimeError" in message
    assert "secret-filename.jpeg" not in message
    assert "private-context" not in message
