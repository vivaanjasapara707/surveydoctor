"""Reliability: whether the questions of each scale agree with each other.

For every declared scale, on reverse-scored answers and respondents who answered all of
that scale's items (listwise deletion, with the count reported):

* cronbach_alpha  - Cronbach's alpha with a 95% confidence interval (via pingouin);
* omega_total     - McDonald's omega total from a one-factor model (via factor_analyzer);
* item_stats      - corrected item-total correlation and alpha if the item is deleted;
* reverse_warnings - items that run against the rest of their scale.

High reliability says the items move together. It does not prove the scale measures a
single concept, or the concept it was meant to measure. Items are never reversed
automatically: a negative item-total correlation only produces a warning.
"""

from __future__ import annotations

import math
import warnings as py_warnings
from dataclasses import dataclass

import numpy as np
import pandas as pd
import pingouin
from factor_analyzer import FactorAnalyzer

from surveydoctor.io import PreparedData
from surveydoctor.schema import SurveySchema

# Omega needs a one-factor model, which needs at least this many items to be informative.
MIN_ITEMS_OMEGA = 3

# factor_analyzer keeps each uniqueness within (0.005, 1). A uniqueness at the lower bound
# means the fit wanted an item to be explained completely (a Heywood case).
_UNIQUENESS_LOWER_BOUND = 0.005

# Below this variance a column or total score is treated as constant.
_ZERO_VARIANCE = 1e-12


@dataclass
class ReverseWarning:
    """An item whose answers run against the rest of its scale (after declared reversals)."""

    scale: str
    item: str
    corrected_item_total: float
    message: str


@dataclass
class ScaleReliability:
    """Reliability results for one scale.

    Attributes:
        scale: Scale name.
        items: The scale's items.
        n_items: Number of items.
        n_used: Respondents who answered every item of the scale (used for all statistics).
        n_excluded: Respondents left out because at least one of the scale's items is missing.
        alpha: Cronbach's alpha (NaN if not computable).
        alpha_ci: 95% confidence interval for alpha (Feldt method, as computed by pingouin,
            which rounds the bounds to 3 decimals); (NaN, NaN) if not computable.
        omega_total: McDonald's omega total (NaN if not computable).
        loadings: Standardized one-factor loadings, signed so that their sum is not negative
            (NaN if omega was not computed).
        item_stats: One row per item: ``corrected_item_total`` and ``alpha_if_deleted``.
        reverse_warnings: Items with a negative corrected item-total correlation.
    """

    scale: str
    items: list[str]
    n_items: int
    n_used: int
    n_excluded: int
    alpha: float
    alpha_ci: tuple[float, float]
    omega_total: float
    loadings: pd.Series
    item_stats: pd.DataFrame
    reverse_warnings: list[ReverseWarning]


def _warn(warnings: list[str] | None, message: str) -> None:
    if warnings is not None:
        warnings.append(message)


def _respondents(n: int) -> str:
    return f"{n} respondent{'' if n == 1 else 's'}"


def complete_cases(scored_items: pd.DataFrame, items: list[str]) -> pd.DataFrame:
    """The scale's items for respondents who answered all of them (listwise deletion)."""
    return scored_items[items].dropna(axis=0, how="any").astype(float)


# --------------------------------------------------------------------------------------
# Alpha
# --------------------------------------------------------------------------------------


def _alpha_computable(data: pd.DataFrame) -> bool:
    """Alpha needs 2+ items, 2+ respondents and a total score that varies."""
    n, k = data.shape
    if k < 2 or n < 2:
        return False
    return float(data.sum(axis=1).var(ddof=1)) > _ZERO_VARIANCE


