"""Tests for careless.py (Stage 2). Expected values are worked out by hand where possible."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest
from scipy import stats

from surveydoctor.careless import (
    INDEX_DIRECTIONS,
    compute_indices,
    even_odd,
    irv,
    leave_one_out_means,
    longstring,
    mahalanobis,
    person_total,
    psychsyn,
    rowwise_pearson,
    seconds_per_item,
    synonym_pairs,
)
from surveydoctor.io import PreparedData, load_csv, prepare_data, reverse_score
from surveydoctor.schema import SurveySchema
from tests.conftest import BFI_SCHEMA

NAN = np.nan


def frame(rows: list[list[float]], prefix: str = "q", index: list[int] | None = None):
    """DataFrame with columns q1, q2, ... from a list of rows."""
    columns = [f"{prefix}{i + 1}" for i in range(len(rows[0]))]
    return pd.DataFrame(rows, columns=columns, index=index, dtype=float)


# ---------------------------------------------------------------------------- helper


class TestRowwisePearson:
    def test_matches_numpy(self):
        rng = np.random.default_rng(1)
        a = rng.normal(size=(20, 6))
        b = rng.normal(size=(20, 6))
        r = rowwise_pearson(a, b)
        expected = [np.corrcoef(a[i], b[i])[0, 1] for i in range(20)]
        np.testing.assert_allclose(r, expected, atol=1e-12)

    def test_uses_only_positions_present_in_both(self):
        a = np.array([[1.0, 2.0, 3.0, NAN, 10.0]])
        b = np.array([[2.0, 4.0, 7.0, 5.0, NAN]])
        expected = np.corrcoef([1, 2, 3], [2, 4, 7])[0, 1]
        assert rowwise_pearson(a, b)[0] == pytest.approx(expected)

    def test_too_few_pairs_or_no_variance_is_nan(self):
        a = np.array([[1.0, 2.0, NAN], [3.0, 3.0, 3.0]])
        b = np.array([[1.0, 2.0, 3.0], [1.0, 2.0, 3.0]])
        assert np.isnan(rowwise_pearson(a, b, min_pairs=3)).all()

    def test_shape_mismatch_raises(self):
        with pytest.raises(ValueError):
            rowwise_pearson(np.zeros((2, 3)), np.zeros((2, 4)))


# ---------------------------------------------------------------------------- longstring


class TestLongstring:
    def test_blueprint_example(self):
        assert longstring(frame([[3, 3, 3, 1, 2]])).iloc[0] == 3

    def test_missing_value_breaks_a_run(self):
        assert longstring(frame([[3, 3, NAN, 3, 3]])).iloc[0] == 2

    def test_run_at_the_end_counts(self):
        assert longstring(frame([[1, 2, 4, 4, 4, 4]])).iloc[0] == 4

    def test_straightliner_equals_number_of_items(self):
        assert longstring(frame([[4] * 25])).iloc[0] == 25

    def test_all_different_is_one_and_all_missing_is_nan(self):
        result = longstring(frame([[1, 2, 3, 4], [NAN, NAN, NAN, NAN]]))
        assert result.iloc[0] == 1
        assert np.isnan(result.iloc[1])

    def test_keeps_index(self):
        result = longstring(frame([[1, 1], [2, 3]], index=[7, 42]))
        assert list(result.index) == [7, 42]
        assert list(result) == [2, 1]


# ---------------------------------------------------------------------------- irv


class TestIrv:
    def test_blueprint_example(self):
        assert irv(frame([[1, 2, 3, 4, 5]])).iloc[0] == pytest.approx(math.sqrt(2.5))
        assert irv(frame([[1, 2, 3, 4, 5]])).iloc[0] == pytest.approx(1.5811, abs=1e-4)

    def test_straightliner_is_zero(self):
        assert irv(frame([[3, 3, 3, 3]])).iloc[0] == 0

    def test_ignores_missing_and_needs_two_answers(self):
        result = irv(frame([[1, NAN, 3, NAN], [2, NAN, NAN, NAN]]))
        assert result.iloc[0] == pytest.approx(math.sqrt(2))
        assert np.isnan(result.iloc[1])


# ---------------------------------------------------------------------------- mahalanobis


class TestMahalanobis:
    def test_single_item_by_hand(self):
        # Mean 3, sample variance 2.5, so D² = (x - 3)² / 2.5.
        result = mahalanobis(frame([[1], [2], [3], [4], [5]]))
        np.testing.assert_allclose(result["mahalanobis"], [1.6, 0.4, 0.0, 0.4, 1.6])
        np.testing.assert_allclose(
            result["mahalanobis_p"], stats.chi2.sf([1.6, 0.4, 0.0, 0.4, 1.6], df=1)
        )

    def test_matches_scipy_distance(self):
        from scipy.spatial.distance import mahalanobis as scipy_mahalanobis

        rng = np.random.default_rng(3)
        data = frame(rng.integers(1, 6, size=(60, 4)).tolist())
        result = mahalanobis(data)
        x = data.to_numpy()
        vi = np.linalg.inv(np.cov(x, rowvar=False))
        expected = [scipy_mahalanobis(row, x.mean(axis=0), vi) ** 2 for row in x]
        np.testing.assert_allclose(result["mahalanobis"], expected, rtol=1e-9)

    def test_mean_d2_identity(self):
        # With mean and covariance (ddof=1) from the same rows, mean D² = k (n - 1) / n.
        rng = np.random.default_rng(4)
        data = frame(rng.normal(size=(50, 5)).tolist())
        assert mahalanobis(data)["mahalanobis"].mean() == pytest.approx(5 * 49 / 50)

    def test_unusual_pattern_scores_highest(self):
        rng = np.random.default_rng(5)
        base = rng.normal(size=200)
        rows = [[b + rng.normal(0, 0.3), b + rng.normal(0, 0.3)] for b in base]
        rows.append([2.0, -2.0])  # each value is ordinary; together they are not
        result = mahalanobis(frame(rows))
        assert result["mahalanobis"].idxmax() == 200
        assert result["mahalanobis_p"].iloc[-1] < 0.001

    def test_rows_with_missing_are_nan_and_excluded_from_mean(self):
        warnings: list[str] = []
        data = frame([[1], [2], [3], [4], [5], [NAN]])
        result = mahalanobis(data, warnings=warnings)
        assert np.isnan(result["mahalanobis"].iloc[5])
        assert result["mahalanobis"].iloc[0] == pytest.approx(1.6)
        assert warnings == [
            "Mahalanobis distance was not computed for 1 respondent with at least one missing "
            "answer."
        ]

    def test_singular_covariance_uses_pseudo_inverse(self):
        rng = np.random.default_rng(6)
        x = rng.normal(size=(30, 2))
        data = frame(np.column_stack([x, x[:, 0]]).tolist())  # third item copies the first
        result = mahalanobis(data)
        assert result["mahalanobis"].notna().all()
        two_items = mahalanobis(frame(x.tolist()))
        # The copied item adds no new information, so the distance is unchanged.
        np.testing.assert_allclose(result["mahalanobis"], two_items["mahalanobis"], atol=1e-8)

    def test_too_few_complete_rows(self):
        warnings: list[str] = []
        result = mahalanobis(frame([[1, 2, 3], [2, 3, 1], [3, 1, 2]]), warnings=warnings)
        assert result.isna().all().all()
        assert "needs more respondents with no missing answers (3) than items (3)" in warnings[0]


# ---------------------------------------------------------------------------- even-odd


def three_scales() -> dict[str, list[str]]:
    """Three 4-item scales over q1..q12."""
    return {
        "S1": ["q1", "q2", "q3", "q4"],
        "S2": ["q5", "q6", "q7", "q8"],
        "S3": ["q9", "q10", "q11", "q12"],
    }


class TestEvenOdd:
    def test_consistent_and_inconsistent_by_hand(self):
        data = frame(
            [
                # Half means (odd, even): S1 (1, 1), S2 (3, 3), S3 (5, 5) -> r = 1.
                [1, 1, 1, 1, 3, 3, 3, 3, 5, 5, 5, 5],
                # S1 (1, 5), S2 (3, 3), S3 (5, 1): odd 1,3,5 vs even 5,3,1 -> r = -1.
                [1, 5, 1, 5, 3, 3, 3, 3, 5, 1, 5, 1],
                # S1 (1, 2), S2 (2, 4), S3 (4, 3): odd 1,2,4 vs even 2,4,3.
                [1, 2, 1, 2, 2, 4, 2, 4, 4, 3, 4, 3],
            ]
        )
        result = even_odd(data, three_scales())
        r3 = np.corrcoef([1, 2, 4], [2, 4, 3])[0, 1]
        np.testing.assert_allclose(result["even_odd"], [1.0, -1.0, r3])
        assert result["even_odd_sb"].iloc[0] == pytest.approx(1.0)
        assert np.isnan(result["even_odd_sb"].iloc[1])  # 2r / (1 + r) undefined at r = -1
        assert result["even_odd_sb"].iloc[2] == pytest.approx(2 * r3 / (1 + r3))

    def test_spearman_brown_missing_when_raw_r_negative(self):
        data = frame(
            [
                # S1 (1, 3), S2 (3, 5), S3 (5, 1): odd 1,3,5 vs even 3,5,1 -> r = -0.5.
                [1, 3, 1, 3, 3, 5, 3, 5, 5, 1, 5, 1],
                # S1 (1, 3), S2 (3, 1), S3 (5, 3): odd 1,3,5 vs even 3,1,3 -> r = 0.
                [1, 3, 1, 3, 3, 1, 3, 1, 5, 3, 5, 3],
            ]
        )
        result = even_odd(data, three_scales())
        np.testing.assert_allclose(result["even_odd"], [-0.5, 0.0], atol=1e-12)
        assert np.isnan(result["even_odd_sb"].iloc[0])  # formula would give -2
        assert result["even_odd_sb"].iloc[1] == pytest.approx(0.0)

    def test_halves_follow_questionnaire_order_not_scale_list_order(self):
        data = frame([[1, 5, 1, 5, 3, 3, 3, 3, 5, 1, 5, 1]])
        shuffled = {**three_scales(), "S1": ["q4", "q2", "q3", "q1"]}
        assert even_odd(data, shuffled)["even_odd"].iloc[0] == pytest.approx(-1.0)

    def test_scales_with_fewer_than_four_items_are_ignored(self):
        scales = {**three_scales(), "Short": ["q13", "q14", "q15"]}
        consistent = [1, 1, 1, 1, 3, 3, 3, 3, 5, 5, 5, 5]
        data = frame([consistent + [5, 1, 5]])
        assert even_odd(data, scales)["even_odd"].iloc[0] == pytest.approx(1.0)

    def test_fewer_than_three_eligible_scales_is_nan_with_warning(self):
        warnings: list[str] = []
        data = frame([[1, 2, 3, 4, 5, 4, 3, 2, 1, 2]])
        scales = {
            "S1": ["q1", "q2", "q3", "q4"],
            "S2": ["q5", "q6", "q7", "q8"],
            "S3": ["q9", "q10"],
        }
        result = even_odd(data, scales, warnings=warnings)
        assert result.isna().all().all()
        assert warnings == [
            "Even-odd consistency was not computed: it needs at least 3 scales with 4 or more "
            "items, and this survey has 2."
        ]

    def test_straightliner_is_nan_with_warning(self):
        warnings: list[str] = []
        result = even_odd(frame([[4] * 12]), three_scales(), warnings=warnings)
        assert np.isnan(result["even_odd"].iloc[0])
        assert "could not be computed for 1 respondent" in warnings[0]

    def test_half_mean_uses_answered_items(self):
        # S1 odd half q1, q3 -> q1 only (q3 missing) = 1; even half q2, q4 = 1.
        data = frame([[1, 1, NAN, 1, 3, 3, 3, 3, 5, 5, 5, 5]])
        assert even_odd(data, three_scales())["even_odd"].iloc[0] == pytest.approx(1.0)


# ---------------------------------------------------------------------------- psychsyn


def synonym_data(n: int = 300, seed: int = 0) -> pd.DataFrame:
    """Six items forming three identical pairs (q1=q2, q3=q4, q5=q6) of independent answers."""
    rng = np.random.default_rng(seed)
    base = rng.integers(1, 6, size=(n, 3))
    return frame(np.repeat(base, 2, axis=1).tolist())


class TestPsychsyn:
    def test_finds_the_synonym_pairs(self):
        pairs = synonym_pairs(synonym_data())
        assert [(a, b) for a, b, _ in pairs] == [("q1", "q2"), ("q3", "q4"), ("q5", "q6")]
        assert all(r == pytest.approx(1.0) for _, _, r in pairs)

    def test_consistent_and_inconsistent_respondents(self):
        data = synonym_data()
        test_rows = frame([[1, 1, 3, 3, 5, 5], [1, 5, 3, 3, 5, 1]], index=[1000, 1001])
        result = psychsyn(pd.concat([data, test_rows]))
        assert result.loc[1000] == pytest.approx(1.0)  # firsts 1,3,5 vs seconds 1,3,5
        assert result.loc[1001] == pytest.approx(-1.0)  # firsts 1,3,5 vs seconds 5,3,1

    def test_negative_correlations_are_not_synonyms(self):
        data = synonym_data()
        data["q2"] = 6 - data["q2"]  # q1-q2 now correlate at -1
        assert ("q1", "q2") not in [(a, b) for a, b, _ in synonym_pairs(data)]

    def test_too_few_pairs_is_nan_with_count_in_warning(self):
        warnings: list[str] = []
        data = synonym_data()[["q1", "q2", "q3", "q4"]]
        result = psychsyn(data, warnings=warnings)
        assert result.isna().all()
        assert warnings == [
            "Psychometric synonyms were not computed: the data has 2 item pair(s) correlating "
            "above 0.60, and at least 3 are needed."
        ]

    def test_straightliner_is_nan(self):
        data = pd.concat([synonym_data(), frame([[2] * 6], index=[999])])
        assert np.isnan(psychsyn(data).loc[999])


# ---------------------------------------------------------------------------- person-total


class TestPersonTotal:
    def test_by_hand(self):
        data = frame([[1, 2, 3], [1, 2, 3], [1, 3, 5], [3, 2, 1]])
        result = person_total(data)
        # Respondent 0: others' means (1+1+3)/3, (2+3+2)/3, (3+5+1)/3 = 5/3, 7/3, 3 -> r = 1.
        assert result.iloc[0] == pytest.approx(1.0)
        # Respondent 3: others' means 1, 7/3, 11/3 (rising) vs answers 3, 2, 1 -> r = -1.
        assert result.iloc[3] == pytest.approx(-1.0)

    def test_leave_one_out_means_by_loop(self):
        rng = np.random.default_rng(7)
        values = rng.integers(1, 6, size=(8, 4)).astype(float)
        values[1, 2] = NAN
        values[5, 0] = NAN
        data = frame(values.tolist())
        loo = leave_one_out_means(data).to_numpy()
        for i in range(8):
            others = np.delete(values, i, axis=0)
            np.testing.assert_allclose(loo[i], np.nanmean(others, axis=0))

    def test_zero_variance_and_too_few_answers_are_nan(self):
        warnings: list[str] = []
        data = frame([[1, 2, 3], [4, 4, 4], [1, NAN, NAN], [3, 2, 1], [1, 3, 5]])
        result = person_total(data, warnings=warnings)
        assert np.isnan(result.iloc[1]) and np.isnan(result.iloc[2])
        assert warnings == [
            "Person-total correlation could not be computed for 2 respondents who gave the "
            "same answer to every item or answered fewer than 3 items."
        ]


# ---------------------------------------------------------------------------- seconds per item


class TestSecondsPerItem:
    def test_division(self):
        result = seconds_per_item(pd.Series([50.0, 25.0, NAN]), 25)
        assert result.iloc[0] == 2.0
        assert result.iloc[1] == 1.0
        assert np.isnan(result.iloc[2])

    def test_invalid_item_count(self):
        with pytest.raises(ValueError):
            seconds_per_item(pd.Series([10.0]), 0)


# ---------------------------------------------------------------------------- compute_indices


def prepared_from(raw: pd.DataFrame, schema: SurveySchema, durations=None) -> PreparedData:
    scored = reverse_score(raw, schema.reverse_items, schema.scale_min, schema.scale_max)
    return PreparedData(raw, scored, pd.DataFrame(index=raw.index), durations, [])


class TestComputeIndices:
    def schema(self, **overrides) -> SurveySchema:
        base = dict(
            items=[f"q{i}" for i in range(1, 13)],
            scales=three_scales(),
            reverse_items=["q2"],
            scale_min=1,
            scale_max=5,
        )
        base.update(overrides)
        return SurveySchema(**base)

    def data(self) -> pd.DataFrame:
        rng = np.random.default_rng(8)
        return frame(rng.integers(1, 6, size=(40, 12)).tolist(), index=list(range(100, 140)))

    def test_columns_index_and_data_sources(self):
        schema = self.schema()
        raw = self.data()
        prepared = prepared_from(raw, schema)
        result = compute_indices(prepared, schema)
        assert list(result.columns) == [
            "longstring", "irv", "mahalanobis", "mahalanobis_p",
            "even_odd", "even_odd_sb", "psychsyn", "person_total",
        ]
        assert list(result.index) == list(raw.index)
        pd.testing.assert_series_equal(result["longstring"], longstring(raw))
        pd.testing.assert_series_equal(result["irv"], irv(raw))
        # Even-odd uses reverse-scored answers, so it differs from even-odd on raw answers.
        expected_eo = even_odd(prepared.scored_items, schema.scales)["even_odd"]
        pd.testing.assert_series_equal(result["even_odd"], expected_eo)
        assert not np.allclose(
            result["even_odd"], even_odd(raw, schema.scales)["even_odd"], equal_nan=True
        )

    def test_seconds_per_item_only_with_durations(self):
        schema = self.schema(duration_column="time")
        raw = self.data()
        durations = pd.Series(np.full(40, 120.0), index=raw.index)
        result = compute_indices(prepared_from(raw, schema, durations), schema)
        assert (result["seconds_per_item"] == 10.0).all()

    def test_warnings_are_collected(self):
        schema = self.schema()
        warnings: list[str] = []
        compute_indices(prepared_from(self.data(), schema), schema, warnings)
        assert any(w.startswith("Psychometric synonyms were not computed") for w in warnings)

    def test_psychsyn_critval_is_passed_through(self):
        # Three pairs whose second item is replaced by a random answer for 45% of rows,
        # so each pair correlates between 0.50 and 0.60.
        rng = np.random.default_rng(9)
        data = synonym_data(seed=9)
        for second in ("q2", "q4", "q6"):
            noisy = rng.random(len(data)) < 0.45
            data.loc[noisy, second] = rng.integers(1, 6, size=noisy.sum())
        assert all(0.50 < r < 0.60 for _, _, r in synonym_pairs(data, critval=0.50))
        assert len(synonym_pairs(data, critval=0.50)) == 3

        schema = SurveySchema(
            items=list(data.columns),
            scales={"S1": ["q1", "q2", "q3"], "S2": ["q4", "q5", "q6"]},
            reverse_items=[],
            scale_min=1,
            scale_max=5,
        )
        prepared = prepared_from(data, schema)
        assert compute_indices(prepared, schema)["psychsyn"].isna().all()
        lowered = compute_indices(prepared, schema, psychsyn_critval=0.50)["psychsyn"]
        pd.testing.assert_series_equal(lowered, psychsyn(data, critval=0.50))
        assert lowered.notna().any()

    def test_every_column_has_a_direction(self):
        schema = self.schema(duration_column="time")
        raw = self.data()
        durations = pd.Series(np.full(40, 60.0), index=raw.index)
        result = compute_indices(prepared_from(raw, schema, durations), schema)
        assert set(result.columns) == set(INDEX_DIRECTIONS)


class TestBfiSample:
    def test_indices_on_bfi(self, bfi_csv_path):
        schema = SurveySchema.load(BFI_SCHEMA)
        prepared = prepare_data(load_csv(bfi_csv_path), schema)
        warnings: list[str] = []
        result = compute_indices(prepared, schema, warnings)

        assert len(result) == len(prepared.raw_items)
        assert result["longstring"].between(1, 25).all()
        complete = prepared.raw_items.notna().all(axis=1)
        assert result.loc[complete, "mahalanobis"].notna().all()
        assert result.loc[~complete, "mahalanobis"].isna().all()
        assert result["mahalanobis_p"].dropna().between(0, 1).all()
        assert result["even_odd"].dropna().between(-1, 1).all()
        assert result["person_total"].dropna().between(-1, 1).all()
        # Attentive respondents are the majority, so the typical consistency is positive.
        assert result["even_odd"].median() > 0.3
        assert result["person_total"].median() > 0.3
        assert "seconds_per_item" not in result.columns
        assert any("Mahalanobis distance was not computed for" in w for w in warnings)
