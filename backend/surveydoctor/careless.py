"""Careless-response indices: per-respondent signs that someone answered without reading.

Each index looks at one respondent's answers from a different angle:

* longstring        - the same answer given many times in a row (straightlining);
* irv               - how spread out a respondent's answers are (reported only);
* mahalanobis       - how unusual the whole answer pattern is compared with everyone else;
* even_odd          - whether two halves of each scale tell the same story;
* psychsyn          - whether near-identical questions get near-identical answers;
* person_total      - whether the respondent's answer profile resembles the group's;
* seconds_per_item  - how fast the survey was completed (only if a duration column exists).

Every function returns values indexed like its input, with NaN where an index cannot be
computed. When a ``warnings`` list is passed, a plain-English reason is appended for every
index (or group of respondents) that could not be computed. No index alone proves that a
respondent was careless; each has blind spots, described in its docstring.
"""

from __future__ import annotations

from typing import Literal

import numpy as np
import pandas as pd
from scipy import stats

from surveydoctor.io import PreparedData
from surveydoctor.schema import SurveySchema

Direction = Literal["high", "low", "ambiguous"]

# Which end of each index looks careless. Used to orient indices for flags and scoring.
INDEX_DIRECTIONS: dict[str, Direction] = {
    "longstring": "high",
    "irv": "ambiguous",
    "mahalanobis": "high",
    "mahalanobis_p": "low",
    "even_odd": "low",
    "even_odd_sb": "low",
    "psychsyn": "low",
    "person_total": "low",
    "seconds_per_item": "low",
}

# Below this sum of squared deviations a set of values is treated as having no variance.
_ZERO_VARIANCE = 1e-12


def _warn(warnings: list[str] | None, message: str) -> None:
    if warnings is not None:
        warnings.append(message)


def _respondents(n: int) -> str:
    return f"{n} respondent{'' if n == 1 else 's'}"


def rowwise_pearson(a: np.ndarray, b: np.ndarray, min_pairs: int = 3) -> np.ndarray:
    """Pearson correlation between row i of ``a`` and row i of ``b``, for every row.

    Within a row, only positions where both values are present are used. The result is NaN
    for a row with fewer than ``min_pairs`` usable positions, or where either side has no
    variance (a correlation is undefined when all values are equal).

    Args:
        a: Array of shape (n_rows, n_positions); NaN marks a missing value.
        b: Array of the same shape as ``a``.
        min_pairs: Minimum number of positions present in both arrays.

    Returns:
        Array of length n_rows with values in [-1, 1] or NaN.
    """
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    if a.shape != b.shape or a.ndim != 2:
        raise ValueError("rowwise_pearson needs two 2-D arrays of the same shape.")
    mask = ~(np.isnan(a) | np.isnan(b))
    count = mask.sum(axis=1)
    safe_count = np.where(count > 0, count, 1)
    a0 = np.where(mask, a, 0.0)
    b0 = np.where(mask, b, 0.0)
    da = np.where(mask, a0 - (a0.sum(axis=1) / safe_count)[:, None], 0.0)
    db = np.where(mask, b0 - (b0.sum(axis=1) / safe_count)[:, None], 0.0)
    ss_a = (da**2).sum(axis=1)
    ss_b = (db**2).sum(axis=1)
    valid = (count >= min_pairs) & (ss_a > _ZERO_VARIANCE) & (ss_b > _ZERO_VARIANCE)
    r = np.full(a.shape[0], np.nan)
    r[valid] = (da * db).sum(axis=1)[valid] / np.sqrt(ss_a[valid] * ss_b[valid])
    return np.clip(r, -1.0, 1.0)


# --------------------------------------------------------------------------------------
# Individual indices
# --------------------------------------------------------------------------------------