def cronbach_alpha(data: pd.DataFrame, ci: float = 0.95) -> tuple[float, tuple[float, float]]:
    """Cronbach's alpha: how consistently a set of items moves together, with a CI.

    alpha = k / (k − 1) × (1 − sum of item variances / variance of the total score), for k
    items. It rises when items correlate with each other and when there are more items. The
    confidence interval uses Feldt's F-distribution method (pingouin's implementation).

    Direction: lower is worse. Values of 0.70 or more are commonly treated as acceptable,
    but this is a convention, not a law.

    Limitations: alpha assumes every item measures the concept equally well (tau-equivalence);
    when they don't, it tends to underestimate reliability (omega relaxes this). A high
    alpha does not show that the scale measures a single concept: long scales get high
    alpha even when they mix several. It treats ordinal answers as continuous. pingouin
    rounds the confidence bounds to 3 decimals.

    Args:
        data: Complete cases only (respondents × items, no missing values). pingouin computes
            the CI's sample size before its own listwise deletion, so incomplete rows would
            give a wrong interval.
        ci: Confidence level of the interval.

    Returns:
        (alpha, (lower, upper)); all NaN if alpha is undefined (fewer than 2 items or 2
        respondents, or a total score with no variance).
    """
    if data.isna().any().any():
        raise ValueError("cronbach_alpha needs complete cases; drop rows with missing answers.")
    if not _alpha_computable(data):
        return math.nan, (math.nan, math.nan)
    alpha, bounds = pingouin.cronbach_alpha(data.astype(float), ci=ci, nan_policy="listwise")
    return float(alpha), (float(bounds[0]), float(bounds[1]))


# --------------------------------------------------------------------------------------
# Omega
# --------------------------------------------------------------------------------------


def omega_from_loadings(loadings: pd.Series | np.ndarray) -> float:
    """McDonald's omega total from standardized one-factor loadings.

    omega = (Σλ)² / ((Σλ)² + Σψ), with uniquenesses ψ = 1 − λ². It is the share of the
    total-score variance explained by the common factor.

    Direction: lower is worse (0 to 1).

    Limitations: only as good as the one-factor model behind it. If the scale really has
    several factors, omega total still treats them as one. Items with negative loadings
    reduce Σλ and so reduce omega.
    """
    lam = np.asarray(loadings, dtype=float)
    if lam.size == 0 or np.isnan(lam).any():
        return math.nan
    common = lam.sum() ** 2
    unique = (1.0 - lam**2).sum()
    total = common + unique
    return float(common / total) if total > 0 else math.nan


def one_factor_loadings(
    data: pd.DataFrame, scale: str = "", warnings: list[str] | None = None
) -> pd.Series:
    """Standardized loadings of a one-factor model (minres, no rotation, factor_analyzer).

    A loading is the correlation between an item and the single common factor. The sign of
    a factor is arbitrary, so the loadings are flipped if needed to make their sum
    non-negative.

    Direction: loadings near 0 (or negative) mean the item shares little with the others.

    Limitations: fitted on the Pearson correlation matrix, treating ordinal answers as
    continuous. Needs at least 3 items, more complete respondents than items, and no
    constant item; otherwise all loadings are NaN and a warning says why. If an item's
    uniqueness reaches the fitting bound (a Heywood case), a warning is added because the
    loadings, and omega, may be overstated.

    Args:
        data: Complete cases only (respondents × items).
        scale: Scale name, used in warnings.
        warnings: List that receives plain-English reasons when the model cannot be fitted.
    """
    nan_loadings = pd.Series(np.nan, index=data.columns, name="loading")
    n, k = data.shape
    label = f"scale '{scale}'" if scale else "this scale"
    if k < MIN_ITEMS_OMEGA:
        _warn(
            warnings,
            f"Omega was not computed for {label}: it needs at least {MIN_ITEMS_OMEGA} items, "
            f"and the scale has {k}.",
        )
        return nan_loadings
    if n <= k:
        _warn(
            warnings,
            f"Omega was not computed for {label}: it needs more respondents with complete "
            f"answers ({n}) than items ({k}).",
        )
        return nan_loadings
    constant = [item for item in data.columns if data[item].var(ddof=1) <= _ZERO_VARIANCE]
    if constant:
        _warn(
            warnings,
            f"Omega was not computed for {label}: every respondent gave the same answer to "
            f"{', '.join(constant)}, so the item has no variance to share.",
        )
        return nan_loadings
    try:
        with py_warnings.catch_warnings():
            # factor_analyzer warns (and falls back to a pseudo-inverse) when the correlation
            # matrix is nearly singular; the Heywood check below covers the consequence.
            py_warnings.simplefilter("ignore")
            model = FactorAnalyzer(n_factors=1, rotation=None, method="minres")
            model.fit(data.to_numpy(dtype=float))
    except (np.linalg.LinAlgError, ValueError) as error:
        _warn(warnings, f"Omega was not computed for {label}: the factor model failed ({error}).")
        return nan_loadings
    lam = model.loadings_[:, 0]
    if lam.sum() < 0:
        lam = -lam
    if np.any(1.0 - lam**2 <= _UNIQUENESS_LOWER_BOUND + 1e-6):
        _warn(
            warnings,
            f"Omega for {label} may be overstated: the one-factor model explains at least one "
            "item almost completely (a Heywood case), which usually means too little data or "
            "near-duplicate items.",
        )
    return pd.Series(lam, index=data.columns, name="loading")


