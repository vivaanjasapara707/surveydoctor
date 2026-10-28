"""Tests for text.py (Stage 10): the approved verdict rules (docs/design.md §5) and the
sentence templates, on constructed inputs."""

from __future__ import annotations

import math
from types import SimpleNamespace as NS

import pytest

from surveydoctor import text
from surveydoctor.fsqca import compare_runs
from surveydoctor.power import min_d_two_groups, min_f_anova, min_r_correlation
from surveydoctor.robustness import Correlation, GroupComparison
from tests.test_fsqca import make_run

# --- Formatting ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "decimals", "expected"),
    [(0.7049, 2, "0.70"), (-0.004, 2, "0.00"), (-0.006, 2, "-0.01"), (math.nan, 2, "–"),
     (None, 2, "–"), (1.23456, 3, "1.235")],
)  # fmt: skip
def test_fmt(value, decimals: int, expected: str) -> None:
    assert text.fmt(value, decimals) == expected


def test_fmt_p_and_counts() -> None:
    assert text.fmt_p(0.0004) == "p < 0.001"
    assert text.fmt_p(0.0493) == "p = 0.049"
    assert text.fmt_count(2800) == "2,800"
    assert text.fmt_share(686, 2800) == "24.5%"
    assert text.join_names(["A"]) == "A"
    assert text.join_names(["A", "B", "C"]) == "A, B and C"


# --- Check statuses -----------------------------------------------------------------------


def results(n2: int = 0, alphas=(0.8, 0.75), kmo: float = 0.85, shared=(), verdict="stable",
            reverse=(), skipped=None):  # fmt: skip
    reliability = {
        f"S{i}": NS(scale=f"S{i}", alpha=a, alpha_ci=(a - 0.02, a + 0.02), n_used=100,
                    reverse_warnings=[NS(item=item) for item in reverse if i == 0])
        for i, a in enumerate(alphas)
    }  # fmt: skip
    alignment = {
        f"S{i}": NS(scale=f"S{i}", shared_with=["other"] if f"S{i}" in shared else [])
        for i in range(len(alphas))
    }
    structure = NS(skipped_reason=skipped, kmo=None if skipped else NS(overall=kmo),
                   efa=None if skipped else object(), alignment=alignment)  # fmt: skip
    robustness = None if verdict is None else NS(verdict=verdict)
    overview = NS(n_respondents=1000, n_items=10, n_scales=2, n_flagged=50, n_flagged_two_rules=n2)
    return NS(overview=overview, reliability=reliability, structure=structure,
              robustness=robustness)  # fmt: skip


def test_careless_review_only_with_two_rule_flags() -> None:
    assert text.careless_status(results(n2=0)).status == "clear"
    status = text.careless_status(results(n2=72))
    assert status.status == "review"
    assert status.reason == "72 respondents were flagged by two or more rules."


def test_careless_is_never_problem() -> None:
    assert text.careless_status(results(n2=1000)).status == "review"


def test_reliability_rules() -> None:
    assert text.reliability_status(results(alphas=(0.70, 0.9)).reliability).status == "clear"
    low = text.reliability_status(results(alphas=(0.69, 0.9)).reliability)
    assert low.status == "review" and "below 0.70 for S0" in low.reason
    nan = text.reliability_status(results(alphas=(math.nan, 0.9)).reliability)
    assert nan.status == "review" and "could not be computed for S0" in nan.reason
    rev = text.reliability_status(results(reverse=("q3",)).reliability)
    assert rev.status == "review" and "q3" in rev.reason
    assert text.reliability_status({}).status == "not_checked"


def test_structure_rules() -> None:
    assert text.structure_status(results().structure).status == "clear"
    assert text.structure_status(results(kmo=0.59).structure).status == "review"
    shared = text.structure_status(results(shared=("S1",)).structure)
    assert shared.status == "review" and "S1 do not have a factor of their own" in shared.reason
    skipped = text.structure_status(results(skipped="too few items").structure)
    assert skipped.status == "review"


@pytest.mark.parametrize(
    ("verdict", "status"),
    [("stable", "clear"), ("sensitive", "review"), ("unstable", "problem"), (None, "not_checked")],
)
def test_robustness_rules(verdict, status: str) -> None:
    robustness = None if verdict is None else NS(verdict=verdict)
    assert text.robustness_status(robustness).status == status


def test_robustness_not_computable() -> None:
    assert text.robustness_status(NS(verdict=None)).status == "not_checked"


# --- Overall verdict ----------------------------------------------------------------------


def test_overall_clear() -> None:
    verdict = text.overall_verdict(results())
    assert verdict.status == "clear"
    assert verdict.headline == "No concerns found by these checks"
    assert verdict.sentence == "None of the checks that ran raised a concern."
    assert [c.check for c in verdict.checks] == ["careless", "reliability", "structure",
                                                 "robustness"]  # fmt: skip


def test_overall_is_worst_check() -> None:
    verdict = text.overall_verdict(results(n2=5, alphas=(0.6, 0.8)))
    assert verdict.status == "review"
    assert (
        verdict.sentence
        == "Look at careless responding and reliability before drawing conclusions."
    )
    problem = text.overall_verdict(results(verdict="unstable"))
    assert problem.status == "problem" and problem.headline == "Serious concern"
    assert problem.sentence.startswith("The declared result reverses")


def test_overall_names_checks_not_run() -> None:
    verdict = text.overall_verdict(results(verdict=None))
    assert verdict.status == "clear"  # never claims more: says what was not checked
    assert verdict.sentence.endswith("Not checked: robustness.")


