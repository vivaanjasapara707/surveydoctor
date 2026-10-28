"""fsQCA (fuzzy-set Qualitative Comparative Analysis).

fsQCA asks which combinations of conditions (here, scale scores) go with an outcome (another
scale score), using set relations rather than correlations (BLUEPRINT §7.14).

Part 1 (Stage 10A) turns scale scores into fuzzy set memberships and tests whether any
condition is necessary for the outcome:

* calibrate       - direct calibration (Ragin's logistic method), as in R's QCA::calibrate;
* percentile_anchors - the default anchors: 95th, 50th and 5th percentiles of the sample;
* necessity       - consistency, coverage and relevance of necessity for each condition and
                    its negation, as in QCA::pof(relation = "necessity").

Part 2 (Stage 10B) looks for combinations that are sufficient for the outcome:

* truth_table     - one row per combination of conditions, with case counts, consistency,
                    PRI and an outcome code, as in QCA::truthTable;
* minimize        - Boolean minimisation (Quine-McCluskey and a prime-implicant chart) into
                    the complex and parsimonious solutions, as in QCA::minimize;
* compare_runs    - reruns without flagged respondents and with shifted anchors, with each
                    solution path marked kept, missing or new.

§3 lists no Python library for fsQCA, so the calculations are implemented here and checked
against R's QCA package (tests/test_reference_r.py).

Limitations: memberships depend on the anchors, which are a modelling choice; set relations
in one sample are not causes; and Likert scale scores take few distinct values, so many
respondents can sit exactly at the crossover (membership 0.5, see :func:`at_crossover`).
"""

from __future__ import annotations

import math
import sys
from collections.abc import Iterable
from dataclasses import dataclass, field
from itertools import product
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

# Truth-table defaults (BLUEPRINT §7.14) [VERIFY with supervisor, verification_log.md item 17]:
# a row needs at least this many cases, this raw consistency and this PRI for outcome 1.
FREQUENCY_THRESHOLD = 1
CONSISTENCY_THRESHOLD = 0.80
PRI_THRESHOLD = 0.70

# QCA (via admisc::agteb) counts a value as reaching a threshold when value + tol > threshold,
# with tol = sqrt(machine epsilon), so that 0.8 computed as 0.79999999999 still passes.
THRESHOLD_TOLERANCE = math.sqrt(sys.float_info.epsilon)

# Calibration-sensitivity shifts (BLUEPRINT §7.14) [VERIFY with supervisor, item 20]. Each
# rerun shifts every scale at once: percentile anchors to the given percentiles, scale-point
# anchors by the given amounts (full, crossover, non).
SHIFTED_PERCENTILES: dict[str, tuple[float, float, float]] = {
    "crossover_lower": (95.0, 45.0, 5.0),
    "crossover_higher": (95.0, 55.0, 5.0),
    "outer_closer": (90.0, 50.0, 10.0),
}
SHIFTED_POINTS: dict[str, tuple[float, float, float]] = {
    "crossover_lower": (0.0, -0.5, 0.0),
    "crossover_higher": (0.0, 0.5, 0.0),
    "outer_closer": (-0.5, 0.0, 0.5),
}

ROBUSTNESS_CAVEAT = (
    "This shows sensitivity to exclusion choices. It does not prove which respondents "
    "should be excluded."
)
CALIBRATION_CAVEAT = (
    "This shows sensitivity to the calibration anchors. It does not show which anchors are right."
)

ALL_RESPONDENTS = "all"

