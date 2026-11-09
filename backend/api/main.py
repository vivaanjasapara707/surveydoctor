"""The SurveyDoctor HTTP API (BLUEPRINT §7.11): a thin layer over surveydoctor.pipeline.

Run locally from ``backend/``: ``uvicorn api.main:app --reload``, then open
http://localhost:8000/docs.

Stateless by design: each request carries the CSV (and the schema and settings), is
processed in memory, and is discarded. Nothing is written to disk: uploads are kept in
memory up to the size limit (Starlette would otherwise spool files over 1 MB to a temporary
file). Limits: 10 MB and 50,000 rows per file.

Settings that are structured (schema, rules, analysis, fsQCA) are sent as JSON text in
multipart form fields next to the file, because a file upload cannot carry a JSON body.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Annotated, Any

import pandas as pd
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel, TypeAdapter, ValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.formparsers import MultiPartParser
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from api import convert
from api import models as m
from api.errors import (
    FIELD_NAMES,
    INTERNAL_ERROR_MESSAGE,
    ApiError,
    api_error_handler,
    error_response,
    http_error_handler,
    log_unexpected,
    request_validation_handler,
    validation_message,
)
from surveydoctor import __version__
from surveydoctor.flagging import merge_rules
from surveydoctor.io import DataError, load_csv
from surveydoctor.pipeline import Results, run_pipeline
from surveydoctor.report import build_report, respondent_table
from surveydoctor.schema import SchemaError, SurveySchema

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_ROWS = 50_000
# Room in a request for the multipart framing and the JSON settings fields.
REQUEST_OVERHEAD_BYTES = 1024 * 1024
MAX_REQUEST_BYTES = MAX_UPLOAD_BYTES + REQUEST_OVERHEAD_BYTES
DEFAULT_ORIGINS = ("http://localhost:5173", "http://127.0.0.1:5173")
SAMPLE_DIR = Path(__file__).resolve().parents[1] / "data" / "sample"

# Keep uploads in memory (BLUEPRINT §2 rule 7: no uploaded data is stored).
MultiPartParser.spool_max_size = MAX_REQUEST_BYTES

TOO_LARGE_MESSAGE = (
    "The file is larger than 10 MB. Remove columns you do not need (for example free-text "
    "answers) or split the responses into smaller files, and upload again."
)

ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    status: {"model": m.ErrorResponse} for status in (400, 413, 422, 500)
}

_RULES = TypeAdapter(dict[str, dict[str, bool | float]])
_ANALYSIS = TypeAdapter(m.AnalysisModel)


# --- Middleware -----------------------------------------------------------------------------


class RequestSizeLimit:
    """Refuse request bodies over ``max_bytes`` with 413, before they are read into memory.

    The Content-Length header is checked first; bodies sent without one are counted as
    they arrive.
    """

    def __init__(self, app: ASGIApp, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        length = dict(scope["headers"]).get(b"content-length")
        if length is not None and length.isdigit() and int(length) > self.max_bytes:
            await error_response("file_too_large", TOO_LARGE_MESSAGE)(scope, receive, send)
            return
        received = 0

        async def counted() -> Message:
            nonlocal received
            message = await receive()
            received += len(message.get("body", b""))
            if received > self.max_bytes:
                raise HTTPException(status_code=413, detail=TOO_LARGE_MESSAGE)
            return message

        await self.app(scope, counted, send)


class CatchUnexpected:
    """Answer unexpected errors with a plain 500 and log them without their message.

    Starlette's own handler for unexpected errors re-raises them after responding, so the
    server would print the full error, which can quote uploaded answers.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        started = False

        async def tracked(message: Message) -> None:
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, receive, tracked)
        except Exception as exc:  # noqa: BLE001 - every unexpected error ends here
            log_unexpected(exc, scope.get("method", ""), scope.get("path", ""))
            if not started:
                response = error_response("internal_error", INTERNAL_ERROR_MESSAGE)
                await response(scope, receive, send)


