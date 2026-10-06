"""Reference tests against R (BLUEPRINT.md §8.2).

The R scripts in validation/ write JSON fixtures; these tests compare SurveyDoctor with them
on the bfi sample. Each test skips with a clear message if its fixture has not been
generated, so the suite runs without R. Tolerances are the blueprint's and are not loosened;
where SurveyDoctor deliberately differs from the R package, the test checks the documented
difference instead (see docs/validation.md).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pytest

from surveydoctor.careless import even_odd, irv, longstring, mahalanobis, psychsyn, synonym_pairs
from surveydoctor.io import PreparedData, load_csv, prepare_data
from surveydoctor.reliability import reliability
from surveydoctor.schema import SurveySchema
from surveydoctor.structure import (
    factor_matching,
    match_factor_correlations,
    match_factors,
    structure,
)
from tests.conftest import BFI_CSV, BFI_SCHEMA, FIXTURES

CARELESS_FIXTURE = FIXTURES / "reference_careless.json"
RELIABILITY_FIXTURE = FIXTURES / "reference_reliability.json"
STRUCTURE_FIXTURE = FIXTURES / "reference_structure.json"


def _load_fixture(path: Path) -> dict[str, Any]:
    if not path.exists():
        pytest.skip(
            f"{path.name} not found. Generate it from backend/ with: "
            f"Rscript validation/{path.stem}.R"
        )
    if not BFI_CSV.exists():
        pytest.skip("data/sample/bfi.csv not found. Run: python scripts/download_data.py")
    return json.loads(path.read_text(encoding="utf-8"))


def _array(values: list[float | None]) -> np.ndarray:
    """JSON list (null = missing) -> float array with NaN."""
    return np.array([np.nan if v is None else v for v in values], dtype=float)


@pytest.fixture(scope="module")
def ref() -> dict[str, Any]:
    return _load_fixture(CARELESS_FIXTURE)


@pytest.fixture(scope="module")
def bfi(ref) -> tuple[SurveySchema, PreparedData]:
    schema = SurveySchema.load(BFI_SCHEMA)
    return schema, prepare_data(load_csv(BFI_CSV), schema)


@pytest.fixture(scope="module")
def raw(bfi) -> pd.DataFrame:
    schema, prepared = bfi
    return prepared.raw_items[schema.items]


@pytest.fixture(scope="module")
def scored(bfi) -> pd.DataFrame:
    schema, prepared = bfi
    return prepared.scored_items[schema.items]


@pytest.fixture(scope="module")
def ids(bfi) -> np.ndarray:
    return bfi[1].meta["id"].astype(int).to_numpy()


# ---------------------------------------------------------------------------- data


def test_same_respondents_and_items_as_r(ref, bfi, ids):
    schema, _ = bfi
    assert ids.tolist() == ref["id"]
    assert schema.items == ref["items"]
    assert sorted(schema.reverse_items) == sorted(ref["reverse_items"])


# ---------------------------------------------------------------------------- careless


def test_longstring_matches_careless_exactly(ref, raw):
    np.testing.assert_array_equal(longstring(raw).to_numpy(), _array(ref["longstring"]))


def test_irv_matches_careless(ref, raw):
    np.testing.assert_allclose(irv(raw).to_numpy(), _array(ref["irv"]), rtol=0, atol=1e-6)


def test_careless_mahad_returns_squared_distance(ref):
    # stats::mahalanobis returns D²; mahad agreeing with it settles "D or D²".
    complete = ref["mahad_complete_cases"]
    np.testing.assert_allclose(
        _array(complete["d_sq"]), _array(complete["stats_mahalanobis"]), rtol=0, atol=1e-8
    )


def test_mahalanobis_matches_careless_on_complete_cases(ref, raw, ids):
    # SurveyDoctor's definition (§7.1) estimates the mean and covariance from complete
    # cases and gives NaN to anyone with a missing answer. careless::mahad run on the
    # complete cases computes exactly that, so it is the like-for-like reference.
    complete = ref["mahad_complete_cases"]
    ours = mahalanobis(raw)["mahalanobis"]
    has_value = ours.notna().to_numpy()
    assert ids[has_value].tolist() == complete["id"]
    np.testing.assert_allclose(
        ours.to_numpy()[has_value], _array(complete["d_sq"]), rtol=0, atol=1e-4
    )


def test_even_odd_spearman_brown_matches_careless_where_raw_r_is_not_negative(ref, scored, bfi):
    # careless::evenodd returns -(Spearman–Brown corrected r), clamped so the corrected
    # value is at least -1. SurveyDoctor keeps the corrected value only when raw r >= 0.
    schema, _ = bfi
    ours = even_odd(scored, schema.scales)
    corrected_r = -_array(ref["evenodd"])
    defined = ours["even_odd_sb"].notna().to_numpy()
    np.testing.assert_allclose(
        ours["even_odd_sb"].to_numpy()[defined], corrected_r[defined], rtol=0, atol=1e-4
    )
    # Every respondent without a corrected value has a negative raw r or none at all.
    raw_r = ours["even_odd"].to_numpy()
    assert np.all((raw_r[~defined] < 0) | np.isnan(raw_r[~defined]))


def test_even_odd_raw_r_matches_careless_after_undoing_the_correction(ref, scored, bfi):
    # Undo Spearman–Brown: v = 2r / (1 + r)  =>  r = v / (2 - v). Not possible where R
    # clamped v to -1; there the raw r must be at most -1/3 (where 2r/(1+r) <= -1).
    schema, _ = bfi
    ours = even_odd(scored, schema.scales)["even_odd"].to_numpy()
    corrected_r = -_array(ref["evenodd"])
    np.testing.assert_array_equal(np.isnan(ours), np.isnan(corrected_r))
    clamped = corrected_r <= -1 + 1e-12
    usable = ~np.isnan(corrected_r) & ~clamped
    recovered = corrected_r[usable] / (2 - corrected_r[usable])
    np.testing.assert_allclose(ours[usable], recovered, rtol=0, atol=1e-4)
    assert np.all(ours[clamped] <= -1 / 3 + 1e-4)


def test_psychsyn_at_060_has_too_few_pairs_in_both(ref, raw):
    assert len(synonym_pairs(raw, 0.60)) == ref["psychsyn_060"]["n_pairs"] == 1
    assert psychsyn(raw, critval=0.60).isna().all()
    assert np.isnan(_array(ref["psychsyn_060"]["values"])).all()


def test_psychsyn_pairs_at_050_match_careless(ref, raw):
    ours = synonym_pairs(raw, 0.50)
    theirs = ref["psychsyn_050"]["pairs"]
    assert [(a, b) for a, b, _ in ours] == [(p["first"], p["second"]) for p in theirs]
    np.testing.assert_allclose([r for _, _, r in ours], [p["r"] for p in theirs], rtol=0, atol=1e-8)


def test_psychsyn_at_050_matches_careless(ref, raw):
    # Reference uses resample_na = FALSE (see docs/validation.md).
    ours = psychsyn(raw, critval=0.50).to_numpy()
    theirs = _array(ref["psychsyn_050"]["values"])
    np.testing.assert_array_equal(np.isnan(ours), np.isnan(theirs))
    present = ~np.isnan(ours)
    assert present.sum() > 0
    np.testing.assert_allclose(ours[present], theirs[present], rtol=0, atol=1e-4)


# ---------------------------------------------------------------------------- reliability
#
# Tolerances (BLUEPRINT §8.2): alpha 1e-3, omega total 1e-3. The other alpha statistics
# (Feldt CI, alpha if deleted, corrected item-total r) and the one-factor loadings that feed
# omega use the same tolerances as the quantity they belong to. pingouin rounds the CI
# bounds to 3 decimals (error at most 5e-4), which fits within 1e-3.


@pytest.fixture(scope="module")
def rel_ref() -> dict[str, Any]:
    return _load_fixture(RELIABILITY_FIXTURE)


@pytest.fixture(scope="module")
def rel_ours(rel_ref):
    schema = SurveySchema.load(BFI_SCHEMA)
    prepared = prepare_data(load_csv(BFI_CSV), schema)
    return schema, prepared, reliability(prepared, schema)


def _by_item(values: dict[str, float], items: list[str]) -> np.ndarray:
    return np.array([values[item] for item in items], dtype=float)


def test_reliability_uses_same_scales_and_respondents_as_r(rel_ref, rel_ours):
    schema, prepared, ours = rel_ours
    assert list(rel_ref["scales"]) == list(schema.scales) == list(ours)
    ids = prepared.meta["id"].astype(int)
    for name, ref_scale in rel_ref["scales"].items():
        assert ours[name].items == ref_scale["items"]
        assert ours[name].n_used == ref_scale["n_used"]
        complete = prepared.scored_items[schema.scales[name]].notna().all(axis=1)
        assert ids[complete].tolist() == ref_scale["id"]


@pytest.mark.parametrize(
    "scale", ["Agreeableness", "Conscientiousness", "Extraversion", "Neuroticism", "Openness"]
)
def test_alpha_matches_psych(rel_ref, rel_ours, scale):
    ours, ref_scale = rel_ours[2][scale], rel_ref["scales"][scale]
    assert ours.alpha == pytest.approx(ref_scale["raw_alpha"], abs=1e-3)
    assert ours.alpha_ci[0] == pytest.approx(ref_scale["feldt_lower"], abs=1e-3)
    assert ours.alpha_ci[1] == pytest.approx(ref_scale["feldt_upper"], abs=1e-3)


@pytest.mark.parametrize(
    "scale", ["Agreeableness", "Conscientiousness", "Extraversion", "Neuroticism", "Openness"]
)
def test_item_stats_match_psych(rel_ref, rel_ours, scale):
    ours, ref_scale = rel_ours[2][scale], rel_ref["scales"][scale]
    items = ref_scale["items"]
    np.testing.assert_allclose(
        ours.item_stats.loc[items, "corrected_item_total"].to_numpy(),
        _by_item(ref_scale["corrected_item_total"], items),
        rtol=0,
        atol=1e-3,
    )
    np.testing.assert_allclose(
        ours.item_stats.loc[items, "alpha_if_deleted"].to_numpy(),
        _by_item(ref_scale["alpha_if_deleted"], items),
        rtol=0,
        atol=1e-3,
    )


@pytest.mark.parametrize(
    "scale", ["Agreeableness", "Conscientiousness", "Extraversion", "Neuroticism", "Openness"]
)
def test_omega_total_matches_psych_fa(rel_ref, rel_ours, scale):
    ours, ref_scale = rel_ours[2][scale], rel_ref["scales"][scale]
    items = ref_scale["items"]
    np.testing.assert_allclose(
        ours.loadings.loc[items].to_numpy(),
        _by_item(ref_scale["fa_loadings"], items),
        rtol=0,
        atol=1e-3,
    )
    assert ours.omega_total == pytest.approx(ref_scale["omega_total"], abs=1e-3)


# ---------------------------------------------------------------------------- structure
#
# Tolerances (BLUEPRINT §8.2): KMO 1e-3, Bartlett chi-square 1e-2, EFA loadings 0.02 after
# matching factor order and sign. Per-item KMO uses the KMO tolerance. Communalities and
# factor correlations come from the same fitted solution as the loadings, so they use the
# loadings' tolerance. The correlation-matrix eigenvalues are plain linear algebra, so they
# are compared at 1e-6 (not in §8.2; see docs/decisions.md).


@pytest.fixture(scope="module")
def struct_ref() -> dict[str, Any]:
    return _load_fixture(STRUCTURE_FIXTURE)


@pytest.fixture(scope="module")
def struct_ours(struct_ref):
    schema = SurveySchema.load(BFI_SCHEMA)
    prepared = prepare_data(load_csv(BFI_CSV), schema)
    result = structure(prepared, schema, n_factors=struct_ref["efa"]["n_factors"])
    return schema, prepared, result


def _ref_matrix(columns: dict[str, dict[str, float]], index: list[str]) -> pd.DataFrame:
    """JSON {column: {row: value}} -> DataFrame with rows in ``index`` order."""
    return pd.DataFrame(
        {c: [values[i] for i in index] for c, values in columns.items()}, index=index
    )


@pytest.fixture(scope="module")
def ref_loadings(struct_ref) -> pd.DataFrame:
    return _ref_matrix(struct_ref["efa"]["loadings"], struct_ref["items"])[
        struct_ref["efa"]["factors"]
    ]


def test_structure_uses_same_items_and_respondents_as_r(struct_ref, struct_ours):
    schema, prepared, ours = struct_ours
    assert ours.items == schema.items == struct_ref["items"]
    assert sorted(schema.reverse_items) == sorted(struct_ref["reverse_items"])
    assert ours.n_used == struct_ref["n_used"]
    complete = prepared.scored_items[schema.items].notna().all(axis=1)
    assert prepared.meta["id"].astype(int)[complete].tolist() == struct_ref["id"]


def test_kmo_matches_psych(struct_ref, struct_ours):
    ours = struct_ours[2].kmo
    assert ours.overall == pytest.approx(struct_ref["kmo_overall"], abs=1e-3)
    items = struct_ref["items"]
    np.testing.assert_allclose(
        ours.per_item.loc[items].to_numpy(),
        _by_item(struct_ref["kmo_per_item"], items),
        rtol=0,
        atol=1e-3,
    )


def test_bartlett_matches_psych(struct_ref, struct_ours):
    ours, theirs = struct_ours[2].bartlett, struct_ref["bartlett"]
    assert ours.chi_square == pytest.approx(theirs["chi_square"], abs=1e-2)
    assert ours.df == theirs["df"]
    assert ours.p_value == pytest.approx(theirs["p_value"], abs=1e-12)


def test_eigenvalues_match_r(struct_ref, struct_ours):
    np.testing.assert_allclose(
        struct_ours[2].parallel.scree["observed"].to_numpy(),
        np.array(struct_ref["eigenvalues"], dtype=float),
        rtol=0,
        atol=1e-6,
    )


def test_efa_loadings_match_psych_fa(struct_ours, ref_loadings):
    matched = match_factors(struct_ours[2].efa.loadings, ref_loadings)
    np.testing.assert_allclose(matched.to_numpy(), ref_loadings.to_numpy(), rtol=0, atol=0.02)


def test_efa_communalities_match_psych_fa(struct_ref, struct_ours):
    items = struct_ref["items"]
    np.testing.assert_allclose(
        struct_ours[2].efa.communalities.loc[items].to_numpy(),
        _by_item(struct_ref["efa"]["communality"], items),
        rtol=0,
        atol=0.02,
    )


def test_efa_factor_correlations_match_psych_fa(struct_ref, struct_ours, ref_loadings):
    efa_result = struct_ours[2].efa
    matching = factor_matching(efa_result.loadings, ref_loadings)
    ours = match_factor_correlations(efa_result.factor_correlations, matching)
    factors = struct_ref["efa"]["factors"]
    theirs = _ref_matrix(struct_ref["efa"]["phi"], factors)[factors]
    np.testing.assert_allclose(ours.to_numpy(), theirs.to_numpy(), rtol=0, atol=0.02)


def test_parallel_analysis_suggests_same_number_as_psych(struct_ref):
    # psych::fa.parallel on the correlation matrix (simulated standard-normal data, 100
    # iterations, 95th percentile) uses SurveyDoctor's definition with R's random numbers,
    # so only the suggested number of components is compared, exactly. Our own run uses the
    # default (parallel-analysis-chosen) settings, not the fixture's fixed 5 factors.
    schema = SurveySchema.load(BFI_SCHEMA)
    ours = structure(prepare_data(load_csv(BFI_CSV), schema), schema)
    theirs = struct_ref["parallel"]
    assert (ours.parallel.n_iterations, ours.parallel.percentile) == (
        theirs["n_iterations"],
        100 * theirs["quant"],
    )
    assert ours.parallel.n_suggested == theirs["ncomp"]
