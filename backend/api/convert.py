"""Turn pipeline results into the API's response models.

Values are copied from :class:`surveydoctor.pipeline.Results` and sentences come from
:mod:`surveydoctor.text`, so the website shows the same numbers and wording as the HTML
report. NaN becomes ``None`` (JSON null). Nothing here computes statistics.
"""

from __future__ import annotations

import math
from typing import Any

import pandas as pd

from api import models as m
from surveydoctor import __version__, text
from surveydoctor.flagging import composite_bins
from surveydoctor.fsqca import Anchors, FsqcaCheck, FsqcaResults, FsqcaRun, FsqcaSpec, Solution
from surveydoctor.io import detect_label_scale, inspect_columns, preview_rows
from surveydoctor.pipeline import Results
from surveydoctor.report import (
    RULE_LABELS,
    csv_rows,
    respondent_ids,
    rule_description,
    rule_status,
)
from surveydoctor.robustness import AnalysisSpec, Correlation, GroupComparison, RobustnessResult
from surveydoctor.schema import SurveySchema
from surveydoctor.structure import PEARSON_NOTE, StructureResults

FLAGGED_ROWS = 200  # BLUEPRINT §7.11: top 200 flagged respondents; the full list is in the CSV


def num(value: Any) -> float | None:
    """A float, or None for NaN and missing values."""
    if value is None:
        return None
    value = float(value)
    return None if math.isnan(value) else value


def _num_dict(series: pd.Series) -> dict[str, float | None]:
    return {str(k): num(v) for k, v in series.items()}


# --- Inputs ---------------------------------------------------------------------------------


def to_analysis(model: m.GroupComparisonModel | m.CorrelationModel) -> AnalysisSpec:
    if isinstance(model, m.GroupComparisonModel):
        return GroupComparison(model.scale, model.group_column, model.group_a, model.group_b)
    return Correlation(model.scale_x, model.scale_y)


def analysis_model(spec: AnalysisSpec) -> m.GroupComparisonModel | m.CorrelationModel:
    if isinstance(spec, GroupComparison):
        return m.GroupComparisonModel(type="group_comparison", **vars(spec))
    return m.CorrelationModel(type="correlation", **vars(spec))


def to_fsqca_spec(model: m.FsqcaSpecModel) -> FsqcaSpec:
    return FsqcaSpec(
        outcome=model.outcome,
        conditions=tuple(model.conditions),
        anchors={scale: tuple(values) for scale, values in model.anchors.items()},
        necessity_threshold=model.necessity_threshold,
        frequency_threshold=model.frequency_threshold,
        consistency_threshold=model.consistency_threshold,
        pri_threshold=model.pri_threshold,
    )


def schema_model(schema: SurveySchema) -> m.SurveySchemaModel:
    return m.SurveySchemaModel(**schema.to_dict())


# --- /api/inspect ---------------------------------------------------------------------------


def inspect_response(df: pd.DataFrame, filename: str | None) -> m.InspectResponse:
    """Columns, a preview without personal columns, short codes and proposed labels."""
    infos = inspect_columns(df)
    preview = preview_rows(df)
    items = [c.header for c in infos if c.suggested_item]
    labels = detect_label_scale(df, items)
    return m.InspectResponse(
        filename=filename,
        n_rows=len(df),
        n_columns=df.shape[1],
        columns=[m.ColumnModel(**vars(c)) for c in infos],
        personal_columns=[c.header for c in infos if c.looks_personal],
        question_text={c.code: c.header for c in infos if c.code is not None},
        preview=m.PreviewModel(
            columns=[str(c) for c in preview.columns],
            rows=[
                [None if pd.isna(v) else str(v) for v in row]
                for row in preview.itertuples(index=False)
            ],
        ),
        labels=m.LabelDetectionModel(**vars(labels)),
    )


# --- /api/analyze ---------------------------------------------------------------------------


def verdict_model(results: Results) -> m.VerdictModel:
    v = text.overall_verdict(results)
    return m.VerdictModel(
        status=v.status,
        headline=v.headline,
        sentence=v.sentence,
        checks=[m.CheckStatusModel(**vars(c)) for c in v.checks],
    )


