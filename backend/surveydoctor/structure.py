"""Factor structure: whether the questions group the way the researcher intended.

On reverse-scored answers of the analysed items (all items by default), for respondents
who answered all of them (listwise deletion, with the count reported):

* kmo               - Kaiser-Meyer-Olkin sampling adequacy, overall and per item;
* bartlett          - Bartlett's test that the items are correlated at all;
* parallel_analysis - Horn's parallel analysis: how many factors stand out from noise;
* efa               - exploratory factor analysis (minres, oblimin rotation);
* loading_flags     - items that load weakly on every factor, or on two factors;
* scale_alignment   - whether each declared scale's items share one factor.

Exploratory factor analysis (EFA) models the correlations between answers as coming from
a few unobserved common factors plus item-specific noise. It differs from principal
component analysis (PCA), which only summarises total variance. Parallel analysis uses
PCA-style eigenvalues to choose how many factors to extract; the EFA then estimates them.

All correlations are Pearson correlations, which treat ordinal answers as continuous.
Factor results from small samples, or from data with little shared variance, can change
noticeably with a different sample.
"""

from __future__ import annotations

import warnings as py_warnings
from dataclasses import dataclass, field
from typing import Literal

import numpy as np
import pandas as pd
from factor_analyzer import FactorAnalyzer, calculate_bartlett_sphericity, calculate_kmo
from scipy.optimize import linear_sum_assignment

from surveydoctor.io import PreparedData
from surveydoctor.reliability import complete_cases
from surveydoctor.schema import SurveySchema

# Fewer items than this cannot show a factor structure.
MIN_ITEMS_STRUCTURE = 3

# Loading-flag thresholds (BLUEPRINT §7.4).
WEAK_LOADING = 0.30
CROSS_LOADING = 0.30

# Warning thresholds (BLUEPRINT §7.4).
MIN_N_STABLE = 200
MIN_N_PER_ITEM = 5
MIN_KMO = 0.60

# Parallel-analysis settings (BLUEPRINT §7.4).
PA_ITERATIONS = 100
PA_PERCENTILE = 95.0
PA_SEED = 42

PEARSON_NOTE = (
    "Factor analysis uses Pearson correlations, which treat ordinal answers (such as 1-5 "
    "ratings) as continuous. Polychoric correlations are planned for version 2."
)

# factor_analyzer keeps each uniqueness within (0.005, 1). A communality at 1 − 0.005 means
# the fit wanted an item to be explained completely (a Heywood case).
_UNIQUENESS_LOWER_BOUND = 0.005

# Below this variance a column is treated as constant.
_ZERO_VARIANCE = 1e-12

# A correlation matrix whose smallest eigenvalue is below this is treated as singular.
_SINGULAR_EIGENVALUE = 1e-10

# Item pairs correlating at least this strongly are named as near-duplicates.
_DUPLICATE_R = 0.999


@dataclass
class KMOResult:
    """Kaiser-Meyer-Olkin sampling adequacy (see :func:`kmo`)."""

    overall: float
    per_item: pd.Series


@dataclass
class BartlettResult:
    """Bartlett's test of sphericity (see :func:`bartlett`)."""

    chi_square: float
    df: int
    p_value: float


@dataclass
class ParallelAnalysis:
    """Horn's parallel analysis (see :func:`parallel_analysis`).

    Attributes:
        scree: One row per position 1..k: ``observed`` eigenvalue of the data's correlation
            matrix and ``threshold``, the chosen percentile of eigenvalues from random data.
        n_suggested: Number of leading observed eigenvalues above their threshold.
        n_kaiser: Number of observed eigenvalues above 1 (Kaiser's rule, for contrast).
        n_iterations: Random datasets generated.
        percentile: Percentile of the random eigenvalues used as the threshold.
        seed: Seed of the random number generator.
    """

    scree: pd.DataFrame
    n_suggested: int
    n_kaiser: int
    n_iterations: int
    percentile: float
    seed: int


