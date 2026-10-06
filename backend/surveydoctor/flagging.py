"""Flag rules, the composite carelessness score, and the exclusion variants for robustness.

Flags answer "did this respondent cross a fixed line on any index?". Each rule compares one
index from :mod:`surveydoctor.careless` with a threshold and gives a readable reason when
it fires. The thresholds are heuristics and conventions, not proven cut-offs.

The composite score answers a different question: "how unusual is this respondent compared
with the rest of *this* dataset?". It averages percentile ranks, so it is a relative
ranking within one dataset, not a probability that anyone was careless.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd

from surveydoctor.careless import INDEX_DIRECTIONS

# Default flag rules (all configurable). Every rule except longstring flags values strictly
# below its threshold; longstring flags runs at least ceil(share_of_items × number of items).
DEFAULT_RULES: dict[str, dict[str, Any]] = {
    "longstring": {"enabled": True, "share_of_items": 0.5},
    "mahalanobis": {"enabled": True, "p_below": 0.001},
    "even_odd": {"enabled": True, "r_below": 0.30},
    "psychsyn": {"enabled": True, "r_below": 0.0},
    "person_total": {"enabled": True, "r_below": 0.0},
    "seconds_per_item": {"enabled": True, "seconds_below": 2.0},
}

# Rule name -> (index column it reads, setting that holds its threshold).
_RULE_SOURCES: dict[str, tuple[str, str]] = {
    "longstring": ("longstring", "share_of_items"),
    "mahalanobis": ("mahalanobis_p", "p_below"),
    "even_odd": ("even_odd", "r_below"),
    "psychsyn": ("psychsyn", "r_below"),
    "person_total": ("person_total", "r_below"),
    "seconds_per_item": ("seconds_per_item", "seconds_below"),
}

# Indices that enter the composite score. IRV is left out because its careless direction
# is ambiguous. Mahalanobis p and the Spearman–Brown even-odd value are left out because
# they repeat (rank for rank) the information in D² and the raw even-odd r.
COMPOSITE_INDICES: tuple[str, ...] = (
    "longstring",
    "mahalanobis",
    "even_odd",
    "psychsyn",
    "person_total",
    "seconds_per_item",
)

# Exclusion variants used by the robustness check (§7.6), in display order.
VARIANT_NAMES: tuple[str, ...] = ("any_rule", "two_rules", "composite_top10")


def _warn(warnings: list[str] | None, message: str) -> None:
    if warnings is not None:
        warnings.append(message)


def merge_rules(rules: dict[str, dict[str, Any]] | None = None) -> dict[str, dict[str, Any]]:
    """Return the default rules with any user settings laid over them.

    Args:
        rules: Rule name -> settings to change, e.g. ``{"even_odd": {"r_below": 0.2}}`` or
            ``{"psychsyn": {"enabled": False}}``. Settings not given keep their defaults.

    Raises:
        ValueError: if a rule or setting name is unknown, or a threshold is out of range.
    """
    merged = {name: dict(settings) for name, settings in DEFAULT_RULES.items()}
    for name, settings in (rules or {}).items():
        if name not in merged:
            known = ", ".join(DEFAULT_RULES)
            raise ValueError(f"Unknown flag rule '{name}'. Known rules: {known}.")
        for key, value in settings.items():
            if key not in merged[name]:
                known = ", ".join(merged[name])
                raise ValueError(f"Unknown setting '{key}' for rule '{name}'. Use: {known}.")
            merged[name][key] = value

    for name, settings in merged.items():
        if not isinstance(settings["enabled"], bool):
            raise ValueError(f"'enabled' for rule '{name}' must be true or false.")
        threshold = settings[_RULE_SOURCES[name][1]]
        if not isinstance(threshold, int | float) or isinstance(threshold, bool):
            raise ValueError(f"The threshold for rule '{name}' must be a number.")
    if not 0 < merged["longstring"]["share_of_items"] <= 1:
        raise ValueError("The longstring share of items must be above 0 and at most 1.")
    if not 0 < merged["mahalanobis"]["p_below"] < 1:
        raise ValueError("The Mahalanobis p-value threshold must be between 0 and 1.")
    for name in ("even_odd", "psychsyn", "person_total"):
        if not -1 <= merged[name]["r_below"] <= 1:
            raise ValueError(f"The correlation threshold for rule '{name}' must be from -1 to 1.")
    if merged["seconds_per_item"]["seconds_below"] <= 0:
        raise ValueError("The seconds-per-item threshold must be above 0.")
    return merged


def longstring_threshold(n_items: int, share_of_items: float = 0.5) -> int:
    """Run length at which the longstring rule fires: ceil(share_of_items × n_items)."""
    if n_items < 1:
        raise ValueError("n_items must be at least 1.")
    # Rounding guards against 0.3 × 10 = 3.0000000000000004 becoming 4.
    return max(1, math.ceil(round(share_of_items * n_items, 9)))


def _format_p(p: float) -> str:
    return "p < 0.001" if p < 0.001 else f"p = {p:.3f}"


def _reason(rule: str, row: pd.Series, threshold: float) -> str:
    """One readable reason, e.g. 'Longstring 25 (threshold 13)'."""
    if rule == "longstring":
        return f"Longstring {int(row['longstring'])} (threshold {int(threshold)})"
    if rule == "mahalanobis":
        d2 = row.get("mahalanobis", np.nan)
        d2_text = f"D² {d2:.1f}, " if pd.notna(d2) else ""
        p_text = _format_p(row["mahalanobis_p"])
        return f"Mahalanobis {d2_text}{p_text} (threshold p < {threshold:g})"
    if rule == "even_odd":
        return f"Even-odd r = {row['even_odd']:.2f} (threshold < {threshold:.2f})"
    if rule == "psychsyn":
        return f"Psychometric synonyms r = {row['psychsyn']:.2f} (threshold < {threshold:.2f})"
    if rule == "person_total":
        return f"Person-total r = {row['person_total']:.2f} (threshold < {threshold:.2f})"
    return f"{row['seconds_per_item']:.1f} seconds per item (threshold < {threshold:g})"


def apply_flags(
    indices: pd.DataFrame,
    rules: dict[str, dict[str, Any]] | None = None,
    *,
    n_items: int,
    warnings: list[str] | None = None,
) -> pd.DataFrame:
    """Apply the flag rules to every respondent and say why each flag fired.

    A rule fires when its index crosses the threshold in the careless direction:
    longstring at or above ceil(share × number of items); Mahalanobis p, even-odd r,
    psychometric-synonym r, person-total r and seconds per item strictly below theirs.

    Direction: a rule that fires is a sign of possible carelessness; more rules firing is
    stronger evidence.

    Limitations: thresholds are heuristics or conventions, not validated cut-offs, and a
    respondent can be flagged for a genuinely unusual but honest answer pattern. A
    respondent whose index could not be computed (NaN) is never flagged by that rule, so
    missing evidence is treated as no evidence. A rule whose index is absent, or missing for
    every respondent, is left out of the result (with a warning) rather than reported as
    flagging nobody.

    Args:
        indices: Output of :func:`surveydoctor.careless.compute_indices`.
        rules: Settings that override :data:`DEFAULT_RULES` (see :func:`merge_rules`).
        n_items: Number of items in the survey (sets the longstring threshold).
        warnings: Optional list that receives a reason for every rule that was not applied.

    Returns:
        One row per respondent (same index as ``indices``) with one boolean column per
        applied rule (named after the rule), ``n_rules_triggered``, ``flagged`` (at least one
        rule fired) and ``reasons`` (readable text, empty when nothing fired).
    """
    settings_by_rule = merge_rules(rules)
    out = pd.DataFrame(index=indices.index)
    thresholds: dict[str, float] = {}
    for rule, settings in settings_by_rule.items():
        if not settings["enabled"]:
            continue
        column, key = _RULE_SOURCES[rule]
        values = indices[column] if column in indices else None
        if values is None or values.isna().all():
            if rule != "seconds_per_item" or values is not None:
                _warn(
                    warnings,
                    f"The {rule.replace('_', '-')} flag rule was not applied because the "
                    "index could not be computed for any respondent.",
                )
            continue
        values = values.astype(float)
        if rule == "longstring":
            threshold = float(longstring_threshold(n_items, settings[key]))
            fired = values >= threshold
        else:
            threshold = float(settings[key])
            fired = values < threshold
        out[rule] = fired.fillna(False).astype(bool)
        thresholds[rule] = threshold

    applied = list(thresholds)
    out["n_rules_triggered"] = out[applied].sum(axis=1).astype(int) if applied else 0
    out["flagged"] = out["n_rules_triggered"] >= 1

    reasons = pd.Series("", index=indices.index, dtype=object)
    for respondent in out.index[out["flagged"]]:
        row = indices.loc[respondent]
        fired_rules = [rule for rule in applied if out.at[respondent, rule]]
        reasons[respondent] = "; ".join(
            _reason(rule, row, thresholds[rule]) for rule in fired_rules
        )
    out["reasons"] = reasons
    return out


def _oriented(values: pd.Series, column: str) -> pd.Series:
    """Index values turned so that higher always means more careless."""
    direction = INDEX_DIRECTIONS[column]
    if direction == "high":
        return values.astype(float)
    if direction == "low":
        return -values.astype(float)
    raise ValueError(f"Index '{column}' has no single careless direction.")


def composite_score(indices: pd.DataFrame) -> pd.Series:
    """Relative carelessness ranking: the average percentile rank across available indices.

    Each index in :data:`COMPOSITE_INDICES` that is present and computed for at least one
    respondent is turned so that higher means more careless, then converted to a percentile
    rank within this dataset (pandas ``rank(pct=True)``: the share of respondents with an
    equal or less careless value, ties sharing the average rank; values in (0, 1]). A
    respondent's composite is the mean of the ranks they have; indices that are NaN for
    them are skipped.

    Direction: higher is more suspicious. 0.95 means "more unusual than most respondents in
    this file on the available indices".

    Limitations: this is a ranking, not a probability. In a dataset with no careless
    respondents someone still gets the top score, and the same answers can rank
    differently in another dataset. Each index counts equally, whatever its quality, and
    respondents with fewer computable indices are ranked on less evidence. IRV is excluded
    because its careless direction is ambiguous.

    Args:
        indices: Output of :func:`surveydoctor.careless.compute_indices`.

    Returns:
        Series named ``composite`` with the same index as ``indices``; NaN for a respondent
        with no computable index.
    """
    ranks = [
        _oriented(indices[column], column).rank(method="average", pct=True)
        for column in COMPOSITE_INDICES
        if column in indices and indices[column].notna().any()
    ]
    if not ranks:
        return pd.Series(np.nan, index=indices.index, name="composite")
    return pd.concat(ranks, axis=1).mean(axis=1, skipna=True).rename("composite")


def top_share_mask(scores: pd.Series, share: float = 0.10) -> pd.Series:
    """True for the respondents with the highest ``share`` of scores.

    The cut-off is the k-th highest score, k = ceil(share × number of non-missing scores);
    everyone tied with that score is included, so slightly more than ``share`` can be
    selected. Missing scores are never selected.
    """
    if not 0 < share <= 1:
        raise ValueError("share must be above 0 and at most 1.")
    valid = scores.dropna()
    mask = pd.Series(False, index=scores.index)
    if valid.empty:
        return mask
    k = math.ceil(round(share * len(valid), 9))
    cutoff = valid.sort_values(ascending=False).iloc[k - 1]
    mask[valid.index[valid >= cutoff]] = True
    return mask


def flag_variants(flags: pd.DataFrame, composite: pd.Series) -> dict[str, pd.Series]:
    """Three alternative sets of respondents to exclude, for the robustness check.

    * ``any_rule``: at least one flag rule fired (the default ``flagged``).
    * ``two_rules``: at least two rules fired (stricter evidence, fewer exclusions).
    * ``composite_top10``: the top 10% of composite scores (see :func:`top_share_mask`).

    Limitations: these are reasonable alternatives, not a ranking of correctness. Comparing
    results across them shows how much a conclusion depends on the exclusion choice; it
    does not show which respondents should be excluded.

    Args:
        flags: Output of :func:`apply_flags`.
        composite: Output of :func:`composite_score`.

    Returns:
        Variant name -> boolean Series (True = exclude), in :data:`VARIANT_NAMES` order.
    """
    n_triggered = flags["n_rules_triggered"]
    return {
        "any_rule": (n_triggered >= 1).rename("any_rule"),
        "two_rules": (n_triggered >= 2).rename("two_rules"),
        "composite_top10": top_share_mask(composite.reindex(flags.index), 0.10).rename(
            "composite_top10"
        ),
    }
