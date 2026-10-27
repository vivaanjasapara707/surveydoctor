"""Tests for report.py and charts.py (Stage 10): the report renders every section, is
self-contained, escapes user text, and its charts are valid PNGs."""

from __future__ import annotations

import base64
import re
from datetime import UTC, datetime

import pandas as pd
import pytest

from surveydoctor.charts import TOKENS, composite_histogram, scree_plot
from surveydoctor.io import load_csv
from surveydoctor.pipeline import run_pipeline
from surveydoctor.report import _issue_rows, build_report, rule_description
from surveydoctor.robustness import GroupComparison
from surveydoctor.schema import SurveySchema
from surveydoctor.structure import ParallelAnalysis
from tests.conftest import BFI_CSV, BFI_SCHEMA

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
WHEN = datetime(2026, 10, 27, 9, 30, tzinfo=UTC)


@pytest.fixture(scope="module")
def bfi_html() -> str:
    if not BFI_CSV.exists():
        pytest.skip("data/sample/bfi.csv not found. Run: python scripts/download_data.py")
    schema = SurveySchema.load(BFI_SCHEMA)
    results = run_pipeline(
        load_csv(BFI_CSV), schema, analysis=GroupComparison("Neuroticism", "gender", 1, 2),
        pa_iterations=20,
    )  # fmt: skip
    return build_report(results, "bfi.csv", WHEN)


# --- Charts -------------------------------------------------------------------------------


def test_histogram_is_png_with_alt_text() -> None:
    scores = pd.Series([0.1, 0.2, 0.2, 0.5, 0.85, 0.9, None])
    chart = composite_histogram(scores, bins=10)
    assert base64.b64decode(chart.png_base64).startswith(PNG_MAGIC)
    assert chart.data_uri.startswith("data:image/png;base64,")
    # 6 scores; bin 0.20-0.30 holds two (0.2, 0.2); two scores are 0.80 or more.
    assert chart.alt == (
        "Histogram of composite scores for 6 respondents in 10 bins from 0 to 1. The largest "
        "bin is 0.20 to 0.30 with 2 respondents; 2 respondents score 0.80 or more."
    )


def test_scree_alt_text_describes_suggestion() -> None:
    scree = pd.DataFrame(
        {"observed": [3.0, 1.5, 0.6, 0.5], "threshold": [1.3, 1.2, 1.1, 1.0]},
        index=pd.Index([1, 2, 3, 4], name="position"),
    )
    pa = ParallelAnalysis(scree=scree, n_suggested=2, n_kaiser=2, n_iterations=10,
                          percentile=95.0, seed=42)  # fmt: skip
    chart = scree_plot(pa)
    assert base64.b64decode(chart.png_base64).startswith(PNG_MAGIC)
    assert "up to position 2 (1.50 against 1.20), so 2 factors are suggested" in chart.alt


def test_scree_with_no_factors() -> None:
    scree = pd.DataFrame({"observed": [0.9, 0.8], "threshold": [1.2, 1.1]},
                         index=pd.Index([1, 2], name="position"))  # fmt: skip
    pa = ParallelAnalysis(scree, 0, 0, 10, 95.0, 42)
    assert "No observed eigenvalue is above" in scree_plot(pa).alt


# --- Helpers ------------------------------------------------------------------------------


def test_rule_descriptions() -> None:
    assert rule_description("longstring", {"share_of_items": 0.5}, 25) == (
        "13 or more identical answers in a row (50% of 25 questions)"
    )
    assert rule_description("mahalanobis", {"p_below": 0.001}, 25) == (
        "answer pattern unusual at p < 0.001"
    )
    assert rule_description("even_odd", {"r_below": 0.3}, 25) == "correlation below 0.30"
    assert rule_description("seconds_per_item", {"seconds_below": 2.0}, 25) == (
        "fewer than 2 seconds per question"
    )


