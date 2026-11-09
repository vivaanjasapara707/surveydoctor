"""Tests for the FastAPI layer (BLUEPRINT §7.11, §8.4): every endpoint with the bfi sample
and the messy Google Forms-style fixture, the error cases, the limits, CORS, and the rule
that no personal information or uploaded data leaks into responses or logs."""

from __future__ import annotations

import csv
import io
import json
import logging
import math

import pytest
from fastapi.testclient import TestClient

import api.main
from api.main import MAX_ROWS, MAX_UPLOAD_BYTES, allowed_origins, create_app, download_name
from surveydoctor import __version__
from surveydoctor.fsqca import FsqcaSpec
from surveydoctor.io import load_csv
from surveydoctor.pipeline import run_pipeline
from surveydoctor.schema import SurveySchema
from tests.conftest import BFI_CSV, BFI_SCHEMA, GOOGLE_FORMS_CSV

CONDITIONS = ["Agreeableness", "Conscientiousness", "Extraversion", "Openness"]
FSQCA = json.dumps({"outcome": "Neuroticism", "conditions": CONDITIONS})
GENDER = json.dumps(
    {
        "type": "group_comparison",
        "scale": "Neuroticism",
        "group_column": "gender",
        "group_a": 1,
        "group_b": 2,
    }
)
PERSONAL = ("@example.com", "Alex P", "Sam K", "Eva L")


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(create_app())


@pytest.fixture(scope="module")
def bfi() -> tuple[bytes, str]:
    if not BFI_CSV.exists():
        pytest.skip("data/sample/bfi.csv not found. Run: python scripts/download_data.py")
    return BFI_CSV.read_bytes(), BFI_SCHEMA.read_text(encoding="utf-8")


def post(client: TestClient, path: str, csv_bytes: bytes, name: str = "survey.csv", **fields):
    data = {k: v for k, v in fields.items() if v is not None}
    return client.post(path, files={"file": (name, csv_bytes, "text/csv")}, data=data)


@pytest.fixture(scope="module")
def bfi_analysis(client, bfi) -> dict:
    csv_bytes, schema = bfi
    response = post(client, "/api/analyze", csv_bytes, "bfi.csv", schema=schema, fsqca=FSQCA)
    assert response.status_code == 200, response.text
    return response.json()


# --- Google Forms-style fixture: schema built the way the website will build it --------------


@pytest.fixture(scope="module")
def forms_inspect(client) -> dict:
    response = post(client, "/api/inspect", GOOGLE_FORMS_CSV.read_bytes(), "responses.csv")
    assert response.status_code == 200, response.text
    return response.json()


@pytest.fixture(scope="module")
def forms_schema(forms_inspect) -> str:
    """Short codes and labels from /api/inspect; the user maps the typo 'Strongly agre'."""
    label_map = dict(forms_inspect["labels"]["label_map"])
    label_map["strongly agre"] = 5
    items = ["Q1", "Q2", "Q3", "Q4", "Q5", "Q6", "Q7"]
    return json.dumps(
        {
            "items": items,
            "scales": {"Teamwork": items[:4], "Course": items[4:]},
            "reverse_items": ["Q2"],
            "scale_min": 1,
            "scale_max": 5,
            "label_map": label_map,
            "question_text": forms_inspect["question_text"],
        }
    )


# --- Health, sample, OpenAPI ------------------------------------------------------------------


def test_health(client) -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": __version__}


def test_sample_returns_csv_and_a_valid_schema(client, bfi) -> None:
    body = client.get("/api/sample").json()
    assert body["filename"] == "bfi.csv"
    # Newlines are normalised to "\n" when the file is read as text; compare line by line.
    # (Comparing into a variable first keeps pytest from diffing 175 KB of text on failure.)
    same = body["csv"].splitlines() == bfi[0].decode("utf-8").splitlines()
    assert same
    schema = SurveySchema.from_dict(body["schema"])
    assert schema == SurveySchema.load(BFI_SCHEMA)


def test_openapi_and_docs(client) -> None:
    spec = client.get("/openapi.json").json()
    assert set(spec["paths"]) == {
        "/api/health", "/api/sample", "/api/inspect", "/api/analyze", "/api/robustness",
        "/api/report", "/api/export/flags",
    }  # fmt: skip
    schemas = spec["components"]["schemas"]
    assert {"AnalyzeResponse", "FsqcaModel", "RobustnessResponse", "ErrorResponse"} <= set(schemas)
    assert "fsqca" in schemas["AnalyzeResponse"]["properties"]
    analyze_errors = spec["paths"]["/api/analyze"]["post"]["responses"]
    assert analyze_errors["422"]["content"]["application/json"]["schema"]["$ref"].endswith(
        "/ErrorResponse"
    )
    assert client.get("/docs").status_code == 200