def careless_model(results: Results) -> m.CarelessModel:
    n_items = len(results.schema.items)
    applied = [name for name in results.rules if name in results.flags.columns]
    rules = [
        m.RuleModel(
            name=name,
            label=RULE_LABELS[name],
            enabled=settings["enabled"],
            settings={k: v for k, v in settings.items() if k != "enabled"},
            description=rule_description(name, settings, n_items),
            status=rule_status(results, name),
            count=int(results.flags[name].sum()) if name in applied else None,
        )
        for name, settings in results.rules.items()
    ]
    flagged = results.flags[results.flags["flagged"]].assign(
        composite=results.composite,
        respondent=respondent_ids(results),
        csv_row=csv_rows(results),
    )
    flagged = flagged.sort_values(["n_rules_triggered", "composite"], ascending=False)
    rows = [
        m.FlaggedRespondentModel(
            respondent=str(row["respondent"]),
            csv_row=int(row["csv_row"]),
            n_rules=int(row["n_rules_triggered"]),
            composite=num(row["composite"]),
            rules=[name for name in applied if bool(row[name])],
            reasons=row["reasons"],
        )
        for _, row in flagged.head(FLAGGED_ROWS).iterrows()
    ]
    edges, counts = composite_bins(results.composite)
    return m.CarelessModel(
        sentence=text.careless_sentence(results),
        rules=rules,
        n_flagged=len(flagged),
        n_shown=len(rows),
        flagged=rows,
        composite_scores=[num(v) for v in results.composite],
        histogram=m.HistogramModel(bin_edges=edges, counts=counts),
        composite_note=text.COMPOSITE_NOTE,
        heuristics_note=text.FLAGS_ARE_HEURISTICS,
    )


def reliability_models(results: Results) -> list[m.ScaleReliabilityModel]:
    out = []
    for r in results.reliability.values():
        out.append(
            m.ScaleReliabilityModel(
                scale=r.scale,
                items=r.items,
                n_items=r.n_items,
                n_used=r.n_used,
                n_excluded=r.n_excluded,
                alpha=num(r.alpha),
                alpha_ci_low=num(r.alpha_ci[0]),
                alpha_ci_high=num(r.alpha_ci[1]),
                omega_total=num(r.omega_total),
                loadings=_num_dict(r.loadings),
                item_stats=[
                    m.ItemStatModel(
                        item=str(item),
                        corrected_item_total=num(row["corrected_item_total"]),
                        alpha_if_deleted=num(row["alpha_if_deleted"]),
                    )
                    for item, row in r.item_stats.iterrows()
                ],
                reverse_warnings=[
                    m.ReverseWarningModel(
                        scale=w.scale,
                        item=w.item,
                        corrected_item_total=num(w.corrected_item_total),
                        message=w.message,
                    )
                    for w in r.reverse_warnings
                ],
                sentence=text.alpha_sentence(r),
            )
        )
    return out


def structure_model(s: StructureResults) -> m.StructureModel:
    efa = None
    if s.efa is not None:
        e = s.efa
        flags = e.item_flags
        efa = m.EFAModel(
            n_factors=e.n_factors,
            factors=[str(f) for f in e.loadings.columns],
            items=[
                m.ItemLoadingModel(
                    item=str(item),
                    loadings=_num_dict(e.loadings.loc[item]),
                    communality=num(e.communalities[item]),
                    primary_factor=str(flags.at[item, "primary_factor"]),
                    primary_loading=num(flags.at[item, "primary_loading"]),
                    weak=bool(flags.at[item, "weak"]),
                    cross_loading=bool(flags.at[item, "cross_loading"]),
                    second_factor=flags.at[item, "second_factor"],
                )
                for item in e.loadings.index
            ],
            factor_correlations=[[num(v) for v in row] for row in e.factor_correlations.values],
        )
    parallel = None
    if s.parallel is not None:
        p = s.parallel
        parallel = m.ParallelModel(
            scree=[
                m.ScreePointModel(
                    position=int(position),
                    observed=num(row["observed"]),
                    threshold=num(row["threshold"]),
                )
                for position, row in p.scree.iterrows()
            ],
            n_suggested=p.n_suggested,
            n_kaiser=p.n_kaiser,
            n_iterations=p.n_iterations,
            percentile=p.percentile,
            seed=p.seed,
        )
    return m.StructureModel(
        items=s.items,
        n_used=s.n_used,
        n_excluded=s.n_excluded,
        skipped_reason=s.skipped_reason,
        kmo=(
            m.KMOModel(overall=num(s.kmo.overall), per_item=_num_dict(s.kmo.per_item))
            if s.kmo is not None
            else None
        ),
        bartlett=(
            m.BartlettModel(
                chi_square=num(s.bartlett.chi_square),
                df=int(s.bartlett.df),
                p_value=num(s.bartlett.p_value),
            )
            if s.bartlett is not None
            else None
        ),
        parallel=parallel,
        n_factors=s.n_factors,
        n_factors_source=s.n_factors_source,
        efa=efa,
        alignment=[
            m.AlignmentModel(
                scale=a.scale,
                items=a.items,
                factor=a.factor,
                n_matching=a.n_matching,
                share_matching=num(a.share_matching),
                item_factors=a.item_factors,
                shared_with=a.shared_with,
            )
            for a in s.alignment.values()
        ],
        sentence=text.structure_sentence(s),
    )