def test_issue_rows_group_per_column_issues() -> None:
    from surveydoctor.io import DataIssue

    issues = [
        DataIssue("missing_answers", 3, "3 blank", column="q1"),
        DataIssue("missing_answers", 2, "2 blank", column="q2"),
        DataIssue("invalid_answers", 1, "1 invalid", column="q2", examples=["x"]),
        DataIssue("empty_rows_removed", 4, "4 respondents had no valid answer."),
    ]
    rows = _issue_rows(issues)
    assert rows[0] == {"what": "Blank or NA answers in 2 columns", "detail": "q1 3 · q2 2",
                       "count": "5"}  # fmt: skip
    assert rows[1]["detail"] == "q2 1. Examples: x"
    assert rows[2] == {"what": "4 respondents had no valid answer.", "detail": "", "count": "4"}


# --- The bfi report -----------------------------------------------------------------------


def test_report_has_every_section(bfi_html: str) -> None:
    for heading in ["1 Summary", "2 Data checks", "3 Careless responding", "4 Reliability",
                    "5 Factor structure", "6 Sample sensitivity", "7 Robustness",
                    "8 Limitations", "9 Methods and references"]:  # fmt: skip
        assert f">{heading}</h2>" in bfi_html


def test_report_verdict_on_bfi(bfi_html: str) -> None:
    # 72 respondents flagged by 2+ rules and Openness alpha 0.60 -> Review (design.md §5).
    assert "Review before drawing conclusions" in bfi_html
    assert "72 respondents were flagged by two or more rules." in bfi_html
    assert "Alpha is below 0.70 for Openness." in bfi_html
    assert "verdict s-review" in bfi_html


def test_report_contains_real_numbers(bfi_html: str) -> None:
    assert "686 of 2,800 respondents (24.5%) were flagged by at least one rule" in bfi_html
    assert "Showing 50 of 686 flagged respondents" in bfi_html
    assert "χ² = 18,146.07, df = 300, p &lt; 0.001" in bfi_html
    assert "Parallel analysis suggests 5 factors." in bfi_html
    assert "Stable: the difference in Neuroticism between gender = 1 and gender = 2" in bfi_html
    # Never a bare "-0.00"; a flag reason may show "-0.001" (see flagging._format_r).
    assert not re.search(r"-0\.00(?!\d)", bfi_html)


def test_report_is_self_contained(bfi_html: str) -> None:
    # No external requests: no http(s) URLs in src/href, no external stylesheets or scripts.
    assert not re.search(r'(src|href)="https?://', bfi_html)
    assert "<script" not in bfi_html
    assert bfi_html.count("data:image/png;base64,") == 2
    assert bfi_html.count("data:font/woff2;base64,") == 3
    assert "No data was stored." in bfi_html
    assert "27 October 2026, 09:30 UTC" in bfi_html


def test_report_uses_design_tokens(bfi_html: str) -> None:
    for name, value in TOKENS.items():
        assert f"--{name}: {value};" in bfi_html


def test_report_escapes_user_text() -> None:
    schema = SurveySchema(
        items=["q1", "q2", "q3", "q4"], scales={"A <b>": ["q1", "q2"], "B": ["q3", "q4"]},
        reverse_items=[], scale_min=1, scale_max=5, id_column="id",
    )  # fmt: skip
    df = pd.DataFrame(
        {"id": ["<script>x</script>"] + [f"r{i}" for i in range(29)],
         **{q: [(i * (j + 2)) % 5 + 1 for i in range(30)] for j, q in enumerate(schema.items)}}
    )  # fmt: skip
    html = build_report(run_pipeline(df, schema, pa_iterations=5), "<evil>.csv", WHEN)
    assert "<evil>" not in html and "&lt;evil&gt;" in html
    assert "<script>x</script>" not in html
    assert "A &lt;b&gt;" in html


def test_pearson_note_appears_once(bfi_html: str) -> None:
    assert bfi_html.count("Pearson correlations, which treat ordinal answers") == 1