# --- Request parsing ------------------------------------------------------------------------


def read_csv(file: UploadFile) -> pd.DataFrame:
    """Read the uploaded CSV within the limits; refuse spreadsheets and binary files."""
    raw = file.file.read(MAX_UPLOAD_BYTES + 1)
    if len(raw) > MAX_UPLOAD_BYTES:
        raise ApiError("file_too_large", TOO_LARGE_MESSAGE)
    if raw.startswith((b"PK\x03\x04", b"\xd0\xcf\x11\xe0")):
        raise ApiError(
            "not_csv",
            "This looks like an Excel workbook, not a CSV file. In Excel choose File > Save As > "
            "'CSV UTF-8'; in Google Forms or Microsoft Forms, download the responses as .csv.",
        )
    if b"\x00" in raw:
        raise ApiError(
            "not_csv",
            "This is not a plain-text CSV file. Save the responses as 'CSV UTF-8' and upload "
            "that file.",
        )
    try:
        df = load_csv(raw)
    except DataError as exc:
        raise ApiError("invalid_csv", str(exc)) from exc
    if len(df) > MAX_ROWS:
        raise ApiError(
            "too_many_rows",
            f"The file has {len(df):,} responses; the limit is {MAX_ROWS:,}. Split the "
            "responses into smaller files and check each one.",
        )
    return df


def _json(value: str, field: str) -> Any:
    try:
        return json.loads(value)
    except json.JSONDecodeError as exc:
        name = FIELD_NAMES.get(field, field)
        raise ApiError(
            "invalid_json",
            f"{name[0].upper()}{name[1:]} is not valid JSON (line {exc.lineno}, column "
            f"{exc.colno}): {exc.msg}.",
        ) from exc


def parse_schema(value: str) -> SurveySchema:
    data = _json(value, "schema")
    try:
        model = m.SurveySchemaModel.model_validate(data, strict=False)
    except ValidationError as exc:
        raise ApiError("invalid_schema", validation_message(exc, "The schema fields")) from exc
    unknown = sorted(set(data) - set(m.SurveySchemaModel.model_fields))
    if unknown:
        raise ApiError("invalid_schema", f"Unknown schema fields: {', '.join(unknown)}.")
    try:
        return SurveySchema.from_dict(model.model_dump())
    except SchemaError as exc:
        raise ApiError("invalid_schema", str(exc)) from exc


def parse_rules(value: str | None) -> dict[str, dict[str, Any]] | None:
    if value is None:
        return None
    try:
        rules = _RULES.validate_python(_json(value, "rules"))
        merge_rules(rules)
    except ValidationError as exc:
        message = validation_message(exc, "The flag-rule settings")
        raise ApiError("invalid_settings", message) from exc
    except ValueError as exc:
        raise ApiError("invalid_settings", str(exc)) from exc
    return rules


def _validated(adapter: TypeAdapter | type[BaseModel], value: str, field: str, what: str) -> Any:
    data = _json(value, field)
    try:
        if isinstance(adapter, TypeAdapter):
            return adapter.validate_python(data)
        return adapter.model_validate(data)
    except ValidationError as exc:
        raise ApiError("invalid_settings", validation_message(exc, what)) from exc


def parse_analysis(value: str | None):
    if value is None:
        return None
    model = _validated(_ANALYSIS, value, "analysis", "The analysis settings")
    return convert.to_analysis(model)


def parse_fsqca(value: str | None):
    if value is None:
        return None
    model = _validated(m.FsqcaSpecModel, value, "fsqca", "The fsQCA settings")
    return convert.to_fsqca_spec(model)


def analyse(df: pd.DataFrame, schema: SurveySchema, **settings: Any) -> Results:
    """Run the pipeline; data that does not fit the schema is a 400, bad settings a 422."""
    try:
        return run_pipeline(df, schema, **settings)
    except DataError as exc:
        raise ApiError("data_mismatch", str(exc)) from exc
    except ValueError as exc:
        raise ApiError("invalid_settings", str(exc)) from exc


