"""Tests for fsqca.py: calibration and necessity (Stage 10A), truth table, minimisation,
robustness and calibration sensitivity (Stage 10B). Expected values are worked out by hand;
tests/test_reference_r.py compares the same functions with R's QCA."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from surveydoctor.fsqca import (
    CALIBRATION_CAVEAT,
    DEFAULT_PERCENTILES,
    INCLUSION_DEGREE,
    ROBUSTNESS_CAVEAT,
    Anchors,
    FsqcaRun,
    FsqcaSpec,
    Model,
    Path,
    Solution,
    _reaches,
    at_crossover,
    calibrate,
    calibration_runs,
    case_rows,
    check_spec,
    compare_runs,
    expression,
    fsqca,
    minimal_covers,
    minimize,
    model_fit,
    necessity,
    necessity_of,
    path_changes,
    percentile_anchors,
    prime_implicants,
    row_configs,
    shifted_anchors,
    truth_table,
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
        (FsqcaSpec("S0", ("S1", "S2"), frequency_threshold=0), "at least 1"),
        (FsqcaSpec("S0", ("S1", "S2"), frequency_threshold=1.5), "whole number"),
        (FsqcaSpec("S0", ("S1", "S2"), consistency_threshold=0.5), "consistency threshold"),
        (FsqcaSpec("S0", ("S1", "S2"), pri_threshold=1.2), "PRI threshold"),
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


# --- Truth table (Stage 10B) --------------------------------------------------------------

# Two conditions, four cases. Rows: 1 = ~A·~B, 2 = ~A·B, 3 = A·~B, 4 = A·B.
# Case 4 has A = 0.5: it belongs to no row but still counts in the sums.
TT = pd.DataFrame({"A": [0.8, 0.7, 0.2, 0.5], "B": [0.3, 0.1, 0.6, 0.9], "Y": [0.9, 0.6, 0.3, 0.2]})


def test_row_configs_number_rows_like_qca() -> None:
    # Row number − 1 in binary, first condition as the most significant bit.
    assert row_configs(2).tolist() == [[0, 0], [0, 1], [1, 0], [1, 1]]
    assert row_configs(3)[5].tolist() == [1, 0, 1]


def test_case_rows_by_hand() -> None:
    assert case_rows(TT, ["A", "B"]).tolist() == [3, 3, 2, 0]


def test_truth_table_by_hand() -> None:
    table, rows = truth_table(TT, "Y", ["A", "B"])
    assert table.index.tolist() == [1, 2, 3, 4]
    assert table[["A", "B"]].to_numpy().tolist() == [[0, 0], [0, 1], [1, 0], [1, 1]]
    assert table["n"].tolist() == [0, 1, 2, 0]
    # Row 3: R = min(A, 1 − B) = 0.7, 0.7, 0.2, 0.1 (ΣR = 1.7); min(R, Y) = 0.7, 0.6, 0.2,
    # 0.1 (1.6); min(R, Y, 1 − Y) = 0.1, 0.4, 0.2, 0.1 (0.8). PRI = 0.8 / 0.9.
    assert table.loc[3, "consistency"] == pytest.approx(1.6 / 1.7)
    assert table.loc[3, "pri"] == pytest.approx(0.8 / 0.9)
    # Row 2: R = min(1 − A, B) = 0.2, 0.1, 0.6, 0.5 (1.4); min(R, Y) = 0.2, 0.1, 0.3, 0.2.
    assert table.loc[2, "consistency"] == pytest.approx(0.8 / 1.4)
    assert table["outcome"].tolist() == ["?", "0", "1", "?"]
    assert rows.tolist() == [3, 3, 2, 0]


def test_truth_table_frequency_threshold_makes_remainders() -> None:
    table, _ = truth_table(TT, "Y", ["A", "B"], frequency_threshold=2)
    assert table["outcome"].tolist() == ["?", "?", "1", "?"]


def test_truth_table_pri_threshold() -> None:
    table, _ = truth_table(TT, "Y", ["A", "B"], pri_threshold=0.9)  # row 3 PRI is 0.889
    assert table.loc[3, "outcome"] == "0"


def test_thresholds_allow_rounding_like_qca() -> None:
    assert _reaches(0.8 - 1e-10, 0.8)
    assert _reaches(0.8, 0.8)
    assert not _reaches(0.8 - 1e-6, 0.8)


# --- Minimisation -------------------------------------------------------------------------


def outcome_table(k: int, positive: set[int], remainders: set[int] = frozenset()) -> pd.DataFrame:
    """A truth table with only an outcome column; rows are 1-based row numbers."""
    rows = range(1, 2**k + 1)
    outcome = ["1" if r in positive else "?" if r in remainders else "0" for r in rows]
    return pd.DataFrame({"outcome": outcome}, index=pd.Index(rows, name="row"))


def model_texts(models) -> set[frozenset[str]]:
    return {frozenset(expression(p) for p in m) for m in models}


def test_prime_implicants_merge_to_one_condition() -> None:
    # Rows 1, 3, 5, 7 (0-based) are exactly the rows with C present.
    assert prime_implicants({1, 3, 5, 7}, set(), 3) == [(None, None, 1)]


def test_minimal_covers_of_a_cyclic_chart() -> None:
    # Classic cyclic function: rows 0, 1, 2, 5, 6, 7 of A, B, C. Six primes, each covering
    # two rows; two different covers of three primes each.
    rows = {0, 1, 2, 5, 6, 7}
    primes = prime_implicants(rows, set(), 3)
    assert len(primes) == 6
    configs = row_configs(3)
    covers = [
        {r for r in rows if all(v is None or configs[r][j] == v for j, v in enumerate(p))}
        for p in primes
    ]
    found = minimal_covers(covers, rows)
    assert len(found) == 2 and all(len(c) == 3 for c in found)


def test_minimize_reports_every_equally_short_model() -> None:
    table = outcome_table(3, {1, 2, 3, 6, 7, 8})
    models = minimize(table, ["A", "B", "C"], "complex")
    assert model_texts(models) == {
        frozenset({"~A*~B", "B*~C", "A*C"}),
        frozenset({"~A*~C", "~B*C", "A*B"}),
    }


def test_remainders_shorten_only_the_parsimonious_solution() -> None:
    table = outcome_table(2, positive={4}, remainders={3})  # A·B positive, A·~B unobserved
    assert model_texts(minimize(table, ["A", "B"], "complex")) == {frozenset({"A*B"})}
    assert model_texts(minimize(table, ["A", "B"], "parsimonious")) == {frozenset({"A"})}


def test_minimize_without_positive_rows_has_no_solution() -> None:
    assert minimize(outcome_table(2, set(), {1}), ["A", "B"], "parsimonious") == []


def test_minimize_can_remove_every_condition() -> None:
    # ~A rows positive and the A rows unobserved: the parsimonious path has no conditions.
    table = outcome_table(2, positive={1, 2}, remainders={3, 4})
    assert model_texts(minimize(table, ["A", "B"], "complex")) == {frozenset({"~A"})}
    assert model_texts(minimize(table, ["A", "B"], "parsimonious")) == {frozenset({"1"})}


def test_model_fit_by_hand() -> None:
    m = pd.DataFrame({"A": [0.8, 0.3], "B": [0.6, 0.9], "Y": [0.7, 0.8]})
    model = model_fit(m, "Y", [(("A", True),), (("B", True),)], "M1")
    a, b = model.paths
    # A: min(A, Y) = 0.7, 0.3 (1.0); ΣA = 1.1; ΣY = 1.5.
    assert (a.consistency, a.raw_coverage) == pytest.approx((1.0 / 1.1, 1.0 / 1.5))
    # B: min(B, Y) = 0.6, 0.8 (1.4); ΣB = 1.5.
    assert (b.consistency, b.raw_coverage) == pytest.approx((1.4 / 1.5, 1.4 / 1.5))
    # Model: max(A, B) = 0.8, 0.9; min with Y = 0.7, 0.8 (1.5); Σmax = 1.7.
    assert (model.consistency, model.coverage) == pytest.approx((1.5 / 1.7, 1.0))
    # Unique coverage: model coverage minus coverage without the path.
    assert a.unique_coverage == pytest.approx(1.0 - 1.4 / 1.5)
    assert b.unique_coverage == pytest.approx(1.0 - 1.0 / 1.5)
    assert model.expression == "A + B"


def test_single_path_unique_coverage_is_its_raw_coverage() -> None:
    m = pd.DataFrame({"A": [0.8, 0.3], "Y": [0.7, 0.8]})
    (path,) = model_fit(m, "Y", [(("A", True),)], "M1").paths
    assert path.unique_coverage == pytest.approx(path.raw_coverage)


def test_expression_notation() -> None:
    assert expression((("Openness", False), ("Extraversion", True))) == "~Openness*Extraversion"
    assert expression(()) == "1"


# --- Robustness and calibration sensitivity -----------------------------------------------


def make_run(label: str, *paths: str, skipped: str | None = None) -> FsqcaRun:
    """A run whose solutions are one model with the given paths (no paths = no solution)."""

    def solution(kind) -> Solution:
        if not paths:
            return Solution(kind, [])
        fitted = [
            Path(tuple((c.lstrip("~"), not c.startswith("~")) for c in p.split("*")), 1, 0.5, 0.1)
            for p in paths
        ]
        return Solution(kind, [Model("M1", fitted, 1.0, 0.5)])

    if skipped:
        return FsqcaRun(label, 0, 0, {}, skipped_reason=skipped)
    return FsqcaRun(
        label, 10, 0, {}, complex=solution("complex"), parsimonious=solution("parsimonious")
    )


def test_path_changes_marks_kept_missing_new() -> None:
    main, other = make_run("all", "A*B", "~C"), make_run("x", "A*B", "D")
    assert path_changes(main.complex, other.complex) == {
        "A*B": "kept", "~C": "missing", "D": "new",
    }  # fmt: skip


def test_compare_runs_same() -> None:
    check = compare_runs("robustness", make_run("all", "A*B"), [make_run("any_rule", "A*B")])
    assert (check.verdict, check.named, check.caveat) == ("same", [], ROBUSTNESS_CAVEAT)


def test_compare_runs_changed_names_the_variant() -> None:
    main = make_run("all", "A*B")
    check = compare_runs(
        "robustness", main, [make_run("any_rule", "A*B"), make_run("two_rules", "A")]
    )
    assert (check.verdict, check.named) == ("changed", ["two_rules"])
    assert check.comparisons[1].paths["complex"] == {"A*B": "missing", "A": "new"}


def test_compare_runs_no_solution_takes_precedence() -> None:
    main = make_run("all", "A*B")
    check = compare_runs("robustness", main, [make_run("any_rule"), make_run("two_rules", "A")])
    assert (check.verdict, check.named) == ("no solution", ["any_rule"])


def test_compare_runs_main_without_solution() -> None:
    check = compare_runs("calibration", make_run("all"), [make_run("crossover_lower")])
    assert (check.verdict, check.named) == ("no solution", ["all", "crossover_lower"])
    assert check.caveat == CALIBRATION_CAVEAT


def test_compare_runs_ignores_skipped_reruns() -> None:
    main = make_run("all", "A")
    check = compare_runs("robustness", main, [make_run("any_rule", skipped="too few")])
    assert check.verdict is None
    check = compare_runs(
        "robustness", main, [make_run("any_rule", skipped="too few"), make_run("two_rules", "A")]
    )
    assert check.verdict == "same"


def test_shifted_scale_point_anchors() -> None:
    anchors = {"S": Anchors(6.0, 4.0, 2.0, source="scale points")}
    scores = pd.DataFrame({"S": [1.0, 7.0]})
    assert shifted_anchors(anchors, scores, "crossover_lower")["S"] == Anchors(
        6.0, 3.5, 2.0, source="scale points"
    )
    assert shifted_anchors(anchors, scores, "crossover_higher")["S"].crossover == 4.5
    outer = shifted_anchors(anchors, scores, "outer_closer")["S"]
    assert (outer.full, outer.crossover, outer.non) == (5.5, 4.0, 2.5)


def test_shifted_percentile_anchors() -> None:
    scores = pd.DataFrame({"S": np.arange(1.0, 11.0)})
    anchors = {"S": percentile_anchors(scores["S"])}
    # numpy linear percentiles of 1..10: 45th = 5.05, 55th = 5.95, 90th = 9.1, 10th = 1.9.
    lower = shifted_anchors(anchors, scores, "crossover_lower")["S"]
    higher = shifted_anchors(anchors, scores, "crossover_higher")["S"]
    assert (lower.crossover, higher.crossover) == pytest.approx((5.05, 5.95))
    outer = shifted_anchors(anchors, scores, "outer_closer")["S"]
    assert (outer.full, outer.non) == pytest.approx((9.1, 1.9))
    assert outer.percentiles == (90.0, 50.0, 10.0)


def test_calibration_rerun_skipped_when_shift_breaks_the_order() -> None:
    scores = pd.DataFrame({"S1": [1.0, 3, 5, 7], "S2": [2.0, 4, 6, 7], "S0": [1.0, 2, 6, 7]})
    anchors = {
        "S1": Anchors(5.0, 4.8, 1.0, source="scale points"),  # +0.5 puts the crossover above 5
        "S2": Anchors(6.0, 4.0, 2.0, source="scale points"),
        "S0": Anchors(6.0, 4.0, 2.0, source="scale points"),
    }
    runs = calibration_runs(scores, FsqcaSpec("S0", ("S1", "S2")), anchors)
    assert [r.label for r in runs] == ["crossover_lower", "crossover_higher", "outer_closer"]
    assert runs[1].skipped_reason is not None and "S1" in runs[1].skipped_reason
    assert runs[0].skipped_reason is None and runs[0].truth_table is not None


def test_fsqca_runs_truth_table_and_both_checks() -> None:
    schema = make_schema()
    prepared = prepare_data(survey(), schema)
    index = prepared.scored_items.index
    exclusions = {"any_rule": pd.Series(index < 10, index=index)}
    spec = FsqcaSpec("S0", ("S1", "S2"), anchors={"S1": (6.5, 4.5, 1.5)})
    result = fsqca(prepared, schema, spec, exclusions=exclusions)
    main = result.main
    assert main.n == 60 and len(main.truth_table) == 4
    assert int(main.truth_table["n"].sum()) == 60 - main.n_at_crossover
    (variant,) = result.robustness.comparisons
    assert (variant.run.n, variant.run.n_excluded) == (50, 10)
    # Anchors stay fixed, so each remaining respondent keeps the same row.
    assert variant.run.case_rows.equals(main.case_rows.iloc[10:])
    assert variant.run.anchors == main.anchors
    assert [c.run.label for c in result.calibration.comparisons] == [
        "crossover_lower", "crossover_higher", "outer_closer",
    ]  # fmt: skip
    assert result.robustness.verdict in {"same", "changed", "no solution"}


def test_fsqca_without_exclusions_skips_robustness() -> None:
    schema = make_schema()
    result = fsqca(prepare_data(survey(), schema), schema, FsqcaSpec("S0", ("S1", "S2")))
    assert result.robustness is None and result.calibration is not None


def test_fsqca_reports_no_solution() -> None:
    schema = make_schema()
    warnings: list[str] = []
    spec = FsqcaSpec("S0", ("S1", "S2"), consistency_threshold=1.0, pri_threshold=1.0)
    result = fsqca(prepare_data(survey(), schema), schema, spec, warnings)
    assert not result.main.has_solution
    assert any(w.startswith("fsQCA found no solution") for w in warnings)


def test_skipped_fsqca_has_no_truth_table() -> None:
    schema = make_schema()
    df = survey()
    df[["s1a", "s1b"]] = 5.0
    result = fsqca(prepare_data(df, schema), schema, FsqcaSpec("S0", ("S1", "S2")))
    assert result.main is None and result.robustness is None and result.calibration is None
