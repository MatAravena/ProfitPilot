"""Centralized error handling: structured error codes, traceback logging, and
consistent JSON error responses across the API.

Response shape (all error responses):

    {
      "error": {
        "code": "backtest_failed",
        "message": "Not enough data for the requested range",
        "details": { ... },          # optional, e.g. which field failed validation
        "traceback": "..."           # only present when settings.DEBUG is true
      }
    }

Routes should raise ``AppError`` (or a subclass) for expected, domain-level
failures. Anything uncaught is treated as an internal error: the full traceback
is logged via structlog and only echoed in the response body when DEBUG is on.
"""
from __future__ import annotations

import traceback as _tb
from typing import Any

import structlog
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.config import get_settings

logger = structlog.get_logger(__name__)


class ErrorCode:
    """Stable, machine-readable error codes the frontend can switch on."""

    VALIDATION_ERROR = "validation_error"
    NOT_FOUND = "not_found"
    BAD_REQUEST = "bad_request"
    UPSTREAM_ERROR = "upstream_error"       # a broker / data provider failed
    BACKTEST_FAILED = "backtest_failed"
    INTERNAL_ERROR = "internal_error"


class AppError(Exception):
    """Base class for expected, domain-level errors with a stable error code."""

    status_code: int = status.HTTP_400_BAD_REQUEST
    code: str = ErrorCode.BAD_REQUEST

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        status_code: int | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        if code is not None:
            self.code = code
        if status_code is not None:
            self.status_code = status_code
        self.details = details


class NotFoundError(AppError):
    status_code = status.HTTP_404_NOT_FOUND
    code = ErrorCode.NOT_FOUND


class UpstreamError(AppError):
    """A dependency we call (broker, data provider) failed."""

    status_code = status.HTTP_502_BAD_GATEWAY
    code = ErrorCode.UPSTREAM_ERROR


class BacktestError(AppError):
    status_code = status.HTTP_502_BAD_GATEWAY
    code = ErrorCode.BACKTEST_FAILED


def _body(
    code: str,
    message: str,
    *,
    details: dict[str, Any] | None = None,
    exc: BaseException | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {"code": code, "message": message}
    if details:
        payload["details"] = details
    if exc is not None and get_settings().DEBUG:
        payload["traceback"] = "".join(
            _tb.format_exception(type(exc), exc, exc.__traceback__)
        )
    return {"error": payload}


def register_exception_handlers(app: FastAPI) -> None:
    """Attach the structured error handlers to a FastAPI app."""

    @app.exception_handler(AppError)
    async def _handle_app_error(request: Request, exc: AppError) -> JSONResponse:
        # Expected domain errors: log at warning, no noisy traceback.
        logger.warning(
            "api.app_error",
            code=exc.code,
            message=exc.message,
            path=request.url.path,
            method=request.method,
        )
        return JSONResponse(
            status_code=exc.status_code,
            content=_body(exc.code, exc.message, details=exc.details, exc=exc),
        )

    @app.exception_handler(RequestValidationError)
    async def _handle_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        # Surface which field(s) failed so the FE can point at them.
        fields = [
            {
                "field": ".".join(str(p) for p in err.get("loc", []) if p != "body"),
                "message": err.get("msg", ""),
                "type": err.get("type", ""),
            }
            for err in exc.errors()
        ]
        logger.info(
            "api.validation_error", path=request.url.path, method=request.method, fields=fields
        )
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=_body(
                ErrorCode.VALIDATION_ERROR,
                "Request validation failed",
                details={"fields": fields},
            ),
        )

    @app.exception_handler(StarletteHTTPException)
    async def _handle_http_exception(
        request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        # Preserve explicit HTTPExceptions but normalize the body shape.
        code = ErrorCode.NOT_FOUND if exc.status_code == 404 else ErrorCode.BAD_REQUEST
        return JSONResponse(
            status_code=exc.status_code,
            content=_body(code, str(exc.detail)),
        )

    @app.exception_handler(Exception)
    async def _handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
        # Anything uncaught: log the full traceback, hide internals in prod.
        logger.error(
            "api.unhandled_exception",
            path=request.url.path,
            method=request.method,
            error=str(exc),
            exc_info=exc,
        )
        message = str(exc) if get_settings().DEBUG else "Internal server error"
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=_body(ErrorCode.INTERNAL_ERROR, message, exc=exc),
        )