def omega_total(data: pd.DataFrame, scale: str = "", warnings: list[str] | None = None) -> float:
    """McDonald's omega total for one scale: one-factor minres model, then the omega formula.

    See :func:`one_factor_loadings` (the model) and :func:`omega_from_loadings` (the
    formula). Direction: lower is worse. Limitations: as for those two functions; NaN with
    a warning when the model cannot be fitted (e.g. fewer than 3 items).

    Args:
        data: Complete cases only (respondents × items).
        scale: Scale name, used in warnings.
        warnings: List that receives plain-English reasons when omega cannot be computed.
    """
    return omega_from_loadings(one_factor_loadings(data, scale, warnings))


# --------------------------------------------------------------------------------------
# Item statistics
# --------------------------------------------------------------------------------------


def corrected_item_total(data: pd.DataFrame) -> pd.Series:
    """Correlation of each item with the sum of the scale's other items.

    "Corrected" means the item itself is left out of the total, so it cannot correlate with
    itself. A good item correlates clearly positively with the rest of its scale.

    Direction: lower is worse; negative values mean the item runs against the others.

    Limitations: Pearson correlation on ordinal answers. NaN when the item or the rest-score
    has no variance, or with fewer than 2 respondents.

    Args:
        data: Complete cases only (respondents × items), reverse items already rescored.
    """
    total = data.sum(axis=1)
    values = {}
    for item in data.columns:
        rest = total - data[item]
        if (
            len(data) < 2
            or data[item].var(ddof=1) <= _ZERO_VARIANCE
            or (rest.var(ddof=1) <= _ZERO_VARIANCE)
        ):
            values[item] = math.nan
        else:
            values[item] = float(np.corrcoef(data[item], rest)[0, 1])
    return pd.Series(values, name="corrected_item_total", dtype=float)


def alpha_if_deleted(data: pd.DataFrame) -> pd.Series:
    """Cronbach's alpha of the scale with each item left out in turn.

    If alpha rises noticeably when an item is removed, that item fits the scale worse than
    the others.

    Direction: a value above the full-scale alpha marks a weak item.

    Limitations: alpha always tends to fall when items are removed (it grows with scale
    length), so small rises matter. NaN when fewer than 2 items would remain.

    Args:
        data: Complete cases only (respondents × items).
    """
    values = {
        item: cronbach_alpha(data.drop(columns=item))[0] if data.shape[1] > 2 else math.nan
        for item in data.columns
    }
    return pd.Series(values, name="alpha_if_deleted", dtype=float)


def item_stats(data: pd.DataFrame) -> pd.DataFrame:
    """Per item: ``corrected_item_total`` and ``alpha_if_deleted`` (see those functions).

    Args:
        data: Complete cases only (respondents × items), reverse items already rescored.
    """
    return pd.concat([corrected_item_total(data), alpha_if_deleted(data)], axis=1)