# --- Sentences ----------------------------------------------------------------------------


def test_alpha_sentence() -> None:
    r = NS(scale="Openness", alpha=0.603, alpha_ci=(0.578, 0.626), n_used=2726)
    assert text.alpha_sentence(r) == (
        "Alpha for Openness is 0.60 (95% CI 0.58 to 0.63, N = 2,726), which is below the 0.70 "
        "commonly treated as acceptable. High alpha does not prove that a scale measures a "
        "single concept."
    )
    ok = NS(scale="N", alpha=0.81, alpha_ci=(0.80, 0.82), n_used=10)
    assert "which is commonly treated as acceptable" in text.alpha_sentence(ok)


def test_sensitivity_sentences() -> None:
    d = text.sensitivity_sentence(min_d_two_groups(64, 64))
    assert d == (
        "For a comparison of two groups (t-test) with groups of 64 and 64, the smallest effect "
        "detected with 80% power at α = 0.05 is d = 0.50 (small to medium on Cohen's scale)."
    )
    assert "|r| = " in text.sensitivity_sentence(min_r_correlation(103))
    assert "3 groups (one-way ANOVA)" in text.sensitivity_sentence(min_f_anova(159, 3))


def test_robustness_sentences() -> None:
    groups = GroupComparison("Neuroticism", "gender", 1, 2)
    stable = NS(analysis=groups, verdict="stable", changed_variants=[], caveat="CAVEAT")
    assert text.robustness_sentence(stable) == (
        "Stable: the difference in Neuroticism between gender = 1 and gender = 2 keeps the same "
        "direction and significance in every exclusion variant. CAVEAT"
    )
    sensitive = NS(analysis=Correlation("A", "B"), verdict="sensitive",
                   changed_variants=["any_rule", "two_rules"], caveat="C")  # fmt: skip
    assert text.robustness_sentence(sensitive) == (
        "Sensitive to careless responses: whether the correlation between A and B is "
        "significant changes when excluding respondents flagged by any rule and excluding "
        "respondents flagged by two or more rules. C"
    )


def test_limitations_always_start_with_sampling_warning() -> None:
    structure = NS(skipped_reason=None, n_used=150, items=list(range(10)), kmo=NS(overall=0.55))
    res = NS(schema=NS(duration_column=None), structure=structure, fsqca=None)
    items = text.limitations(res)
    assert items[0] == text.CONVENIENCE_SAMPLE
    assert text.NO_DURATION in items
    assert (
        "Factor results may be unstable (only 150 complete respondents and KMO of 0.55)." in items
    )
    assert text.PEARSON_LIMITATION in items
    assert text.COMPOSITE_NOTE in items and text.ITEM_ORDER_NOTE in items
    assert not set(text.FSQCA_LIMITATIONS) & set(items)
    with_time = NS(schema=NS(duration_column="secs"), fsqca=None,
                   structure=NS(skipped_reason="x", n_used=0, items=[], kmo=None))  # fmt: skip
    assert text.NO_DURATION not in text.limitations(with_time)
    assert text.PEARSON_LIMITATION not in text.limitations(with_time)
    with_fsqca = NS(schema=NS(duration_column=None), structure=structure,
                    fsqca=NS(skipped_reason=None))  # fmt: skip
    assert text.limitations(with_fsqca)[-3:] == text.FSQCA_LIMITATIONS
    skipped_fsqca = NS(schema=NS(duration_column=None), structure=structure,
                       fsqca=NS(skipped_reason="tied anchors"))  # fmt: skip
    assert not set(text.FSQCA_LIMITATIONS) & set(text.limitations(skipped_fsqca))


# --- fsQCA --------------------------------------------------------------------------------


def test_fsqca_check_sentences() -> None:
    main = make_run("all", "A*B")
    same = compare_runs("robustness", main, [make_run("any_rule", "A*B")])
    assert text.fsqca_check_sentence(same).startswith(
        "Same: the solution paths are identical in every exclusion variant. This shows "
        "sensitivity to exclusion choices."
    )
    assert text.fsqca_check_status(same) == "clear"
    changed = compare_runs("calibration", main, [make_run("crossover_lower", "A")])
    assert text.fsqca_check_sentence(changed).startswith(
        "Changed: solution paths are added or removed with crossover lower (45th percentile"
    )
    assert text.fsqca_check_status(changed) == "review"
    gone = compare_runs("robustness", main, [make_run("two_rules")])
    assert text.fsqca_check_sentence(gone).startswith(
        "No solution: no truth-table row reaches the thresholds with excluding respondents "
        "flagged by two or more rules."
    )
    assert text.fsqca_check_status(gone) == "review"
    none = compare_runs("robustness", make_run("all"), [make_run("any_rule", "A")])
    assert text.fsqca_check_sentence(none).startswith(
        "No solution on all respondents, so there are no solution paths to compare. A solution "
        "appears with excluding respondents flagged by any rule."
    )
    assert text.fsqca_check_status(none) == "not_checked"


def test_path_status_summary() -> None:
    assert text.path_status_summary(make_run("x", "A"), {"A": "kept"}) == "same"
    changes = {"A": "kept", "B": "new", "C": "missing"}
    assert text.path_status_summary(make_run("x", "A"), changes) == "1 new, 1 missing"
    assert text.path_status_summary(make_run("x"), {"A": "missing"}) == "no solution"
    assert text.path_status_summary(make_run("x", skipped="too few"), {}) == "not run"
