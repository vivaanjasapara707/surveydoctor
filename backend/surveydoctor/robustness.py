"""Robustness: does one declared conclusion survive removing flagged respondents?

The user declares exactly one analysis:

* GroupComparison - a scale score compared between two groups of a chosen column
  (Welch's t-test, mean difference with 95% CI, Cohen's d; Mann-Whitney U as a companion);
* Correlation     - between two scale scores (Pearson r with a Fisher-z 95% CI;
  Spearman's rho as a companion).

The analysis is run on all respondents, then again excluding each of the three flag
variants (``any_rule``, ``two_rules``, ``composite_top10``; see
:func:`surveydoctor.flagging.flag_variants`). The verdict compares the variants with the
all-respondents result:

* "stable"   - same significance and same direction everywhere;
* "sensitive" - significance changes in at least one variant;
* "unstable" - a significant result reverses: in at least one variant the result is
  significant in the opposite direction (strongest warning). The sign of a non-significant
  estimate is not counted, because it can flip by chance (see docs/decisions.md, Stage 9).

This shows how much the conclusion depends on the exclusion choice. It does not show which
respondents should be excluded, and a stable result can still be wrong for other reasons
(sampling, measurement, confounding).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Literal

import numpy as np
import pandas as pd
from scipy import stats

from surveydoctor.io import PreparedData, scale_scores
from surveydoctor.schema import SurveySchema

ALPHA = 0.05
ALL_RESPONDENTS = "all"

Verdict = Literal["stable", "sensitive", "unstable"]
Direction = Literal["positive", "negative", "none"]

ROBUSTNESS_CAVEAT = (
    "This shows sensitivity to exclusion choices. It does not prove which respondents "
    "should be excluded."
)

MIN_PER_GROUP = 2  # Welch's t-test needs a variance in each group
MIN_CORRELATION_N = 4  # a Fisher-z interval needs n - 3 > 0


@dataclass(frozen=True)
class GroupComparison:
    """Compare ``scale`` between respondents whose ``group_column`` equals ``group_a`` and
    those whose value equals ``group_b``. The estimate is mean(A) − mean(B)."""

    scale: str
    group_column: str
    group_a: str | int | float
    group_b: str | int | float


@dataclass(frozen=True)
class Correlation:
    """Correlate the scores of ``scale_x`` and ``scale_y``."""

    scale_x: str
    scale_y: str


AnalysisSpec = GroupComparison | Correlation


@dataclass
class VariantResult:
    """The declared analysis on one set of respondents.

    Attributes:
        variant: "all" or the flag variant whose respondents were excluded.
        n_excluded: Respondents removed by the variant (0 for "all").
        n: Respondents used (with the needed scores, and in group A or B).
        estimate: Mean difference A − B, or Pearson r. NaN if not computable.
        ci_low, ci_high: 95% confidence interval for the estimate.
        p: Two-sided p-value (Welch's t-test or Pearson).
        significant: p < 0.05; None if not computable.
        direction: Sign of the estimate.
        effect_size: Cohen's d (pooled SD) for groups; r for correlations.
        companion: Mann-Whitney U or Spearman's rho.
        companion_p: Its two-sided p-value.
        n_a, n_b: Group sizes (group comparisons only).
        note: Why the result could not be computed, if it could not.
    """

    variant: str
    n_excluded: int
    n: int
    estimate: float
    ci_low: float
    ci_high: float
    p: float
    significant: bool | None
    direction: Direction | None
    effect_size: float
    companion: float
    companion_p: float
    n_a: int | None = None
    n_b: int | None = None
    note: str | None = None


@dataclass
class RobustnessResult:
    """The variant table and the verdict.

    Attributes:
        analysis: The declared analysis.
        variants: One row per variant, "all" first.
        verdict: "stable", "sensitive" or "unstable" (None if the all-respondents result
            could not be computed).
        changed_variants: Variants whose significance or direction differs from "all".
        caveat: The sentence that must always accompany the verdict.
    """

    analysis: AnalysisSpec
    variants: list[VariantResult]
    verdict: Verdict | None
    changed_variants: list[str] = field(default_factory=list)
    caveat: str = ROBUSTNESS_CAVEAT

    def table(self) -> pd.DataFrame:
        """The variant table for the report and the API."""
        return pd.DataFrame([vars(v) for v in self.variants])


def _direction(estimate: float) -> Direction:
    if estimate > 0:
        return "positive"
    if estimate < 0:
        return "negative"
    return "none"


def _not_computable(variant: str, n_excluded: int, n: int, note: str, **groups) -> VariantResult:
    nan = math.nan
    return VariantResult(
        variant, n_excluded, n, nan, nan, nan, nan, None, None, nan, nan, nan, note=note, **groups
    )


def cohens_d(a: np.ndarray, b: np.ndarray) -> float:
    """Cohen's d with the pooled standard deviation: (mean A − mean B) / SD_pooled.

    SD_pooled = sqrt(((n_A − 1) s_A² + (n_B − 1) s_B²) / (n_A + n_B − 2)). Positive when A
    scores higher. NaN if the pooled SD is 0. Rough benchmarks: 0.2 small, 0.5 medium,
    0.8 large.
    """
    na, nb = len(a), len(b)
    pooled = ((na - 1) * a.var(ddof=1) + (nb - 1) * b.var(ddof=1)) / (na + nb - 2)
    if pooled <= 0:
        return math.nan
    return float((a.mean() - b.mean()) / math.sqrt(pooled))


def compare_groups(
    a: np.ndarray, b: np.ndarray, variant: str = ALL_RESPONDENTS, n_excluded: int = 0
) -> VariantResult:
    """Welch's t-test of A against B, with the mean difference, its 95% CI and Cohen's d.

    Welch's test does not assume equal variances. Mann-Whitney U (two-sided) is reported as
    a companion that does not assume normal scores. Direction: positive means A scores
    higher. Limitation: a significant difference says nothing about why the groups differ.
    """
    na, nb = len(a), len(b)
    if na < MIN_PER_GROUP or nb < MIN_PER_GROUP:
        return _not_computable(
            variant, n_excluded, na + nb,
            f"Each group needs at least {MIN_PER_GROUP} respondents with a score "
            f"(group A has {na}, group B has {nb}).",
            n_a=na, n_b=nb,
        )  # fmt: skip
    if a.var(ddof=1) == 0 and b.var(ddof=1) == 0:
        return _not_computable(
            variant, n_excluded, na + nb,
            "Every respondent in both groups has the same score, so there is nothing to test.",
            n_a=na, n_b=nb,
        )  # fmt: skip
    test = stats.ttest_ind(a, b, equal_var=False)
    ci = test.confidence_interval(1 - ALPHA)
    mw = stats.mannwhitneyu(a, b, alternative="two-sided")
    estimate = float(a.mean() - b.mean())
    return VariantResult(
        variant=variant,
        n_excluded=n_excluded,
        n=na + nb,
        estimate=estimate,
        ci_low=float(ci.low),
        ci_high=float(ci.high),
        p=float(test.pvalue),
        significant=bool(test.pvalue < ALPHA),
        direction=_direction(estimate),
        effect_size=cohens_d(a, b),
        companion=float(mw.statistic),
        companion_p=float(mw.pvalue),
        n_a=na,
        n_b=nb,
    )


def correlate(
    x: np.ndarray, y: np.ndarray, variant: str = ALL_RESPONDENTS, n_excluded: int = 0
) -> VariantResult:
    """Pearson r between x and y with a Fisher-z 95% CI and two-sided p (via SciPy).

    Spearman's rho is reported as a companion that only assumes a monotonic relationship.
    Direction: positive means higher x goes with higher y. Limitation: a correlation is not
    evidence of cause, and Pearson r understates relationships that are not linear.
    """
    n = len(x)
    if n < MIN_CORRELATION_N:
        return _not_computable(
            variant, n_excluded, n,
            f"A correlation needs at least {MIN_CORRELATION_N} respondents with both scores "
            f"(found {n}).",
        )  # fmt: skip
    if np.ptp(x) == 0 or np.ptp(y) == 0:
        return _not_computable(
            variant, n_excluded, n,
            "One of the scales has the same score for every respondent, so no correlation "
            "can be computed.",
        )  # fmt: skip
    pearson = stats.pearsonr(x, y)
    ci = pearson.confidence_interval(1 - ALPHA)
    spearman = stats.spearmanr(x, y)
    r = float(pearson.statistic)
    return VariantResult(
        variant=variant,
        n_excluded=n_excluded,
        n=n,
        estimate=r,
        ci_low=float(ci.low),
        ci_high=float(ci.high),
        p=float(pearson.pvalue),
        significant=bool(pearson.pvalue < ALPHA),
        direction=_direction(r),
        effect_size=r,
        companion=float(spearman.statistic),
        companion_p=float(spearman.pvalue),
    )


def verdict(variants: list[VariantResult]) -> tuple[Verdict | None, list[str]]:
    """Compare every variant with the all-respondents result (the first entry).

    Returns the verdict and the variants that differ. "unstable" (both results significant,
    in opposite directions) takes precedence over "sensitive" (a significance change). A
    sign change between non-significant estimates is ignored: it can happen by chance and
    is not evidence of a reversed conclusion. Variants that could not be computed are
    ignored here; the caller reports them separately. Returns (None, []) if the
    all-respondents result could not be computed.
    """
    base, others = variants[0], [v for v in variants[1:] if v.significant is not None]
    if base.significant is None:
        return None, []
    flipped = [
        v.variant
        for v in others
        if base.significant and v.significant and v.direction != base.direction
    ]
    changed = [v.variant for v in others if v.significant != base.significant]
    if flipped:
        return "unstable", [v.variant for v in others if v.variant in set(flipped + changed)]
    if changed:
        return "sensitive", changed
    return "stable", []


def _group_mask(column: pd.Series, value: str | int | float) -> pd.Series:
    """Rows whose value equals ``value``. Numbers are compared as numbers (so 1, 1.0 and
    "1" match), everything else as trimmed text."""
    numeric_column = pd.to_numeric(column, errors="coerce")
    try:
        numeric_value = float(value)
    except (TypeError, ValueError):
        numeric_value = math.nan
    if not math.isnan(numeric_value) and numeric_column.notna().any():
        return numeric_column == numeric_value
    return column.astype(str).str.strip() == str(value).strip()


def check_analysis(analysis: AnalysisSpec, prepared: PreparedData, schema: SurveySchema) -> None:
    """Raise ValueError (plain English) if the declared analysis cannot be run at all."""
    if isinstance(analysis, GroupComparison):
        scales = [analysis.scale]
    else:
        scales = [analysis.scale_x, analysis.scale_y]
        if analysis.scale_x == analysis.scale_y:
            raise ValueError("Choose two different scales to correlate.")
    unknown = [s for s in scales if s not in schema.scales]
    if unknown:
        raise ValueError(
            f"Unknown scale: {', '.join(unknown)}. Choose one of: {', '.join(schema.scales)}."
        )
    if isinstance(analysis, GroupComparison):
        if analysis.group_column not in prepared.meta.columns:
            raise ValueError(
                f"The column '{analysis.group_column}' is not available for grouping. Choose a "
                "non-question column; columns that look like personal information are excluded."
            )
        if str(analysis.group_a).strip() == str(analysis.group_b).strip():
            raise ValueError("Choose two different group values to compare.")
        column = prepared.meta[analysis.group_column]
        for value in (analysis.group_a, analysis.group_b):
            if not _group_mask(column, value).any():
                raise ValueError(
                    f"No respondent has the value '{value}' in column '{analysis.group_column}'."
                )


def _run_variant(
    analysis: AnalysisSpec,
    scores: pd.DataFrame,
    meta: pd.DataFrame,
    keep: pd.Series,
    variant: str,
) -> VariantResult:
    n_excluded = int((~keep).sum())
    kept = scores[keep]
    if isinstance(analysis, GroupComparison):
        column = meta.loc[keep, analysis.group_column]
        values = kept[analysis.scale]
        a = values[_group_mask(column, analysis.group_a)].dropna().to_numpy(dtype=float)
        b = values[_group_mask(column, analysis.group_b)].dropna().to_numpy(dtype=float)
        return compare_groups(a, b, variant, n_excluded)
    pair = kept[[analysis.scale_x, analysis.scale_y]].dropna()
    return correlate(
        pair[analysis.scale_x].to_numpy(dtype=float),
        pair[analysis.scale_y].to_numpy(dtype=float),
        variant,
        n_excluded,
    )


def robustness(
    analysis: AnalysisSpec,
    prepared: PreparedData,
    schema: SurveySchema,
    exclusions: dict[str, pd.Series],
    warnings: list[str] | None = None,
) -> RobustnessResult:
    """Run the declared analysis on all respondents and without each flag variant.

    Scale scores are the mean of a scale's reverse-scored items, computed only for
    respondents who answered at least 80% of them (:func:`surveydoctor.io.scale_scores`).

    Args:
        analysis: A GroupComparison or a Correlation.
        prepared: Output of :func:`surveydoctor.io.prepare_data`.
        schema: The survey schema.
        exclusions: Variant name -> boolean Series (True = exclude), as returned by
            :func:`surveydoctor.flagging.flag_variants`.
        warnings: Optional list that receives plain-English notes.

    Raises:
        ValueError: If the analysis refers to unknown scales, columns or group values.
    """
    check_analysis(analysis, prepared, schema)
    index = prepared.scored_items.index
    scores = scale_scores(prepared.scored_items, schema.scales)
    meta = prepared.meta.reindex(index)

    variants = [_run_variant(analysis, scores, meta, pd.Series(True, index=index), ALL_RESPONDENTS)]
    for name, exclude in exclusions.items():
        keep = ~exclude.reindex(index, fill_value=False).astype(bool)
        variants.append(_run_variant(analysis, scores, meta, keep, name))

    result_verdict, changed = verdict(variants)
    if warnings is not None:
        needed = [analysis.scale] if isinstance(analysis, GroupComparison) else [
            analysis.scale_x, analysis.scale_y,
        ]  # fmt: skip
        missing = int(scores[needed].isna().any(axis=1).sum())
        if missing:
            warnings.append(
                f"Robustness check: {missing} respondents have no score on "
                f"{' or '.join(needed)} (fewer than 80% of the scale's items answered) and "
                "are left out of every variant."
            )
        for v in variants:
            if v.note is not None:
                warnings.append(f"Robustness check, variant '{v.variant}': {v.note}")
    return RobustnessResult(analysis, variants, result_verdict, changed)
