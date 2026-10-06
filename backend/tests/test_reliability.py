"""Tests for reliability.py (Stage 4). Expected values are worked out by hand where possible."""

from __future__ import annotations

import math
from dataclasses import replace

import numpy as np
import pandas as pd
import pytest
from scipy import stats

from surveydoctor.io import load_csv, prepare_data, reverse_score
from surveydoctor.reliability import (
    MIN_ITEMS_OMEGA,
    alpha_if_deleted,
    complete_cases,
    corrected_item_total,
    cronbach_alpha,
    item_stats,
    omega_from_loadings,
    omega_total,
    one_factor_loadings,
    reliability,
    reverse_warnings,
    scale_reliability,
    summary_table,
)
from surveydoctor.schema import SurveySchema
from tests.conftest import BFI_SCHEMA

NAN = np.nan


def frame(columns: dict[str, list[float]]) -> pd.DataFrame:
    return pd.DataFrame(columns, dtype=float)


def one_factor_data(loadings: list[float], n: int = 20_000, seed: int = 0) -> pd.DataFrame:
    """Continuous data from a one-factor model: x_i = λ_i F + sqrt(1 − λ_i²) e_i."""
    rng = np.random.default_rng(seed)
    factor = rng.standard_normal(n)
    columns = {
        f"q{i + 1}": lam * factor + math.sqrt(1 - lam**2) * rng.standard_normal(n)
        for i, lam in enumerate(loadings)
    }
    return pd.DataFrame(columns)


# Two items: x = 1,2,3,4 and y = 2,1,4,3. Each has variance 5/3; the total 3,3,7,7 has
# variance 16/3. alpha = 2 × (1 − (10/3)/(16/3)) = 0.75.
HAND = frame({"x": [1, 2, 3, 4], "y": [2, 1, 4, 3]})

# Three identical items and a fourth that is their mirror image (6 − x on a 1–5 scale).
MIRRORED = frame(
    {"q1": [1, 2, 3, 4, 5], "q2": [1, 2, 3, 4, 5], "q3": [1, 2, 3, 4, 5], "q4": [5, 4, 3, 2, 1]}
)


# ---------------------------------------------------------------------------- alpha


class TestCronbachAlpha:
    def test_hand_computed_value(self):
        alpha, _ = cronbach_alpha(HAND)
        assert alpha == pytest.approx(0.75, abs=1e-12)

    def test_feldt_interval(self):
        # Feldt: 1 − (1 − alpha) × F quantile, df1 = n − 1, df2 = (n − 1)(k − 1).
        alpha, (low, high) = cronbach_alpha(HAND)
        f_dist = stats.f(3, 3)
        assert low == round(1 - (1 - alpha) * f_dist.isf(0.025), 3)
        assert high == round(1 - (1 - alpha) * f_dist.isf(0.975), 3)
        assert low < alpha < high

    def test_perfectly_correlated_items_give_one(self):
        data = frame({"a": [1, 2, 3, 4, 5], "b": [1, 2, 3, 4, 5], "c": [1, 2, 3, 4, 5]})
        assert cronbach_alpha(data)[0] == pytest.approx(1.0, abs=1e-12)

    def test_alpha_drops_when_a_random_item_is_added(self):
        data = one_factor_data([0.8, 0.8, 0.8, 0.8], n=2_000)
        rng = np.random.default_rng(1)
        with_noise = data.assign(noise=rng.standard_normal(len(data)))
        assert cronbach_alpha(with_noise)[0] < cronbach_alpha(data)[0]

    def test_wider_interval_with_fewer_respondents(self):
        data = one_factor_data([0.7, 0.7, 0.7, 0.7], n=2_000)
        small_low, small_high = cronbach_alpha(data.head(50))[1]
        big_low, big_high = cronbach_alpha(data)[1]
        assert small_high - small_low > big_high - big_low

    def test_missing_values_are_refused(self):
        with pytest.raises(ValueError, match="complete cases"):
            cronbach_alpha(frame({"x": [1, 2, NAN], "y": [2, 1, 3]}))

    @pytest.mark.parametrize(
        "data",
        [
            frame({"x": [1, 2, 3]}),  # one item
            frame({"x": [1.0], "y": [2.0]}),  # one respondent
            frame({"x": [3, 3, 3], "y": [2, 2, 2]}),  # total score never varies
        ],
    )
    def test_undefined_cases_return_nan(self, data):
        alpha, (low, high) = cronbach_alpha(data)
        assert math.isnan(alpha) and math.isnan(low) and math.isnan(high)