def longstring(raw_items: pd.DataFrame) -> pd.Series:
    """Longest run of identical consecutive answers, following the questionnaire order.

    Measures straightlining: ticking the same box again and again. A respondent who gives
    every item the same answer has a longstring equal to the number of items.

    Direction: higher is more suspicious.

    Limitations: depends entirely on item order. A genuinely consistent person can produce
    a long run on a block of similar questions, and a careless person answering at random
    or in a zig-zag pattern gets a low value. A missing answer ends a run. Respondents with
    no answers get NaN.

    Args:
        raw_items: Item answers as given (not reverse-scored), columns in questionnaire order.
    """
    values = raw_items.to_numpy(dtype=float)
    n_rows, n_cols = values.shape
    if n_cols == 0:
        return pd.Series(np.nan, index=raw_items.index, name="longstring")
    present = ~np.isnan(values)
    run = present[:, 0].astype(float)
    longest = run.copy()
    for j in range(1, n_cols):
        same = present[:, j] & present[:, j - 1] & (values[:, j] == values[:, j - 1])
        run = np.where(same, run + 1, present[:, j].astype(float))
        longest = np.maximum(longest, run)
    longest[~present.any(axis=1)] = np.nan
    return pd.Series(longest, index=raw_items.index, name="longstring")


def irv(raw_items: pd.DataFrame) -> pd.Series:
    """Intra-individual response variability: standard deviation of a respondent's answers.

    Uses the sample standard deviation (ddof=1) of the answers the respondent gave.
    For answers 1, 2, 3, 4, 5 it is about 1.58; for a straightliner it is 0.

    Direction: ambiguous. Very low values suggest straightlining, very high values can
    suggest random answering, and ordinary values say little. For that reason IRV is
    reported only and is not used in flags or the composite score.

    Limitations: mixes up careless answering with genuine extreme or uniform opinions, and
    is affected by reverse-worded items (computed on raw answers). Needs at least two
    answers, otherwise NaN.

    Args:
        raw_items: Item answers as given (not reverse-scored).
    """
    return raw_items.std(axis=1, ddof=1).astype(float).rename("irv")


def mahalanobis(raw_items: pd.DataFrame, warnings: list[str] | None = None) -> pd.DataFrame:
    """Mahalanobis distance: how far a respondent's whole answer pattern is from the average.

    D² = (x − μ)ᵀ Σ⁻¹ (x − μ), where μ and Σ are the item means and covariance matrix
    (ddof=1) of respondents with no missing answers. Σ⁻¹ is the pseudo-inverse, so the
    distance still exists if some items are perfectly correlated. Unlike looking at items
    one by one, this takes the correlations between items into account: answering "agree"
    to two items that most people answer in opposite directions is unusual even if each
    answer on its own is common. The p-value comes from a chi-square distribution with
    degrees of freedom equal to the number of items.

    Direction: higher D² (lower p) is more suspicious.

    Limitations: an unusual pattern is not proof of carelessness; genuinely atypical people
    also score high. The chi-square p-value assumes multivariate normal data, which rating
    answers only approximate. Respondents with any missing answer get NaN. Not computed
    when there are not more complete respondents than items.

    Args:
        raw_items: Item answers as given (not reverse-scored).
        warnings: Optional list that receives reasons for values that could not be computed.

    Returns:
        DataFrame with columns ``mahalanobis`` (D²) and ``mahalanobis_p``.
    """
    out = pd.DataFrame(np.nan, index=raw_items.index, columns=["mahalanobis", "mahalanobis_p"])
    values = raw_items.to_numpy(dtype=float)
    n_items = values.shape[1]
    complete = ~np.isnan(values).any(axis=1)
    n_complete = int(complete.sum())
    if n_items == 0 or n_complete <= n_items:
        _warn(
            warnings,
            f"Mahalanobis distance was not computed: it needs more respondents with no missing "
            f"answers ({n_complete}) than items ({n_items}).",
        )
        return out

    x = values[complete]
    mean = x.mean(axis=0)
    cov = np.cov(x, rowvar=False, ddof=1).reshape(n_items, n_items)
    inv = np.linalg.pinv(cov)
    centred = x - mean
    d2 = np.einsum("ij,jk,ik->i", centred, inv, centred)
    d2 = np.maximum(d2, 0.0)
    out.loc[complete, "mahalanobis"] = d2
    out.loc[complete, "mahalanobis_p"] = stats.chi2.sf(d2, df=n_items)

    n_incomplete = len(values) - n_complete
    if n_incomplete:
        _warn(
            warnings,
            f"Mahalanobis distance was not computed for {_respondents(n_incomplete)} with at "
            "least one missing answer.",
        )
    return out