def download_name(upload_name: str | None, prefix: str, extension: str) -> str:
    """A safe download file name based on the uploaded file's name."""
    stem = re.sub(r"[^A-Za-z0-9_-]+", "_", Path(upload_name or "").stem).strip("_")[:60]
    return f"{prefix}_{stem or 'survey'}.{extension}"


def _attachment(name: str) -> dict[str, str]:
    return {"Content-Disposition": f'attachment; filename="{name}"'}


# --- Form fields ----------------------------------------------------------------------------

FileField = Annotated[UploadFile, File(description="The survey responses as a CSV file.")]
SchemaField = Annotated[
    str,
    Form(
        alias="schema",
        description="The survey schema as JSON text (see the SurveySchemaModel shape).",
    ),
]
RulesField = Annotated[
    str | None,
    Form(
        description=(
            'Optional flag-rule overrides as JSON text, e.g. {"even_odd": {"r_below": 0.2}} or '
            '{"psychsyn": {"enabled": false}}.'
        )
    ),
]
NFactorsField = Annotated[
    int | None,
    Form(description="Optional number of EFA factors; leave out to let parallel analysis decide."),
]
FsqcaField = Annotated[
    str | None,
    Form(description="Optional fsQCA settings as JSON text (see the FsqcaSpecModel shape)."),
]
AnalysisField = Annotated[
    str,
    Form(
        description=(
            "The analysis to check, as JSON text: "
            '{"type": "group_comparison", "scale": ..., "group_column": ..., "group_a": ..., '
            '"group_b": ...} or {"type": "correlation", "scale_x": ..., "scale_y": ...}.'
        )
    ),
]
OptionalAnalysisField = Annotated[
    str | None, Form(description="Optional analysis to check for robustness, as JSON text.")
]


# --- App ------------------------------------------------------------------------------------


def allowed_origins() -> list[str]:
    """Origins allowed by CORS: the comma-separated ALLOWED_ORIGINS variable, or the local
    development addresses of the website."""
    value = os.environ.get("ALLOWED_ORIGINS", "")
    origins = [o.strip().rstrip("/") for o in value.split(",") if o.strip()]
    return origins or list(DEFAULT_ORIGINS)