# ---------------------------------------------------------------------------- omega


class TestOmega:
    def test_formula_by_hand(self):
        # Σλ = 2, (Σλ)² = 4; Σψ = 4 × 0.75 = 3; omega = 4 / 7.
        assert omega_from_loadings([0.5, 0.5, 0.5, 0.5]) == pytest.approx(4 / 7)

    def test_perfect_loadings_give_one(self):
        assert omega_from_loadings([1.0, 1.0, 1.0]) == pytest.approx(1.0)

    def test_negative_loading_lowers_omega(self):
        assert omega_from_loadings([0.7, 0.7, -0.7]) < omega_from_loadings([0.7, 0.7, 0.7])

    def test_nan_loadings_give_nan(self):
        assert math.isnan(omega_from_loadings([0.5, NAN, 0.5]))
        assert math.isnan(omega_from_loadings([]))

    def test_recovers_known_loadings(self):
        true = [0.8, 0.7, 0.6, 0.5]
        loadings = one_factor_loadings(one_factor_data(true))
        np.testing.assert_allclose(loadings.to_numpy(), true, atol=0.03)
        assert omega_total(one_factor_data(true)) == pytest.approx(
            omega_from_loadings(true), abs=0.01
        )

    def test_loadings_are_signed_to_a_positive_sum(self):
        flipped = -one_factor_data([0.8, 0.7, 0.6])
        loadings = one_factor_loadings(flipped)
        assert loadings.sum() > 0
        assert (loadings > 0).all()

    def test_equal_loadings_make_omega_close_to_alpha(self):
        # With equal loadings (tau-equivalence) alpha and omega estimate the same thing.
        data = one_factor_data([0.6, 0.6, 0.6, 0.6, 0.6])
        assert omega_total(data) == pytest.approx(cronbach_alpha(data)[0], abs=0.01)

    def test_too_few_items(self):
        warnings: list[str] = []
        data = one_factor_data([0.8, 0.8], n=100)
        assert MIN_ITEMS_OMEGA == 3
        assert math.isnan(omega_total(data, "Short", warnings))
        assert warnings == [
            "Omega was not computed for scale 'Short': it needs at least 3 items, and the "
            "scale has 2."
        ]

    def test_too_few_respondents(self):
        warnings: list[str] = []
        data = one_factor_data([0.8, 0.8, 0.8], n=3)
        assert math.isnan(omega_total(data, "S", warnings))
        assert "more respondents with complete answers (3) than items (3)" in warnings[0]

    def test_constant_item(self):
        warnings: list[str] = []
        data = one_factor_data([0.8, 0.8, 0.8], n=50).assign(q3=4.0)
        assert one_factor_loadings(data, "S", warnings).isna().all()
        assert "same answer to q3" in warnings[0]

    def test_near_duplicate_items_trigger_the_heywood_warning(self):
        # q2 is q1 plus tiny noise, so the one-factor model explains both almost
        # completely and their uniquenesses hit factor_analyzer's lower bound (0.005).
        rng = np.random.default_rng(0)
        factor = rng.standard_normal(500)
        data = pd.DataFrame(
            {
                "q1": factor,
                "q2": factor + 1e-3 * rng.standard_normal(500),
                "q3": 0.5 * factor + rng.standard_normal(500),
                "q4": 0.5 * factor + rng.standard_normal(500),
            }
        )
        warnings: list[str] = []
        loadings = one_factor_loadings(data, "Dup", warnings)
        assert 1 - loadings["q1"] ** 2 <= 0.005 + 1e-6
        assert loadings.notna().all()  # loadings are still reported, with the warning
        assert warnings == [
            "Omega for scale 'Dup' may be overstated: the one-factor model explains at least "
            "one item almost completely (a Heywood case), which usually means too little data "
            "or near-duplicate items."
        ]

    def test_identical_items_make_the_model_fail_with_a_warning(self):
        # Two identical columns (e.g. a question exported twice) make the correlation
        # matrix singular; factor_analyzer raises LinAlgError and omega is left missing.
        # The warning explains the cause in plain English, not the library's error text.
        rng = np.random.default_rng(0)
        factor = rng.standard_normal(500)
        data = pd.DataFrame(
            {
                "q1": factor,
                "q2": factor,
                "q3": 0.5 * factor + rng.standard_normal(500),
                "q4": 0.5 * factor + rng.standard_normal(500),
            }
        )
        warnings: list[str] = []
        assert math.isnan(omega_total(data, "Twin", warnings))
        assert warnings == [
            "Two or more questions in scale 'Twin' have identical or nearly identical answers, "
            "so omega could not be calculated."
        ]
        assert "Singular" not in warnings[0]


