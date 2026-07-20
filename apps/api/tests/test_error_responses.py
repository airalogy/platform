import asyncio
import json

from sqlalchemy.exc import SQLAlchemyError
from starlette.requests import Request
from starlette.responses import Response

from app.routers import (
    logger_middleware,
    request_id_var,
    sqlalchemy_exception_handler,
    unhandled_exception_handler,
)


def make_request() -> Request:
    return Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": "/test",
            "raw_path": b"/test",
            "query_string": b"",
            "headers": [],
            "client": ("127.0.0.1", 1234),
            "server": ("testserver", 80),
        }
    )


def test_logger_middleware_adds_request_id_header():
    request = make_request()

    async def call_next(_: Request) -> Response:
        return Response(status_code=204)

    response = asyncio.run(logger_middleware(request, call_next))

    assert response.status_code == 204
    assert response.headers["x-request-id"] == request.state.request_id


def test_unhandled_exception_returns_safe_request_reference(monkeypatch):
    request = make_request()
    request.state.request_id = "request-reference"
    token = request_id_var.set("request-reference")
    monkeypatch.setattr("app.routers.logger.exception", lambda *_args, **_kwargs: None)

    try:
        response = asyncio.run(
            unhandled_exception_handler(request, RuntimeError("secret server detail"))
        )
    finally:
        request_id_var.reset(token)

    payload = json.loads(response.body)
    assert response.status_code == 500
    assert response.headers["x-request-id"] == "request-reference"
    assert payload == {
        "detail": {
            "code": "internal_server_error",
            "message": "The server could not complete this request.",
            "request_id": "request-reference",
        }
    }
    assert "secret server detail" not in response.body.decode()


def test_database_exception_in_production_hides_internal_detail(monkeypatch):
    request = make_request()
    request.state.request_id = "production-request"
    token = request_id_var.set("production-request")
    monkeypatch.setattr("app.routers.config.APP_ENV", "production")
    monkeypatch.setattr("app.routers.logger.exception", lambda *_args, **_kwargs: None)

    try:
        response = asyncio.run(
            sqlalchemy_exception_handler(
                request,
                SQLAlchemyError("secret table and constraint detail"),
            )
        )
    finally:
        request_id_var.reset(token)

    payload = json.loads(response.body)
    assert response.status_code == 500
    assert response.headers["x-request-id"] == "production-request"
    assert payload == {
        "detail": {
            "code": "internal_server_error",
            "message": "The server could not complete this request.",
            "request_id": "production-request",
        }
    }
    assert "secret table and constraint detail" not in response.body.decode()


def test_database_exception_in_development_includes_debug_detail(monkeypatch):
    request = make_request()
    request.state.request_id = "development-request"
    token = request_id_var.set("development-request")
    monkeypatch.setattr("app.routers.config.APP_ENV", "development")
    monkeypatch.setattr("app.routers.logger.exception", lambda *_args, **_kwargs: None)

    try:
        response = asyncio.run(
            sqlalchemy_exception_handler(
                request,
                SQLAlchemyError("useful development detail"),
            )
        )
    finally:
        request_id_var.reset(token)

    payload = json.loads(response.body)
    assert response.status_code == 500
    assert response.headers["x-request-id"] == "development-request"
    assert payload == {
        "detail": {
            "code": "internal_server_error",
            "message": "The server could not complete this request.",
            "request_id": "development-request",
            "debug": {
                "exception": "SQLAlchemyError",
                "message": "SQLAlchemyError('useful development detail')",
            },
        }
    }