AnchorSource = Literal["percentiles", "scale points"]
SolutionKind = Literal["complex", "parsimonious"]
PathStatus = Literal["kept", "missing", "new"]
CheckVerdict = Literal["same", "changed", "no solution"]


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
        frequency_threshold: Cases a truth-table row needs to count as observed (default 1).
        consistency_threshold: Raw consistency a row needs for outcome 1 (default 0.80).
        pri_threshold: PRI a row needs for outcome 1 (default 0.70).
    """

    outcome: str
    conditions: tuple[str, ...]
    anchors: dict[str, tuple[float, float, float]] = field(default_factory=dict)
    necessity_threshold: float = NECESSITY_THRESHOLD
    frequency_threshold: int = FREQUENCY_THRESHOLD
    consistency_threshold: float = CONSISTENCY_THRESHOLD
    pri_threshold: float = PRI_THRESHOLD

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


Literals = tuple[tuple[str, bool], ...]  # (condition, present) pairs, in condition order


def expression(literals: Literals) -> str:
    """QCA notation: "~" for absence (low), "*" for AND, e.g. "~Openness*Extraversion".
    A path without conditions (every configuration is sufficient) is written "1"."""
    if not literals:
        return "1"
    return "*".join(name if present else f"~{name}" for name, present in literals)


@dataclass
class Path:
    """One path (prime implicant) of a solution: a combination sufficient for the outcome.

    Attributes:
        literals: The conditions in the path; present=False means the condition is absent
            (low membership, written with "~").
        consistency: Σ min(P, Y) / Σ P, where P is membership in the path. Near 1: cases in
            the path almost always show the outcome.
        raw_coverage: Σ min(P, Y) / Σ Y: how much of the outcome the path accounts for.
        unique_coverage: Coverage lost if the path is removed from its model: what only this
            path accounts for. Low values are normal when paths overlap.
    """

    literals: Literals
    consistency: float
    raw_coverage: float
    unique_coverage: float

    @property
    def expression(self) -> str:
        return expression(self.literals)


@dataclass
class Model:
    """One solution model: paths joined by OR (written "+").

    Attributes:
        name: "M1", "M2", ... (several models when equally short alternatives exist).
        paths: The model's paths.
        consistency: Consistency of the model as a whole (membership = max over paths).
        coverage: Coverage of the model as a whole.
    """

    name: str
    paths: list[Path]
    consistency: float
    coverage: float

    @property
    def expression(self) -> str:
        return " + ".join(p.expression for p in self.paths)


@dataclass
class Solution:
    """The complex or the parsimonious solution.

    The complex solution uses only the truth-table rows with outcome 1. The parsimonious
    solution may also use logical remainders (rows without enough cases) where that gives
    shorter paths, so it rests on assumptions about combinations nobody in the sample had.

    Attributes:
        kind: "complex" or "parsimonious".
        models: Equally minimal models (M1, M2, ...); empty when no truth-table row has
            outcome 1 ("no solution").
    """

    kind: SolutionKind
    models: list[Model]

    @property
    def has_solution(self) -> bool:
        return bool(self.models)

    def path_expressions(self) -> list[str]:
        """Every distinct path across the models, in order of first appearance."""
        seen: dict[str, None] = {}
        for model in self.models:
            for path in model.paths:
                seen.setdefault(path.expression, None)
        return list(seen)


@dataclass
class FsqcaRun:
    """One truth table and its two solutions, for one set of respondents and anchors.

    Attributes:
        label: "all", a flag variant (e.g. "any_rule") or an anchor shift (e.g.
            "crossover_lower").
        n: Respondents in this run.
        n_excluded: Respondents removed from the full fsQCA sample (flag variants only).
        anchors: Anchors used.
        n_at_crossover: Respondents at exactly 0.5 in at least one condition (in no row).
        truth_table: Every row (2^k), indexed by row number 1..2^k as in QCA: the condition
            columns (1/0), ``n``, ``consistency``, ``pri`` and ``outcome`` ("1", "0", or "?"
            for a logical remainder).
        case_rows: Row number of each respondent, 0 for respondents at exactly 0.5.
        complex: The complex solution.
        parsimonious: The parsimonious solution.
        skipped_reason: Why this run could not be computed (None when it ran).
    """

    label: str
    n: int
    n_excluded: int
    anchors: dict[str, Anchors]
    n_at_crossover: int = 0
    truth_table: pd.DataFrame | None = None
    case_rows: pd.Series | None = None
    complex: Solution | None = None
    parsimonious: Solution | None = None
    skipped_reason: str | None = None

    @property
    def n_positive_rows(self) -> int:
        if self.truth_table is None:
            return 0
        return int((self.truth_table["outcome"] == "1").sum())

    @property
    def has_solution(self) -> bool:
        return self.complex is not None and self.complex.has_solution


@dataclass
class RunComparison:
    """One rerun compared with the main run.

    Attributes:
        run: The rerun.
        paths: Solution kind -> path expression -> "kept" (in both), "missing" (only in the
            main run) or "new" (only in the rerun). Empty if the rerun was skipped.
        changed: True if any path is missing or new.
    """

    run: FsqcaRun
    paths: dict[SolutionKind, dict[str, PathStatus]]
    changed: bool


@dataclass
class FsqcaCheck:
    """A set of reruns and the verdict, for the flag variants or the anchor shifts.

    Attributes:
        kind: "robustness" (flag variants) or "calibration" (shifted anchors).
        comparisons: One per rerun, in order.
        verdict: "same" (identical paths in every rerun), "changed" (a path added or
            removed in a rerun) or "no solution" (no truth-table row has outcome 1 in the
            main run or in a rerun). None if the main run did not run.
        named: The runs behind the verdict: those that changed, or those without a solution.
        caveat: The fixed sentence that always goes with the verdict.
    """

    kind: Literal["robustness", "calibration"]
    comparisons: list[RunComparison]
    verdict: CheckVerdict | None
    named: list[str]
    caveat: str


@dataclass
class FsqcaResults:
    """fsQCA results.

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
        main: Truth table and solutions on every respondent used (None if skipped).
        robustness: Reruns without each flag variant, or None if no variants were given.
        calibration: Reruns with shifted anchors (None if skipped).
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
    main: FsqcaRun | None = None
    robustness: FsqcaCheck | None = None
    calibration: FsqcaCheck | None = None

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
    if isinstance(spec.frequency_threshold, bool) or not (
        isinstance(spec.frequency_threshold, int) and spec.frequency_threshold >= 1
    ):
        raise ValueError("The frequency threshold must be a whole number of cases, at least 1.")
    if not 0.5 < spec.consistency_threshold <= 1:
        raise ValueError("The consistency threshold must be above 0.5 and at most 1.")
    if not 0 <= spec.pri_threshold <= 1:
        raise ValueError("The PRI threshold must be between 0 and 1.")


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