def create_app(origins: list[str] | None = None) -> FastAPI:
    app = FastAPI(
        title="SurveyDoctor API",
        version=__version__,
        description=(
            "Quality checks for rating-scale survey data. Stateless: every request carries its "
            "CSV, which is processed in memory and discarded. No uploaded data is stored."
        ),
    )
    app.add_exception_handler(ApiError, api_error_handler)
    app.add_exception_handler(RequestValidationError, request_validation_handler)
    app.add_exception_handler(StarletteHTTPException, http_error_handler)
    # Added innermost first: CORS is outermost, so error responses carry CORS headers too.
    app.add_middleware(CatchUnexpected)
    app.add_middleware(RequestSizeLimit, max_bytes=MAX_REQUEST_BYTES)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins if origins is not None else allowed_origins(),
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
        expose_headers=["Content-Disposition"],
    )

    @app.get("/api/health", response_model=m.HealthResponse)
    def health() -> m.HealthResponse:
        """Used by the website to check that the server is awake."""
        return m.HealthResponse(status="ok", version=__version__)

    @app.get("/api/sample", response_model=m.SampleResponse, responses=ERROR_RESPONSES)
    def sample() -> m.SampleResponse:
        """The bfi sample dataset as CSV text, with its schema."""
        csv_path, schema_path = SAMPLE_DIR / "bfi.csv", SAMPLE_DIR / "bfi_schema.json"
        if not (csv_path.exists() and schema_path.exists()):
            raise ApiError(
                "sample_missing",
                "The sample data is not on the server. Run 'python scripts/download_data.py' "
                "in the backend folder.",
            )
        return m.SampleResponse(
            filename=csv_path.name,
            csv=csv_path.read_text(encoding="utf-8"),
            schema=convert.schema_model(SurveySchema.load(schema_path)),
        )

    @app.post("/api/inspect", response_model=m.InspectResponse, responses=ERROR_RESPONSES)
    def inspect(file: FileField) -> m.InspectResponse:
        """Columns, a 10-row preview without personal columns, short codes and the
        proposed answer-label mapping."""
        return convert.inspect_response(read_csv(file), file.filename)

    @app.post("/api/analyze", response_model=m.AnalyzeResponse, responses=ERROR_RESPONSES)
    def analyze(
        file: FileField,
        schema_text: SchemaField,
        rules: RulesField = None,
        n_factors: NFactorsField = None,
        fsqca: FsqcaField = None,
    ) -> m.AnalyzeResponse:
        """Every check on the survey: flags, reliability, structure, sample sensitivity and,
        if requested, the fsQCA."""
        survey_schema, rule_settings = parse_schema(schema_text), parse_rules(rules)
        spec = parse_fsqca(fsqca)
        results = analyse(
            read_csv(file), survey_schema, rules=rule_settings, n_factors=n_factors, fsqca_spec=spec
        )
        return convert.analyze_response(results)

    @app.post("/api/robustness", response_model=m.RobustnessResponse, responses=ERROR_RESPONSES)
    def robustness(
        file: FileField,
        schema_text: SchemaField,
        analysis: AnalysisField,
        rules: RulesField = None,
        n_factors: NFactorsField = None,
    ) -> m.RobustnessResponse:
        """The declared analysis on all respondents and without each flag variant, the
        verdict, and the verdict band updated with it. Send the same rules and n_factors as
        to /api/analyze so the verdict band matches."""
        survey_schema, rule_settings = parse_schema(schema_text), parse_rules(rules)
        spec = parse_analysis(analysis)
        results = analyse(
            read_csv(file), survey_schema, rules=rule_settings, n_factors=n_factors, analysis=spec
        )
        return convert.robustness_response(results)

    @app.post(
        "/api/report",
        response_class=HTMLResponse,
        responses={**ERROR_RESPONSES, 200: {"content": {"text/html": {}}}},
    )
    def report(
        file: FileField,
        schema_text: SchemaField,
        rules: RulesField = None,
        n_factors: NFactorsField = None,
        analysis: OptionalAnalysisField = None,
        fsqca: FsqcaField = None,
    ) -> HTMLResponse:
        """The self-contained HTML report, as a file download."""
        survey_schema, rule_settings = parse_schema(schema_text), parse_rules(rules)
        spec, fsqca_spec = parse_analysis(analysis), parse_fsqca(fsqca)
        df = read_csv(file)
        results = analyse(
            df, survey_schema, rules=rule_settings, n_factors=n_factors, analysis=spec,
            fsqca_spec=fsqca_spec,
        )  # fmt: skip
        html = build_report(results, source_name=file.filename)
        name = download_name(file.filename, "surveydoctor_report", "html")
        return HTMLResponse(html, headers=_attachment(name))

    @app.post(
        "/api/export/flags",
        response_class=Response,
        responses={**ERROR_RESPONSES, 200: {"content": {"text/csv": {}}}},
    )
    def export_flags(
        file: FileField, schema_text: SchemaField, rules: RulesField = None
    ) -> Response:
        """Respondent-level indices, flags and reasons as CSV. Personal columns are never
        included."""
        survey_schema, rule_settings = parse_schema(schema_text), parse_rules(rules)
        results = analyse(read_csv(file), survey_schema, rules=rule_settings)
        body = respondent_table(results).to_csv(index=False, lineterminator="\n")
        name = download_name(file.filename, "surveydoctor_flags", "csv")
        return Response(
            body.encode("utf-8-sig"), media_type="text/csv; charset=utf-8",
            headers=_attachment(name),
        )  # fmt: skip

    return app


app = create_app()