# ---------------------------------------------------------------------------- items


class TestItemStats:
    def test_corrected_item_total_by_hand(self):
        # q4's rest-score is 3 × q1, so r = −1; q1's rest-score is q1 + 6, so r = +1.
        r = corrected_item_total(MIRRORED)
        np.testing.assert_allclose(r.to_numpy(), [1, 1, 1, -1], atol=1e-12)

    def test_corrected_item_total_nan_when_rest_is_constant(self):
        # q1's rest-score (q2 + q3) is 5 for everyone.
        data = frame({"q1": [1, 2, 3, 4], "q2": [1, 2, 3, 4], "q3": [4, 3, 2, 1]})
        r = corrected_item_total(data)
        assert math.isnan(r["q1"]) and math.isnan(r["q2"])
        assert r["q3"] == pytest.approx(-1.0)

    def test_alpha_if_deleted_by_hand(self):
        data = HAND.assign(z=HAND["x"])
        dropped = alpha_if_deleted(data)
        assert dropped["z"] == pytest.approx(0.75)  # alpha of x, y
        assert dropped["x"] == pytest.approx(0.75)  # alpha of y, z (z = x)
        assert dropped["y"] == pytest.approx(1.0)  # alpha of x, z: identical items

    def test_alpha_if_deleted_needs_two_remaining_items(self):
        assert alpha_if_deleted(HAND).isna().all()

    def test_item_stats_columns(self):
        out = item_stats(MIRRORED)
        assert list(out.columns) == ["corrected_item_total", "alpha_if_deleted"]
        assert list(out.index) == ["q1", "q2", "q3", "q4"]


class TestReverseWarnings:
    def test_negative_item_is_warned_about_not_reversed(self):
        before = MIRRORED.copy()
        flagged = reverse_warnings("Mood", item_stats(MIRRORED))
        assert [w.item for w in flagged] == ["q4"]
        assert flagged[0].corrected_item_total == pytest.approx(-1.0)
        assert flagged[0].message == (
            "Check this question: it disagrees with the rest of its scale. Item q4 has a "
            "corrected item-total correlation of -1.00 with the other items of scale 'Mood'. "
            "SurveyDoctor does not change answers automatically."
        )
        pd.testing.assert_frame_equal(MIRRORED, before)

    def test_message_does_not_claim_the_item_is_reversed(self):
        message = reverse_warnings("Mood", item_stats(MIRRORED))[0].message
        assert "revers" not in message.lower()

    def test_declaring_the_reverse_item_removes_the_warning(self):
        scored = reverse_score(MIRRORED, ["q4"], 1, 5)
        assert reverse_warnings("Mood", item_stats(scored)) == []
        assert cronbach_alpha(scored)[0] == pytest.approx(1.0)


# ---------------------------------------------------------------------------- per scale