# --- Truth table --------------------------------------------------------------------------


def _reaches(value: float, threshold: float) -> bool:
    """value >= threshold, allowing for rounding as QCA does (THRESHOLD_TOLERANCE)."""
    return bool(value + THRESHOLD_TOLERANCE > threshold)


def row_configs(k: int) -> np.ndarray:
    """All 2^k combinations of k conditions (1 = present, 0 = absent), one per row.

    Row i (0-based) is i in binary with the first condition as the most significant bit, so
    QCA's row number is i + 1 (row 1 = every condition absent).
    """
    return np.array(list(product((0, 1), repeat=k)), dtype=int)


def row_memberships(memberships: pd.DataFrame, conditions: list[str]) -> np.ndarray:
    """Membership of every case in every truth-table row: an array of shape (cases, 2^k).

    A case's membership in a row is the minimum over conditions of X (condition present in
    the row) or 1 − X (absent).
    """
    x = memberships[conditions].to_numpy(dtype=float)
    configs = row_configs(len(conditions)).astype(bool)
    stacked = np.where(configs[None, :, :], x[:, None, :], 1 - x[:, None, :])
    return stacked.min(axis=2)


def case_rows(memberships: pd.DataFrame, conditions: list[str]) -> pd.Series:
    """The truth-table row (1..2^k) each case belongs to: the row where its membership is
    above 0.5. Cases with any condition at exactly 0.5 belong to no row and get 0, as in
    QCA (see :func:`at_crossover`)."""
    x = memberships[conditions].to_numpy(dtype=float)
    weights = 2 ** np.arange(len(conditions) - 1, -1, -1)
    rows = (x > 0.5).astype(int) @ weights + 1
    rows[at_crossover(memberships, conditions).to_numpy()] = 0
    return pd.Series(rows, index=memberships.index, name="row")


