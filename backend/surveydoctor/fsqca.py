"""fsQCA (fuzzy-set Qualitative Comparative Analysis), part 1: calibration and necessity.

fsQCA asks which combinations of conditions (here, scale scores) go with an outcome (another
scale score), using set relations rather than correlations. Part 1 (BLUEPRINT §7.14, Stage
10A) turns scale scores into fuzzy set memberships and tests whether any condition is
necessary for the outcome:

* calibrate       - direct calibration (Ragin's logistic method), as in R's QCA::calibrate;
* percentile_anchors - the default anchors: 95th, 50th and 5th percentiles of the sample;
* necessity       - consistency, coverage and relevance of necessity for each condition and
                    its negation, as in QCA::pof(relation = "necessity").

§3 lists no Python library for fsQCA, so the calculations are implemented here and checked
against R's QCA package (tests/test_reference_r.py).

Limitations: memberships depend on the anchors, which are a modelling choice; set relations
in one sample are not causes; and Likert scale scores take few distinct values, so many
respondents can sit exactly at the crossover (membership 0.5, see :func:`at_crossover`).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Literal

import numpy as np
import pandas as pd

from surveydoctor.io import PreparedData, scale_scores
from surveydoctor.schema import SurveySchema

MIN_CONDITIONS = 2
MAX_CONDITIONS = 7  # 2^7 = 128 truth-table rows; beyond that most rows would be empty

DEFAULT_PERCENTILES = (95.0, 50.0, 5.0)  # full membership, crossover, full non-membership

# Membership at the outer anchors. QCA::calibrate's default (idm = 0.95): the full-membership
# anchor maps to 0.95 and the non-membership anchor to 0.05. Ragin's original ±3 log-odds
# would give 0.953 and 0.047 (verification_log.md, item 19).
INCLUSION_DEGREE = 0.95

NECESSITY_THRESHOLD = 0.90  # BLUEPRINT §7.14 default [VERIFY with supervisor]

AnchorSource = Literal["percentiles", "scale points"]


@dataclass(frozen=True)
class Anchors:
    """The three calibration anchors of one scale, in scale points.

    Attributes:
        full: Score at which membership is 0.95 (full membership).
        crossover: Score at which membership is exactly 0.5.
        non: Score at which membership is 0.05 (full non-membership).
        source: "percentiles" (computed from the sample) or "scale points" (set by the user).
        percentiles: The (full, crossover, non) percentiles used, for percentile anchors.
    """

    full: float
    crossover: float
    non: float
    source: AnchorSource = "scale points"
    percentiles: tuple[float, float, float] | None = None

    def is_ordered(self) -> bool:
        return self.full > self.crossover > self.non


@dataclass(frozen=True)
class FsqcaSpec:
    """The fsQCA the user asked for.

    Attributes:
        outcome: The outcome scale.
        conditions: 2 to 7 condition scales (not including the outcome).
        anchors: Optional scale-point anchors, scale name -> (full, crossover, non). Scales
            not listed use the default percentile anchors.
        necessity_threshold: Consistency at or above which a condition passes the
            necessity test (default 0.90).
    """

    outcome: str
    conditions: tuple[str, ...]
    anchors: dict[str, tuple[float, float, float]] = field(default_factory=dict)
    necessity_threshold: float = NECESSITY_THRESHOLD

    def scales(self) -> list[str]:
        return [*self.conditions, self.outcome]


@dataclass
class NecessityResult:
    """Necessity of one condition (or its negation) for the outcome.

    Attributes:
        condition: Scale name, with "~" in front for the negation.
        consistency: Σ min(X, Y) / Σ Y. Near 1: the outcome rarely occurs without X.
        coverage: Σ min(X, Y) / Σ X. Low: X is much more common than the outcome.
        relevance: Relevance of necessity, Σ (1 − X) / Σ (1 − min(X, Y)). Low: X is present
            almost everywhere, so calling it necessary says little (a trivial condition).
        passes: consistency >= the necessity threshold.
    """

    condition: str
    consistency: float
    coverage: float
    relevance: float
    passes: bool


@dataclass
class FsqcaResults:
    """fsQCA results (part 1: calibration and necessity).

    Attributes:
        spec: The analysis asked for.
        n_used: Respondents with a score on every scale involved.
        n_excluded: Respondents left out because a scale score is missing.
        anchors: Scale name -> anchors used.
        scores: Scale scores of the respondents used.
        memberships: Calibrated memberships (0–1), same shape as ``scores``.
        n_at_crossover: Respondents with membership exactly 0.5 in at least one condition.
        necessity: Necessity results, two rows per condition (X and ~X), or empty if skipped.
        skipped_reason: Why the analysis could not run (None when it ran).
    """

    spec: FsqcaSpec
    n_used: int
    n_excluded: int
    anchors: dict[str, Anchors]
    scores: pd.DataFrame
    memberships: pd.DataFrame
    n_at_crossover: int
    necessity: list[NecessityResult]
    skipped_reason: str | None = None

    def necessity_table(self) -> pd.DataFrame:
        """One row per condition and negation, for the report and the API."""
        return pd.DataFrame([vars(r) for r in self.necessity])


# --- Input checks -------------------------------------------------------------------------


def check_spec(spec: FsqcaSpec, schema: SurveySchema) -> None:
    """Raise ValueError (plain English) if the requested fsQCA cannot be run at all."""
    unknown = [s for s in spec.scales() if s not in schema.scales]
    if unknown:
        raise ValueError(
            f"Unknown scale: {', '.join(unknown)}. Choose from: {', '.join(schema.scales)}."
        )
    if spec.outcome in spec.conditions:
        raise ValueError(f"The outcome '{spec.outcome}' cannot also be a condition.")
    if len(set(spec.conditions)) != len(spec.conditions):
        raise ValueError("Each condition can be chosen only once.")
    if not MIN_CONDITIONS <= len(spec.conditions) <= MAX_CONDITIONS:
        raise ValueError(
            f"Choose {MIN_CONDITIONS} to {MAX_CONDITIONS} conditions; "
            f"{len(spec.conditions)} were chosen."
        )
    for scale, values in spec.anchors.items():
        if scale not in spec.scales():
            raise ValueError(f"Anchors were given for '{scale}', which is not in this analysis.")
        if len(values) != 3:
            raise ValueError(
                f"Anchors for '{scale}' need three numbers: full membership, crossover and "
                "full non-membership."
            )
        full, crossover, non = values
        if not full > crossover > non:
            raise ValueError(
                f"Anchors for '{scale}' must be in order: full membership ({full}) above the "
                f"crossover ({crossover}) above full non-membership ({non})."
            )
        if non < schema.scale_min or full > schema.scale_max:
            raise ValueError(
                f"Anchors for '{scale}' must lie on the answer scale "
                f"({schema.scale_min} to {schema.scale_max})."
            )
    if not 0.5 < spec.necessity_threshold <= 1:
        raise ValueError("The necessity threshold must be above 0.5 and at most 1.")


# --- Calibration --------------------------------------------------------------------------


def percentile_anchors(
    values: pd.Series, percentiles: tuple[float, float, float] = DEFAULT_PERCENTILES
) -> Anchors:
    """Anchors at the given percentiles of the observed scores (default 95th, 50th, 5th).

    Uses numpy's default (linear) percentile, the same as R's ``quantile(type = 7)``.
    The anchors can tie when many respondents share a score; check
    :meth:`Anchors.is_ordered` before calibrating.
    """
    full, crossover, non = (float(np.percentile(values.dropna(), p)) for p in percentiles)
    return Anchors(full, crossover, non, source="percentiles", percentiles=percentiles)


def calibrate(values: pd.Series, anchors: Anchors, idm: float = INCLUSION_DEGREE) -> pd.Series:
    """Direct calibration (Ragin's logistic method) of scores into fuzzy membership.

    The log-odds of membership are 0 at the crossover and grow linearly with the distance
    from it, scaled separately on each side so that the full-membership anchor gets
    membership ``idm`` (0.95) and the non-membership anchor gets 1 − ``idm`` (0.05):

        membership = 1 / (1 + exp(−(x − c) · ln(idm / (1 − idm)) / d))

    with d = full − c for x ≥ c and d = c − non for x < c (both positive, so scores below
    the crossover get log-odds below 0 and membership below 0.5).
    Scores beyond the outer anchors keep moving towards 0 or 1 (no clamping), as in
    QCA::calibrate(type = "fuzzy", method = "direct", logistic = TRUE).

    Direction: higher membership means more clearly "in" the set (e.g. high Neuroticism).
    Limitation: the result depends entirely on the anchors chosen.
    """
    if not anchors.is_ordered():
        raise ValueError(
            "Anchors must be in order: full membership above the crossover above full "
            "non-membership."
        )
    x = values.astype(float)
    log_odds_at_anchor = math.log(idm / (1 - idm))
    distance = np.where(
        x >= anchors.crossover,
        anchors.full - anchors.crossover,
        anchors.crossover - anchors.non,
    )
    log_odds = (x - anchors.crossover) * log_odds_at_anchor / distance
    return (1 / (1 + np.exp(-log_odds))).rename(values.name)


def at_crossover(memberships: pd.DataFrame, conditions: list[str]) -> pd.Series:
    """True for respondents with membership exactly 0.5 in at least one condition.

    Such a respondent is neither in nor out of that condition, so it belongs to no truth-table
    row. R's QCA package (3.25) warns about them, leaves them out of every row's case count
    and case list, but keeps them in the consistency, coverage and PRI sums
    (verification_log.md, item 18). SurveyDoctor follows the same convention.
    """
    return memberships[conditions].eq(0.5).any(axis=1)


# --- Necessity ----------------------------------------------------------------------------


def _ratio(numerator: float, denominator: float) -> float:
    return numerator / denominator if denominator > 0 else math.nan


def necessity_of(x: pd.Series, y: pd.Series, label: str, threshold: float) -> NecessityResult:
    """Consistency, coverage and relevance of necessity of X for Y (see NecessityResult)."""
    both = np.minimum(x, y)
    consistency = _ratio(both.sum(), y.sum())
    return NecessityResult(
        condition=label,
        consistency=consistency,
        coverage=_ratio(both.sum(), x.sum()),
        relevance=_ratio((1 - x).sum(), (1 - both).sum()),
        passes=bool(consistency >= threshold),
    )


def necessity(
    memberships: pd.DataFrame,
    outcome: str,
    conditions: list[str],
    threshold: float = NECESSITY_THRESHOLD,
) -> list[NecessityResult]:
    """Necessity of each condition and of its negation (1 − X) for the outcome.

    Passing the threshold is consistent with necessity, not proof of it: check coverage and
    relevance too, because a condition that almost everyone has passes trivially.
    """
    y = memberships[outcome]
    results = []
    for condition in conditions:
        x = memberships[condition]
        results.append(necessity_of(x, y, condition, threshold))
        results.append(necessity_of(1 - x, y, f"~{condition}", threshold))
    return results


# --- The analysis -------------------------------------------------------------------------


def fsqca(
    prepared: PreparedData,
    schema: SurveySchema,
    spec: FsqcaSpec,
    warnings: list[str] | None = None,
) -> FsqcaResults:
    """Calibrate the chosen scales and test the necessity of each condition.

    Scale scores are the mean of a scale's reverse-scored items for respondents who answered
    at least 80% of them (:func:`surveydoctor.io.scale_scores`). Respondents without a score
    on every scale involved are left out, and the count is reported.

    Raises:
        ValueError: If the spec names unknown scales, repeats a scale, has fewer than 2 or
            more than 7 conditions, or gives anchors that are out of order or off the scale.
    """
    check_spec(spec, schema)
    notes: list[str] = []
    scales = spec.scales()
    all_scores = scale_scores(prepared.scored_items, {s: schema.scales[s] for s in scales})
    scores = all_scores.dropna()
    n_excluded = len(all_scores) - len(scores)
    if n_excluded:
        notes.append(
            f"fsQCA used {len(scores)} respondents with a score on every scale involved; "
            f"{n_excluded} without one (fewer than 80% of a scale's items answered) were left out."
        )

    def skipped(reason: str) -> FsqcaResults:
        notes.append(f"fsQCA was not run: {reason}")
        if warnings is not None:
            warnings.extend(notes)
        empty = pd.DataFrame(columns=scales, dtype=float)
        return FsqcaResults(spec, len(scores), n_excluded, anchors, scores, empty, 0, [], reason)

    anchors: dict[str, Anchors] = {}
    for scale in scales:
        if scale in spec.anchors:
            anchors[scale] = Anchors(*map(float, spec.anchors[scale]), source="scale points")
        else:
            anchors[scale] = percentile_anchors(scores[scale])
    if len(scores) < 2:
        return skipped("fewer than 2 respondents have a score on every scale involved.")
    tied = [s for s, a in anchors.items() if not a.is_ordered()]
    if tied:
        return skipped(
            f"the percentile anchors of {', '.join(tied)} are not distinct, because many "
            "respondents share the same score. Set the anchors in scale points instead."
        )

    memberships = pd.DataFrame({s: calibrate(scores[s], anchors[s]) for s in scales})
    n_half = int(at_crossover(memberships, list(spec.conditions)).sum())
    if n_half:
        notes.append(
            f"{n_half} of {len(scores)} respondents have a membership of exactly 0.5 in at least "
            "one condition (their score equals the crossover anchor). They count in consistency "
            "and coverage but belong to no truth-table row, as in R's QCA package. Moving the "
            "crossover slightly off the observed scores avoids this."
        )
    results = necessity(memberships, spec.outcome, list(spec.conditions), spec.necessity_threshold)
    if warnings is not None:
        warnings.extend(notes)
    return FsqcaResults(
        spec, len(scores), n_excluded, anchors, scores, memberships, n_half, results
    )
