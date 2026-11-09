"""Pydantic request and response models (BLUEPRINT §7.11).

FastAPI publishes these at ``/openapi.json``; the website's TypeScript types are generated
from that file, so the two cannot silently disagree. Numbers that could not be computed
are ``null`` (JSON has no NaN). :mod:`api.convert` fills these models from
:class:`surveydoctor.pipeline.Results`; nothing here computes statistics.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from surveydoctor.fsqca import (
    CONSISTENCY_THRESHOLD,
    FREQUENCY_THRESHOLD,
    NECESSITY_THRESHOLD,
    PRI_THRESHOLD,
)

Num = float | None
Status = Literal["clear", "review", "problem", "not_checked"]


class ErrorResponse(BaseModel):
    """Every error: a stable code and a message saying what went wrong and how to fix it."""

    code: str
    message: str


class HealthResponse(BaseModel):
    status: Literal["ok"]
    version: str


# --- Inputs ---------------------------------------------------------------------------------


class SurveySchemaModel(BaseModel):
    """The survey schema (see surveydoctor.schema.SurveySchema). Sent as JSON text in the
    'schema' form field; validated by SurveySchema itself for plain-English messages."""

    items: list[str]
    scales: dict[str, list[str]]
    reverse_items: list[str]
    scale_min: int
    scale_max: int
    id_column: str | None = None
    duration_column: str | None = None
    duration_unit: Literal["seconds", "minutes", "milliseconds"] = "seconds"
    label_map: dict[str, int] | None = None
    question_text: dict[str, str] | None = None


class GroupComparisonModel(BaseModel):
    """Compare a scale score between two groups: mean(A) − mean(B), Welch's t-test."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["group_comparison"]
    scale: str
    group_column: str
    group_a: str | int | float
    group_b: str | int | float


