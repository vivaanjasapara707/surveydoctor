"""Tests for flagging.py (Stage 3). Expected values are worked out by hand."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from surveydoctor.careless import compute_indices
from surveydoctor.flagging import (
    COMPOSITE_INDICES,
    DEFAULT_RULES,
    VARIANT_NAMES,
    apply_flags,
    composite_score,
    flag_variants,
    longstring_threshold,
    merge_rules,
    top_share_mask,
)
from surveydoctor.io import load_csv, prepare_data
from surveydoctor.schema import SurveySchema
from tests.conftest import BFI_SCHEMA

NAN = np.nan
BENIGN = {
    "longstring": 2.0,
    "irv": 1.2,
    "mahalanobis": 20.0,
    "mahalanobis_p": 0.5,
    "even_odd": 0.8,
    "even_odd_sb": 0.89,
    "psychsyn": 0.7,
    "person_total": 0.6,
}


def indices_frame(*changes: dict[str, float]) -> pd.DataFrame:
    """One row per dict: benign values, with the given entries changed."""
    return pd.DataFrame([{**BENIGN, **change} for change in changes], dtype=float)


# ---------------------------------------------------------------------------- rules


class TestRules:
    def test_defaults_follow_the_blueprint(self):
        assert DEFAULT_RULES["longstring"]["share_of_items"] == 0.5
        assert DEFAULT_RULES["mahalanobis"]["p_below"] == 0.001
        assert DEFAULT_RULES["even_odd"]["r_below"] == 0.30
        assert DEFAULT_RULES["psychsyn"]["r_below"] == 0.0
        assert DEFAULT_RULES["person_total"]["r_below"] == 0.0
        assert DEFAULT_RULES["seconds_per_item"]["seconds_below"] == 2.0
        assert all(rule["enabled"] for rule in DEFAULT_RULES.values())

    def test_merge_overrides_without_changing_defaults(self):
        merged = merge_rules({"even_odd": {"r_below": 0.2}, "psychsyn": {"enabled": False}})
        assert merged["even_odd"]["r_below"] == 0.2
        assert merged["psychsyn"]["enabled"] is False
        assert merged["mahalanobis"] == DEFAULT_RULES["mahalanobis"]
        assert DEFAULT_RULES["even_odd"]["r_below"] == 0.30
        assert DEFAULT_RULES["psychsyn"]["enabled"] is True

    @pytest.mark.parametrize(
        ("rules", "message"),
        [
            ({"speed": {"enabled": True}}, "Unknown flag rule 'speed'"),
            ({"even_odd": {"cutoff": 0.2}}, "Unknown setting 'cutoff'"),
            ({"even_odd": {"r_below": "low"}}, "must be a number"),
            ({"even_odd": {"enabled": "yes"}}, "true or false"),
            ({"longstring": {"share_of_items": 0}}, "longstring share"),
            ({"mahalanobis": {"p_below": 1.5}}, "between 0 and 1"),
            ({"person_total": {"r_below": 2}}, "from -1 to 1"),
            ({"seconds_per_item": {"seconds_below": 0}}, "above 0"),
        ],
    )
    def test_bad_rules_raise_plain_messages(self, rules, message):
        with pytest.raises(ValueError, match=message):
            merge_rules(rules)

    @pytest.mark.parametrize(
        ("n_items", "share", "expected"),
        [(25, 0.5, 13), (10, 0.5, 5), (5, 0.5, 3), (10, 0.3, 3), (3, 0.1, 1), (4, 1.0, 4)],
    )
    def test_longstring_threshold_is_ceiling_of_share(self, n_items, share, expected):
        assert longstring_threshold(n_items, share) == expected

    def test_longstring_threshold_needs_items(self):
        with pytest.raises(ValueError):
            longstring_threshold(0)


# ---------------------------------------------------------------------------- apply_flags


class TestApplyFlags:
    def test_each_rule_and_its_boundary(self):
        indices = indices_frame(
            {"longstring": 13},  # 0: at the threshold (>=) -> flagged
            {"longstring": 12},  # 1: just below -> not flagged
            {"mahalanobis_p": 0.0005, "mahalanobis": 60.2},  # 2: flagged
            {"mahalanobis_p": 0.001},  # 3: p equal to threshold -> not flagged (strict)
            {"even_odd": 0.29},  # 4: flagged
            {"even_odd": 0.30},  # 5: equal -> not flagged
            {"psychsyn": -0.1, "person_total": -0.2},  # 6: two rules
            {"psychsyn": 0.0, "person_total": 0.0},  # 7: equal to 0 -> not flagged
        )
        flags = apply_flags(indices, n_items=25)
        assert flags["longstring"].tolist() == [1, 0, 0, 0, 0, 0, 0, 0]
        assert flags["mahalanobis"].tolist() == [0, 0, 1, 0, 0, 0, 0, 0]
        assert flags["even_odd"].tolist() == [0, 0, 0, 0, 1, 0, 0, 0]
        assert flags["psychsyn"].tolist() == [0, 0, 0, 0, 0, 0, 1, 0]
        assert flags["person_total"].tolist() == [0, 0, 0, 0, 0, 0, 1, 0]
        assert flags["n_rules_triggered"].tolist() == [1, 0, 1, 0, 1, 0, 2, 0]
        assert flags["flagged"].tolist() == [True, False, True, False, True, False, True, False]

    def test_reasons_are_readable(self):
        indices = indices_frame(
            {"longstring": 25, "mahalanobis_p": 1e-9, "mahalanobis": 98.24},
            {"mahalanobis_p": 0.0004, "mahalanobis": 51.0},
            {"even_odd": 0.123, "psychsyn": -0.25, "person_total": -0.051},
            {},
        )
        reasons = apply_flags(indices, n_items=25)["reasons"].tolist()
        assert reasons[0] == (
            "Longstring 25 (threshold 13); Mahalanobis D² 98.2, p < 0.001 (threshold p < 0.001)"
        )
        assert reasons[1] == "Mahalanobis D² 51.0, p < 0.001 (threshold p < 0.001)"
        assert reasons[2] == (
            "Even-odd r = 0.12 (threshold < 0.30); "
            "Psychometric synonyms r = -0.25 (threshold < 0.00); "
            "Person-total r = -0.05 (threshold < 0.00)"
        )
        assert reasons[3] == ""

    def test_p_value_shown_when_not_tiny(self):
        indices = indices_frame({"mahalanobis_p": 0.004, "mahalanobis": 40.0})
        flags = apply_flags(indices, {"mahalanobis": {"p_below": 0.01}}, n_items=25)
        assert flags.at[0, "reasons"] == "Mahalanobis D² 40.0, p = 0.004 (threshold p < 0.01)"

    def test_missing_index_value_never_flags(self):
        nan_row = {key: NAN for key in BENIGN}
        flags = apply_flags(indices_frame(nan_row, {"even_odd": 0.1}), n_items=25)
        assert flags.loc[0, ["longstring", "mahalanobis", "even_odd"]].tolist() == [0, 0, 0]
        assert not flags.at[0, "flagged"]
        assert flags.at[0, "reasons"] == ""
        assert flags.at[1, "flagged"]

    def test_disabled_rule_is_left_out(self):
        indices = indices_frame({"even_odd": 0.1})
        flags = apply_flags(indices, {"even_odd": {"enabled": False}}, n_items=25)
        assert "even_odd" not in flags
        assert not flags.at[0, "flagged"]

    def test_custom_thresholds(self):
        indices = indices_frame({"longstring": 4}, {"even_odd": 0.25})
        rules = {"longstring": {"share_of_items": 0.3}, "even_odd": {"r_below": 0.2}}
        flags = apply_flags(indices, rules, n_items=10)
        assert flags["longstring"].tolist() == [True, False]
        assert flags.at[0, "reasons"] == "Longstring 4 (threshold 3)"
        assert flags["even_odd"].tolist() == [False, False]

    def test_index_missing_for_everyone_is_left_out_with_warning(self):
        indices = indices_frame({"psychsyn": NAN}, {"psychsyn": NAN})
        warnings: list[str] = []
        flags = apply_flags(indices, n_items=25, warnings=warnings)
        assert "psychsyn" not in flags
        assert any("psychsyn flag rule was not applied" in w for w in warnings)

    def test_no_duration_column_means_no_speed_rule_and_no_warning(self):
        warnings: list[str] = []
        flags = apply_flags(indices_frame({}), n_items=25, warnings=warnings)
        assert "seconds_per_item" not in flags
        assert warnings == []

    def test_seconds_per_item_rule(self):
        indices = indices_frame({"seconds_per_item": 1.5}, {"seconds_per_item": 2.0})
        flags = apply_flags(indices, n_items=25)
        assert flags["seconds_per_item"].tolist() == [True, False]
        assert flags.at[0, "reasons"] == "1.5 seconds per item (threshold < 2)"

    def test_keeps_the_index(self):
        indices = indices_frame({"longstring": 25}, {}).set_axis([7, 42])
        flags = apply_flags(indices, n_items=25)
        assert flags.index.tolist() == [7, 42]
        assert flags.at[7, "flagged"]

    def test_no_rules_applied_flags_nobody(self):
        rules = {name: {"enabled": False} for name in DEFAULT_RULES}
        flags = apply_flags(indices_frame({"longstring": 25}), rules, n_items=25)
        assert flags["n_rules_triggered"].tolist() == [0]
        assert flags["flagged"].tolist() == [False]


# ---------------------------------------------------------------------------- composite


class TestCompositeScore:
    def test_by_hand(self):
        # longstring (high = careless):     1, 2, 3       -> ranks 1/3, 2/3, 1
        # person_total (low = careless):  0.5, 0.9, -0.1  -> oriented -0.5, -0.9, 0.1
        #                                                 -> ranks 2/3, 1/3, 1
        indices = pd.DataFrame({"longstring": [1.0, 2, 3], "person_total": [0.5, 0.9, -0.1]})
        expected = [(1 / 3 + 2 / 3) / 2, (2 / 3 + 1 / 3) / 2, 1.0]
        np.testing.assert_allclose(composite_score(indices), expected)

    def test_ties_share_the_average_rank(self):
        indices = pd.DataFrame({"longstring": [5.0, 5, 1, 9]})
        # sorted: 1 (rank 1), 5, 5 (ranks 2 and 3 -> 2.5), 9 (rank 4); divided by 4
        np.testing.assert_allclose(composite_score(indices), [0.625, 0.625, 0.25, 1.0])

    def test_missing_index_uses_the_others(self):
        indices = pd.DataFrame({"longstring": [1.0, 2, 3], "even_odd": [0.9, NAN, 0.1]})
        # longstring ranks 1/3, 2/3, 1; even_odd (low) over 2 values: 0.9 -> 0.5, 0.1 -> 1
        np.testing.assert_allclose(composite_score(indices), [(1 / 3 + 0.5) / 2, 2 / 3, 1.0])

    def test_only_composite_indices_count(self):
        base = pd.DataFrame({"longstring": [1.0, 2, 3]})
        extra = base.assign(
            irv=[0.0, 3.0, 1.0], mahalanobis_p=[0.9, 0.0, 0.5], even_odd_sb=[1.0, -1.0, 0.0]
        )
        pd.testing.assert_series_equal(composite_score(base), composite_score(extra))
        assert "irv" not in COMPOSITE_INDICES

    def test_index_missing_for_everyone_is_ignored(self):
        indices = pd.DataFrame({"longstring": [1.0, 2], "psychsyn": [NAN, NAN]})
        np.testing.assert_allclose(composite_score(indices), [0.5, 1.0])

    def test_no_indices_gives_nan(self):
        assert composite_score(pd.DataFrame({"irv": [1.0, 2.0]})).isna().all()

    def test_respondent_with_no_values_is_nan_and_range_is_0_to_1(self):
        indices = pd.DataFrame({"longstring": [1.0, NAN, 4, 2], "mahalanobis": [3.0, NAN, 1, 9]})
        score = composite_score(indices)
        assert np.isnan(score[1])
        assert score.drop(1).between(0, 1, inclusive="right").all()
        assert score.name == "composite"


# ---------------------------------------------------------------------------- variants


class TestVariants:
    def test_top_share_distinct_scores(self):
        scores = pd.Series(np.arange(20, dtype=float))
        assert top_share_mask(scores, 0.10).tolist() == [False] * 18 + [True, True]

    def test_top_share_rounds_up_and_keeps_ties(self):
        # 11 scores -> ceil(1.1) = 2; the 2nd highest (8) is tied, so three are selected.
        scores = pd.Series([1.0, 2, 3, 4, 5, 6, 7, 8, 8, 0, 9])
        mask = top_share_mask(scores, 0.10)
        assert scores[mask].sort_values().tolist() == [8.0, 8.0, 9.0]

    def test_top_share_ignores_missing(self):
        scores = pd.Series([NAN, 0.2, 0.9, NAN])
        assert top_share_mask(scores, 0.10).tolist() == [False, False, True, False]
        assert not top_share_mask(pd.Series([NAN, NAN]), 0.10).any()

    def test_top_share_invalid(self):
        with pytest.raises(ValueError):
            top_share_mask(pd.Series([1.0]), 0)

    def test_flag_variants(self):
        flags = pd.DataFrame({"n_rules_triggered": [0, 1, 2, 3, 0, 0, 0, 0, 0, 0]})
        composite = pd.Series([0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 0.95])
        variants = flag_variants(flags, composite)
        assert tuple(variants) == VARIANT_NAMES
        assert variants["any_rule"].tolist() == [0, 1, 1, 1, 0, 0, 0, 0, 0, 0]
        assert variants["two_rules"].tolist() == [0, 0, 1, 1, 0, 0, 0, 0, 0, 0]
        assert variants["composite_top10"].tolist() == [0] * 9 + [1]
        assert all(v.dtype == bool for v in variants.values())


# ---------------------------------------------------------------------------- bfi


def test_flags_on_bfi(bfi_csv_path):
    schema = SurveySchema.load(BFI_SCHEMA)
    prepared = prepare_data(load_csv(bfi_csv_path), schema)
    warnings: list[str] = []
    indices = compute_indices(prepared, schema, warnings=warnings)
    flags = apply_flags(indices, n_items=len(schema.items), warnings=warnings)
    composite = composite_score(indices)
    variants = flag_variants(flags, composite)

    # psychsyn finds only one pair at 0.60 on bfi, so its rule cannot be applied.
    assert "psychsyn" not in flags
    assert any("psychsyn flag rule was not applied" in w for w in warnings)
    assert {"longstring", "mahalanobis", "even_odd", "person_total"} <= set(flags.columns)
    assert flags.index.equals(indices.index)
    assert (flags["reasons"] != "").equals(flags["flagged"])
    assert composite.notna().all()
    assert composite.between(0, 1, inclusive="right").all()
    n_top = int(variants["composite_top10"].sum())
    assert n_top >= math.ceil(0.10 * len(composite))
    assert variants["two_rules"].sum() <= variants["any_rule"].sum()