@dataclass
class EFAResult:
    """Exploratory factor analysis results (see :func:`efa`).

    Attributes:
        n_factors: Number of factors extracted.
        loadings: Pattern loadings, items × factors ("F1", "F2", ... in order of variance
            explained). Each factor is signed so that its loadings sum to a positive number.
        communalities: Share of each item's variance explained by the factors, diag(LΦLᵀ).
        factor_correlations: Factor correlation matrix Φ (identity for one factor).
        item_flags: Per item: primary factor, its loading, weak and cross-loading flags
            (see :func:`loading_flags`).
    """

    n_factors: int
    loadings: pd.DataFrame
    communalities: pd.Series
    factor_correlations: pd.DataFrame
    item_flags: pd.DataFrame


@dataclass
class ScaleAlignment:
    """How one declared scale lines up with the EFA factors (see :func:`scale_alignment`).

    Attributes:
        scale: Scale name.
        items: The scale's analysed items.
        factor: The factor most of its items load on most strongly.
        n_matching: Items whose primary factor is ``factor``.
        share_matching: ``n_matching`` divided by the number of analysed items.
        item_factors: Item -> its primary factor.
        shared_with: Other scales whose main factor is the same one.
    """

    scale: str
    items: list[str]
    factor: str
    n_matching: int
    share_matching: float
    item_factors: dict[str, str]
    shared_with: list[str] = field(default_factory=list)


@dataclass
class StructureResults:
    """Factor-structure results for the analysed items.

    Attributes:
        items: The analysed items.
        n_used: Respondents who answered every analysed item.
        n_excluded: Respondents left out because of at least one missing answer.
        skipped_reason: Why nothing could be computed (None when the analysis ran).
        kmo, bartlett, parallel: Results, or None when skipped.
        n_factors: Factors requested for the EFA (None when the EFA was not run).
        n_factors_source: "parallel analysis" or "user".
        efa: EFA results, or None when the EFA was not run (the warnings say why).
        alignment: Scale name -> :class:`ScaleAlignment` for scales with 2+ analysed items.
    """

    items: list[str]
    n_used: int
    n_excluded: int
    skipped_reason: str | None
    kmo: KMOResult | None
    bartlett: BartlettResult | None
    parallel: ParallelAnalysis | None
    n_factors: int | None
    n_factors_source: Literal["parallel analysis", "user"]
    efa: EFAResult | None
    alignment: dict[str, ScaleAlignment]


def _warn(warnings: list[str] | None, message: str) -> None:
    if warnings is not None:
        warnings.append(message)


def _respondents(n: int) -> str:
    return f"{n} respondent{'' if n == 1 else 's'}"


def _correlation(data: pd.DataFrame) -> np.ndarray:
    return np.corrcoef(data.to_numpy(dtype=float), rowvar=False)


def structure_problem(data: pd.DataFrame) -> str | None:
    """Why factor-structure statistics cannot be computed on these answers, or None.

    Checks, in order: at least 3 items, more respondents than items, no item with a single
    answer for everyone, and a correlation matrix that is not singular (no question is an
    exact or near-exact copy, or combination, of others).

    Args:
        data: Complete cases only (respondents × items).

    Returns:
        A plain-English reason, or None if the data can be analysed.
    """
    n, k = data.shape
    if k < MIN_ITEMS_STRUCTURE:
        return (
            f"Factor structure was not analysed: it needs at least {MIN_ITEMS_STRUCTURE} "
            f"questions, and {k} were selected."
        )
    if n <= k:
        return (
            f"Factor structure was not analysed: it needs more respondents with complete "
            f"answers ({n}) than questions ({k})."
        )
    constant = [item for item in data.columns if data[item].var(ddof=1) <= _ZERO_VARIANCE]
    if constant:
        return (
            "Factor structure was not analysed: every respondent gave the same answer to "
            f"{', '.join(constant)}, so it has no variance to share. Leave it out of the "
            "analysis."
        )
    r = _correlation(data)
    if np.linalg.eigvalsh(r).min() < _SINGULAR_EIGENVALUE:
        items = list(data.columns)
        pairs = [
            f"{items[i]} and {items[j]}"
            for i in range(k)
            for j in range(i + 1, k)
            if abs(r[i, j]) >= _DUPLICATE_R
        ]
        if pairs:
            return (
                "Factor structure was not analysed: some questions have identical or nearly "
                f"identical answers ({'; '.join(pairs)}). Check whether a question was "
                "exported twice, and leave one copy out of the analysis."
            )
        return (
            "Factor structure was not analysed: the answers to some questions can be "
            "predicted exactly from the answers to others (for example a total-score "
            "column), so the correlations cannot be used. Leave such columns out."
        )
    return None


