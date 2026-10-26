"""Tests for power.py (Stage 6).

Hand-checkable cases use textbook results (Cohen's tables, the normal approximation, the
equivalence of a two-group ANOVA and a t-test). The G*Power comparison reads values the
owner computed in G*Power (``tests/fixtures/gpower_reference.json``, BLUEPRINT §8.3) and
skips if that file has not been filled in.
"""

from __future__ import annotations

import json
import math
from typing import Any

import pytest
from statsmodels.stats.power import FTestAnovaPower, TTestIndPower

from surveydoctor.power import (
    BENCHMARK_CAVEAT,
    benchmark_label,
    min_d_two_groups,
    min_f_anova,
    min_r_correlation,
    sample_sensitivity,
)
from tests.conftest import FIXTURES

GPOWER_FIXTURE = FIXTURES / "gpower_reference.json"
GPOWER_TOLERANCE = 0.01  # BLUEPRINT §8.3

# Standard normal quantiles for alpha = 0.05 (two-sided) and power = 0.80.
Z_975 = 1.959964
Z_80 = 0.841621


# --- Two groups (Cohen's d) ---------------------------------------------------------------


def test_d_64_per_group_is_about_half() -> None:
    # Cohen's table: 64 per group detect d = 0.5 with 80% power at alpha = 0.05.
    result = min_d_two_groups(64, 64)
    assert result.min_effect == pytest.approx(0.5, abs=0.002)
    assert result.effect_measure == "d"
    assert result.test == "two_groups"
    assert result.n_total == 128
    assert result.details == {"n1": 64, "n2": 64}
    # statsmodels gives 0.4991, just under the medium benchmark of 0.5.
    assert result.label == "small to medium"


def test_d_large_groups_match_normal_approximation() -> None:
    # For large groups the t-test is close to a z-test: d = (z_.975 + z_.80) * sqrt(1/n1 + 1/n2).
    result = min_d_two_groups(1000, 1000)
    assert result.min_effect == pytest.approx((Z_975 + Z_80) * math.sqrt(2 / 1000), abs=1e-3)


def test_d_achieves_target_power() -> None:
    result = min_d_two_groups(30, 90)
    achieved = TTestIndPower().power(effect_size=result.min_effect, nobs1=30, ratio=3, alpha=0.05)
    assert achieved == pytest.approx(0.80, abs=1e-5)


def test_d_group_order_does_not_matter() -> None:
    assert min_d_two_groups(30, 90).min_effect == pytest.approx(
        min_d_two_groups(90, 30).min_effect, abs=1e-6
    )


def test_d_unequal_groups_are_less_sensitive() -> None:
    assert min_d_two_groups(30, 90).min_effect > min_d_two_groups(60, 60).min_effect


def test_d_shrinks_as_sample_grows() -> None:
    effects = [min_d_two_groups(n, n).min_effect for n in (10, 50, 200, 1000)]
    assert effects == sorted(effects, reverse=True)


def test_d_smallest_groups_still_solve() -> None:
    result = min_d_two_groups(2, 2)
    assert math.isfinite(result.min_effect)
    assert result.label == "large or above"


@pytest.mark.parametrize(("n1", "n2"), [(1, 10), (10, 1), (0, 0)])
def test_d_rejects_groups_below_two(n1: int, n2: int) -> None:
    with pytest.raises(ValueError, match="at least 2 respondents"):
        min_d_two_groups(n1, n2)


# --- Correlation (r) ----------------------------------------------------------------------


def test_r_by_hand() -> None:
    # n = 103: sqrt(n - 3) = 10, so z = (1.959964 + 0.841621) / 10 = 0.2801585.
    result = min_r_correlation(103)
    assert result.min_effect == pytest.approx(math.tanh(0.2801585), abs=1e-6)
    assert result.min_effect == pytest.approx(0.2730, abs=1e-4)
    assert result.effect_measure == "r"
    assert result.n_total == 103
    assert result.details == {}
    assert result.label == "small to medium"


def test_r_shrinks_as_sample_grows() -> None:
    effects = [min_r_correlation(n).min_effect for n in (10, 50, 200, 1000)]
    assert effects == sorted(effects, reverse=True)


def test_r_stays_below_one_for_tiny_samples() -> None:
    assert 0 < min_r_correlation(4).min_effect < 1


def test_r_rejects_fewer_than_four() -> None:
    with pytest.raises(ValueError, match="at least 4 respondents"):
        min_r_correlation(3)


# --- One-way ANOVA (Cohen's f) ------------------------------------------------------------


def test_f_two_groups_is_half_of_d() -> None:
    # With 2 groups the ANOVA F-test equals the two-sided t-test (F = t²), and f = d / 2.
    d = min_d_two_groups(50, 50).min_effect
    f = min_f_anova(100, 2).min_effect
    assert f == pytest.approx(d / 2, abs=1e-4)


def test_f_achieves_target_power() -> None:
    result = min_f_anova(159, 3)
    assert FTestAnovaPower().power(result.min_effect, 159, 0.05, 3) == pytest.approx(0.80, abs=1e-6)
    # Cohen's table: about 52 per group (N = 156) detect f = 0.25 with 3 groups.
    assert result.min_effect == pytest.approx(0.25, abs=0.005)
    assert result.details == {"k_groups": 3}
    assert result.n_total == 159