def reverse_warnings(scale: str, stats: pd.DataFrame) -> list[ReverseWarning]:
    """Items whose corrected item-total correlation is negative on reverse-scored data.

    Such an item runs against the rest of its scale. Possible causes include reverse wording
    that was not declared, a confusing question, or a coding error, but the data cannot
    tell these apart. The message therefore only asks the user to check the question; it
    does not say the item is reversed. SurveyDoctor never changes answers automatically.

    Limitations: when several items of a scale are mis-keyed, the rest-score is pulled the
    wrong way and correctly keyed items can be warned about too (on bfi with no reverse
    items declared, 13 items are warned about, including all 7 truly reverse-keyed ones;
    with the correct reverse items declared, none are).

    Args:
        scale: Scale name.
        stats: Output of :func:`item_stats` for that scale.
    """
    out = []
    for item, r in stats["corrected_item_total"].items():
        if pd.notna(r) and r < 0:
            out.append(
                ReverseWarning(
                    scale=scale,
                    item=str(item),
                    corrected_item_total=float(r),
                    message=(
                        f"Check this question: it disagrees with the rest of its scale. Item "
                        f"{item} has a corrected item-total correlation of {r:.2f} with the "
                        f"other items of scale '{scale}'. SurveyDoctor does not change answers "
                        "automatically."
                    ),
                )
            )
    return out


# --------------------------------------------------------------------------------------
# Per scale and for the whole survey
# --------------------------------------------------------------------------------------


def scale_reliability(
    scored_items: pd.DataFrame,
    scale: str,
    items: list[str],
    warnings: list[str] | None = None,
) -> ScaleReliability:
    """All reliability statistics for one scale, on respondents who answered all its items.

    Args:
        scored_items: Reverse-scored answers (``PreparedData.scored_items``).
        scale: Scale name.
        items: The scale's items.
        warnings: List that receives plain-English notes: respondents left out, statistics
            that could not be computed, and items that may be reverse-worded.
    """
    data = complete_cases(scored_items, items)
    n_used = len(data)
    n_excluded = len(scored_items) - n_used
    if n_excluded:
        _warn(
            warnings,
            f"Reliability for scale '{scale}' used {_respondents(n_used)} who answered all "
            f"its items; {_respondents(n_excluded)} with a missing answer were left out.",
        )
    alpha, ci = cronbach_alpha(data)
    if math.isnan(alpha):
        _warn(
            warnings,
            f"Cronbach's alpha was not computed for scale '{scale}': it needs at least 2 "
            "respondents with complete answers whose total scores differ.",
        )
    loadings = one_factor_loadings(data, scale, warnings)
    stats = item_stats(data)
    flagged = reverse_warnings(scale, stats)
    for warning in flagged:
        _warn(warnings, warning.message)
    return ScaleReliability(
        scale=scale,
        items=list(items),
        n_items=len(items),
        n_used=n_used,
        n_excluded=n_excluded,
        alpha=alpha,
        alpha_ci=ci,
        omega_total=omega_from_loadings(loadings),
        loadings=loadings,
        item_stats=stats,
        reverse_warnings=flagged,
    )


def reliability(
    prepared: PreparedData, schema: SurveySchema, warnings: list[str] | None = None
) -> dict[str, ScaleReliability]:
    """Reliability of every scale in the schema, in schema order.

    Args:
        prepared: Output of :func:`surveydoctor.io.prepare_data`.
        schema: The survey schema (scales and their items).
        warnings: List that receives plain-English notes (see :func:`scale_reliability`).

    Returns:
        Scale name -> :class:`ScaleReliability`.
    """
    return {
        scale: scale_reliability(prepared.scored_items, scale, items, warnings)
        for scale, items in schema.scales.items()
    }


def summary_table(results: dict[str, ScaleReliability]) -> pd.DataFrame:
    """One row per scale: items, N used, N excluded, alpha with CI, omega total."""
    rows = [
        {
            "scale": r.scale,
            "n_items": r.n_items,
            "n_used": r.n_used,
            "n_excluded": r.n_excluded,
            "alpha": r.alpha,
            "alpha_ci_low": r.alpha_ci[0],
            "alpha_ci_high": r.alpha_ci[1],
            "omega_total": r.omega_total,
        }
        for r in results.values()
    ]
    return pd.DataFrame(rows).set_index("scale")