# --------------------------------------------------------------------------------------
# Suitability: KMO and Bartlett
# --------------------------------------------------------------------------------------


def kmo(data: pd.DataFrame) -> KMOResult:
    """Kaiser-Meyer-Olkin measure of sampling adequacy (via factor_analyzer).

    Compares the items' correlations with their partial correlations (the correlation of
    two items after removing what all other items explain). If items share common factors,
    partial correlations are small relative to plain correlations and KMO approaches 1.
    Per-item values (MSA) show which items share little with the rest.

    Direction: lower is worse. Below 0.60 is commonly treated as unsuitable for factor
    analysis; this is a rule of thumb, not a test.

    Limitations: uses Pearson correlations on ordinal answers. With only 2 items the
    partial correlation equals the plain correlation, so KMO is always 0.5.

    Args:
        data: Complete cases only (respondents × items), with no constant item.
    """
    with py_warnings.catch_warnings():
        # With many items the covariance determinant is tiny even when the matrix is fine,
        # and factor_analyzer then warns that it used a pseudo-inverse (identical to the
        # inverse for a non-singular matrix). Real singularity is caught by
        # structure_problem.
        py_warnings.simplefilter("ignore")
        per_item, overall = calculate_kmo(data.to_numpy(dtype=float))
    return KMOResult(
        overall=float(overall), per_item=pd.Series(per_item, index=data.columns, name="msa")
    )


