"""Tests for structure.py (Stage 5). Expected values are worked out by hand where possible."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest
from factor_analyzer import FactorAnalyzer
from scipy import stats

from surveydoctor.io import PreparedData, load_csv, prepare_data
from surveydoctor.reliability import one_factor_loadings
from surveydoctor.schema import SurveySchema
from surveydoctor.structure import (
    PEARSON_NOTE,
    alignment_table,
    bartlett,
    efa,
    eigenvalues,
    factor_matching,
    factor_names,
    kmo,
    loading_flags,
    match_factor_correlations,
    match_factors,
    parallel_analysis,
    scale_alignment,
    structure,
    structure_problem,
)
from tests.conftest import BFI_SCHEMA


def factor_data(
    loadings: np.ndarray, phi: np.ndarray | None = None, n: int = 2_000, seed: int = 0
) -> pd.DataFrame:
    """Continuous data from a factor model: x = L f + sqrt(1 − h²) e, with corr(f) = Φ."""
    loadings = np.asarray(loadings, dtype=float)
    k, m = loadings.shape
    phi = np.eye(m) if phi is None else np.asarray(phi, dtype=float)
    rng = np.random.default_rng(seed)
    factors = rng.multivariate_normal(np.zeros(m), phi, size=n)
    communality = np.einsum("ij,jk,ik->i", loadings, phi, loadings)
    noise = rng.standard_normal((n, k)) * np.sqrt(1 - communality)
    return pd.DataFrame(factors @ loadings.T + noise, columns=[f"q{i + 1}" for i in range(k)])


def simple_structure(n_factors: int, per_factor: int, loading: float) -> np.ndarray:
    """Each item loads ``loading`` on one factor and 0 on the others."""
    return np.kron(np.eye(n_factors), np.full((per_factor, 1), loading))


# Three factors, three items each (loading 0.7), factors correlated 0.3.
THREE_L = simple_structure(3, 3, 0.7)
THREE_PHI = np.array([[1.0, 0.3, 0.3], [0.3, 1.0, 0.3], [0.3, 0.3, 1.0]])
THREE = factor_data(THREE_L, THREE_PHI, n=5_000)


def prepared_from(data: pd.DataFrame) -> PreparedData:
    return PreparedData(
        raw_items=data,
        scored_items=data,
        meta=pd.DataFrame(index=data.index),
        durations_seconds=None,
        issues=[],
    )


def schema_for(data: pd.DataFrame, scales: dict[str, list[str]]) -> SurveySchema:
    return SurveySchema(
        items=list(data.columns), scales=scales, reverse_items=[], scale_min=1, scale_max=5
    )


THREE_SCALES = {"A": ["q1", "q2", "q3"], "B": ["q4", "q5", "q6"], "C": ["q7", "q8", "q9"]}


# ---------------------------------------------------------------------------- data checks


class TestStructureProblem:
    def test_usable_data(self):
        assert structure_problem(THREE) is None

    def test_too_few_items(self):
        assert "at least 3 questions, and 2 were selected" in structure_problem(THREE.iloc[:, :2])

    def test_too_few_respondents(self):
        message = structure_problem(THREE.head(9))
        assert "more respondents with complete answers (9) than questions (9)" in message

    def test_constant_item(self):
        message = structure_problem(THREE.assign(q9=3.0))
        assert "every respondent gave the same answer to q9" in message

    def test_duplicate_questions_are_named(self):
        message = structure_problem(THREE.assign(q10=THREE["q2"]))
        assert "identical or nearly identical answers (q2 and q10)" in message

    def test_exact_combination_without_a_duplicate_pair(self):
        message = structure_problem(THREE.assign(total=THREE.sum(axis=1)))
        assert "predicted exactly from the answers to others" in message


# ---------------------------------------------------------------------------- KMO, Bartlett


class TestKMO:
    def test_two_items_give_one_half(self):
        # With 2 items the partial correlation equals the plain correlation, so
        # KMO = r² / (r² + r²) = 0.5 overall and for each item.
        result = kmo(THREE[["q1", "q2"]])
        assert result.overall == pytest.approx(0.5)
        np.testing.assert_allclose(result.per_item.to_numpy(), [0.5, 0.5])

    def test_three_items_by_hand(self):
        data = THREE[["q1", "q2", "q4"]]
        r = data.corr().to_numpy()
        r12, r13, r23 = r[0, 1], r[0, 2], r[1, 2]

        def partial(rab: float, rac: float, rbc: float) -> float:
            return (rab - rac * rbc) / math.sqrt((1 - rac**2) * (1 - rbc**2))

        p12, p13, p23 = partial(r12, r13, r23), partial(r13, r12, r23), partial(r23, r12, r13)
        plain = r12**2 + r13**2 + r23**2
        overall = plain / (plain + p12**2 + p13**2 + p23**2)
        item1 = (r12**2 + r13**2) / (r12**2 + r13**2 + p12**2 + p13**2)
        result = kmo(data)
        assert result.overall == pytest.approx(overall, abs=1e-10)
        assert result.per_item["q1"] == pytest.approx(item1, abs=1e-10)
        assert list(result.per_item.index) == ["q1", "q2", "q4"]

    def test_factor_data_scores_higher_than_noise(self):
        noise = pd.DataFrame(np.random.default_rng(3).standard_normal((2_000, 9)))
        assert kmo(THREE).overall > 0.7
        assert kmo(noise).overall < 0.6


class TestBartlett:
    def test_formula_by_hand(self):
        data = THREE
        n, k = data.shape
        chi_square = -(n - 1 - (2 * k + 5) / 6) * math.log(np.linalg.det(data.corr()))
        result = bartlett(data)
        assert result.chi_square == pytest.approx(chi_square, rel=1e-10)
        assert result.df == k * (k - 1) // 2 == 36
        assert result.p_value == pytest.approx(stats.chi2.sf(chi_square, 36))

    def test_correlated_items_reject_sphericity(self):
        assert bartlett(THREE).p_value < 1e-10


# ---------------------------------------------------------------------------- parallel


class TestParallelAnalysis:
    def test_known_three_factor_structure_suggests_three(self):
        result = parallel_analysis(factor_data(THREE_L, THREE_PHI, n=500, seed=1))
        assert result.n_suggested == 3
        assert (result.n_iterations, result.percentile, result.seed) == (100, 95.0, 42)

    def test_pure_noise_suggests_none_while_kaiser_counts_several(self):
        noise = pd.DataFrame(np.random.default_rng(7).standard_normal((300, 10)))
        result = parallel_analysis(noise)
        assert result.n_suggested == 0
        assert result.n_kaiser >= 3  # noise alone pushes several eigenvalues above 1

    def test_scree_table(self):
        result = parallel_analysis(THREE)
        assert list(result.scree.columns) == ["observed", "threshold"]
        assert list(result.scree.index) == list(range(1, 10))
        np.testing.assert_allclose(result.scree["observed"], eigenvalues(THREE))
        assert result.scree["threshold"].is_monotonic_decreasing

    def test_same_seed_same_thresholds(self):
        a = parallel_analysis(THREE, n_iterations=20)
        b = parallel_analysis(THREE, n_iterations=20)
        c = parallel_analysis(THREE, n_iterations=20, seed=1)
        pd.testing.assert_frame_equal(a.scree, b.scree)
        assert not np.allclose(a.scree["threshold"], c.scree["threshold"])

    def test_eigenvalues_sum_to_number_of_items_largest_first(self):
        values = eigenvalues(THREE)
        assert values.sum() == pytest.approx(9)
        assert np.all(np.diff(values) <= 0)


# ---------------------------------------------------------------------------- EFA


class TestEFA:
    def test_recovers_known_loadings_and_factor_correlations(self):
        result = efa(THREE, 3)
        truth = pd.DataFrame(THREE_L, index=THREE.columns, columns=["T1", "T2", "T3"])
        matched = match_factors(result.loadings, truth)
        np.testing.assert_allclose(matched.to_numpy(), THREE_L, atol=0.05)
        # All true factor correlations are 0.3, so factor order does not matter here.
        np.testing.assert_allclose(
            np.sort(result.factor_correlations.to_numpy()[np.triu_indices(3, 1)]),
            [0.3, 0.3, 0.3],
            atol=0.05,
        )
        np.testing.assert_allclose(result.communalities, 0.49, atol=0.05)

    def test_factor_correlations_are_a_correlation_matrix(self):
        phi = efa(THREE, 3).factor_correlations.to_numpy()
        np.testing.assert_allclose(np.diag(phi), 1.0, atol=1e-8)
        np.testing.assert_allclose(phi, phi.T, atol=1e-12)

    @pytest.mark.filterwarnings("ignore::FutureWarning")
    def test_factor_correlations_follow_the_factor_order(self):
        # factor_analyzer 0.5.1 sorts factors by variance but leaves phi_ unsorted; ours
        # must satisfy structure = L Φ in the final order.
        x = THREE.to_numpy()
        model = FactorAnalyzer(n_factors=3, rotation="oblimin", method="minres").fit(x)
        result = efa(THREE, 3)
        np.testing.assert_allclose(
            result.loadings.to_numpy() @ result.factor_correlations.to_numpy(),
            model.structure_,
            atol=1e-10,
        )

    @pytest.mark.filterwarnings("ignore::FutureWarning")
    def test_communalities_do_not_depend_on_the_rotation(self):
        # A rotation only redistributes what the factors explain, so diag(LΦLᵀ) must equal
        # the unrotated communalities (factor_analyzer's get_communalities is wrong here).
        unrotated = FactorAnalyzer(n_factors=3, rotation=None, method="minres").fit(
            THREE.to_numpy()
        )
        np.testing.assert_allclose(
            efa(THREE, 3).communalities.to_numpy(), unrotated.get_communalities(), atol=1e-8
        )

    def test_one_factor_matches_the_omega_model(self):
        data = THREE[["q1", "q2", "q3", "q4"]]
        result = efa(data, 1)
        np.testing.assert_allclose(
            result.loadings["F1"].to_numpy(), one_factor_loadings(data).to_numpy(), atol=1e-10
        )
        assert result.factor_correlations.to_numpy().tolist() == [[1.0]]
        np.testing.assert_allclose(result.communalities, result.loadings["F1"] ** 2)

    def test_factor_names_and_shapes(self):
        result = efa(THREE, 3)
        assert factor_names(3) == ["F1", "F2", "F3"]
        assert list(result.loadings.columns) == ["F1", "F2", "F3"]
        assert list(result.loadings.index) == list(THREE.columns)
        assert list(result.factor_correlations.index) == ["F1", "F2", "F3"]
        assert list(result.item_flags.index) == list(THREE.columns)

    @pytest.mark.parametrize("n_factors", [0, 9, 12])
    def test_invalid_number_of_factors(self, n_factors):
        with pytest.raises(ValueError, match="between 1 and 8"):
            efa(THREE, n_factors)

    def test_heywood_case_is_warned_about(self):
        rng = np.random.default_rng(0)
        f = rng.standard_normal(500)
        data = pd.DataFrame(
            {
                "q1": f,
                "q2": f + 1e-3 * rng.standard_normal(500),
                "q3": 0.5 * f + rng.standard_normal(500),
                "q4": 0.5 * f + rng.standard_normal(500),
            }
        )
        warnings: list[str] = []
        result = efa(data, 1, warnings)
        assert result is not None
        assert len(warnings) == 1
        assert "almost completely (a Heywood case)" in warnings[0]
        assert "q1" in warnings[0]


class TestMatchFactors:
    def test_undoes_reordering_and_sign_flips(self):
        reference = pd.DataFrame(THREE_L + 0.05, index=THREE.columns, columns=["MR1", "MR2", "MR3"])
        shuffled = pd.DataFrame(
            {"F1": -reference["MR3"], "F2": reference["MR1"], "F3": -reference["MR2"]}
        )
        assert factor_matching(shuffled, reference) == {
            "MR1": ("F2", 1.0),
            "MR2": ("F3", -1.0),
            "MR3": ("F1", -1.0),
        }
        pd.testing.assert_frame_equal(match_factors(shuffled, reference), reference)

    def test_factor_correlations_follow_the_matching(self):
        # Our F1 is -MR3, F2 is MR1, F3 is -MR2.
        matching = {"MR1": ("F2", 1.0), "MR2": ("F3", -1.0), "MR3": ("F1", -1.0)}
        ours = pd.DataFrame(
            [[1.0, 0.1, 0.2], [0.1, 1.0, 0.3], [0.2, 0.3, 1.0]],
            index=["F1", "F2", "F3"],
            columns=["F1", "F2", "F3"],
        )
        matched = match_factor_correlations(ours, matching)
        # MR1-MR2 = corr(F2, -F3) = -0.3; MR1-MR3 = corr(F2, -F1) = -0.1;
        # MR2-MR3 = corr(-F3, -F1) = 0.2.
        expected = [[1.0, -0.3, -0.1], [-0.3, 1.0, 0.2], [-0.1, 0.2, 1.0]]
        np.testing.assert_allclose(matched.to_numpy(), expected)
        assert list(matched.columns) == ["MR1", "MR2", "MR3"]

    def test_matching_is_in_reference_order(self):
        reference = pd.DataFrame(THREE_L, index=THREE.columns, columns=["MR1", "MR2", "MR3"])
        ours = pd.DataFrame(
            {"F1": reference["MR3"], "F2": reference["MR2"], "F3": reference["MR1"]}
        )
        assert list(factor_matching(ours, reference)) == ["MR1", "MR2", "MR3"]

    def test_needs_same_shape(self):
        reference = pd.DataFrame(THREE_L, index=THREE.columns)
        with pytest.raises(ValueError, match="same items"):
            match_factors(reference.iloc[:, :2], reference)


# ---------------------------------------------------------------------------- flags


class TestLoadingFlags:
    def test_flags_by_hand(self):
        loadings = pd.DataFrame(
            {"F1": [0.70, 0.25, 0.45, -0.60], "F2": [0.10, -0.20, -0.35, 0.29]},
            index=["clean", "weak", "cross", "negative"],
        )
        flags = loading_flags(loadings)
        assert flags.loc["clean"].to_dict() == {
            "primary_factor": "F1",
            "primary_loading": 0.70,
            "weak": False,
            "cross_loading": False,
            "second_factor": None,
        }
        assert flags.loc["weak", "weak"] and not flags.loc["weak", "cross_loading"]
        assert flags.loc["cross", "cross_loading"]
        assert flags.loc["cross", "second_factor"] == "F2"
        # A negative loading counts by its size; 0.29 is just below the cross-loading bar.
        assert flags.loc["negative", "primary_loading"] == -0.60
        assert not flags.loc["negative", "cross_loading"]

    def test_boundaries(self):
        # Weak means max |loading| < 0.30; cross-loading means second |loading| >= 0.30.
        loadings = pd.DataFrame({"F1": [0.30, 0.50], "F2": [0.0, 0.30]}, index=["a", "b"])
        flags = loading_flags(loadings)
        assert not flags.loc["a", "weak"]
        assert flags.loc["b", "cross_loading"]

    def test_one_factor_never_cross_loads(self):
        flags = loading_flags(pd.DataFrame({"F1": [0.5, 0.1]}, index=["a", "b"]))
        assert flags["cross_loading"].tolist() == [False, False]
        assert flags["weak"].tolist() == [False, True]


class TestScaleAlignment:
    LOADINGS = pd.DataFrame(
        {
            "F1": [0.7, 0.6, 0.1, 0.5, 0.1, 0.2, 0.6],
            "F2": [0.1, 0.2, 0.6, 0.1, 0.7, 0.4, 0.1],
        },
        index=["a1", "a2", "a3", "b1", "b2", "c1", "c2"],
    )

    def test_majority_factor_and_share(self):
        result = scale_alignment(self.LOADINGS, {"A": ["a1", "a2", "a3"]})["A"]
        assert result.factor == "F1"
        assert result.n_matching == 2
        assert result.share_matching == pytest.approx(2 / 3)
        assert result.item_factors == {"a1": "F1", "a2": "F1", "a3": "F2"}

    def test_tie_goes_to_the_stronger_factor(self):
        # b1 -> F1 (0.5), b2 -> F2 (0.7): one each; summed |loading| is 0.6 vs 0.8.
        result = scale_alignment(self.LOADINGS, {"B": ["b1", "b2"]})["B"]
        assert result.factor == "F2"
        assert result.share_matching == 0.5

    def test_scales_on_the_same_factor_are_reported(self):
        out = scale_alignment(self.LOADINGS, {"A": ["a1", "a2", "a3"], "C": ["c1", "c2"]})
        # C: c1 -> F2 (0.4), c2 -> F1 (0.6); tie broken by sum: F1 0.8 vs F2 0.5.
        assert out["C"].factor == "F1"
        assert out["A"].shared_with == ["C"]
        assert out["C"].shared_with == ["A"]

    def test_scales_with_fewer_than_two_analysed_items_are_skipped(self):
        out = scale_alignment(self.LOADINGS, {"A": ["a1", "x9"], "B": ["b1", "b2"]})
        assert list(out) == ["B"]


# ---------------------------------------------------------------------------- structure()


class TestStructure:
    def test_three_factor_survey_end_to_end(self):
        data = factor_data(THREE_L, THREE_PHI, n=500, seed=1)
        warnings: list[str] = []
        result = structure(prepared_from(data), schema_for(data, THREE_SCALES), warnings=warnings)
        assert result.skipped_reason is None
        assert (result.n_used, result.n_excluded) == (500, 0)
        assert result.parallel.n_suggested == result.n_factors == 3
        assert result.n_factors_source == "parallel analysis"
        assert {a.share_matching for a in result.alignment.values()} == {1.0}
        assert len({a.factor for a in result.alignment.values()}) == 3
        assert warnings == [PEARSON_NOTE]
        table = alignment_table(result)
        assert list(table.index) == ["A", "B", "C"]
        assert table["n_matching"].tolist() == [3, 3, 3]

    def test_listwise_deletion_is_counted(self):
        data = THREE.head(400).copy()
        data.iloc[:7, 0] = np.nan
        warnings: list[str] = []
        result = structure(prepared_from(data), schema_for(data, THREE_SCALES), warnings=warnings)
        assert (result.n_used, result.n_excluded) == (393, 7)
        assert (
            "Factor analysis used 393 respondents who answered all 9 analysed questions; "
            "7 respondents with a missing answer were left out." in warnings
        )

    def test_small_sample_warning(self):
        data = THREE.head(150)
        warnings: list[str] = []
        structure(prepared_from(data), schema_for(data, THREE_SCALES), warnings=warnings)
        assert any(
            w.startswith(
                "The factor solution may be unstable: it rests on 150 respondents "
                "(16.7 per question)."
            )
            for w in warnings
        )

    def test_few_respondents_per_item_warning(self):
        # 250 respondents is enough in total (>= 200), but 250 / 60 items = 4.2 per item.
        data = factor_data(simple_structure(3, 20, 0.6), n=250, seed=2)
        scales = {f"S{i}": list(data.columns[20 * i : 20 * i + 20]) for i in range(3)}
        warnings: list[str] = []
        structure(prepared_from(data), schema_for(data, scales), warnings=warnings)
        assert any("(4.2 per question)" in w for w in warnings)

    def test_low_kmo_and_no_factors_on_noise(self):
        data = pd.DataFrame(
            np.random.default_rng(7).standard_normal((300, 10)),
            columns=[f"q{i + 1}" for i in range(10)],
        )
        warnings: list[str] = []
        result = structure(
            prepared_from(data), schema_for(data, {"A": list(data.columns)}), warnings=warnings
        )
        assert result.kmo.overall < 0.6
        assert any(w.startswith("The data may be unsuitable for factor analysis") for w in warnings)
        assert result.efa is None and result.n_factors is None and result.alignment == {}
        assert any("Parallel analysis found no factor" in w for w in warnings)

    def test_user_chosen_number_of_factors(self):
        data = factor_data(THREE_L, THREE_PHI, n=500, seed=1)
        result = structure(prepared_from(data), schema_for(data, THREE_SCALES), n_factors=2)
        assert result.n_factors == 2 and result.n_factors_source == "user"
        assert result.efa.loadings.shape == (9, 2)
        assert result.parallel.n_suggested == 3  # still reported for comparison

    def test_item_subset(self):
        data = THREE.head(500)
        items = ["q1", "q2", "q3", "q4", "q5", "q6"]
        result = structure(prepared_from(data), schema_for(data, THREE_SCALES), items=items)
        assert result.items == items
        assert list(result.efa.loadings.index) == items
        assert list(result.alignment) == ["A", "B"]  # C has no analysed items

    def test_bad_inputs_raise_plain_english_errors(self):
        data = THREE.head(100)
        schema = schema_for(data, THREE_SCALES)
        with pytest.raises(ValueError, match="not items in the schema: zz"):
            structure(prepared_from(data), schema, items=["q1", "q2", "zz"])
        with pytest.raises(ValueError, match="between 1 and 8"):
            structure(prepared_from(data), schema, n_factors=9)

    def test_unusable_data_is_skipped_with_a_reason(self):
        data = THREE.head(300).assign(q10=THREE["q2"].head(300))
        warnings: list[str] = []
        result = structure(prepared_from(data), schema_for(data, THREE_SCALES), warnings=warnings)
        assert result.skipped_reason is not None
        assert "(q2 and q10)" in result.skipped_reason
        assert result.kmo is None and result.parallel is None and result.efa is None
        assert warnings == [PEARSON_NOTE, result.skipped_reason]


# ---------------------------------------------------------------------------- bfi


def test_bfi_five_factors_and_five_aligned_scales(bfi_csv_path):
    schema = SurveySchema.load(BFI_SCHEMA)
    prepared = prepare_data(load_csv(bfi_csv_path), schema)
    warnings: list[str] = []
    result = structure(prepared, schema, warnings=warnings)
    # Measured on bfi in Stage 5 (docs/decisions.md): 2,436 complete respondents, parallel
    # analysis suggests 5 factors (Kaiser's rule would say 6), and every item of every
    # scale has its primary loading on its own scale's factor.
    assert (result.n_used, result.n_excluded) == (2436, 364)
    assert result.kmo.overall > 0.8
    assert result.parallel.n_suggested == 5
    assert result.parallel.n_kaiser == 6
    assert result.n_factors == 5
    assert list(result.alignment) == list(schema.scales)
    assert {a.share_matching for a in result.alignment.values()} == {1.0}
    assert len({a.factor for a in result.alignment.values()}) == 5
    assert not result.efa.item_flags["weak"].any()
    assert warnings == [
        PEARSON_NOTE,
        "Factor analysis used 2436 respondents who answered all 25 analysed questions; "
        "364 respondents with a missing answer were left out.",
    ]