def truth_table(
    memberships: pd.DataFrame,
    outcome: str,
    conditions: list[str],
    frequency_threshold: int = FREQUENCY_THRESHOLD,
    consistency_threshold: float = CONSISTENCY_THRESHOLD,
    pri_threshold: float = PRI_THRESHOLD,
) -> tuple[pd.DataFrame, pd.Series]:
    """The truth table, as in QCA::truthTable(complete = TRUE).

    For each row R (a combination of conditions present or absent):

    * n: cases whose membership in R is above 0.5;
    * consistency = Σ min(R, Y) / Σ R: near 1 when cases in the row show the outcome;
    * PRI = (Σ min(R, Y) − Σ min(R, Y, 1 − Y)) / (Σ R − Σ min(R, Y, 1 − Y)): consistency
      after removing what R also shares with the absence of the outcome. Low PRI with high
      consistency warns that the row is also consistent with "not Y".
    * outcome: "?" (logical remainder) if n is below the frequency threshold; otherwise "1"
      if consistency and PRI both reach their thresholds, else "0".

    Every case counts in the consistency and PRI sums, including cases at exactly 0.5 that
    belong to no row (QCA's convention). Returns the table (indexed by row number) and
    each case's row (:func:`case_rows`).
    """
    r = row_memberships(memberships, conditions)
    y = memberships[outcome].to_numpy(dtype=float)[:, None]
    both = np.minimum(r, y).sum(axis=0)
    with_not_y = np.minimum(np.minimum(r, y), 1 - y).sum(axis=0)
    total = r.sum(axis=0)
    rows = case_rows(memberships, conditions)
    n_rows = 2 ** len(conditions)
    counts = np.bincount(rows.to_numpy(), minlength=n_rows + 1)[1:]
    table = pd.DataFrame(row_configs(len(conditions)), columns=conditions)
    table.index = pd.RangeIndex(1, n_rows + 1, name="row")
    table["n"] = counts
    table["consistency"] = [_ratio(b, t) for b, t in zip(both, total, strict=True)]
    table["pri"] = [_ratio(b - w, t - w) for b, w, t in zip(both, with_not_y, total, strict=True)]
    table["outcome"] = [
        "?" if n < frequency_threshold
        else "1" if _reaches(c, consistency_threshold) and _reaches(p, pri_threshold)
        else "0"
        for n, c, p in zip(table["n"], table["consistency"], table["pri"], strict=True)
    ]  # fmt: skip
    return table, rows


# --- Boolean minimisation -----------------------------------------------------------------

Implicant = tuple[int | None, ...]  # per condition: 1 present, 0 absent, None not in the path


def prime_implicants(minterms: Iterable[int], dont_cares: Iterable[int], k: int) -> list[Implicant]:
    """Prime implicants by Quine-McCluskey: merge terms that differ in one condition until no
    more merges are possible. Rows are 0-based (row number − 1). Only primes that cover at
    least one of ``minterms`` are returned."""
    on = set(minterms)
    configs = row_configs(k)
    current = {tuple(int(v) for v in configs[m]) for m in on | set(dont_cares)}
    primes: set[Implicant] = set()
    while current:
        merged: set[Implicant] = set()
        used: set[Implicant] = set()
        for term in current:
            for j, value in enumerate(term):
                if value is None:
                    continue
                partner = term[:j] + (1 - value,) + term[j + 1 :]
                if partner in current:
                    merged.add(term[:j] + (None,) + term[j + 1 :])
                    used.add(term)
        primes |= current - used
        current = merged
    return sorted((p for p in primes if _covered(p, on, configs)), key=_implicant_order)


def _covered(implicant: Implicant, rows: set[int], configs: np.ndarray) -> set[int]:
    """The rows (0-based) among ``rows`` that the implicant covers."""
    return {
        r for r in rows
        if all(v is None or configs[r][j] == v for j, v in enumerate(implicant))
    }  # fmt: skip


def _implicant_order(implicant: Implicant) -> tuple:
    """Shorter paths first, then by condition order, present before absent."""
    used = sum(v is not None for v in implicant)
    return (used, [(0, 1 - v) if v is not None else (1, 0) for v in implicant])