# --- /api/inspect -----------------------------------------------------------------------------


def test_inspect_bfi(client, bfi) -> None:
    body = post(client, "/api/inspect", bfi[0], "bfi.csv").json()
    assert (body["filename"], body["n_rows"], body["n_columns"]) == ("bfi.csv", 2800, 29)
    suggested = {c["header"] for c in body["columns"] if c["suggested_item"]}
    assert set(SurveySchema.load(BFI_SCHEMA).items) <= suggested
    assert body["personal_columns"] == []
    assert body["labels"]["label_set"] is None and body["labels"]["label_map"] is None
    assert len(body["preview"]["rows"]) == 10
    assert body["preview"]["rows"][0][body["preview"]["columns"].index("education")] is None


def test_inspect_google_forms(forms_inspect) -> None:
    body = forms_inspect
    assert (body["n_rows"], body["n_columns"]) == (12, 12)
    assert body["personal_columns"] == ["Email Address", "Your name"]
    by_header = {c["header"]: c for c in body["columns"]}
    for header in body["personal_columns"]:
        assert by_header[header]["code"] is None and by_header[header]["distinct_values"] == []
        assert header not in body["preview"]["columns"]
    assert body["question_text"]["Q1"] == "I enjoy working in teams."
    assert body["labels"]["label_set"] == "agreement_5"
    assert body["labels"]["unrecognised"] == ["Strongly agre"]
    assert not any(p in json.dumps(body) for p in PERSONAL)


# --- /api/analyze -----------------------------------------------------------------------------


def test_analyze_bfi_sections(bfi_analysis) -> None:
    body = bfi_analysis
    assert body["version"] == __version__
    assert body["overview"] == {
        "n_respondents": 2800, "n_items": 25, "n_scales": 5, "n_flagged": 686,
        "n_flagged_two_rules": 72,
    }  # fmt: skip
    assert body["verdict"]["status"] in {"clear", "review", "problem"}
    assert [c["check"] for c in body["verdict"]["checks"]] == [
        "careless", "reliability", "structure", "robustness",
    ]  # fmt: skip
    assert [r["scale"] for r in body["reliability"]] == list(SurveySchema.load(BFI_SCHEMA).scales)
    assert all(r["sentence"].startswith("Alpha for") for r in body["reliability"])
    structure = body["structure"]
    assert structure["n_factors"] == 5 and structure["n_factors_source"] == "parallel analysis"
    assert len(structure["parallel"]["scree"]) == 25 and len(structure["efa"]["items"]) == 25
    assert len(structure["efa"]["factor_correlations"]) == 5
    assert [s["test"] for s in body["sensitivity"]] == ["two_groups", "correlation", "anova"]
    assert body["limitations"][0].startswith("Statistical checks cannot fix who was sampled")
    assert body["warnings"]


def test_analyze_careless_section(bfi_analysis) -> None:
    careless = bfi_analysis["careless"]
    assert careless["n_flagged"] == 686 and careless["n_shown"] == len(careless["flagged"]) == 200
    order = [(r["n_rules"], r["composite"]) for r in careless["flagged"]]
    assert order == sorted(order, reverse=True)
    top = careless["flagged"][0]
    assert top["n_rules"] == len(top["rules"]) >= 2 and top["reasons"]
    statuses = {r["name"]: r["status"] for r in careless["rules"]}
    assert statuses["seconds_per_item"] == "not applied (no completion-time column)"
    counts = {r["name"]: r["count"] for r in careless["rules"]}
    assert counts["seconds_per_item"] is None and counts["longstring"] >= 0
    assert len(careless["composite_scores"]) == 2800
    histogram = careless["histogram"]
    assert len(histogram["bin_edges"]) == 21 and len(histogram["counts"]) == 20
    assert sum(histogram["counts"]) == sum(s is not None for s in careless["composite_scores"])


