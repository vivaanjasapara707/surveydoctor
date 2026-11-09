"""Error codes and plain-English messages for the API (BLUEPRINT §7.11).

Every error response is ``{"code": ..., "message": ...}``. The message says what went wrong
and how to fix it. Stack traces are never returned, and log lines never contain uploaded
data: for unexpected errors only the exception type and code location are logged, because
exception messages can quote answers from the file.
"""

from __future__ import annotations

import logging
import traceback
from typing import Literal

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger("surveydoctor.api")

ErrorCode = Literal[
    "invalid_csv",
    "not_csv",
    "data_mismatch",
    "invalid_json",
    "invalid_schema",
    "invalid_settings",
    "invalid_request",
    "file_too_large",
    "too_many_rows",
    "not_found",
    "method_not_allowed",
    "sample_missing",
    "internal_error",
]

STATUS: dict[str, int] = {
    "invalid_csv": 400,
    "not_csv": 400,
    "data_mismatch": 400,
    "invalid_json": 422,
    "invalid_schema": 422,
    "invalid_settings": 422,
    "invalid_request": 422,
    "file_too_large": 413,
    "too_many_rows": 413,
    "not_found": 404,
    "method_not_allowed": 405,
    "sample_missing": 500,
    "internal_error": 500,
}

INTERNAL_ERROR_MESSAGE = (
    "Something went wrong inside SurveyDoctor while analysing the file. Nothing was stored. "
    "Try again; if it keeps happening, check the file against the sample CSV and report the "
    "problem with the steps you took (not the data)."
)

# Readable names for request fields in validation messages.
FIELD_NAMES: dict[str, str] = {
    "file": "the CSV file ('file')",
    "schema": "the survey schema ('schema')",
    "analysis": "the analysis to check ('analysis')",
    "n_factors": "the number of factors ('n_factors')",
    "rules": "the flag rules ('rules')",
    "fsqca": "the fsQCA settings ('fsqca')",
}


class ApiError(Exception):
    """An error with a code from :data:`STATUS` and a message for the user."""

    def __init__(self, code: ErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = STATUS[code]


def error_response(code: str, message: str) -> JSONResponse:
    return JSONResponse({"code": code, "message": message}, status_code=STATUS[code])


def _location(loc: tuple) -> str:
    return ".".join(str(part) for part in loc)


def validation_message(exc: ValidationError, what: str) -> str:
    """Turn Pydantic errors for one JSON field into one plain-English message.

    Args:
        exc: The validation error.
        what: What the field describes, e.g. "The analysis settings".
    """
    problems = []
    for error in exc.errors():
        where = _location(error["loc"])
        if error["type"] == "missing":
            problems.append(f"'{where}' is missing")
        elif error["type"] == "extra_forbidden":
            problems.append(f"'{where}' is not a known setting")
        elif error["type"] in ("union_tag_invalid", "union_tag_not_found"):
            problems.append(f"'type' must be one of: {error.get('ctx', {}).get('expected_tags')}")
        elif where:
            problems.append(f"'{where}': {error['msg']}")
        else:
            problems.append(error["msg"])
    return f"{what} are not valid: {'; '.join(problems)}."


async def api_error_handler(_: Request, exc: ApiError) -> JSONResponse:
    return error_response(exc.code, exc.message)


async def request_validation_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    """Missing or malformed form fields (e.g. no file, or n_factors that is not a number)."""
    problems = []
    for error in exc.errors():
        loc = [str(part) for part in error["loc"] if part not in ("body", "query")]
        field = FIELD_NAMES.get(loc[0], f"'{loc[0]}'") if loc else "the request"
        if error["type"] == "missing":
            problems.append(f"{field} is missing")
        else:
            problems.append(f"{field}: {error['msg']}")
    message = (
        f"The request is not complete: {'; '.join(problems)}. Send the CSV file as 'file' and "
        "the settings as form fields (see /docs)."
    )
    return error_response("invalid_request", message)


async def http_error_handler(_: Request, exc: StarletteHTTPException) -> JSONResponse:
    """Unknown routes, wrong methods and unreadable request bodies."""
    if exc.status_code == 404:
        return error_response("not_found", "There is no such API address. See /docs for the list.")
    if exc.status_code == 405:
        return error_response(
            "method_not_allowed", "This API address does not accept that method. See /docs."
        )
    if exc.status_code == 413:
        return error_response("file_too_large", str(exc.detail))
    return JSONResponse(
        {
            "code": "invalid_request",
            "message": (
                "The request could not be read. Send the CSV file as 'file' in a multipart "
                "form upload, with the settings as form fields (see /docs)."
            ),
        },
        status_code=400 if exc.status_code < 500 else exc.status_code,
    )


def log_unexpected(exc: Exception, method: str, path: str) -> None:
    """Log where an unexpected error happened, never its message (it may quote the data)."""
    frames = traceback.extract_tb(exc.__traceback__)
    where = f"{frames[-1].filename}:{frames[-1].lineno} in {frames[-1].name}" if frames else "?"
    logger.error("Unexpected %s at %s (%s %s)", type(exc).__name__, where, method, path)