def sensitivity_models(results: Results) -> list[m.SensitivityModel]:
    return [
        m.SensitivityModel(
            **{**vars(s), "min_effect": num(s.min_effect)},
            sentence=text.sensitivity_sentence(s),
        )
        for s in results.sensitivity
    ]


# --- fsQCA ----------------------------------------------------------------------------------


def _anchors(anchors: dict[str, Anchors]) -> dict[str, m.AnchorsModel]:
    return {scale: m.AnchorsModel(**vars(a)) for scale, a in anchors.items()}


def _solution(solution: Solution | None) -> m.SolutionModel | None:
    if solution is None:
        return None
    return m.SolutionModel(
        kind=solution.kind,
        has_solution=solution.has_solution,
        models=[
            m.SolutionModelModel(
                name=model.name,
                expression=model.expression,
                paths=[
                    m.PathModel(
                        expression=path.expression,
                        literals=[
                            m.LiteralModel(condition=name, present=present)
                            for name, present in path.literals
                        ],
                        consistency=num(path.consistency),
                        raw_coverage=num(path.raw_coverage),
                        unique_coverage=num(path.unique_coverage),
                    )
                    for path in model.paths
                ],
                consistency=num(model.consistency),
                coverage=num(model.coverage),
            )
            for model in solution.models
        ],
    )


def _run(run: FsqcaRun, conditions: list[str]) -> m.FsqcaRunModel:
    table = None
    if run.truth_table is not None:
        table = [
            m.TruthTableRowModel(
                row=int(row_number),
                configuration={c: int(row[c]) for c in conditions},
                n=int(row["n"]),
                consistency=num(row["consistency"]),
                pri=num(row["pri"]),
                outcome=str(row["outcome"]),
            )
            for row_number, row in run.truth_table.iterrows()
        ]
    return m.FsqcaRunModel(
        label=run.label,
        n=run.n,
        n_excluded=run.n_excluded,
        anchors=_anchors(run.anchors),
        n_at_crossover=run.n_at_crossover,
        n_positive_rows=run.n_positive_rows,
        has_solution=run.has_solution,
        truth_table=table,
        complex=_solution(run.complex),
        parsimonious=_solution(run.parsimonious),
        skipped_reason=run.skipped_reason,
    )


def _check(check: FsqcaCheck | None, conditions: list[str]) -> m.FsqcaCheckModel | None:
    if check is None:
        return None
    return m.FsqcaCheckModel(
        kind=check.kind,
        comparisons=[
            m.RunComparisonModel(run=_run(c.run, conditions), paths=c.paths, changed=c.changed)
            for c in check.comparisons
        ],
        verdict=check.verdict,
        named=check.named,
        caveat=check.caveat,
        status=text.fsqca_check_status(check),
        sentence=text.fsqca_check_sentence(check),
    )