def test_analyze_values_come_from_the_pipeline(bfi_analysis) -> None:
    """The API is a thin layer: its numbers are the pipeline's numbers."""
    schema = SurveySchema.load(BFI_SCHEMA)
    spec = FsqcaSpec("Neuroticism", tuple(CONDITIONS))
    results = run_pipeline(load_csv(BFI_CSV), schema, fsqca_spec=spec)
    for r in bfi_analysis["reliability"]:
        assert r["alpha"] == results.reliability[r["scale"]].alpha
        assert r["omega_total"] == results.reliability[r["scale"]].omega_total
    assert bfi_analysis["structure"]["kmo"]["overall"] == results.structure.kmo.overall
    composite = [None if math.isnan(v) else v for v in results.composite]
    same_composite = bfi_analysis["careless"]["composite_scores"] == composite
    assert same_composite
    assert bfi_analysis["warnings"] == [
        w for w in results.warnings if not w.startswith("Factor analysis uses Pearson")
    ]


def test_analyze_fsqca_section(bfi_analysis) -> None:
    f = bfi_analysis["fsqca"]
    assert f["spec"]["conditions"] == CONDITIONS and f["spec"]["pri_threshold"] == 0.7
    assert (f["n_used"], f["n_excluded"], f["n_at_crossover"]) == (2782, 18, 792)
    assert f["anchors"]["Neuroticism"]["source"] == "percentiles"
    assert len(f["necessity"]) == 8
    main = f["main"]
    assert len(main["truth_table"]) == 16 and main["truth_table"][0]["row"] == 1
    assert set(main["truth_table"][0]["configuration"]) == set(CONDITIONS)
    # Recorded in Stage 10B: no row reaches PRI 0.70 on bfi, so there is no solution.
    assert main["has_solution"] is False and main["complex"]["models"] == []
    assert [c["run"]["label"] for c in f["robustness"]["comparisons"]] == [
        "any_rule", "two_rules", "composite_top10",
    ]  # fmt: skip
    assert f["robustness"]["verdict"] == "no solution"
    assert len(f["calibration"]["comparisons"]) == 3
    assert f["sentences"]["solution"].startswith("No truth-table row reached the thresholds")
    assert len(f["limitations"]) == 3


def test_analyze_fsqca_with_a_solution(client, bfi) -> None:
    """PRI 0.55 gives the solution recorded in Stage 10B (docs/decisions.md)."""
    spec = json.dumps({"outcome": "Neuroticism", "conditions": CONDITIONS, "pri_threshold": 0.55})
    body = post(client, "/api/analyze", bfi[0], schema=bfi[1], fsqca=spec).json()
    complex_solution = body["fsqca"]["main"]["complex"]
    assert complex_solution["has_solution"] is True
    model = complex_solution["models"][0]
    assert model["expression"] == (
        "~Agreeableness*~Conscientiousness + ~Conscientiousness*~Extraversion"
    )
    assert round(model["consistency"], 3) == 0.766 and round(model["coverage"], 3) == 0.624
    assert model["paths"][0]["literals"][0] == {"condition": "Agreeableness", "present": False}


def test_analyze_without_fsqca_and_with_settings(client, bfi) -> None:
    rules = json.dumps({"psychsyn": {"enabled": False}, "even_odd": {"r_below": 0.2}})
    body = post(client, "/api/analyze", bfi[0], schema=bfi[1], rules=rules, n_factors="3").json()
    assert body["fsqca"] is None
    rules_used = {r["name"]: r for r in body["careless"]["rules"]}
    assert rules_used["psychsyn"]["status"] == "switched off"
    assert rules_used["psychsyn"]["count"] is None
    assert rules_used["even_odd"]["settings"] == {"r_below": 0.2}
    assert body["structure"]["n_factors"] == 3 and body["structure"]["n_factors_source"] == "user"


def test_analyze_google_forms(client, forms_schema) -> None:
    response = post(
        client, "/api/analyze", GOOGLE_FORMS_CSV.read_bytes(), schema=forms_schema,
        fsqca=json.dumps({"outcome": "Course", "conditions": ["Teamwork", "Course"]}),
    )  # fmt: skip
    assert response.status_code == 422  # the outcome cannot also be a condition
    response = post(client, "/api/analyze", GOOGLE_FORMS_CSV.read_bytes(), schema=forms_schema)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["overview"]["n_respondents"] == 11  # the all-blank row is removed and counted
    kinds = {i["kind"] for i in body["issues"]}
    assert {"empty_rows_removed", "personal_columns_excluded", "invalid_answers"} <= kinds
    invalid = [i for i in body["issues"] if i["kind"] == "invalid_answers"]
    assert invalid == [
        {
            "kind": "invalid_answers", "count": 1, "column": "Q5", "examples": ["6"],
            "message": invalid[0]["message"],
        }
    ]  # fmt: skip
    assert not any(p in response.text for p in PERSONAL)