def _in_questionnaire_order(items: list[str], order: list[str]) -> list[str]:
    position = {item: i for i, item in enumerate(order)}
    return sorted(items, key=lambda item: position.get(item, len(order)))


def even_odd(
    scored_items: pd.DataFrame,
    scales: dict[str, list[str]],
    min_scale_items: int = 4,
    min_scales: int = 3,
    warnings: list[str] | None = None,
) -> pd.DataFrame:
    """Even-odd consistency: do two halves of each scale give the same picture?

    Each scale with at least ``min_scale_items`` items is split by position (in the order of
    the scored_items columns) into odd items (1st, 3rd, ...) and even items (2nd, 4th, ...).
    For each respondent the mean of each half is taken, giving one odd-half score and one
    even-half score per scale. The index is the Pearson correlation, across scales, between
    the odd-half and the even-half scores. An attentive respondent who is high on one scale
    and low on another shows this in both halves, so the correlation is high.

    Also returns the Spearman–Brown corrected value 2r / (1 + r), which estimates the
    consistency of full-length rather than half-length scales. The correction is only
    meaningful for r ≥ 0: for negative r the formula falls below −1 (e.g. −94 at
    r = −0.979) and is undefined at r = −1, so it can no longer be read as a correlation.
    The corrected value is therefore NaN whenever r < 0; the raw r is always kept, and flag
    rules use the raw r.

    Direction: lower is more suspicious (values near zero or negative).

    Limitations: needs at least ``min_scales`` eligible scales; with few scales the
    correlation rests on very few points and is noisy. A straightliner has identical half
    scores on every scale, so the correlation is undefined (NaN); longstring covers that
    case. Reverse-worded items must be declared, because this runs on reverse-scored data.
    Half means use the answers given; a respondent needs both halves of a scale answered
    for it to count, and at least ``min_scales`` such scales.

    Args:
        scored_items: Answers with reverse items recoded, columns in questionnaire order.
        scales: Scale name -> item columns.
        min_scale_items: Smallest scale that is split into halves.
        min_scales: Number of eligible scales needed to compute the index.
        warnings: Optional list that receives reasons for values that could not be computed.

    Returns:
        DataFrame with columns ``even_odd`` (raw r) and ``even_odd_sb`` (Spearman–Brown).
    """
    out = pd.DataFrame(np.nan, index=scored_items.index, columns=["even_odd", "even_odd_sb"])
    order = list(scored_items.columns)
    eligible = {name: items for name, items in scales.items() if len(items) >= min_scale_items}
    if len(eligible) < min_scales:
        _warn(
            warnings,
            f"Even-odd consistency was not computed: it needs at least {min_scales} scales with "
            f"{min_scale_items} or more items, and this survey has {len(eligible)}.",
        )
        return out

    odd_means: list[np.ndarray] = []
    even_means: list[np.ndarray] = []
    for items in eligible.values():
        ordered = _in_questionnaire_order(items, order)
        odd_means.append(scored_items[ordered[0::2]].mean(axis=1).to_numpy(dtype=float))
        even_means.append(scored_items[ordered[1::2]].mean(axis=1).to_numpy(dtype=float))
    r = rowwise_pearson(np.column_stack(odd_means), np.column_stack(even_means), min_scales)

    with np.errstate(divide="ignore", invalid="ignore"):
        sb = np.where(r >= 0.0, 2.0 * r / (1.0 + r), np.nan)
    out["even_odd"] = r
    out["even_odd_sb"] = sb

    n_missing = int(np.isnan(r).sum())
    if n_missing:
        _warn(
            warnings,
            f"Even-odd consistency could not be computed for {_respondents(n_missing)}: their "
            "half-scale scores were identical across scales (e.g. the same answer everywhere) "
            f"or fewer than {min_scales} scales had both halves answered.",
        )
    return out