def minimal_covers(cover_sets: list[set[int]], minterms: set[int]) -> list[tuple[int, ...]]:
    """Every smallest set of implicants that together cover all ``minterms``.

    Solves the prime-implicant chart exactly: a depth-first search that always branches on
    the uncovered row with the fewest implicants covering it, and stops at the size of the
    smallest cover found so far. Like QCA::minimize (all.sol = FALSE), it returns every
    cover with the minimum number of implicants, as tuples of indices into ``cover_sets``.
    """
    covering = {m: [i for i, s in enumerate(cover_sets) if m in s] for m in minterms}
    best = math.inf
    found: set[frozenset[int]] = set()
    seen: set[frozenset[int]] = set()

    def search(chosen: frozenset[int], uncovered: frozenset[int]) -> None:
        nonlocal best
        if chosen in seen or len(chosen) > best:
            return
        seen.add(chosen)
        if not uncovered:
            if len(chosen) < best:
                best = len(chosen)
                found.clear()
            found.add(chosen)
            return
        if len(chosen) == best:
            return
        row = min(uncovered, key=lambda m: (len(covering[m]), m))
        for i in covering[row]:
            search(chosen | {i}, uncovered - cover_sets[i])

    search(frozenset(), frozenset(minterms))
    return sorted(tuple(sorted(c)) for c in found)


def minimize(
    table: pd.DataFrame, conditions: list[str], kind: SolutionKind
) -> list[list[Literals]]:
    """Boolean minimisation of a truth table into the complex or parsimonious solution.

    The rows with outcome "1" must be covered. The complex solution may use only those rows;
    the parsimonious solution may also use logical remainders ("?") as "don't care" rows.
    Rows with outcome "0" are never covered. Returns the models (several when equally short
    alternatives exist), each a list of paths, or [] when no row has outcome "1".
    """
    positive = {int(r) - 1 for r in table.index[table["outcome"] == "1"]}
    if not positive:
        return []
    remainders = (
        {int(r) - 1 for r in table.index[table["outcome"] == "?"]}
        if kind == "parsimonious"
        else set()
    )
    k = len(conditions)
    primes = prime_implicants(positive, remainders, k)
    configs = row_configs(k)
    cover_sets = [_covered(p, positive, configs) for p in primes]
    models = [
        sorted((primes[i] for i in cover), key=_implicant_order)
        for cover in minimal_covers(cover_sets, positive)
    ]
    models.sort(key=lambda m: [_implicant_order(p) for p in m])
    return [[_literals(p, conditions) for p in model] for model in models]


def _literals(implicant: Implicant, conditions: list[str]) -> Literals:
    return tuple((c, v == 1) for c, v in zip(conditions, implicant, strict=True) if v is not None)


def path_membership(memberships: pd.DataFrame, literals: Literals) -> np.ndarray:
    """Each case's membership in a path: the minimum over its conditions of X or 1 − X."""
    values = np.ones(len(memberships))
    for name, present in literals:
        x = memberships[name].to_numpy(dtype=float)
        values = np.minimum(values, x if present else 1 - x)
    return values


def model_fit(memberships: pd.DataFrame, outcome: str, paths: list[Literals], name: str) -> Model:
    """A model with the fit of each path and of the whole model, as in QCA::minimize.

    Unique coverage of a path is the model's coverage minus the coverage of the model
    without that path, within this model (QCA's per-model covU).
    """
    y = memberships[outcome].to_numpy(dtype=float)
    sum_y = y.sum()
    members = [path_membership(memberships, p) for p in paths]

    def coverage_of(indices: list[int]) -> float:
        if not indices:
            return 0.0
        union = np.max([members[i] for i in indices], axis=0)
        return _ratio(np.minimum(union, y).sum(), sum_y)

    union = np.max(members, axis=0)
    model_coverage = coverage_of(list(range(len(paths))))
    fitted = []
    for i, (literals, p) in enumerate(zip(paths, members, strict=True)):
        both = np.minimum(p, y).sum()
        others = [j for j in range(len(paths)) if j != i]
        fitted.append(
            Path(
                literals=literals,
                consistency=_ratio(both, p.sum()),
                raw_coverage=_ratio(both, sum_y),
                unique_coverage=model_coverage - coverage_of(others),
            )
        )
    return Model(
        name=name,
        paths=fitted,
        consistency=_ratio(np.minimum(union, y).sum(), union.sum()),
        coverage=model_coverage,
    )


