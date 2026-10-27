"""The whole analysis in one call: every module's output in a single Results object.

The report and the API read only from :class:`Results`; neither computes statistics.
Order: prepare the data, compute the careless-response indices, flags, composite score and
flag variants, then reliability, factor structure, sample sensitivity and, if declared, the
robustness check. Each module adds its plain-English notes to ``Results.warnings``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from surveydoctor.careless import compute_indices
from surveydoctor.flagging import apply_flags, composite_score, flag_variants
from surveydoctor.io import DataIssue, PreparedData, prepare_data
from surveydoctor.power import SensitivityResult, sample_sensitivity
from surveydoctor.reliability import ScaleReliability, reliability
from surveydoctor.robustness import AnalysisSpec, RobustnessResult, check_analysis, robustness
from surveydoctor.schema import SurveySchema
from surveydoctor.structure import PA_ITERATIONS, StructureResults, structure


@dataclass
class Overview:
    """Headline counts for the summary.

    Attributes:
        n_respondents: Respondents analysed (with at least one valid answer).
        n_items: Item columns in the schema.
        n_scales: Scales in the schema.
        n_flagged: Respondents with at least one flag rule triggered.
        n_flagged_two_rules: Respondents with at least two rules triggered.
    """

    n_respondents: int
    n_items: int
    n_scales: int
    n_flagged: int
    n_flagged_two_rules: int


@dataclass
class Results:
    """Every module's output for one survey, plus all warnings (in the order produced).

    Attributes:
        schema: The schema the analysis used.
        prepared: Cleaned and scored data (:class:`surveydoctor.io.PreparedData`).
        overview: Headline counts.
        issues: Counted data problems (invalid answers, removed rows, excluded columns).
        indices: Careless-response indices, one row per respondent.
        flags: Flag rules, ``n_rules_triggered``, ``flagged`` and ``reasons`` per respondent.
        composite: Composite carelessness score (a relative ranking, not a probability).
        variants: The three exclusion masks used by the robustness check.
        reliability: Scale name -> reliability results.
        structure: Factor-structure results.
        sensitivity: The three sensitivity results for the analysed sample size.
        robustness: The robustness check, or None if no analysis was declared.
        warnings: Plain-English notes from every module.
    """

    schema: SurveySchema
    prepared: PreparedData
    overview: Overview
    issues: list[DataIssue]
    indices: pd.DataFrame
    flags: pd.DataFrame
    composite: pd.Series
    variants: dict[str, pd.Series]
    reliability: dict[str, ScaleReliability]
    structure: StructureResults
    sensitivity: list[SensitivityResult]
    robustness: RobustnessResult | None
    warnings: list[str]


def run_pipeline(
    df: pd.DataFrame,
    schema: SurveySchema,
    *,
    rules: dict[str, dict[str, Any]] | None = None,
    n_factors: int | None = None,
    analysis: AnalysisSpec | None = None,
    pa_iterations: int = PA_ITERATIONS,
) -> Results:
    """Run every check on a loaded survey (output of :func:`surveydoctor.io.load_csv`).

    Args:
        df: The survey as loaded from the CSV.
        schema: Which columns are items, the scales, reverse items and the answer range.
        rules: Flag-rule overrides (see :data:`surveydoctor.flagging.DEFAULT_RULES`).
        n_factors: Number of EFA factors; None lets parallel analysis decide.
        analysis: The one analysis to check for robustness, or None.
        pa_iterations: Random datasets used by parallel analysis.

    Raises:
        surveydoctor.io.DataError: If the CSV does not fit the schema.
        ValueError: If ``analysis``, ``rules`` or ``n_factors`` are invalid. The analysis is
            checked before any slow step runs.
    """
    warnings: list[str] = []
    prepared = prepare_data(df, schema)
    if analysis is not None:
        check_analysis(analysis, prepared, schema)

    indices = compute_indices(prepared, schema, warnings=warnings)
    flags = apply_flags(indices, rules, n_items=len(schema.items), warnings=warnings)
    composite = composite_score(indices)
    variants = flag_variants(flags, composite)

    reliability_results = reliability(prepared, schema, warnings=warnings)
    structure_results = structure(
        prepared, schema, n_factors=n_factors, warnings=warnings, pa_iterations=pa_iterations
    )
    n_respondents = len(prepared.raw_items)
    sensitivity = sample_sensitivity(n_respondents) if n_respondents >= 4 else []
    if not sensitivity:
        warnings.append("Sample sensitivity was not computed: at least 4 respondents are needed.")
    robustness_result = (
        robustness(analysis, prepared, schema, variants, warnings=warnings)
        if analysis is not None
        else None
    )

    overview = Overview(
        n_respondents=n_respondents,
        n_items=len(schema.items),
        n_scales=len(schema.scales),
        n_flagged=int(flags["flagged"].sum()),
        n_flagged_two_rules=int((flags["n_rules_triggered"] >= 2).sum()),
    )
    return Results(
        schema=schema,
        prepared=prepared,
        overview=overview,
        issues=list(prepared.issues),
        indices=indices,
        flags=flags,
        composite=composite,
        variants=variants,
        reliability=reliability_results,
        structure=structure_results,
        sensitivity=sensitivity,
        robustness=robustness_result,
        warnings=warnings,
    )