def synonym_pairs(raw_items: pd.DataFrame, critval: float = 0.60) -> list[tuple[str, str, float]]:
    """Find item pairs whose answers correlate above ``critval`` across all respondents.

    Correlations are Pearson, computed on pairwise complete answers. Each pair is returned
    as (earlier item, later item, r) in questionnaire order, sorted by that order.
    """
    corr = raw_items.corr(method="pearson")
    columns = list(raw_items.columns)
    pairs: list[tuple[str, str, float]] = []
    for i, first in enumerate(columns):
        for second in columns[i + 1 :]:
            r = corr.at[first, second]
            if pd.notna(r) and r > critval:
                pairs.append((first, second, float(r)))
    return pairs


def psychsyn(
    raw_items: pd.DataFrame,
    critval: float = 0.60,
    min_pairs: int = 3,
    warnings: list[str] | None = None,
) -> pd.Series:
    """Psychometric synonyms: do questions that most people answer alike get alike answers?

    First, item pairs that correlate above ``critval`` across the whole sample are found
    ("synonyms", see :func:`synonym_pairs`). Then, for each respondent, the answers to the
    first items of the pairs are correlated with the answers to the second items. An
    attentive respondent answers synonyms similarly, giving a high positive correlation.

    Direction: lower is more suspicious (near zero or negative).

    Limitations: needs at least ``min_pairs`` synonym pairs in the data; many short or
    heterogeneous questionnaires have few. A respondent needs ``min_pairs`` pairs with
    both items answered. Straightliners give identical answers everywhere, so the
    correlation is undefined (NaN); longstring covers that case. Computed on raw answers,
    so reverse-worded items only pair with items worded in the same direction.

    Args:
        raw_items: Item answers as given (not reverse-scored).
        critval: Correlation above which two items count as synonyms.
        min_pairs: Minimum number of synonym pairs (in the data, and per respondent).
        warnings: Optional list that receives reasons for values that could not be computed.
    """
    out = pd.Series(np.nan, index=raw_items.index, name="psychsyn")
    pairs = synonym_pairs(raw_items, critval)
    if len(pairs) < min_pairs:
        _warn(
            warnings,
            f"Psychometric synonyms were not computed: the data has {len(pairs)} item pair(s) "
            f"correlating above {critval:.2f}, and at least {min_pairs} are needed.",
        )
        return out

    first = raw_items[[p[0] for p in pairs]].to_numpy(dtype=float)
    second = raw_items[[p[1] for p in pairs]].to_numpy(dtype=float)
    out[:] = rowwise_pearson(first, second, min_pairs)

    n_missing = int(out.isna().sum())
    if n_missing:
        _warn(
            warnings,
            f"Psychometric synonyms could not be computed for {_respondents(n_missing)}: their "
            f"answers to the {len(pairs)} synonym pairs did not vary, or fewer than {min_pairs} "
            "pairs were fully answered.",
        )
    return out


def leave_one_out_means(raw_items: pd.DataFrame) -> pd.DataFrame:
    """For each respondent and item, the item mean over all *other* respondents.

    If the respondent answered the item, their own answer is removed from the mean; if not,
    the ordinary mean of the item is used. NaN where no other respondent answered.
    """
    values = raw_items.to_numpy(dtype=float)
    present = ~np.isnan(values)
    sums = np.nansum(values, axis=0)
    counts = present.sum(axis=0)
    others_sum = np.where(present, sums - np.where(present, values, 0.0), sums)
    others_count = np.where(present, counts - 1, counts)
    with np.errstate(divide="ignore", invalid="ignore"):
        means = np.where(others_count > 0, others_sum / others_count, np.nan)
    return pd.DataFrame(means, index=raw_items.index, columns=raw_items.columns)