# --- /api/robustness --------------------------------------------------------------------------


def test_robustness_group_comparison(client, bfi) -> None:
    response = post(client, "/api/robustness", bfi[0], schema=bfi[1], analysis=GENDER)
    assert response.status_code == 200, response.text
    body = response.json()
    r = body["robustness"]
    assert r["analysis"]["type"] == "group_comparison" and r["analysis"]["group_a"] == 1
    assert [v["variant"] for v in r["variants"]] == [
        "all", "any_rule", "two_rules", "composite_top10",
    ]  # fmt: skip
    assert r["variants"][1]["n_excluded"] == 686
    assert r["verdict"] in {"stable", "sensitive", "unstable"}
    assert r["sentence"].endswith(r["caveat"])
    assert r["estimate_label"] == "Difference (A − B)"
    robustness_chip = [c for c in body["verdict"]["checks"] if c["check"] == "robustness"][0]
    assert robustness_chip["status"] != "not_checked"


def test_robustness_correlation_google_forms(client, forms_schema) -> None:
    analysis = json.dumps({"type": "correlation", "scale_x": "Teamwork", "scale_y": "Course"})
    response = post(
        client, "/api/robustness", GOOGLE_FORMS_CSV.read_bytes(), schema=forms_schema,
        analysis=analysis,
    )  # fmt: skip
    assert response.status_code == 200, response.text
    r = response.json()["robustness"]
    assert r["analysis"] == {"type": "correlation", "scale_x": "Teamwork", "scale_y": "Course"}
    assert r["variants"][0]["n"] <= 11
    assert not any(p in response.text for p in PERSONAL)


# --- /api/report and /api/export/flags --------------------------------------------------------


def test_report_download(client, bfi) -> None:
    response = post(
        client, "/api/report", bfi[0], "my survey (final).csv", schema=bfi[1], fsqca=FSQCA,
        analysis=GENDER,
    )  # fmt: skip
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert response.headers["content-disposition"] == (
        'attachment; filename="surveydoctor_report_my_survey_final.html"'
    )
    html = response.text
    assert html.startswith("<!DOCTYPE html>") or html.lstrip().lower().startswith("<!doctype html")
    assert "my survey (final).csv" in html and "fsQCA" in html and "No data was stored" in html


def test_report_google_forms_has_no_personal_data(client, forms_schema) -> None:
    response = post(client, "/api/report", GOOGLE_FORMS_CSV.read_bytes(), schema=forms_schema)
    assert response.status_code == 200
    assert not any(p in response.text for p in PERSONAL)


def _read_export(response) -> list[dict[str, str]]:
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/csv")
    return list(csv.DictReader(io.StringIO(response.content.decode("utf-8-sig"))))


def test_export_flags_bfi(client, bfi) -> None:
    response = post(client, "/api/export/flags", bfi[0], "bfi.csv", schema=bfi[1])
    assert response.headers["content-disposition"] == (
        'attachment; filename="surveydoctor_flags_bfi.csv"'
    )
    rows = _read_export(response)
    assert len(rows) == 2800
    columns = list(rows[0])
    assert columns[:2] == ["respondent", "csv_row"]
    expected = {"longstring", "mahalanobis_p", "composite", "flag_longstring", "reasons"}
    assert expected <= set(columns)
    assert not {"gender", "education", "age"} & set(columns)
    assert (rows[0]["respondent"], rows[0]["csv_row"]) == ("61617", "2")
    assert sum(r["flagged"] == "True" for r in rows) == 686


def test_export_flags_google_forms_rows_and_privacy(client, forms_schema) -> None:
    response = post(client, "/api/export/flags", GOOGLE_FORMS_CSV.read_bytes(), schema=forms_schema)
    rows = _read_export(response)
    # CSV row 11 (all answers blank) was removed; the rows after it keep their own numbers.
    assert [r["csv_row"] for r in rows] == [str(n) for n in [*range(2, 11), 12, 13]]
    assert rows[-1]["respondent"] == "row 13"
    assert not any(p in response.text for p in PERSONAL)
    assert "Timestamp" not in rows[0] and "Any other comments?" not in rows[0]