def solve(
    memberships: pd.DataFrame,
    table: pd.DataFrame,
    outcome: str,
    conditions: list[str],
    kind: SolutionKind,
) -> Solution:
    """The complex or parsimonious solution with fit measures for every model and path."""
    models = minimize(table, conditions, kind)
    return Solution(
        kind,
        [model_fit(memberships, outcome, paths, f"M{i}") for i, paths in enumerate(models, 1)],
    )


def run(
    memberships: pd.DataFrame,
    spec: FsqcaSpec,
    anchors: dict[str, Anchors],
    label: str = ALL_RESPONDENTS,
    n_excluded: int = 0,
) -> FsqcaRun:
    """Truth table and both solutions for one set of respondents and anchors."""
    conditions = list(spec.conditions)
    if len(memberships) < 2:
        return FsqcaRun(
            label, len(memberships), n_excluded, anchors,
            skipped_reason="fewer than 2 respondents are left.",
        )  # fmt: skip
    table, rows = truth_table(
        memberships, spec.outcome, conditions,
        spec.frequency_threshold, spec.consistency_threshold, spec.pri_threshold,
    )  # fmt: skip
    return FsqcaRun(
        label=label,
        n=len(memberships),
        n_excluded=n_excluded,
        anchors=anchors,
        n_at_crossover=int((rows == 0).sum()),
        truth_table=table,
        case_rows=rows,
        complex=solve(memberships, table, spec.outcome, conditions, "complex"),
        parsimonious=solve(memberships, table, spec.outcome, conditions, "parsimonious"),
    )


# --- Robustness and calibration sensitivity -----------------------------------------------


def path_changes(main: Solution, other: Solution) -> dict[str, PathStatus]:
    """Each path of either solution: "kept" (in both), "missing" (main only), "new" (other
    only). Paths are compared across all models (M1, M2, ...) of each solution."""
    before, after = main.path_expressions(), other.path_expressions()
    changes: dict[str, PathStatus] = {p: "kept" if p in after else "missing" for p in before}
    changes.update({p: "new" for p in after if p not in before})
    return changes


def compare_runs(
    kind: Literal["robustness", "calibration"], main: FsqcaRun, reruns: list[FsqcaRun]
) -> FsqcaCheck:
    """Compare each rerun's solution paths with the main run's, and give the verdict.

    * "no solution": no truth-table row has outcome 1 in the main run or in a rerun, so
      there are no paths to compare there; names those runs ("all" for the main run).
    * "changed": a path is missing or new in at least one rerun; names those reruns.
    * "same": identical paths in every rerun.

    Skipped reruns are listed but do not count towards the verdict; if every rerun was
    skipped, the verdict is None.
    """
    caveat = ROBUSTNESS_CAVEAT if kind == "robustness" else CALIBRATION_CAVEAT
    comparisons = []
    for rerun in reruns:
        if rerun.skipped_reason is not None:
            comparisons.append(RunComparison(rerun, {}, changed=False))
            continue
        paths = {
            "complex": path_changes(main.complex, rerun.complex),
            "parsimonious": path_changes(main.parsimonious, rerun.parsimonious),
        }
        changed = any(s != "kept" for statuses in paths.values() for s in statuses.values())
        comparisons.append(RunComparison(rerun, paths, changed))
    computed = [c for c in comparisons if c.run.skipped_reason is None]
    if reruns and not computed:
        return FsqcaCheck(kind, comparisons, None, [], caveat)
    without = [r.label for r in [main] + [c.run for c in computed] if not r.has_solution]
    if without:
        return FsqcaCheck(kind, comparisons, "no solution", without, caveat)
    changed = [c.run.label for c in computed if c.changed]
    if changed:
        return FsqcaCheck(kind, comparisons, "changed", changed, caveat)
    return FsqcaCheck(kind, comparisons, "same", [], caveat)


def shifted_anchors(
    anchors: dict[str, Anchors], scores: pd.DataFrame, shift: str
) -> dict[str, Anchors]:
    """The anchors of every scale shifted for one calibration-sensitivity rerun.

    Percentile anchors are recomputed at :data:`SHIFTED_PERCENTILES` [shift]; scale-point
    anchors move by :data:`SHIFTED_POINTS` [shift]. The result may be out of order (check
    :meth:`Anchors.is_ordered`).
    """
    shifted = {}
    for scale, a in anchors.items():
        if a.source == "percentiles":
            shifted[scale] = percentile_anchors(scores[scale], SHIFTED_PERCENTILES[shift])
        else:
            d_full, d_cross, d_non = SHIFTED_POINTS[shift]
            shifted[scale] = Anchors(
                a.full + d_full, a.crossover + d_cross, a.non + d_non, source="scale points"
            )
    return shifted