def test_f_small_sample_beyond_library_solver_range() -> None:
    # statsmodels' own solver only searches f < 1 and fails here; the fallback must
    # still return the f at which the same statsmodels power function gives 0.80.
    with pytest.raises(ValueError):
        FTestAnovaPower().solve_power(effect_size=None, nobs=12, k_groups=3, alpha=0.05, power=0.80)
    result = min_f_anova(12, 3)
    assert result.min_effect > 1
    assert FTestAnovaPower().power(result.min_effect, 12, 0.05, 3) == pytest.approx(0.80, abs=1e-6)
    assert result.label == "large or above"


def test_f_more_groups_need_larger_effect_at_same_n() -> None:
    assert min_f_anova(120, 6).min_effect > min_f_anova(120, 3).min_effect


@pytest.mark.parametrize(
    ("n_total", "k", "message"), [(100, 1, "at least 2 groups"), (3, 3, "more than 3 respondents")]
)
def test_f_rejects_bad_inputs(n_total: int, k: int, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        min_f_anova(n_total, k)


# --- Shared behaviour ---------------------------------------------------------------------


def test_alpha_and_power_are_configurable() -> None:
    base = min_d_two_groups(50, 50).min_effect
    stricter_alpha = min_d_two_groups(50, 50, alpha=0.01)
    higher_power = min_d_two_groups(50, 50, power=0.90)
    assert stricter_alpha.min_effect > base
    assert higher_power.min_effect > base
    assert stricter_alpha.alpha == 0.01
    assert higher_power.power == 0.90


@pytest.mark.parametrize(
    ("alpha", "power", "message"),
    [
        (0, 0.8, "alpha"),
        (1, 0.8, "alpha"),
        (0.05, 1, "power"),
        (0.05, 0.0, "power"),
        (0.5, 0.4, "larger than alpha"),
    ],
)
def test_rejects_bad_alpha_or_power(alpha: float, power: float, message: str) -> None:
    for call in (
        lambda: min_d_two_groups(50, 50, alpha, power),
        lambda: min_r_correlation(50, alpha, power),
        lambda: min_f_anova(50, 3, alpha, power),
    ):
        with pytest.raises(ValueError, match=message):
            call()


@pytest.mark.parametrize(
    ("value", "measure", "expected"),
    [
        (0.19, "d", "below small"),
        (0.2, "d", "small to medium"),
        (0.5, "d", "medium to large"),
        (0.8, "d", "large or above"),
        (0.09, "r", "below small"),
        (0.3, "r", "medium to large"),
        (0.5, "r", "large or above"),
        (-0.35, "r", "medium to large"),
        (0.1, "f", "small to medium"),
        (0.25, "f", "medium to large"),
        (0.39, "f", "medium to large"),
        (0.4, "f", "large or above"),
    ],
)
def test_benchmark_label(value: float, measure: str, expected: str) -> None:
    assert benchmark_label(value, measure) == expected


def test_benchmark_label_rejects_unknown_measure() -> None:
    with pytest.raises(ValueError, match="Unknown effect measure"):
        benchmark_label(0.3, "eta")


def test_every_result_carries_the_benchmark_caveat() -> None:
    for result in sample_sensitivity(200):
        assert result.caveat == BENCHMARK_CAVEAT
        assert "rough" in result.caveat


def test_sample_sensitivity_splits_evenly() -> None:
    two_groups, correlation, anova = sample_sensitivity(201, k_groups=4)
    assert two_groups.details == {"n1": 100, "n2": 101}
    assert two_groups.min_effect == pytest.approx(min_d_two_groups(100, 101).min_effect)
    assert correlation.min_effect == pytest.approx(min_r_correlation(201).min_effect)
    assert anova.min_effect == pytest.approx(min_f_anova(201, 4).min_effect)
    assert {r.n_total for r in (two_groups, correlation, anova)} == {201}


# --- G*Power reference (BLUEPRINT §8.3) ---------------------------------------------------


def _gpower_cases() -> list[dict[str, Any]]:
    if not GPOWER_FIXTURE.exists():
        pytest.skip(
            "tests/fixtures/gpower_reference.json not found. Compute the cases listed in "
            "docs/gpower_cases.md in G*Power and save them there."
        )
    cases = json.loads(GPOWER_FIXTURE.read_text(encoding="utf-8"))["cases"]
    if any(case.get("gpower_effect") is None for case in cases):
        pytest.skip("gpower_reference.json has cases without a G*Power effect size yet.")
    return cases


def _ours(case: dict[str, Any]) -> float:
    alpha, power = case["alpha"], case["power"]
    if case["test"] == "two_groups":
        return min_d_two_groups(case["n1"], case["n2"], alpha, power).min_effect
    if case["test"] == "correlation":
        return min_r_correlation(case["n"], alpha, power).min_effect
    if case["test"] == "anova":
        return min_f_anova(case["n"], case["k_groups"], alpha, power).min_effect
    raise ValueError(f"Unknown test '{case['test']}' in gpower_reference.json")


def test_matches_gpower() -> None:
    cases = _gpower_cases()
    assert len(cases) >= 5, "BLUEPRINT §8.3 asks for 5 G*Power cases."
    mismatches = [
        f"{case['id']}: ours {_ours(case):.4f}, G*Power {case['gpower_effect']:.4f}"
        for case in cases
        if abs(_ours(case) - case["gpower_effect"]) > GPOWER_TOLERANCE
    ]
    assert not mismatches, "Differences above 0.01:\n" + "\n".join(mismatches)