# --- Errors -----------------------------------------------------------------------------------


def assert_error(response, status: int, code: str, *fragments: str) -> str:
    assert response.status_code == status, response.text
    body = response.json()
    assert set(body) == {"code", "message"} and body["code"] == code
    for fragment in fragments:
        assert fragment in body["message"]
    return body["message"]


def test_missing_file_and_schema(client) -> None:
    assert_error(
        client.post("/api/analyze", data={"schema": "{}"}), 422, "invalid_request",
        "the CSV file ('file') is missing",
    )  # fmt: skip
    assert_error(
        client.post("/api/analyze", files={"file": ("a.csv", b"q\n1\n")}), 422,
        "invalid_request", "the survey schema ('schema') is missing",
    )  # fmt: skip
    assert_error(
        client.post("/api/robustness", files={"file": ("a.csv", b"q\n1\n")}, data={"schema": "{}"}),
        422, "invalid_request", "('analysis') is missing",
    )  # fmt: skip


def test_invalid_csv_files(client, bfi) -> None:
    schema = bfi[1]
    assert_error(post(client, "/api/inspect", b""), 400, "invalid_csv", "The file is empty")
    assert_error(post(client, "/api/inspect", b"a,b\n1,2,3\n"), 400, "invalid_csv", "Line 2")
    assert_error(
        post(client, "/api/analyze", b"PK\x03\x04rest-of-a-zip", schema=schema), 400, "not_csv",
        "Excel workbook",
    )  # fmt: skip
    assert_error(post(client, "/api/inspect", "q\n1\n".encode("utf-16")), 400, "not_csv")


def test_schema_errors(client, bfi) -> None:
    csv_bytes, schema = bfi
    good = json.loads(schema)
    cases = [
        ("{", 422, "invalid_json", "not valid JSON"),
        (json.dumps({**good, "scale_min": 6, "scale_max": 1}), 422, "invalid_schema",
         "must be smaller"),
        (json.dumps({**good, "colour": "red"}), 422, "invalid_schema", "Unknown schema fields"),
        (json.dumps({**good, "items": "A1"}), 422, "invalid_schema", "'items'"),
        (json.dumps({k: v for k, v in good.items() if k != "scales"}), 422, "invalid_schema",
         "'scales' is missing"),
        (json.dumps({**good, "items": [*good["items"], "Z9"]}), 400, "data_mismatch",
         "not in the CSV: Z9"),
    ]  # fmt: skip
    for value, status, code, fragment in cases:
        assert_error(post(client, "/api/analyze", csv_bytes, schema=value), status, code, fragment)


def test_settings_errors(client, bfi) -> None:
    csv_bytes, schema = bfi
    bad_rules = [
        (json.dumps({"nope": {}}), "Unknown flag rule 'nope'"),
        (json.dumps({"even_odd": {"r_below": "low"}}), "flag-rule settings are not valid"),
        (json.dumps({"mahalanobis": {"p_below": 2}}), "between 0 and 1"),
        ("[1, 2]", "flag-rule settings are not valid"),
    ]
    for rules, fragment in bad_rules:
        response = post(client, "/api/analyze", csv_bytes, schema=schema, rules=rules)
        assert_error(response, 422, "invalid_settings", fragment)
    bad_analyses = [
        (json.dumps({"type": "anova"}), "'type' must be one of"),
        (json.dumps({"type": "correlation", "scale_x": "Openness"}), "'correlation.scale_y'"),
        (json.dumps({**json.loads(GENDER), "group_column": "id2"}), "not available for grouping"),
        (json.dumps({**json.loads(GENDER), "group_b": 9}), "No respondent has the value '9'"),
    ]
    for analysis, fragment in bad_analyses:
        response = post(client, "/api/robustness", csv_bytes, schema=schema, analysis=analysis)
        assert_error(response, 422, "invalid_settings", fragment)
    one_condition = json.dumps({"outcome": "Neuroticism", "conditions": ["Openness"]})
    assert_error(
        post(client, "/api/analyze", csv_bytes, schema=schema, fsqca=one_condition), 422,
        "invalid_settings",
    )  # fmt: skip
    assert_error(
        post(client, "/api/analyze", csv_bytes, schema=schema, fsqca='{"outcome": "N"}'), 422,
        "invalid_settings", "'conditions' is missing",
    )  # fmt: skip
    assert_error(
        post(client, "/api/analyze", csv_bytes, schema=schema, n_factors="many"), 422,
        "invalid_request", "('n_factors')",
    )  # fmt: skip
    assert_error(
        post(client, "/api/analyze", csv_bytes, schema=schema, n_factors="30"), 422,
        "invalid_settings",
    )  # fmt: skip