class CorrelationModel(BaseModel):
    """Correlate two scale scores (Pearson r)."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["correlation"]
    scale_x: str
    scale_y: str


AnalysisModel = Annotated[GroupComparisonModel | CorrelationModel, Field(discriminator="type")]


class FsqcaSpecModel(BaseModel):
    """The fsQCA to run. Scales without scale-point anchors use the 95th, 50th and 5th
    percentiles of the sample."""

    model_config = ConfigDict(extra="forbid")

    outcome: str
    conditions: list[str]
    anchors: dict[str, tuple[float, float, float]] = Field(
        default_factory=dict,
        description="Scale -> (full membership, crossover, full non-membership) in scale points.",
    )
    necessity_threshold: float = NECESSITY_THRESHOLD
    frequency_threshold: int = FREQUENCY_THRESHOLD
    consistency_threshold: float = CONSISTENCY_THRESHOLD
    pri_threshold: float = PRI_THRESHOLD


# --- /api/sample and /api/inspect ------------------------------------------------------------


class SampleResponse(BaseModel):
    """The bfi sample: CSV text plus its schema."""

    model_config = ConfigDict(populate_by_name=True)

    filename: str
    csv: str
    survey_schema: SurveySchemaModel = Field(alias="schema")


class ColumnModel(BaseModel):
    """One uploaded column. Personal columns have no code and no listed values."""

    code: str | None
    header: str
    n_missing: int
    n_distinct: int
    distinct_values: list[str]
    suggested_item: bool
    looks_personal: bool


class PreviewModel(BaseModel):
    """The first rows, with personal columns removed. Missing cells are null."""

    columns: list[str]
    rows: list[list[str | None]]


class LabelDetectionModel(BaseModel):
    """Proposed text-label mapping for the suggested item columns. Unrecognised labels must
    be mapped by the user; they are never guessed."""

    label_set: str | None
    label_map: dict[str, int] | None
    scale_min: int | None
    scale_max: int | None
    unrecognised: list[str]
    alternatives: list[str]


class InspectResponse(BaseModel):
    filename: str | None
    n_rows: int
    n_columns: int
    columns: list[ColumnModel]
    personal_columns: list[str]
    question_text: dict[str, str] = Field(
        description="Short code -> original header for every non-personal column."
    )
    preview: PreviewModel
    labels: LabelDetectionModel


# --- /api/analyze ---------------------------------------------------------------------------


class OverviewModel(BaseModel):
    n_respondents: int
    n_items: int
    n_scales: int
    n_flagged: int
    n_flagged_two_rules: int


class CheckStatusModel(BaseModel):
    check: str
    label: str
    status: Status
    reason: str


class VerdictModel(BaseModel):
    """The verdict band at the top of the results."""

    status: Status
    headline: str
    sentence: str
    checks: list[CheckStatusModel]


class DataIssueModel(BaseModel):
    kind: str
    count: int
    message: str
    column: str | None = None
    examples: list[str] = []


class RuleModel(BaseModel):
    """One flag rule as used: its settings, whether it was applied and how many it flagged."""

    name: str
    label: str
    enabled: bool
    settings: dict[str, float | bool]
    description: str
    status: str
    count: int | None


class FlaggedRespondentModel(BaseModel):
    respondent: str = Field(description="ID column value, or 'row N' without an ID column.")
    csv_row: int = Field(description="Row in the uploaded CSV, counting the header as row 1.")
    n_rules: int
    composite: Num
    rules: list[str]
    reasons: str


class HistogramModel(BaseModel):
    bin_edges: list[float]
    counts: list[int]


class CarelessModel(BaseModel):
    sentence: str
    rules: list[RuleModel]
    n_flagged: int
    n_shown: int
    flagged: list[FlaggedRespondentModel] = Field(
        description="Flagged respondents, most rules first, then highest composite (top 200)."
    )
    composite_scores: list[Num] = Field(description="One per respondent, in file order.")
    histogram: HistogramModel
    composite_note: str
    heuristics_note: str


class ItemStatModel(BaseModel):
    item: str
    corrected_item_total: Num
    alpha_if_deleted: Num


class ReverseWarningModel(BaseModel):
    scale: str
    item: str
    corrected_item_total: Num
    message: str


class ScaleReliabilityModel(BaseModel):
    scale: str
    items: list[str]
    n_items: int
    n_used: int
    n_excluded: int
    alpha: Num
    alpha_ci_low: Num
    alpha_ci_high: Num
    omega_total: Num
    loadings: dict[str, Num]
    item_stats: list[ItemStatModel]
    reverse_warnings: list[ReverseWarningModel]
    sentence: str


class KMOModel(BaseModel):
    overall: Num
    per_item: dict[str, Num]


class BartlettModel(BaseModel):
    chi_square: Num
    df: int
    p_value: Num


class ScreePointModel(BaseModel):
    position: int
    observed: Num
    threshold: Num


class ParallelModel(BaseModel):
    scree: list[ScreePointModel]
    n_suggested: int
    n_kaiser: int
    n_iterations: int
    percentile: float
    seed: int


class ItemLoadingModel(BaseModel):
    item: str
    loadings: dict[str, Num]
    communality: Num
    primary_factor: str
    primary_loading: Num
    weak: bool
    cross_loading: bool
    second_factor: str | None


class EFAModel(BaseModel):
    n_factors: int
    factors: list[str]
    items: list[ItemLoadingModel]
    factor_correlations: list[list[Num]] = Field(description="Rows and columns in factor order.")


class AlignmentModel(BaseModel):
    scale: str
    items: list[str]
    factor: str
    n_matching: int
    share_matching: Num
    item_factors: dict[str, str]
    shared_with: list[str]


class StructureModel(BaseModel):
    items: list[str]
    n_used: int
    n_excluded: int
    skipped_reason: str | None
    kmo: KMOModel | None
    bartlett: BartlettModel | None
    parallel: ParallelModel | None
    n_factors: int | None
    n_factors_source: Literal["parallel analysis", "user"]
    efa: EFAModel | None
    alignment: list[AlignmentModel]
    sentence: str


class SensitivityModel(BaseModel):
    test: str
    effect_measure: str
    min_effect: Num
    label: str
    n_total: int
    alpha: float
    power: float
    details: dict[str, int]
    caveat: str
    sentence: str


# --- fsQCA ----------------------------------------------------------------------------------


class AnchorsModel(BaseModel):
    full: float
    crossover: float
    non: float
    source: Literal["percentiles", "scale points"]
    percentiles: tuple[float, float, float] | None


class NecessityModel(BaseModel):
    condition: str
    consistency: Num
    coverage: Num
    relevance: Num
    passes: bool


class TruthTableRowModel(BaseModel):
    row: int
    configuration: dict[str, int] = Field(description="Condition -> 1 (present) or 0 (absent).")
    n: int
    consistency: Num
    pri: Num
    outcome: Literal["1", "0", "?"] = Field(description="'?' marks a logical remainder.")


class LiteralModel(BaseModel):
    condition: str
    present: bool


class PathModel(BaseModel):
    expression: str
    literals: list[LiteralModel]
    consistency: Num
    raw_coverage: Num
    unique_coverage: Num


class SolutionModelModel(BaseModel):
    """One model (M1, M2, ...) of a solution: paths joined by OR."""

    name: str
    expression: str
    paths: list[PathModel]
    consistency: Num
    coverage: Num


class SolutionModel(BaseModel):
    kind: Literal["complex", "parsimonious"]
    has_solution: bool
    models: list[SolutionModelModel]


class FsqcaRunModel(BaseModel):
    label: str
    n: int
    n_excluded: int
    anchors: dict[str, AnchorsModel]
    n_at_crossover: int
    n_positive_rows: int
    has_solution: bool
    truth_table: list[TruthTableRowModel] | None
    complex: SolutionModel | None
    parsimonious: SolutionModel | None
    skipped_reason: str | None


class RunComparisonModel(BaseModel):
    run: FsqcaRunModel
    paths: dict[str, dict[str, Literal["kept", "missing", "new"]]]
    changed: bool


class FsqcaCheckModel(BaseModel):
    kind: Literal["robustness", "calibration"]
    comparisons: list[RunComparisonModel]
    verdict: Literal["same", "changed", "no solution"] | None
    named: list[str]
    caveat: str
    status: Status
    sentence: str


class FsqcaSentencesModel(BaseModel):
    summary: str
    necessity: str | None
    truth_table: str | None
    solution: str | None


class FsqcaModel(BaseModel):
    spec: FsqcaSpecModel
    n_used: int
    n_excluded: int
    anchors: dict[str, AnchorsModel]
    n_at_crossover: int
    necessity: list[NecessityModel]
    skipped_reason: str | None
    main: FsqcaRunModel | None
    robustness: FsqcaCheckModel | None
    calibration: FsqcaCheckModel | None
    sentences: FsqcaSentencesModel
    necessity_caveat: str
    notation: str
    limitations: list[str]


class AnalyzeResponse(BaseModel):
    version: str
    overview: OverviewModel
    verdict: VerdictModel
    summary_sentence: str
    issues: list[DataIssueModel]
    careless: CarelessModel
    reliability: list[ScaleReliabilityModel]
    structure: StructureModel
    sensitivity: list[SensitivityModel]
    fsqca: FsqcaModel | None
    limitations: list[str]
    warnings: list[str]


# --- /api/robustness ------------------------------------------------------------------------


class VariantResultModel(BaseModel):
    variant: str
    label: str
    n_excluded: int
    n: int
    estimate: Num
    ci_low: Num
    ci_high: Num
    p: Num
    significant: bool | None
    direction: Literal["positive", "negative", "none"] | None
    effect_size: Num
    companion: Num
    companion_p: Num
    n_a: int | None
    n_b: int | None
    note: str | None
    changed: bool


class RobustnessModel(BaseModel):
    analysis: AnalysisModel
    description: str
    estimate_label: str
    effect_label: str
    companion_label: str
    variants: list[VariantResultModel]
    verdict: Literal["stable", "sensitive", "unstable"] | None
    changed_variants: list[str]
    status: CheckStatusModel
    sentence: str
    caveat: str


class RobustnessResponse(BaseModel):
    """The variant table and verdict, plus the verdict band updated with robustness."""

    robustness: RobustnessModel
    verdict: VerdictModel
    warnings: list[str]