def person_total(
    raw_items: pd.DataFrame, min_items: int = 3, warnings: list[str] | None = None
) -> pd.Series:
    """Person-total correlation: does the respondent's answer profile resemble the group's?

    For each respondent, the Pearson correlation across items between their answers and
    the item means of all other respondents (leave-one-out, so a respondent's own answers
    do not inflate the result). Attentive respondents tend to endorse the items most people
    endorse and reject the items most people reject, giving a positive correlation.

    Direction: lower is more suspicious (near zero or negative).

    Limitations: a respondent with a genuinely unusual profile also scores low. When items
    have similar means the group profile is flat and the correlation is noisy for everyone.
    Respondents who gave the same answer to every item get NaN (longstring covers them),
    as do respondents with fewer than ``min_items`` answers.

    Args:
        raw_items: Item answers as given (not reverse-scored).
        min_items: Minimum number of answered items.
        warnings: Optional list that receives reasons for values that could not be computed.
    """
    loo = leave_one_out_means(raw_items).to_numpy(dtype=float)
    r = rowwise_pearson(raw_items.to_numpy(dtype=float), loo, min_items)
    out = pd.Series(r, index=raw_items.index, name="person_total")
    n_missing = int(out.isna().sum())
    if n_missing:
        _warn(
            warnings,
            f"Person-total correlation could not be computed for {_respondents(n_missing)} who "
            f"gave the same answer to every item or answered fewer than {min_items} items.",
        )
    return out


def seconds_per_item(
    durations_seconds: pd.Series, n_items: int, warnings: list[str] | None = None
) -> pd.Series:
    """Average time spent per item: total completion time in seconds ÷ number of items.

    Direction: lower is more suspicious (answering faster than reading allows).

    Limitations: total time includes reading instructions, breaks and other questions, and
    some people read fast. A respondent who left the survey open for a long time looks
    attentive even if they were not. Missing durations give NaN.

    Args:
        durations_seconds: Completion time per respondent, in seconds.
        n_items: Number of rating items in the survey.
        warnings: Optional list that receives reasons for values that could not be computed.
    """
    if n_items < 1:
        raise ValueError("n_items must be at least 1.")
    out = (durations_seconds.astype(float) / n_items).rename("seconds_per_item")
    n_missing = int(out.isna().sum())
    if n_missing:
        _warn(
            warnings,
            f"Seconds per item could not be computed for {_respondents(n_missing)} without a "
            "usable completion time.",
        )
    return out


# --------------------------------------------------------------------------------------
# All indices
# --------------------------------------------------------------------------------------


def compute_indices(
    prepared: PreparedData,
    schema: SurveySchema,
    warnings: list[str] | None = None,
    psychsyn_critval: float = 0.60,
) -> pd.DataFrame:
    """Compute every available careless-response index for every respondent.

    Longstring, IRV, Mahalanobis, psychometric synonyms and person-total use the answers as
    given (``raw_items``); even-odd consistency uses reverse-scored answers
    (``scored_items``), because it averages items within scales. Seconds per item is
    included only if the schema declares a duration column.

    Args:
        prepared: Output of :func:`surveydoctor.io.prepare_data`.
        schema: The survey schema (item order and scales).
        warnings: Optional list that receives reasons for values that could not be computed.
        psychsyn_critval: Correlation above which two items count as psychometric synonyms.

    Returns:
        One row per respondent (same index as ``prepared.raw_items``) with columns
        longstring, irv, mahalanobis, mahalanobis_p, even_odd, even_odd_sb, psychsyn,
        person_total and, if available, seconds_per_item.
    """
    raw = prepared.raw_items[schema.items]
    scored = prepared.scored_items[schema.items]
    parts: list[pd.Series | pd.DataFrame] = [
        longstring(raw),
        irv(raw),
        mahalanobis(raw, warnings=warnings),
        even_odd(scored, schema.scales, warnings=warnings),
        psychsyn(raw, critval=psychsyn_critval, warnings=warnings),
        person_total(raw, warnings=warnings),
    ]
    if prepared.durations_seconds is not None:
        parts.append(
            seconds_per_item(prepared.durations_seconds, len(schema.items), warnings=warnings)
        )
    return pd.concat(parts, axis=1)