def test_unknown_route_and_method(client) -> None:
    assert_error(client.get("/api/nothing"), 404, "not_found")
    assert_error(client.get("/api/analyze"), 405, "method_not_allowed")


# --- Limits -----------------------------------------------------------------------------------


def test_file_over_10_mb_is_refused(client) -> None:
    big = b"q\n" + b"1\n" * (MAX_UPLOAD_BYTES // 2)
    assert len(big) > MAX_UPLOAD_BYTES
    assert_error(post(client, "/api/inspect", big), 413, "file_too_large", "10 MB")


def test_file_just_under_the_request_limit_is_checked_after_reading(client) -> None:
    """A file a little over 10 MB but within the request allowance is refused by the
    file-size check rather than the request-size check."""
    big = b"q\n" + b"1" * (MAX_UPLOAD_BYTES + 10) + b"\n"
    assert_error(post(client, "/api/inspect", big), 413, "file_too_large")


def test_body_without_content_length_is_counted(monkeypatch) -> None:
    monkeypatch.setattr(api.main, "MAX_REQUEST_BYTES", 1000)
    small_client = TestClient(create_app())

    def chunks():
        for _ in range(20):
            yield b"x" * 100

    response = small_client.post(
        "/api/inspect", content=chunks(),
        headers={"content-type": "multipart/form-data; boundary=abc"},
    )  # fmt: skip
    assert_error(response, 413, "file_too_large")


def test_too_many_rows(client) -> None:
    rows = b"q\n" + b"1\n" * (MAX_ROWS + 1)
    assert_error(post(client, "/api/inspect", rows), 413, "too_many_rows", "50,000")
    ok = b"q\n" + b"1\n" * MAX_ROWS
    assert post(client, "/api/inspect", ok).status_code == 200


# --- Privacy and unexpected errors ------------------------------------------------------------


def test_unexpected_error_hides_details_and_logs_no_data(monkeypatch, caplog, forms_schema) -> None:
    secret = "alex.p@example.com answered Strongly agree"

    def broken(*args, **kwargs):
        raise RuntimeError(secret)

    monkeypatch.setattr(api.main, "run_pipeline", broken)
    with caplog.at_level(logging.DEBUG):
        response = post(
            TestClient(create_app()), "/api/analyze", GOOGLE_FORMS_CSV.read_bytes(),
            schema=forms_schema,
        )  # fmt: skip
    message = assert_error(response, 500, "internal_error", "Nothing was stored")
    assert secret not in message
    assert "Unexpected RuntimeError" in caplog.text
    assert "example.com" not in caplog.text and "Strongly agree" not in caplog.text


def test_uploads_stay_in_memory() -> None:
    from starlette.formparsers import MultiPartParser

    assert MultiPartParser.spool_max_size >= MAX_UPLOAD_BYTES


# --- CORS and helpers -------------------------------------------------------------------------


def test_cors_allows_only_the_configured_origin() -> None:
    cors_client = TestClient(create_app(["https://surveydoctor.example"]))
    allowed = cors_client.get("/api/health", headers={"Origin": "https://surveydoctor.example"})
    assert allowed.headers["access-control-allow-origin"] == "https://surveydoctor.example"
    other = cors_client.get("/api/health", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in other.headers
    error = cors_client.get("/api/nothing", headers={"Origin": "https://surveydoctor.example"})
    assert error.headers["access-control-allow-origin"] == "https://surveydoctor.example"


def test_allowed_origins_from_environment(monkeypatch) -> None:
    monkeypatch.setenv("ALLOWED_ORIGINS", " https://a.example/ , https://b.example ")
    assert allowed_origins() == ["https://a.example", "https://b.example"]
    monkeypatch.delenv("ALLOWED_ORIGINS")
    assert allowed_origins() == ["http://localhost:5173", "http://127.0.0.1:5173"]


def test_download_name() -> None:
    assert download_name("Survey 2026 (final).csv", "x", "csv") == "x_Survey_2026_final.csv"
    assert download_name(None, "x", "html") == "x_survey.html"
    assert download_name('"; evil.csv', "x", "csv") == "x_evil.csv"
