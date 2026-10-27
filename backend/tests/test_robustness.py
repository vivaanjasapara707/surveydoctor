"""Tests for robustness.py (Stage 9). Expected values are worked out by hand."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from surveydoctor.io import prepare_data
from surveydoctor.robustness import (
    ALL_RESPONDENTS,
    ROBUSTNESS_CAVEAT,
    Correlation,
    GroupComparison,
    VariantResult,
    _group_mask,
    check_analysis,
    cohens_d,
    compare_groups,
    correlate,
    robustness,
    verdict,
)
from surveydoctor.schema import SurveySchema

# --- Cohen's d and the group comparison ---------------------------------------------------


def test_cohens_d_by_hand() -> None:
    # Means 2 and 4; both variances 1, so the pooled SD is 1 and d = (2 − 4) / 1 = −2.
    assert cohens_d(np.array([1.0, 2, 3]), np.array([3.0, 4, 5])) == pytest.approx(-2.0)


def test_cohens_d_unequal_sizes() -> None:
    # A = 1,2,3 (var 1), B = 2,4,6,8 (var 20/3). Pooled var = (2 × 1 + 3 × 20/3) / 5 = 4.4.
    a, b = np.array([1.0, 2, 3]), np.array([2.0, 4, 6, 8])
    assert cohens_d(a, b) == pytest.approx((2 - 5) / math.sqrt(4.4))


def test_compare_groups_welch_by_hand() -> None:
    a, b = np.array([1.0, 2, 3, 4, 5]), np.array([2.0, 4, 6, 8, 10, 12])
    # Welch: se² = 2.5/5 + 14/6; df = (se²)² / ((2.5/5)²/4 + (14/6)²/5).
    va, vb = 2.5 / 5, 14 / 6
    se = math.sqrt(va + vb)
    df = (va + vb) ** 2 / (va**2 / 4 + vb**2 / 5)
    from scipy import stats

    q = stats.t.ppf(0.975, df)
    result = compare_groups(a, b)
    assert result.estimate == pytest.approx(3 - 7)
    assert result.ci_low == pytest.approx(-4 - q * se)
    assert result.ci_high == pytest.approx(-4 + q * se)
    assert result.p == pytest.approx(2 * stats.t.sf(4 / se, df))
    assert result.p == pytest.approx(0.0493, abs=1e-4)
    assert result.significant is True
    assert result.direction == "negative"
    assert (result.n, result.n_a, result.n_b) == (11, 5, 6)
    assert result.variant == ALL_RESPONDENTS and result.note is None


def test_compare_groups_mann_whitney_companion() -> None:
    # Complete separation: every A below every B, so U(A) = 0.
    result = compare_groups(np.array([1.0, 2, 3]), np.array([4.0, 5, 6]))
    assert result.companion == 0.0


def test_compare_groups_too_small() -> None:
    result = compare_groups(np.array([1.0]), np.array([2.0, 3, 4]), "two_rules", 7)
    assert math.isnan(result.estimate) and result.significant is None
    assert result.n_excluded == 7 and result.variant == "two_rules"
    assert "at least 2" in result.note


def test_compare_groups_constant_scores() -> None:
    result = compare_groups(np.array([3.0, 3, 3]), np.array([3.0, 3]))
    assert result.significant is None and "same score" in result.note


# --- Correlation --------------------------------------------------------------------------


def test_correlate_by_hand() -> None:
    # x = 1..5, y = 2,1,4,3,5: deviations give Σxy = 8 and Σx² = Σy² = 10, so r = 0.8.
    # Fisher z: z = atanh(0.8), SE = 1/sqrt(5 − 3), CI = tanh(z ± 1.959964 SE).
    result = correlate(np.array([1.0, 2, 3, 4, 5]), np.array([2.0, 1, 4, 3, 5]))
    z, se = math.atanh(0.8), 1 / math.sqrt(2)
    assert result.estimate == pytest.approx(0.8)
    assert result.ci_low == pytest.approx(math.tanh(z - 1.959964 * se), abs=1e-6)
    assert result.ci_high == pytest.approx(math.tanh(z + 1.959964 * se), abs=1e-6)
    assert result.significant is False  # p ≈ 0.104 with only 5 points
    assert result.direction == "positive"
    assert result.effect_size == result.estimate
    assert result.companion == pytest.approx(0.8)  # Spearman: the data are already ranks


def test_correlate_too_few_or_constant() -> None:
    assert "at least 4" in correlate(np.array([1.0, 2, 3]), np.array([1.0, 2, 3])).note
    assert "same score" in correlate(np.ones(5), np.arange(5.0)).note


# --- Verdict logic ------------------------------------------------------------------------


def row(variant: str, significant: bool | None, direction: str | None) -> VariantResult:
    estimate = {"positive": 0.3, "negative": -0.3, "none": 0.0, None: math.nan}[direction]
    return VariantResult(variant, 0, 100, estimate, 0, 0, 0.01, significant, direction, 0, 0, 0)


def test_verdict_stable() -> None:
    rows = [row("all", True, "positive"), row("any_rule", True, "positive"),
            row("two_rules", True, "positive")]  # fmt: skip
    assert verdict(rows) == ("stable", [])


def test_verdict_sensitive_names_variants() -> None:
    rows = [
        row("all", True, "positive"),
        row("any_rule", False, "positive"),
        row("two_rules", True, "positive"),
        row("composite_top10", False, "positive"),
    ]
    assert verdict(rows) == ("sensitive", ["any_rule", "composite_top10"])


def test_verdict_unstable_takes_precedence() -> None:
    # two_rules reverses a significant result; any_rule only loses significance.
    rows = [row("all", True, "positive"), row("any_rule", False, "positive"),
            row("two_rules", True, "negative")]  # fmt: skip
    assert verdict(rows) == ("unstable", ["any_rule", "two_rules"])


def test_verdict_nonsignificant_stays_stable() -> None:
    rows = [row("all", False, "negative"), row("any_rule", False, "negative")]
    assert verdict(rows) == ("stable", [])


def test_sign_flip_without_significance_is_not_unstable() -> None:
    # Both non-significant, opposite signs: chance, not a reversed conclusion.
    assert verdict([row("all", False, "positive"), row("any_rule", False, "negative")]) == (
        "stable",
        [],
    )
    # Significant positive -> non-significant estimate of 0 or below: lost significance only.
    for direction in ("none", "negative"):
        rows = [row("all", True, "positive"), row("any_rule", False, direction)]
        assert verdict(rows) == ("sensitive", ["any_rule"])
    # Non-significant -> significant in the opposite direction: a significance change.
    rows = [row("all", False, "positive"), row("any_rule", True, "negative")]
    assert verdict(rows) == ("sensitive", ["any_rule"])


def test_verdict_ignores_uncomputable_variants() -> None:
    rows = [row("all", True, "positive"), row("any_rule", None, None)]
    assert verdict(rows) == ("stable", [])
    assert verdict([row("all", None, None), row("any_rule", True, "positive")]) == (None, [])


# --- Group matching and input checks ------------------------------------------------------


def test_group_mask_numbers_and_text() -> None:
    numbers = pd.Series([1.0, 2.0, np.nan, 1.0])
    assert _group_mask(numbers, 1).tolist() == [True, False, False, True]
    assert _group_mask(numbers, "1").tolist() == [True, False, False, True]
    text = pd.Series(["Male", " Female", "male"])
    assert _group_mask(text, "Female").tolist() == [False, True, False]


SCHEMA = SurveySchema(
    items=["a1", "a2", "b1", "b2"],
    scales={"A": ["a1", "a2"], "B": ["b1", "b2"]},
    reverse_items=[],
    scale_min=1,
    scale_max=7,
    id_column="id",
)


def survey(values_a: list[float], values_b: list[float], groups: list[str]) -> pd.DataFrame:
    """Each respondent answers both items of a scale with the same value."""
    return pd.DataFrame(
        {
            "id": range(len(groups)),
            "a1": values_a,
            "a2": values_a,
            "b1": values_b,
            "b2": values_b,
            "group": groups,
        }  # fmt: skip
    )


@pytest.fixture
def prepared():
    rng = np.random.default_rng(0)
    values = rng.integers(1, 8, size=40).astype(float)
    return prepare_data(survey(list(values), list(values[::-1]), ["x", "y"] * 20), SCHEMA)


@pytest.mark.parametrize(
    ("analysis", "message"),
    [
        (GroupComparison("C", "group", "x", "y"), "Unknown scale: C"),
        (GroupComparison("A", "nope", "x", "y"), "not available for grouping"),
        (GroupComparison("A", "group", "x", " x "), "two different group values"),
        (GroupComparison("A", "group", "x", "z"), "No respondent has the value 'z'"),
        (Correlation("A", "A"), "two different scales"),
        (Correlation("A", "Q"), "Unknown scale: Q"),
    ],
)
def test_check_analysis_errors(prepared, analysis, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        check_analysis(analysis, prepared, SCHEMA)


# --- End to end on constructed data -------------------------------------------------------


def test_difference_carried_by_flagged_respondents_is_sensitive() -> None:
    # 20 x and 20 y respondents with identical score patterns (no real difference), plus 10
    # flagged x respondents scoring 7. With them, x scores clearly higher; without, it doesn't.
    base = [2.0, 3, 4, 5] * 5
    values_a = base + base + [7.0] * 10
    groups = ["x"] * 20 + ["y"] * 20 + ["x"] * 10
    data = prepare_data(survey(values_a, values_a, groups), SCHEMA)
    flagged = pd.Series([False] * 40 + [True] * 10, index=data.raw_items.index)
    exclusions = {"any_rule": flagged, "two_rules": pd.Series(False, index=flagged.index)}
    result = robustness(GroupComparison("A", "group", "x", "y"), data, SCHEMA, exclusions)

    table = result.table().set_index("variant")
    assert table.loc["all", "significant"] == True  # noqa: E712 (object column)
    assert table.loc["any_rule", "estimate"] == pytest.approx(0.0)
    assert table.loc["any_rule", "n_excluded"] == 10
    assert table.loc["two_rules", "n"] == 50
    assert result.verdict == "sensitive"
    assert result.changed_variants == ["any_rule"]
    assert result.caveat == ROBUSTNESS_CAVEAT


def test_correlation_end_to_end_and_missing_scores() -> None:
    values = [1.0, 2, 3, 4, 5, 6, 7, 2, 3, 4]
    frame = survey(values, values, ["x"] * 10)
    frame.loc[0, "a2"] = np.nan  # 1 of 2 items answered: below 80%, so no score on A
    data = prepare_data(frame, SCHEMA)
    warnings: list[str] = []
    none = {"any_rule": pd.Series(False, index=data.raw_items.index)}
    result = robustness(Correlation("A", "B"), data, SCHEMA, none, warnings=warnings)
    assert result.variants[0].n == 9
    assert result.variants[0].estimate == pytest.approx(1.0)
    assert result.verdict == "stable"
    assert any("1 respondents have no score on A or B" in w for w in warnings)


def test_variant_that_cannot_be_computed_is_reported() -> None:
    values = [2.0, 3, 4, 5, 6, 2, 3, 4]
    data = prepare_data(survey(values, values, ["x", "x", "x", "x", "y", "y", "y", "y"]), SCHEMA)
    drop_y = pd.Series([False] * 4 + [True] * 3 + [False], index=data.raw_items.index)
    warnings: list[str] = []
    result = robustness(
        GroupComparison("A", "group", "x", "y"), data, SCHEMA, {"any_rule": drop_y}, warnings
    )
    assert result.variants[1].note is not None and result.variants[1].n_b == 1
    assert any("variant 'any_rule'" in w for w in warnings)
    assert result.verdict is not None  # decided on the computable variants only
