"""Tests for fsqca.py part 1 (Stage 10A): calibration and necessity. Expected values are
worked out by hand; tests/test_reference_r.py compares the same functions with R's QCA."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from surveydoctor.fsqca import (
    DEFAULT_PERCENTILES,
    INCLUSION_DEGREE,
    Anchors,
    FsqcaSpec,
    at_crossover,
    calibrate,
    check_spec,
    fsqca,
    necessity,
    necessity_of,
    percentile_anchors,
)
from surveydoctor.io import prepare_data
from surveydoctor.schema import SurveySchema

SQRT19 = math.sqrt(19)  # ln(0.95/0.05) = ln 19, so half of it gives odds of sqrt(19)

# --- Calibration --------------------------------------------------------------------------


def test_calibrate_symmetric_anchors_by_hand() -> None:
    # Anchors 5 / 3 / 1. At 4: log-odds = (4 − 3) · ln 19 / 2, so membership = 1/(1 + 19^-½).
    result = calibrate(pd.Series([1.0, 2, 3, 4, 5]), Anchors(5, 3, 1))
    expected = [0.05, 1 / (1 + SQRT19), 0.5, 1 / (1 + 1 / SQRT19), 0.95]
    assert result.tolist() == pytest.approx(expected, abs=1e-12)


def test_calibrate_asymmetric_anchors_scale_each_side() -> None:
    # Full 6, crossover 4, non-membership 1: halfway up (5) and halfway down (2.5) mirror.
    result = calibrate(pd.Series([6.0, 5.0, 4.0, 2.5, 1.0]), Anchors(6, 4, 1)).tolist()
    assert result == pytest.approx([0.95, 1 / (1 + 1 / SQRT19), 0.5, 1 / (1 + SQRT19), 0.05])


def test_calibrate_does_not_clamp_beyond_anchors() -> None:
    result = calibrate(pd.Series([0.0, 6.0]), Anchors(5, 3, 1)).tolist()
    assert result[0] < 0.05 and result[1] > 0.95
    # Two anchor-widths above the crossover: log-odds 2 ln 19, membership 361/362.
    assert calibrate(pd.Series([7.0]), Anchors(5, 3, 1)).iloc[0] == pytest.approx(361 / 362)


def test_calibrate_is_increasing_and_keeps_name_and_missing() -> None:
    values = pd.Series(np.linspace(1, 6, 26), name="Openness")
    result = calibrate(values, Anchors(5.5, 3.5, 1.5))
    assert result.name == "Openness"
    assert (result.diff().dropna() > 0).all()
    assert calibrate(pd.Series([np.nan, 3.0]), Anchors(5, 3, 1)).isna().tolist() == [True, False]


def test_inclusion_degree_matches_qca_default() -> None:
    assert INCLUSION_DEGREE == 0.95


@pytest.mark.parametrize("anchors", [Anchors(3, 3, 1), Anchors(5, 3, 3), Anchors(1, 3, 5)])
def test_calibrate_rejects_unordered_anchors(anchors: Anchors) -> None:
    with pytest.raises(ValueError, match="in order"):
        calibrate(pd.Series([2.0]), anchors)


def test_percentile_anchors_use_linear_percentiles() -> None:
    values = pd.Series([1.0, 2, 3, 4, 5, 6, 7, 8, 9, 10, np.nan])
    anchors = percentile_anchors(values)
    # numpy linear (= R type 7) on 1..10: 95th = 9.55, 50th = 5.5, 5th = 1.45.
    assert (anchors.full, anchors.crossover, anchors.non) == pytest.approx((9.55, 5.5, 1.45))
    assert anchors.source == "percentiles" and anchors.percentiles == DEFAULT_PERCENTILES


def test_at_crossover_counts_conditions_only() -> None:
    m = pd.DataFrame({"A": [0.5, 0.7, 0.2], "B": [0.6, 0.5, 0.3], "Y": [0.9, 0.9, 0.5]})
    assert at_crossover(m, ["A", "B"]).tolist() == [True, True, False]


# --- Necessity ----------------------------------------------------------------------------

X = pd.Series([0.8, 0.6, 0.3])
Y = pd.Series([0.7, 0.9, 0.2])


def test_necessity_by_hand() -> None:
    # min(X, Y) = 0.7, 0.6, 0.2 (sum 1.5); ΣY = 1.8; ΣX = 1.7;
    # Σ(1 − X) = 1.3; Σ(1 − min) = 1.5.
    result = necessity_of(X, Y, "X", threshold=0.8)
    assert result.consistency == pytest.approx(1.5 / 1.8)
    assert result.coverage == pytest.approx(1.5 / 1.7)
    assert result.relevance == pytest.approx(1.3 / 1.5)
    assert result.passes is True  # 0.833 >= 0.8


def test_necessity_of_negation_by_hand() -> None:
    # ~X = 0.2, 0.4, 0.7; min(~X, Y) = 0.2, 0.4, 0.2 (sum 0.8); Σ~X = 1.3;
    # Σ(1 − ~X) = ΣX = 1.7; Σ(1 − min) = 2.2.
    m = pd.DataFrame({"X": X, "Y": Y})
    plain, negated = necessity(m, "Y", ["X"], threshold=0.9)
    assert (plain.condition, negated.condition) == ("X", "~X")
    assert negated.consistency == pytest.approx(0.8 / 1.8)
    assert negated.coverage == pytest.approx(0.8 / 1.3)
    assert negated.relevance == pytest.approx(1.7 / 2.2)
    assert not plain.passes and not negated.passes  # 0.833 < 0.9


def test_necessity_threshold_is_inclusive() -> None:
    x = pd.Series([1.0, 1.0])
    y = pd.Series([0.9, 0.9])
    assert necessity_of(x * 0.9, y, "X", threshold=1.0).passes is True  # consistency exactly 1


def test_necessity_zero_denominators_are_nan() -> None:
    zero = pd.Series([0.0, 0.0])
    result = necessity_of(zero, zero, "X", threshold=0.9)
    assert math.isnan(result.consistency) and math.isnan(result.coverage)
    full = pd.Series([1.0, 1.0])
    assert math.isnan(necessity_of(full, full, "X", threshold=0.9).relevance)
    assert result.passes is False


def test_trivial_condition_has_low_relevance() -> None:
    # X almost always present: consistency is high, but relevance of necessity is low.
    x = pd.Series([0.95, 0.95, 0.95, 0.95])
    y = pd.Series([0.9, 0.2, 0.6, 0.1])
    result = necessity_of(x, y, "X", threshold=0.9)
    assert result.consistency == pytest.approx(1.0)
    assert result.relevance < 0.25


# --- Input checks -------------------------------------------------------------------------


def make_schema(n_scales: int = 4) -> SurveySchema:
    scales = {f"S{i}": [f"s{i}a", f"s{i}b"] for i in range(n_scales)}
    return SurveySchema(
        items=[item for items in scales.values() for item in items], scales=scales,
        reverse_items=[], scale_min=1, scale_max=7,
    )  # fmt: skip


@pytest.mark.parametrize(
    ("spec", "message"),
    [
        (FsqcaSpec("S0", ("S1", "Q")), "Unknown scale: Q"),
        (FsqcaSpec("S0", ("S0", "S1")), "cannot also be a condition"),
        (FsqcaSpec("S0", ("S1", "S1")), "only once"),
        (FsqcaSpec("S0", ("S1",)), "Choose 2 to 7 conditions; 1 were chosen"),
        (FsqcaSpec("S0", ("S1", "S2"), anchors={"S3": (6, 4, 2)}), "not in this analysis"),
        (FsqcaSpec("S0", ("S1", "S2"), anchors={"S1": (6, 4)}), "three numbers"),
        (FsqcaSpec("S0", ("S1", "S2"), anchors={"S1": (4, 6, 2)}), "must be in order"),
        (FsqcaSpec("S0", ("S1", "S2"), anchors={"S1": (8, 4, 2)}), "on the answer scale"),
        (FsqcaSpec("S0", ("S1", "S2"), anchors={"S1": (6, 4, 0.5)}), "on the answer scale"),
        (FsqcaSpec("S0", ("S1", "S2"), necessity_threshold=0.5), "above 0.5"),
    ],
)
def test_check_spec_errors(spec: FsqcaSpec, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        check_spec(spec, make_schema())


def test_check_spec_allows_two_to_seven_conditions() -> None:
    schema = make_schema(9)
    check_spec(FsqcaSpec("S0", tuple(f"S{i}" for i in range(1, 8))), schema)
    with pytest.raises(ValueError, match="8 were chosen"):
        check_spec(FsqcaSpec("S0", tuple(f"S{i}" for i in range(1, 9))), schema)


# --- The analysis -------------------------------------------------------------------------


def survey(n: int = 60, seed: int = 0) -> pd.DataFrame:
    """Each scale's two items get the same random 1-7 answer (score = that answer)."""
    rng = np.random.default_rng(seed)
    data = {}
    for i in range(4):
        values = rng.integers(1, 8, size=n).astype(float)
        data[f"s{i}a"] = values
        data[f"s{i}b"] = values
    return pd.DataFrame(data)


