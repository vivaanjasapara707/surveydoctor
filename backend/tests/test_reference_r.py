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
from surveydoctor.schema import SurveySchema
from tests.conftest import BFI_CSV, BFI_SCHEMA, FIXTURES

CARELESS_FIXTURE = FIXTURES / "reference_careless.json"


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