class TestScaleReliability:
    def test_listwise_deletion_is_counted_and_reported(self):
        scored = pd.DataFrame(
            {
                "a": [1, 2, 3, 4, 5, NAN, 3],
                "b": [2, 2, 3, 5, 5, 4, NAN],
                "c": [1, 3, 3, 4, 4, 2, 2],
            },
            dtype=float,
        )
        warnings: list[str] = []
        result = scale_reliability(scored, "S", ["a", "b", "c"], warnings)
        assert result.n_items == 3
        assert result.n_used == 5
        assert result.n_excluded == 2
        assert warnings[0] == (
            "Reliability for scale 'S' used 5 respondents who answered all its items; "
            "2 respondents with a missing answer were left out."
        )
        assert result.alpha == pytest.approx(
            cronbach_alpha(complete_cases(scored, ["a", "b", "c"]))[0]
        )

    def test_two_item_scale_has_alpha_but_no_omega(self):
        warnings: list[str] = []
        result = scale_reliability(HAND, "Pair", ["x", "y"], warnings)
        assert result.alpha == pytest.approx(0.75)
        assert math.isnan(result.omega_total)
        assert result.loadings.isna().all()
        assert any("needs at least 3 items" in w for w in warnings)

    def test_constant_scale_warns_that_alpha_is_missing(self):
        warnings: list[str] = []
        data = frame({"a": [3, 3, 3, 3], "b": [3, 3, 3, 3], "c": [3, 3, 3, 3]})
        result = scale_reliability(data, "Flat", ["a", "b", "c"], warnings)
        assert math.isnan(result.alpha)
        assert any(
            w.startswith("Cronbach's alpha was not computed for scale 'Flat'") for w in warnings
        )


# ---------------------------------------------------------------------------- bfi


@pytest.fixture(scope="module")
def bfi_schema() -> SurveySchema:
    return SurveySchema.load(BFI_SCHEMA)


def _bfi(schema: SurveySchema, bfi_csv):
    return prepare_data(load_csv(bfi_csv), schema)


def test_bfi_all_scales_in_schema_order(bfi_csv_path, bfi_schema):
    warnings: list[str] = []
    results = reliability(_bfi(bfi_schema, bfi_csv_path), bfi_schema, warnings)
    assert list(results) == list(bfi_schema.scales)
    for result in results.values():
        assert 0 < result.alpha < 1
        assert result.alpha_ci[0] < result.alpha < result.alpha_ci[1]
        assert 0 < result.omega_total < 1
        assert result.n_used + result.n_excluded == 2800
        assert result.reverse_warnings == []
    table = summary_table(results)
    assert list(table.columns) == [
        "n_items",
        "n_used",
        "n_excluded",
        "alpha",
        "alpha_ci_low",
        "alpha_ci_high",
        "omega_total",
    ]
    assert len(warnings) == 5  # one listwise-deletion note per scale, nothing else


def test_bfi_undeclared_reverse_items_are_all_warned_about(bfi_csv_path, bfi_schema):
    schema = replace(bfi_schema, reverse_items=[])
    results = reliability(_bfi(schema, bfi_csv_path), schema)
    warned = {w.item for r in results.values() for w in r.reverse_warnings}
    assert set(bfi_schema.reverse_items) <= warned
    # Measured on bfi in Stage 4 and quoted in docs/decisions.md: the 7 truly reverse-keyed
    # items plus 6 correctly keyed items pulled the wrong way by the mis-keyed ones.
    assert len(warned) == 13


def test_bfi_with_declared_reverse_items_has_no_check_question_warnings(bfi_csv_path, bfi_schema):
    # Measured on bfi in Stage 4: with A1, C4, C5, E1, E2, O2 and O5 declared as reverse
    # items, every corrected item-total r is positive (lowest: O4, 0.22), so none fire.
    warnings: list[str] = []
    results = reliability(_bfi(bfi_schema, bfi_csv_path), bfi_schema, warnings)
    flagged = [w for r in results.values() for w in r.reverse_warnings]
    assert len(flagged) == 0
    assert not any(w.startswith("Check this question") for w in warnings)
    lowest = min(r.item_stats["corrected_item_total"].min() for r in results.values())
    assert lowest == pytest.approx(0.2199, abs=1e-4)