def fsqca_model(f: FsqcaResults) -> m.FsqcaModel:
    conditions = list(f.spec.conditions)
    ran = f.skipped_reason is None
    spec = f.spec
    return m.FsqcaModel(
        spec=m.FsqcaSpecModel(
            outcome=spec.outcome,
            conditions=conditions,
            anchors=dict(spec.anchors),
            necessity_threshold=spec.necessity_threshold,
            frequency_threshold=spec.frequency_threshold,
            consistency_threshold=spec.consistency_threshold,
            pri_threshold=spec.pri_threshold,
        ),
        n_used=f.n_used,
        n_excluded=f.n_excluded,
        anchors=_anchors(f.anchors),
        n_at_crossover=f.n_at_crossover,
        necessity=[
            m.NecessityModel(
                condition=r.condition,
                consistency=num(r.consistency),
                coverage=num(r.coverage),
                relevance=num(r.relevance),
                passes=r.passes,
            )
            for r in f.necessity
        ],
        skipped_reason=f.skipped_reason,
        main=_run(f.main, conditions) if f.main is not None else None,
        robustness=_check(f.robustness, conditions),
        calibration=_check(f.calibration, conditions),
        sentences=m.FsqcaSentencesModel(
            summary=text.fsqca_sentence(f),
            necessity=text.necessity_sentence(f) if ran else None,
            truth_table=text.truth_table_sentence(f) if ran else None,
            solution=text.solution_sentence(f) if ran else None,
        ),
        necessity_caveat=text.NECESSITY_CAVEAT,
        notation=text.FSQCA_NOTATION,
        limitations=list(text.FSQCA_LIMITATIONS) if ran else [],
    )


def _warnings(results: Results) -> list[str]:
    # The Pearson note is already a limitation (text.PEARSON_LIMITATION); as in the report,
    # it is not repeated among the warnings.
    return [w for w in results.warnings if w != PEARSON_NOTE]


def analyze_response(results: Results) -> m.AnalyzeResponse:
    return m.AnalyzeResponse(
        version=__version__,
        overview=m.OverviewModel(**vars(results.overview)),
        verdict=verdict_model(results),
        summary_sentence=text.summary_sentence(results),
        issues=[m.DataIssueModel(**vars(issue)) for issue in results.issues],
        careless=careless_model(results),
        reliability=reliability_models(results),
        structure=structure_model(results.structure),
        sensitivity=sensitivity_models(results),
        fsqca=fsqca_model(results.fsqca) if results.fsqca is not None else None,
        limitations=text.limitations(results),
        warnings=_warnings(results),
    )


# --- /api/robustness ------------------------------------------------------------------------


def robustness_model(r: RobustnessResult) -> m.RobustnessModel:
    is_groups = isinstance(r.analysis, GroupComparison)
    return m.RobustnessModel(
        analysis=analysis_model(r.analysis),
        description=text.analysis_description(r),
        estimate_label="Difference (A − B)" if is_groups else "Pearson r",
        effect_label="Cohen's d" if is_groups else "r",
        companion_label="Mann–Whitney U" if is_groups else "Spearman's rho",
        variants=[
            m.VariantResultModel(
                variant=v.variant,
                label=text.VARIANT_LABELS.get(v.variant, v.variant),
                n_excluded=v.n_excluded,
                n=v.n,
                estimate=num(v.estimate),
                ci_low=num(v.ci_low),
                ci_high=num(v.ci_high),
                p=num(v.p),
                significant=v.significant,
                direction=v.direction,
                effect_size=num(v.effect_size),
                companion=num(v.companion),
                companion_p=num(v.companion_p),
                n_a=v.n_a,
                n_b=v.n_b,
                note=v.note,
                changed=v.variant in r.changed_variants,
            )
            for v in r.variants
        ],
        verdict=r.verdict,
        changed_variants=r.changed_variants,
        status=m.CheckStatusModel(**vars(text.robustness_status(r))),
        sentence=text.robustness_sentence(r),
        caveat=r.caveat,
    )


def robustness_response(results: Results) -> m.RobustnessResponse:
    assert results.robustness is not None
    return m.RobustnessResponse(
        robustness=robustness_model(results.robustness),
        verdict=verdict_model(results),
        warnings=_warnings(results),
    )
