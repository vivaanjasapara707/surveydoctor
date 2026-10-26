"""Tests for the simulation study (Stage 7): pattern generation, contamination, metrics and
the summary. Expected values are worked out by hand."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from evaluation.run_simulation import (
    _share,
    flag_table,
    missing_table,
    partial_availability,
    run_all,
    score_table,
    summary_markdown,
)
from evaluation.simulate import (
    FLAG_MEASURE,
    PATTERNS,
    RATES,
    RULE_PREFIX,
    base_data,
    careless_answers,
    contaminate,
    flag_metrics,
    n_contaminated,
    oriented_score,
    run_condition,
    score_metrics,
)
from surveydoctor.schema import SurveySchema
from tests.conftest import BFI_SCHEMA


def rng(seed: int = 0) -> np.random.Generator:
    return np.random.default_rng(seed)


ORIGINAL = np.arange(1, 1 + 40 * 10).reshape(40, 10) % 6 + 1  # 40 respondents, 10 items


# --- Careless patterns --------------------------------------------------------------------


@pytest.mark.parametrize("pattern", PATTERNS)
def test_patterns_stay_on_the_scale(pattern: str) -> None:
    answers = careless_answers(pattern, ORIGINAL, 1, 6, rng())
    assert answers.shape == ORIGINAL.shape
    assert answers.min() >= 1 and answers.max() <= 6
    assert np.array_equal(answers, np.round(answers))


def test_random_uses_every_answer() -> None:
    answers = careless_answers("random", np.zeros((500, 25)), 1, 6, rng())
    assert set(np.unique(answers)) == {1, 2, 3, 4, 5, 6}


def test_straightline_is_constant_per_respondent() -> None:
    answers = careless_answers("straightline", np.zeros((500, 25)), 1, 6, rng())
    assert (answers == answers[:, [0]]).all()
    assert set(np.unique(answers[:, 0])) == {1, 2, 3, 4, 5, 6}


def test_patterned_cycles_through_the_scale() -> None:
    answers = careless_answers("patterned", np.zeros((300, 8)), 1, 6, rng())
    starts = answers[:, 0]
    # Each row is start, start+1, ..., wrapping from 6 back to 1.
    expected = (starts[:, None] - 1 + np.arange(8)) % 6 + 1
    assert np.array_equal(answers, expected)
    assert set(np.unique(starts)) == {1, 2, 3, 4, 5, 6}
    # By hand: starting at 5 on 8 items gives 5, 6, 1, 2, 3, 4, 5, 6.
    row = answers[starts == 5][0]
    assert row.tolist() == [5, 6, 1, 2, 3, 4, 5, 6]


def test_midpoint_on_even_scale_is_lower_or_upper_middle() -> None:
    answers = careless_answers("midpoint", np.zeros((400, 25)), 1, 6, rng())
    assert (answers == answers[:, [0]]).all()
    assert set(np.unique(answers)) == {3, 4}


def test_midpoint_on_odd_scale_is_the_middle() -> None:
    answers = careless_answers("midpoint", np.zeros((50, 9)), 1, 5, rng())
    assert (answers == 3).all()


def test_partial_keeps_first_half() -> None:
    original = np.full((200, 25), 9)  # 9 is off the 1-6 scale, so kept answers are visible
    answers = careless_answers("partial", original, 1, 6, rng())
    assert (answers[:, :12] == 9).all()  # floor(25 / 2) = 12 items kept
    assert answers[:, 12:].min() >= 1 and answers[:, 12:].max() <= 6
    assert (original == 9).all()  # the input is not modified


def test_unknown_pattern() -> None:
    with pytest.raises(ValueError, match="Unknown pattern"):
        careless_answers("zigzag", ORIGINAL, 1, 6, rng())


# --- Contamination ------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("n", "rate", "expected"),
    [(2436, 0.05, 122), (2436, 0.10, 244), (2436, 0.20, 487), (10, 0.05, 1), (30, 0.05, 2)],
)
def test_n_contaminated_rounds_half_up(n: int, rate: float, expected: int) -> None:
    # 2436 × 0.05 = 121.8, × 0.10 = 243.6, × 0.20 = 487.2; 10 × 0.05 = 0.5; 30 × 0.05 = 1.5.
    assert n_contaminated(n, rate) == expected


@pytest.fixture
def schema() -> SurveySchema:
    return SurveySchema.load(BFI_SCHEMA)


@pytest.fixture
def small_base(schema: SurveySchema) -> pd.DataFrame:
    values = np.random.default_rng(1).integers(1, 7, size=(100, len(schema.items)))
    data = pd.DataFrame(values.astype(float), columns=schema.items)
    data.insert(0, "id", range(1000, 1100))
    return data


def test_contaminate_replaces_only_labelled_rows(
    small_base: pd.DataFrame, schema: SurveySchema
) -> None:
    data, labels = contaminate(small_base, schema, "straightline", 0.10, rng(3))
    assert labels.sum() == 10
    changed = (data[schema.items] != small_base[schema.items]).any(axis=1)
    assert not changed[labels == 0].any()
    replaced = data.loc[labels == 1, schema.items]
    assert replaced.nunique(axis=1).eq(1).all()
    assert data["id"].equals(small_base["id"])
    assert small_base[schema.items].nunique(axis=1).gt(1).all()  # base not modified


def test_contaminate_is_reproducible(small_base: pd.DataFrame, schema: SurveySchema) -> None:
    first = contaminate(small_base, schema, "random", 0.2, rng(7))
    second = contaminate(small_base, schema, "random", 0.2, rng(7))
    other = contaminate(small_base, schema, "random", 0.2, rng(8))
    assert first[0].equals(second[0]) and first[1].equals(second[1])
    assert not first[1].equals(other[1])


def test_same_seed_selects_same_rows_across_patterns(
    small_base: pd.DataFrame, schema: SurveySchema
) -> None:
    labels = [contaminate(small_base, schema, p, 0.1, rng(5))[1] for p in PATTERNS]
    assert all(lab.equals(labels[0]) for lab in labels)


@pytest.mark.parametrize("rate", [0, 1, -0.1])
def test_contaminate_rejects_bad_rate(
    small_base: pd.DataFrame, schema: SurveySchema, rate: float
) -> None:
    with pytest.raises(ValueError, match="rate"):
        contaminate(small_base, schema, "random", rate, rng())


# --- Metrics ------------------------------------------------------------------------------

LABELS = pd.Series([0, 0, 0, 1, 1])


def test_perfect_high_score() -> None:
    result = score_metrics(pd.Series([1.0, 2, 3, 8, 9]), LABELS, "longstring")
    assert result == {"roc_auc": 1.0, "pr_auc": 1.0, "missing_careless": 0.0}


def test_low_direction_is_turned_around() -> None:
    # even_odd: low = careless. The two careless rows have the lowest r.
    result = score_metrics(pd.Series([0.9, 0.8, 0.7, -0.5, 0.1]), LABELS, "even_odd")
    assert result["roc_auc"] == 1.0


def test_roc_auc_by_hand() -> None:
    # Careless scores 2 and 4 against attentive 1, 3, 5: of the 6 careless-attentive pairs,
    # the careless one is higher in (2>1), (4>1), (4>3) = 3 pairs, so ROC-AUC = 3/6 = 0.5.
    result = score_metrics(pd.Series([1.0, 3, 5, 2, 4]), LABELS, "longstring")
    assert result["roc_auc"] == pytest.approx(0.5)
    # Average precision by hand: ranking 5(0), 4(1), 3(0), 2(1), 1(0). Precision at the two
    # careless hits: 1/2 and 2/4, so AP = (0.5 + 0.5) / 2 = 0.5.
    assert result["pr_auc"] == pytest.approx(0.5)


def test_missing_values_rank_as_least_careless() -> None:
    values = pd.Series([1.0, 2, 3, np.nan, np.nan])
    assert oriented_score(values, "longstring").tolist() == [1.0, 2, 3, 0.0, 0.0]
    assert oriented_score(pd.Series([0.5, np.nan]), "person_total").tolist() == [-0.5, -1.5]
    result = score_metrics(values, LABELS, "longstring")
    assert result["roc_auc"] == 0.0
    assert result["missing_careless"] == 1.0


def test_composite_is_already_oriented() -> None:
    assert oriented_score(pd.Series([0.2, 0.9]), "composite").tolist() == [0.2, 0.9]


def test_irv_has_no_direction() -> None:
    with pytest.raises(ValueError, match="no single careless direction"):
        oriented_score(pd.Series([1.0]), "irv")


def test_flag_metrics_by_hand() -> None:
    # Flags on rows 2, 3: one true positive (row 3) of 2 careless -> recall 0.5;
    # 1 of 2 flagged is careless -> precision 0.5.
    flagged = pd.Series([False, False, True, True, False])
    assert flag_metrics(flagged, LABELS) == {
        "recall": 0.5,
        "precision": 0.5,
        "share_flagged": 0.4,
    }


def test_flag_metrics_nobody_flagged() -> None:
    result = flag_metrics(pd.Series([False] * 5), LABELS)
    assert result["recall"] == 0.0 and result["precision"] == 0.0


# --- On the bfi sample --------------------------------------------------------------------


@pytest.fixture
def bfi_base(bfi_csv_path, schema: SurveySchema) -> pd.DataFrame:
    return base_data(bfi_csv_path, schema)


def test_base_data_is_complete_cases_with_ids(bfi_base: pd.DataFrame, schema: SurveySchema) -> None:
    assert len(bfi_base) == 2436  # complete cases, as in Stages 4 and 5
    assert bfi_base.columns.tolist() == ["id", *schema.items]
    assert bfi_base[schema.items].notna().all().all()
    assert bfi_base["id"].is_unique


def test_run_condition_on_bfi(bfi_base: pd.DataFrame, schema: SurveySchema) -> None:
    records = pd.DataFrame(run_condition(bfi_base, schema, "straightline", 0.1, 0))
    assert set(records["n_careless"]) == {244}
    measures = records.set_index("measure")
    assert {"composite", "longstring", "mahalanobis", FLAG_MEASURE} <= set(measures.index)
    # Every straightliner has the maximum longstring (25 items), so few attentive
    # respondents can tie with them and longstring separates almost perfectly.
    assert measures.loc["longstring", "roc_auc"] > 0.99
    # Any longstring of 25 crosses the default threshold (13), so every straightliner is flagged.
    assert measures.loc[FLAG_MEASURE, "recall"] == 1.0
    assert measures.loc[RULE_PREFIX + "longstring", "recall"] == 1.0
    # The combined flag fires if any rule fires, so no single rule can have higher recall.
    rule_recalls = measures.loc[measures.index.str.startswith(RULE_PREFIX), "recall"]
    assert (rule_recalls <= measures.loc[FLAG_MEASURE, "recall"]).all()
    assert len(rule_recalls) >= 4  # longstring, mahalanobis, even_odd, person_total


def test_run_all_covers_every_condition(bfi_base: pd.DataFrame, schema: SurveySchema) -> None:
    results = run_all(bfi_base, schema, n_reps=2)
    conditions = results[["pattern", "rate", "seed"]].drop_duplicates()
    assert len(conditions) == len(PATTERNS) * len(RATES) * 2
    text = summary_markdown(results, n_reps=2)
    assert "2436" in text and "seeds 0–1" in text
    for pattern in PATTERNS:
        assert f"## Pattern: {pattern}" in text
    assert "### Longstring rule" in text
    assert "nan" not in text


# --- Summary tables -----------------------------------------------------------------------


def _fake_results() -> pd.DataFrame:
    rows = []
    for seed, (auc, recall) in enumerate([(0.8, 0.6), (0.9, 0.8)]):
        base = {"pattern": "random", "rate": 0.1, "seed": seed}
        base |= {"n_respondents": 100, "n_careless": 10}
        rows.append(base | {"measure": "composite", "roc_auc": auc, "pr_auc": auc / 2})
        rows.append(
            base
            | {"measure": "person_total", "roc_auc": auc, "pr_auc": 0.1}
            | {"missing_careless": 0.25}
        )
        rows.append(base | {"measure": FLAG_MEASURE, "recall": recall, "precision": 0.5})
    frame = pd.DataFrame(rows)
    frame["missing_careless"] = frame["missing_careless"].fillna(0.0)
    return frame


def test_score_table_mean_and_sd() -> None:
    # ROC-AUC 0.8 and 0.9: mean 0.85, SD (ddof 1) = sqrt(2 × 0.05² / 1) = 0.0707.
    table = score_table(_fake_results(), "random", "roc_auc")
    assert "| Composite score | 0.850 ± 0.071 |" in table
    assert table.splitlines()[0] == "| Measure | 10% |"


def test_flag_table() -> None:
    table = flag_table(_fake_results())
    assert "| random | 0.700 ± 0.141 | 0.500 ± 0.000 |" in table


def test_missing_table_lists_only_measures_with_gaps() -> None:
    table = missing_table(_fake_results())
    assert "Person-total correlation | 25%" in table
    assert "Composite" not in table


@pytest.mark.parametrize(
    ("value", "expected"),
    [(np.nan, "not computed"), (0.0, "0%"), (0.0002, "<1%"), (0.25, "25%"), (1.0, "100%")],
)
def test_share_formatting(value: float, expected: str) -> None:
    assert _share(value) == expected


def test_partial_availability_names_conditions() -> None:
    results = _fake_results()
    other_run = results[results["seed"] == 0].assign(pattern="midpoint")
    other_run = other_run[other_run["measure"] != "person_total"]
    combined = pd.concat([results, other_run], ignore_index=True)
    (sentence,) = partial_availability(combined)
    assert sentence.startswith(
        "Person-total correlation was computed in 2 of 3 runs (random at 10%)"
    )
    assert partial_availability(results) == []


def test_flag_table_for_one_rule() -> None:
    results = _fake_results()
    rule_rows = results[results["measure"] == FLAG_MEASURE].assign(measure="rule_longstring")
    table = flag_table(pd.concat([results, rule_rows]), "rule_longstring")
    assert "| random | 0.700 ± 0.141 | 0.500 ± 0.000 |" in table
    assert flag_table(results, "rule_longstring").count("\n") == 1  # header only