def test_fsqca_uses_given_and_percentile_anchors() -> None:
    schema = make_schema()
    spec = FsqcaSpec("S0", ("S1", "S2", "S3"), anchors={"S1": (6.5, 4.5, 1.5)})
    result = fsqca(prepare_data(survey(), schema), schema, spec)
    assert result.skipped_reason is None
    assert result.anchors["S1"] == Anchors(6.5, 4.5, 1.5, source="scale points")
    assert result.anchors["S2"].source == "percentiles"
    assert list(result.memberships.columns) == ["S1", "S2", "S3", "S0"]
    assert len(result.necessity) == 6
    table = result.necessity_table()
    assert table["condition"].tolist() == ["S1", "~S1", "S2", "~S2", "S3", "~S3"]
    # Crossover 4.5 is off the integer scores, so no S1 membership is exactly 0.5.
    assert not result.memberships["S1"].eq(0.5).any()


def test_fsqca_reports_excluded_and_crossover_cases() -> None:
    schema = make_schema()
    df = survey()
    df.loc[[0, 1], ["s2a", "s2b"]] = np.nan  # no S2 score for two respondents
    warnings: list[str] = []
    result = fsqca(prepare_data(df, schema), schema, FsqcaSpec("S0", ("S1", "S2")), warnings)
    assert (result.n_used, result.n_excluded) == (58, 2)
    assert any("58 respondents" in w and "2 without one" in w for w in warnings)
    # Percentile crossovers are medians of integer scores, so some scores sit exactly on them.
    expected = int(at_crossover(result.memberships, ["S1", "S2"]).sum())
    assert result.n_at_crossover == expected > 0
    assert any(f"{expected} of 58 respondents have a membership of exactly 0.5" in w
               for w in warnings)  # fmt: skip


def test_fsqca_skips_when_percentile_anchors_tie() -> None:
    schema = make_schema()
    df = survey()
    df[["s1a", "s1b"]] = 5.0  # everyone has the same S1 score: all percentiles are 5
    warnings: list[str] = []
    result = fsqca(prepare_data(df, schema), schema, FsqcaSpec("S0", ("S1", "S2")), warnings)
    assert result.skipped_reason is not None and "S1" in result.skipped_reason
    assert "scale points" in result.skipped_reason
    assert result.necessity == [] and result.memberships.empty
    assert any(w.startswith("fsQCA was not run") for w in warnings)


def test_fsqca_scale_point_anchors_avoid_the_tie() -> None:
    schema = make_schema()
    df = survey()
    df[["s1a", "s1b"]] = 5.0
    spec = FsqcaSpec("S0", ("S1", "S2"), anchors={"S1": (6.0, 4.0, 2.0)})
    result = fsqca(prepare_data(df, schema), schema, spec)
    assert result.skipped_reason is None
    assert result.memberships["S1"].unique().tolist() == pytest.approx([1 / (1 + 1 / SQRT19)])