def bartlett(data: pd.DataFrame) -> BartlettResult:
    """Bartlett's test of sphericity (via factor_analyzer).

    Tests whether the items' correlation matrix could be an identity matrix, i.e. whether
    the items are uncorrelated in the population. χ² = −(n − 1 − (2k + 5)/6) × ln|R| with
    k(k − 1)/2 degrees of freedom.

    Direction: a large p-value is bad news (no evidence the items correlate at all, so
    there is nothing to factor). A small p-value is necessary but far from sufficient: with
    a few hundred respondents almost any survey passes.

    Limitations: assumes multivariate normal data; very sensitive to sample size.

    Args:
        data: Complete cases only (respondents × items), with a non-singular correlation
            matrix (see :func:`structure_problem`).
    """
    chi_square, p_value = calculate_bartlett_sphericity(data.to_numpy(dtype=float))
    k = data.shape[1]
    return BartlettResult(chi_square=float(chi_square), df=k * (k - 1) // 2, p_value=float(p_value))


# --------------------------------------------------------------------------------------
# Number of factors: parallel analysis
# --------------------------------------------------------------------------------------


def eigenvalues(data: pd.DataFrame) -> np.ndarray:
    """Eigenvalues of the items' Pearson correlation matrix, largest first.

    Each eigenvalue is the variance captured by one principal component; they sum to the
    number of items. Used for the scree plot and parallel analysis.
    """
    return np.linalg.eigvalsh(_correlation(data))[::-1]


def parallel_analysis(
    data: pd.DataFrame,
    n_iterations: int = PA_ITERATIONS,
    percentile: float = PA_PERCENTILE,
    seed: int = PA_SEED,
) -> ParallelAnalysis:
    """Horn's parallel analysis: how many factors are stronger than random noise.

    Generates ``n_iterations`` datasets of independent standard-normal values with the
    same number of respondents and items, and takes the ``percentile`` of their correlation
    eigenvalues at each position (1st largest, 2nd largest, ...). Even pure noise produces
    some eigenvalues above 1, so this is a fairer bar than Kaiser's "eigenvalue > 1" rule.
    The suggested number of factors is the count of leading observed eigenvalues above
    their threshold (counting stops at the first one that is not).

    Direction: not good or bad; more factors means more distinct groups of questions.

    Limitations: uses PCA eigenvalues (total variance) on Pearson correlations of ordinal
    answers. With very large samples, minor factors can pass the bar; with small samples,
    real factors can miss it. Results depend slightly on the random seed (fixed at 42 by
    default, so they are reproducible). Kaiser's count (``n_kaiser``) is reported for
    contrast only; it tends to suggest too many factors.

    Args:
        data: Complete cases only (respondents × items), with no constant item.
        n_iterations: Number of random datasets.
        percentile: Percentile of the random eigenvalues used as the threshold (0-100).
        seed: Seed for numpy's default random generator.
    """
    n, k = data.shape
    rng = np.random.default_rng(seed)
    random_eigs = np.empty((n_iterations, k))
    for i in range(n_iterations):
        noise = rng.standard_normal((n, k))
        random_eigs[i] = np.linalg.eigvalsh(np.corrcoef(noise, rowvar=False))[::-1]
    threshold = np.percentile(random_eigs, percentile, axis=0)
    observed = eigenvalues(data)
    above = observed > threshold
    n_suggested = k if above.all() else int(np.argmin(above))
    scree = pd.DataFrame(
        {"observed": observed, "threshold": threshold},
        index=pd.RangeIndex(1, k + 1, name="position"),
    )
    return ParallelAnalysis(
        scree=scree,
        n_suggested=n_suggested,
        n_kaiser=int((observed > 1).sum()),
        n_iterations=n_iterations,
        percentile=percentile,
        seed=seed,
    )


# --------------------------------------------------------------------------------------
# Exploratory factor analysis
# --------------------------------------------------------------------------------------


def factor_names(n_factors: int) -> list[str]:
    """Labels F1..Fn used for factors, in order of variance explained."""
    return [f"F{i + 1}" for i in range(n_factors)]


def loading_flags(loadings: pd.DataFrame) -> pd.DataFrame:
    """Per item: its primary factor and whether it loads weakly or on two factors.

    An item's primary factor is the one with the largest absolute loading. An item is
    ``weak`` if even that loading is below 0.30 in absolute value: no factor explains it
    well. It is ``cross_loading`` if its second-largest absolute loading is 0.30 or more:
    it seems to measure two things.

    Direction: weak and cross-loading items are worse.

    Limitations: 0.30 is a common rule of thumb, not a statistical test. With oblique
    rotations, loadings are partial regression weights and can exceed 1 in absolute value.

    Args:
        loadings: Pattern loadings, items × factors.

    Returns:
        DataFrame indexed by item with ``primary_factor``, ``primary_loading`` (signed),
        ``weak``, ``cross_loading`` and ``second_factor`` (None unless cross-loading).
    """
    rows = {}
    for item, row in loadings.iterrows():
        absolute = row.abs().sort_values(ascending=False)
        primary = str(absolute.index[0])
        second = str(absolute.index[1]) if len(absolute) > 1 else None
        cross = second is not None and bool(absolute.iloc[1] >= CROSS_LOADING)
        rows[item] = {
            "primary_factor": primary,
            "primary_loading": float(row[primary]),
            "weak": bool(absolute.iloc[0] < WEAK_LOADING),
            "cross_loading": cross,
            "second_factor": second if cross else None,
        }
    flags = pd.DataFrame.from_dict(rows, orient="index")
    # Keep "no second factor" as None rather than letting pandas turn it into NaN.
    flags["second_factor"] = pd.Series(
        [row["second_factor"] for row in rows.values()], index=flags.index, dtype=object
    )
    return flags


def efa(data: pd.DataFrame, n_factors: int, warnings: list[str] | None = None) -> EFAResult | None:
    """Exploratory factor analysis: minres extraction, oblimin rotation (factor_analyzer).

    Estimates ``n_factors`` common factors behind the items' correlations. Pattern loadings
    show how strongly each factor drives each item (holding the other factors constant).
    Oblimin lets factors correlate, as psychological constructs usually do; the factor
    correlation matrix Φ shows by how much. Communalities (diag(LΦLᵀ)) show how much of
    each item's variance the factors explain together.

    Direction: low loadings and communalities mean an item is poorly explained.

    Limitations: exploratory, not a test of a hypothesised structure (that is CFA, planned
    for version 2). Pearson correlations on ordinal answers. The solution can change with
    the number of factors and with the sample. Two corrections to factor_analyzer 0.5.1 are
    applied here: its ``phi_`` is not reordered when factors are sorted by variance, so Φ is
    recovered exactly from its pattern and structure matrices (structure = LΦ); and its
    ``get_communalities`` sums squared pattern loadings, which is wrong after an oblique
    rotation, so communalities are diag(LΦLᵀ) instead.

    Args:
        data: Complete cases only (respondents × items); see :func:`structure_problem`.
        n_factors: Number of factors, from 1 to (number of items − 1).
        warnings: List that receives plain-English notes (fit failure, Heywood cases).

    Returns:
        :class:`EFAResult`, or None (with a warning) if the model could not be fitted.
    """
    k = data.shape[1]
    if not 1 <= n_factors < k:
        raise ValueError(
            f"The number of factors must be between 1 and {k - 1} (one fewer than the "
            f"number of questions analysed); got {n_factors}."
        )
    try:
        with py_warnings.catch_warnings():
            # factor_analyzer warns that one factor cannot be rotated (expected) and, via
            # scikit-learn, about deprecated arguments; neither affects the results.
            py_warnings.simplefilter("ignore")
            model = FactorAnalyzer(n_factors=n_factors, rotation="oblimin", method="minres")
            model.fit(data.to_numpy(dtype=float))
    except (np.linalg.LinAlgError, ValueError):
        _warn(
            warnings,
            f"Exploratory factor analysis could not be fitted with {n_factors} factor"
            f"{'' if n_factors == 1 else 's'}. Try fewer factors.",
        )
        return None

    pattern = np.asarray(model.loadings_, dtype=float)
    if n_factors == 1:
        # factor_analyzer only aligns signs for 2+ factors.
        if pattern.sum() < 0:
            pattern = -pattern
        phi = np.ones((1, 1))
    else:
        structure_matrix = np.asarray(model.structure_, dtype=float)
        phi = np.linalg.lstsq(pattern, structure_matrix, rcond=None)[0]
        phi = (phi + phi.T) / 2
    communalities = np.einsum("ij,ij->i", pattern @ phi, pattern)

    names = factor_names(n_factors)
    loadings = pd.DataFrame(pattern, index=data.columns, columns=names)
    heywood = [
        item
        for item, h2 in zip(data.columns, communalities, strict=True)
        if h2 >= 1 - _UNIQUENESS_LOWER_BOUND - 1e-6
    ]
    if heywood:
        _warn(
            warnings,
            "The factor solution explains "
            f"{', '.join(heywood)} almost completely (a Heywood case), which usually means "
            "too many factors, too little data or near-duplicate questions. Treat the "
            "loadings with caution.",
        )
    return EFAResult(
        n_factors=n_factors,
        loadings=loadings,
        communalities=pd.Series(communalities, index=data.columns, name="communality"),
        factor_correlations=pd.DataFrame(phi, index=names, columns=names),
        item_flags=loading_flags(loadings),
    )


def factor_matching(
    loadings: pd.DataFrame, reference: pd.DataFrame
) -> dict[str, tuple[str, float]]:
    """Pair each reference factor with one of our factors, and the sign that aligns them.

    Factor order and sign are arbitrary, so two correct solutions can list the same
    factors differently. Each factor is paired with the reference factor whose loadings it
    correlates with most strongly in absolute value (an optimal one-to-one assignment,
    ``scipy.optimize.linear_sum_assignment``); the sign is −1 if that correlation is
    negative.

    Limitations: needs the same items in the same order and the same number of factors.
    Matching is by loading pattern, so two near-identical factors could be swapped.

    Returns:
        Reference factor -> (our factor, sign), in the reference's factor order.
    """
    if list(loadings.index) != list(reference.index) or loadings.shape != reference.shape:
        raise ValueError("Both loading matrices need the same items and number of factors.")
    k = loadings.shape[1]
    corr = np.corrcoef(loadings.to_numpy().T, reference.to_numpy().T)[:k, k:]
    ours, theirs = linear_sum_assignment(-np.abs(corr))
    pairs = sorted(zip(theirs, ours, strict=True))  # reference order
    return {
        str(reference.columns[j]): (str(loadings.columns[i]), 1.0 if corr[i, j] >= 0 else -1.0)
        for j, i in pairs
    }


def match_factors(loadings: pd.DataFrame, reference: pd.DataFrame) -> pd.DataFrame:
    """``loadings`` with factors reordered, re-signed and renamed to line up with ``reference``.

    See :func:`factor_matching` for how factors are paired.
    """
    matching = factor_matching(loadings, reference)
    return pd.DataFrame(
        {ref: sign * loadings[ours] for ref, (ours, sign) in matching.items()},
        index=loadings.index,
    )[list(reference.columns)]


def match_factor_correlations(
    factor_correlations: pd.DataFrame, matching: dict[str, tuple[str, float]]
) -> pd.DataFrame:
    """Factor correlation matrix Φ reordered, re-signed and renamed by a :func:`factor_matching`.

    Flipping the sign of a factor flips the sign of its correlations with other factors.
    """
    names = list(matching)
    values = [
        [
            matching[a][1]
            * matching[b][1]
            * factor_correlations.loc[matching[a][0], matching[b][0]]
            for b in names
        ]
        for a in names
    ]
    return pd.DataFrame(values, index=names, columns=names, dtype=float)


def scale_alignment(
    loadings: pd.DataFrame, scales: dict[str, list[str]]
) -> dict[str, ScaleAlignment]:
    """For each declared scale: which factor its items mostly load on, and how many do.

    Each item's primary factor is the one with its largest absolute loading. A scale's
    factor is the most common primary factor among its items; a tie goes to the factor with
    the larger sum of absolute loadings over the scale's items. ``share_matching`` is the
    share of the scale's items whose primary factor is that factor. If two scales end up
    on the same factor (``shared_with``), the data do not separate them.

    Direction: a lower share, or a factor shared with another scale, means the questions
    group differently from what was intended.

    Limitations: counts primary factors only, so an item with a weak or split loading still
    counts for its strongest factor; check the loading flags too. Scales with fewer than 2
    analysed items are skipped.

    Args:
        loadings: Pattern loadings, items × factors.
        scales: Scale name -> its items; items not in ``loadings`` are ignored.
    """
    primary = loadings.abs().idxmax(axis=1).astype(str)
    out: dict[str, ScaleAlignment] = {}
    for scale, items in scales.items():
        analysed = [item for item in items if item in loadings.index]
        if len(analysed) < 2:
            continue
        counts = primary[analysed].value_counts()
        tied = [str(f) for f in counts.index[counts == counts.max()]]
        strength = loadings.loc[analysed, tied].abs().sum()
        factor = str(strength.idxmax())
        n_matching = int(counts[factor])
        out[scale] = ScaleAlignment(
            scale=scale,
            items=analysed,
            factor=factor,
            n_matching=n_matching,
            share_matching=n_matching / len(analysed),
            item_factors={item: primary[item] for item in analysed},
        )
    for scale, result in out.items():
        result.shared_with = [
            other for other, r in out.items() if other != scale and r.factor == result.factor
        ]
    return out


# --------------------------------------------------------------------------------------
# All together
# --------------------------------------------------------------------------------------


def structure(
    prepared: PreparedData,
    schema: SurveySchema,
    items: list[str] | None = None,
    n_factors: int | None = None,
    warnings: list[str] | None = None,
    pa_iterations: int = PA_ITERATIONS,
) -> StructureResults:
    """Factor-structure analysis of the survey: KMO, Bartlett, parallel analysis, EFA.

    Uses reverse-scored answers of respondents who answered every analysed item. The EFA
    extracts the number of factors suggested by parallel analysis unless ``n_factors`` is
    given. Warnings note excluded respondents, small samples (N < 200 or fewer than 5
    respondents per item), KMO below 0.60, and always the Pearson-correlation limitation.

    Args:
        prepared: Output of :func:`surveydoctor.io.prepare_data`.
        schema: The survey schema.
        items: Items to analyse (default: all schema items), in questionnaire order.
        n_factors: Number of EFA factors chosen by the user (default: parallel analysis).
        warnings: List that receives plain-English notes.
        pa_iterations: Random datasets for parallel analysis.

    Raises:
        ValueError: if ``items`` contains unknown items, or ``n_factors`` is out of range.
    """
    selected = list(schema.items) if items is None else list(items)
    unknown = [item for item in selected if item not in schema.items]
    if unknown:
        raise ValueError(
            f"These questions are not items in the schema: {', '.join(unknown)}. Choose "
            "from the schema's items."
        )
    if n_factors is not None and not 1 <= n_factors < len(selected):
        raise ValueError(
            f"The number of factors must be between 1 and {len(selected) - 1} (one fewer "
            f"than the number of questions analysed); got {n_factors}."
        )
    _warn(warnings, PEARSON_NOTE)

    data = complete_cases(prepared.scored_items, selected)
    n_used, k = data.shape
    n_excluded = len(prepared.scored_items) - n_used
    source: Literal["parallel analysis", "user"] = (
        "parallel analysis" if n_factors is None else "user"
    )
    if n_excluded:
        _warn(
            warnings,
            f"Factor analysis used {_respondents(n_used)} who answered all {k} analysed "
            f"questions; {_respondents(n_excluded)} with a missing answer were left out.",
        )

    problem = structure_problem(data)
    if problem:
        _warn(warnings, problem)
        return StructureResults(
            items=selected,
            n_used=n_used,
            n_excluded=n_excluded,
            skipped_reason=problem,
            kmo=None,
            bartlett=None,
            parallel=None,
            n_factors=None,
            n_factors_source=source,
            efa=None,
            alignment={},
        )

    if n_used < MIN_N_STABLE or n_used / k < MIN_N_PER_ITEM:
        _warn(
            warnings,
            f"The factor solution may be unstable: it rests on {_respondents(n_used)} "
            f"({n_used / k:.1f} per question). At least {MIN_N_STABLE} respondents and "
            f"{MIN_N_PER_ITEM} per question are commonly recommended.",
        )
    kmo_result = kmo(data)
    if kmo_result.overall < MIN_KMO:
        _warn(
            warnings,
            f"The data may be unsuitable for factor analysis: the overall KMO is "
            f"{kmo_result.overall:.2f}, below {MIN_KMO:.2f}, so the questions share "
            "little common variance.",
        )
    parallel = parallel_analysis(data, n_iterations=pa_iterations)

    chosen = parallel.n_suggested if n_factors is None else n_factors
    efa_result = None
    if chosen < 1:
        _warn(
            warnings,
            "Parallel analysis found no factor stronger than random data, so the questions "
            "may not share common factors. Exploratory factor analysis was not run.",
        )
    elif chosen >= k:
        _warn(
            warnings,
            f"Parallel analysis suggested {chosen} factors for {k} questions, which cannot "
            "be estimated. Exploratory factor analysis was not run; choose fewer factors.",
        )
    else:
        efa_result = efa(data, chosen, warnings)

    alignment = (
        scale_alignment(efa_result.loadings, schema.scales) if efa_result is not None else {}
    )
    return StructureResults(
        items=selected,
        n_used=n_used,
        n_excluded=n_excluded,
        skipped_reason=None,
        kmo=kmo_result,
        bartlett=bartlett(data),
        parallel=parallel,
        n_factors=chosen if efa_result is not None else None,
        n_factors_source=source,
        efa=efa_result,
        alignment=alignment,
    )


def alignment_table(results: StructureResults) -> pd.DataFrame:
    """One row per aligned scale: factor, items matching, share, scales sharing the factor."""
    rows = [
        {
            "scale": a.scale,
            "factor": a.factor,
            "n_items": len(a.items),
            "n_matching": a.n_matching,
            "share_matching": a.share_matching,
            "shared_with": ", ".join(a.shared_with),
        }
        for a in results.alignment.values()
    ]
    columns = ["scale", "factor", "n_items", "n_matching", "share_matching", "shared_with"]
    return pd.DataFrame(rows, columns=columns).set_index("scale")