def robustness_runs(
    memberships: pd.DataFrame, spec: FsqcaSpec, anchors: dict[str, Anchors],
    exclusions: dict[str, pd.Series],
) -> list[FsqcaRun]:  # fmt: skip
    """Reruns without each flag variant's respondents. Anchors stay fixed in scale points,
    so each respondent keeps the same memberships and only the set of respondents changes."""
    reruns = []
    for name, exclude in exclusions.items():
        drop = exclude.reindex(memberships.index, fill_value=False).astype(bool)
        reruns.append(run(memberships[~drop], spec, anchors, name, int(drop.sum())))
    return reruns


def calibration_runs(
    scores: pd.DataFrame, spec: FsqcaSpec, anchors: dict[str, Anchors]
) -> list[FsqcaRun]:
    """Reruns on every respondent with the anchors shifted (see :func:`shifted_anchors`)."""
    reruns = []
    for shift in SHIFTED_PERCENTILES:
        new = shifted_anchors(anchors, scores, shift)
        unordered = [s for s, a in new.items() if not a.is_ordered()]
        if unordered:
            reason = (
                f"the shifted anchors of {', '.join(unordered)} are not in order (full "
                "membership above the crossover above full non-membership)."
            )
            reruns.append(FsqcaRun(shift, len(scores), 0, new, skipped_reason=reason))
            continue
        memberships = pd.DataFrame({s: calibrate(scores[s], new[s]) for s in scores.columns})
        reruns.append(run(memberships, spec, new, shift))
    return reruns


# --- The analysis -------------------------------------------------------------------------


def fsqca(
    prepared: PreparedData,
    schema: SurveySchema,
    spec: FsqcaSpec,
    warnings: list[str] | None = None,
    exclusions: dict[str, pd.Series] | None = None,
) -> FsqcaResults:
    """The full fsQCA: calibration, necessity, truth table, complex and parsimonious
    solutions, the robustness check and the calibration sensitivity check.

    Scale scores are the mean of a scale's reverse-scored items for respondents who answered
    at least 80% of them (:func:`surveydoctor.io.scale_scores`). Respondents without a score
    on every scale involved are left out, and the count is reported.

    Args:
        prepared: Output of :func:`surveydoctor.io.prepare_data`.
        schema: The survey schema.
        spec: Outcome, conditions, anchors and thresholds.
        warnings: Optional list that receives plain-English notes.
        exclusions: Flag variant name -> boolean Series (True = exclude), as returned by
            :func:`surveydoctor.flagging.flag_variants`. None skips the robustness check.

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
    main = run(memberships, spec, anchors)
    if not main.has_solution:
        notes.append(
            "fsQCA found no solution: no truth-table row reached the thresholds (at least "
            f"{spec.frequency_threshold} case{'s' if spec.frequency_threshold != 1 else ''}, "
            f"consistency {spec.consistency_threshold:.2f} and PRI {spec.pri_threshold:.2f})."
        )
    robustness_check = (
        compare_runs("robustness", main, robustness_runs(memberships, spec, anchors, exclusions))
        if exclusions is not None
        else None
    )
    calibration_check = compare_runs("calibration", main, calibration_runs(scores, spec, anchors))
    for check in (robustness_check, calibration_check):
        if check is None:
            continue
        for c in check.comparisons:
            if c.run.skipped_reason is not None:
                notes.append(f"fsQCA {check.kind} rerun '{c.run.label}' was not run: "
                             f"{c.run.skipped_reason}")  # fmt: skip
    if warnings is not None:
        warnings.extend(notes)
    return FsqcaResults(
        spec, len(scores), n_excluded, anchors, scores, memberships, n_half, results,
        main=main, robustness=robustness_check, calibration=calibration_check,
    )  # fmt: skip
