"""End-to-end test of the pipeline on the bfi sample (BLUEPRINT §8.4): every section of
Results is populated and the HTML report renders."""

from __future__ import annotations

import pandas as pd
import pytest

from surveydoctor.io import load_csv
from surveydoctor.pipeline import Results, run_pipeline
from surveydoctor.report import build_report
from surveydoctor.robustness import GroupComparison
from surveydoctor.schema import SurveySchema
from tests.conftest import BFI_SCHEMA

GENDER = GroupComparison(scale="Neuroticism", group_column="gender", group_a=1, group_b=2)


@pytest.fixture(scope="module")
def results(request) -> Results:
    from tests.conftest import BFI_CSV

    if not BFI_CSV.exists():
        pytest.skip("data/sample/bfi.csv not found. Run: python scripts/download_data.py")
    schema = SurveySchema.load(BFI_SCHEMA)
    return run_pipeline(load_csv(BFI_CSV), schema, analysis=GENDER)


def test_every_section_is_populated(results: Results) -> None:
    n = 2800
    assert results.overview.n_respondents == n
    assert (results.overview.n_items, results.overview.n_scales) == (25, 5)
    assert len(results.indices) == len(results.flags) == len(results.composite) == n
    assert set(results.variants) == {"any_rule", "two_rules", "composite_top10"}
    assert set(results.reliability) == set(results.schema.scales)
    assert results.structure.efa is not None and results.structure.n_factors == 5
    assert [s.test for s in results.sensitivity] == ["two_groups", "correlation", "anova"]
    assert results.robustness is not None
    assert results.warnings


def test_overview_matches_flags(results: Results) -> None:
    # Stage 3 recorded 686 respondents with at least one rule and 72 with two or more.
    assert results.overview.n_flagged == int(results.flags["flagged"].sum()) == 686
    assert results.overview.n_flagged_two_rules == 72


def test_gender_robustness_table(results: Results) -> None:
    table = results.robustness.table()
    assert table["variant"].tolist() == ["all", "any_rule", "two_rules", "composite_top10"]
    assert table.loc[table["variant"] == "any_rule", "n_excluded"].item() == 686
    assert table["significant"].notna().all()
    assert results.robustness.verdict in {"stable", "sensitive", "unstable"}


def test_sensitivity_uses_analysed_sample(results: Results) -> None:
    assert {s.n_total for s in results.sensitivity} == {2800}


def test_bad_analysis_fails_before_slow_steps() -> None:
    schema = SurveySchema.load(BFI_SCHEMA)
    df = pd.DataFrame({"id": [1, 2], **{item: [1, 2] for item in schema.items}})
    with pytest.raises(ValueError, match="not available for grouping"):
        run_pipeline(df, schema, analysis=GroupComparison("Openness", "gender", 1, 2))


def test_html_report_renders(results: Results) -> None:
    html = build_report(results, "bfi.csv")
    assert html.lstrip().startswith("<!doctype html>")
    assert html.rstrip().endswith("</html>")
    assert "Review before drawing conclusions" in html
    assert "7 Robustness" in html and "Stable:" in html
