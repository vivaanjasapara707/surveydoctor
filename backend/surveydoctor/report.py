"""The self-contained HTML report (BLUEPRINT §7.9): one file, no external requests.

:func:`build_report` turns a :class:`surveydoctor.pipeline.Results` into HTML. It computes
no statistics: it formats values already in ``Results`` and fills the sentence templates in
:mod:`surveydoctor.text`. Fonts (IBM Plex, SIL Open Font Licence) and charts are embedded
as base64, so the file works offline and can be emailed or printed to A4.
"""

from __future__ import annotations

import base64
import math
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd
from jinja2 import Environment, FileSystemLoader, select_autoescape

from surveydoctor import __version__, text
from surveydoctor.charts import FONT_DIR, TOKENS, composite_histogram, scree_plot
from surveydoctor.flagging import longstring_threshold
from surveydoctor.pipeline import Results
from surveydoctor.structure import CROSS_LOADING, PEARSON_NOTE, WEAK_LOADING

TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"
FLAGGED_ROWS = 50  # top flagged respondents shown in the report; the full list is in the CSV

FONTS = (  # (family, weight, file)
    ("IBM Plex Sans", 400, "IBMPlexSans-Regular.woff2"),
    ("IBM Plex Sans", 600, "IBMPlexSans-SemiBold.woff2"),
    ("IBM Plex Mono", 400, "IBMPlexMono-Regular.woff2"),
)

RULE_LABELS = {
    "longstring": "Longstring",
    "mahalanobis": "Mahalanobis distance",
    "even_odd": "Even-odd consistency",
    "psychsyn": "Psychometric synonyms",
    "person_total": "Person-total correlation",
    "seconds_per_item": "Seconds per item",
}

METHODS = [
    (
        "Careless-response indices",
        "Longstring is the longest run of identical answers in question order. Mahalanobis D² "
        "measures how unusual a whole answer pattern is (p from a chi-square distribution). "
        "Even-odd consistency correlates the odd-item and even-item halves of each scale across "
        "scales. Psychometric synonyms correlates answers to pairs of items that correlate above "
        "0.60 in the sample. Person-total correlation compares a respondent's answers with "
        "everyone else's item means. IRV (the spread of a respondent's answers) is reported in "
        "the flags CSV only.",
    ),
    (
        "Composite score",
        "The average percentile rank across the available indices, each turned so that higher "
        "means more unusual. A relative ranking within one file, not a probability.",
    ),
    (
        "Reliability",
        "Cronbach's alpha with a 95% confidence interval (Feldt method), McDonald's omega total "
        "from a one-factor model, corrected item-total correlations and alpha if an item is "
        "deleted, on respondents who answered every item of the scale.",
    ),
    (
        "Factor structure",
        "Kaiser-Meyer-Olkin measure (KMO) and Bartlett's test of sphericity; parallel analysis "
        "against the 95th percentile of eigenvalues from random normal data; exploratory factor "
        "analysis (minimum residuals, oblimin rotation) with the suggested number of factors.",
    ),
    (
        "Sample sensitivity",
        "The smallest true effect that a two-sided test would detect with 80% power at α = 0.05 "
        "for the analysed sample size. Not post-hoc power: it uses no observed result.",
    ),
    (
        "Robustness",
        "The declared analysis rerun without the respondents of each flag variant: Welch's "
        "t-test with Cohen's d (Mann-Whitney U as a companion), or Pearson's r with a Fisher-z "
        "interval (Spearman's ρ as a companion).",
    ),
]

REFERENCES = [
    "Cohen, J. (1988). Statistical power analysis for the behavioral sciences (2nd ed.). "
    "Lawrence Erlbaum.",
    "Cronbach, L. J. (1951). Coefficient alpha and the internal structure of tests. "
    "Psychometrika, 16(3), 297–334.",
    "Curran, P. G. (2016). Methods for the detection of carelessly invalid responses in survey "
    "data. Journal of Experimental Social Psychology, 66, 4–19.",
    "Horn, J. L. (1965). A rationale and test for the number of factors in factor analysis. "
    "Psychometrika, 30(2), 179–185.",
    "Huang, J. L., Curran, P. G., Keeney, J., Poposki, E. M., & DeShon, R. P. (2012). "
    "Detecting and deterring insufficient effort responding to surveys. Journal of Business "
    "and Psychology, 27(1), 99–114.",
    "Johnson, J. A. (2005). Ascertaining the validity of individual protocols from Web-based "
    "personality inventories. Journal of Research in Personality, 39(1), 103–129.",
    "Kaiser, H. F. (1974). An index of factorial simplicity. Psychometrika, 39(1), 31–36.",
    "McDonald, R. P. (1999). Test theory: A unified treatment. Lawrence Erlbaum.",
    "Meade, A. W., & Craig, S. B. (2012). Identifying careless responses in survey data. "
    "Psychological Methods, 17(3), 437–455.",
]


@dataclass
class Cell:
    """One table cell: display text plus an optional marker word and tint class."""

    text: str
    note: str = ""
    tint: str = ""
    strong: bool = False


def rule_description(name: str, settings: dict[str, Any], n_items: int) -> str:
    """The flag rule in words, with its threshold."""
    if name == "longstring":
        share = settings["share_of_items"]
        return (
            f"{longstring_threshold(n_items, share)} or more identical answers in a row "
            f"({share:.0%} of {n_items} questions)"
        )
    if name == "mahalanobis":
        return f"answer pattern unusual at p < {settings['p_below']:g}"
    if name == "seconds_per_item":
        return f"fewer than {settings['seconds_below']:g} seconds per question"
    return f"correlation below {settings['r_below']:.2f}"


_PER_COLUMN_ISSUES = {
    "missing_answers": "Blank or NA answers",
    "invalid_answers": "Answers that were not valid, treated as missing",
}


def _issue_rows(issues: list) -> list[dict[str, str]]:
    """One row per kind of per-column issue (columns listed with counts), then every other
    issue with its own message."""
    rows = []
    for kind, label in _PER_COLUMN_ISSUES.items():
        found = [i for i in issues if i.kind == kind]
        if not found:
            continue
        detail = " · ".join(f"{i.column} {i.count}" for i in found)
        examples = sorted({e for i in found for e in i.examples})[:5]
        if examples:
            detail += f". Examples: {', '.join(examples)}"
        rows.append(
            {
                "what": f"{label} in {len(found)} column{'s' if len(found) != 1 else ''}",
                "detail": detail,
                "count": text.fmt_count(sum(i.count for i in found)),
            }
        )
    for issue in issues:
        if issue.kind not in _PER_COLUMN_ISSUES:
            rows.append({"what": issue.message, "detail": "", "count": text.fmt_count(issue.count)})
    return rows


def _font_faces() -> str:
    faces = []
    for family, weight, filename in FONTS:
        path = FONT_DIR / filename
        if not path.exists():
            continue
        data = base64.b64encode(path.read_bytes()).decode("ascii")
        faces.append(
            f'@font-face{{font-family:"{family}";font-weight:{weight};font-style:normal;'
            f'font-display:swap;src:url(data:font/woff2;base64,{data}) format("woff2");}}'
        )
    return "\n".join(faces)


def _respondent_ids(results: Results) -> pd.Series:
    """The schema's ID column if there is one, otherwise the CSV row number (header = row 1)."""
    index = results.prepared.raw_items.index
    id_column = results.schema.id_column
    if id_column is not None and id_column in results.prepared.meta.columns:
        return results.prepared.meta.loc[index, id_column].astype(str)
    return pd.Series([f"row {i + 2}" for i in range(len(index))], index=index)


def _careless_section(results: Results) -> dict[str, Any]:
    n_items = len(results.schema.items)
    rules = []
    for name, settings in results.rules.items():
        applied = name in results.flags.columns
        rules.append(
            {
                "label": RULE_LABELS[name],
                "description": rule_description(name, settings, n_items),
                "count": text.fmt_count(int(results.flags[name].sum())) if applied else "–",
                "status": "applied" if applied else (
                    "switched off" if not settings["enabled"]
                    else "not applied (no completion-time column)"
                    if name == "seconds_per_item" and results.schema.duration_column is None
                    else "not applied (index not computed)"
                ),
            }
        )  # fmt: skip
    flagged = results.flags[results.flags["flagged"]].assign(
        composite=results.composite, respondent=_respondent_ids(results)
    )
    flagged = flagged.sort_values(["n_rules_triggered", "composite"], ascending=False)
    rows = [
        {
            "respondent": row["respondent"],
            "n_rules": int(row["n_rules_triggered"]),
            "composite": text.fmt(row["composite"]),
            "reasons": row["reasons"],
        }
        for _, row in flagged.head(FLAGGED_ROWS).iterrows()
    ]
    histogram = composite_histogram(results.composite)
    return {
        "sentence": text.careless_sentence(results),
        "rules": rules,
        "rows": rows,
        "n_shown": len(rows),
        "n_flagged": len(flagged),
        "histogram": histogram,
        "composite_note": text.COMPOSITE_NOTE,
        "heuristics_note": text.FLAGS_ARE_HEURISTICS,
    }


def _reliability_section(results: Results) -> dict[str, Any]:
    scales = []
    for r in results.reliability.values():
        low, high = r.alpha_ci
        below = r.alpha < text.ALPHA_ACCEPTABLE
        scales.append(
            {
                "scale": r.scale,
                "n_items": r.n_items,
                "n_used": text.fmt_count(r.n_used),
                "alpha": Cell(
                    text.fmt(r.alpha), "below 0.70" if below else "", "review" if below else ""
                ),  # fmt: skip
                "ci": f"{text.fmt(low)} to {text.fmt(high)}",
                "omega": text.fmt(r.omega_total),
                "sentence": text.alpha_sentence(r),
                "warnings": [w.message for w in r.reverse_warnings],
            }
        )
    return {"scales": scales}


def _structure_section(results: Results) -> dict[str, Any]:
    s = results.structure
    section: dict[str, Any] = {"sentence": text.structure_sentence(s), "skipped": s.skipped_reason}
    if s.skipped_reason is not None:
        return section
    section["kmo"] = text.fmt(s.kmo.overall)
    section["bartlett"] = (
        f"χ² = {s.bartlett.chi_square:,.2f}, df = {s.bartlett.df}, {text.fmt_p(s.bartlett.p_value)}"
    )
    section["n_used"] = text.fmt_count(s.n_used)
    section["scree"] = scree_plot(s.parallel) if s.parallel is not None else None
    if s.efa is not None:
        factor_scale = {a.factor: a.scale for a in s.alignment.values()}
        factors = list(s.efa.loadings.columns)
        section["factors"] = [(f, factor_scale.get(f, "")) for f in factors]
        rows = []
        for item, loadings in s.efa.loadings.iterrows():
            flags = s.efa.item_flags.loc[item]
            cells = []
            for factor in factors:
                value = loadings[factor]
                primary = factor == flags["primary_factor"]
                second = factor == flags["second_factor"] and flags["cross_loading"]
                note = "weak" if primary and flags["weak"] else ("cross" if second else "")
                tint = "review" if note else ""
                cells.append(Cell(text.fmt(value), note, tint, strong=primary))
            rows.append({"item": item, "cells": cells,
                         "communality": text.fmt(s.efa.communalities[item])})  # fmt: skip
        section["loadings"] = rows
        section["alignment"] = [
            {
                "scale": a.scale,
                "factor": a.factor,
                "matching": f"{a.n_matching} of {len(a.items)}",
                "shared": text.join_names(a.shared_with) or "–",
                "tint": "review" if a.shared_with else "",
            }
            for a in s.alignment.values()
        ]
        section["thresholds"] = (
            f"Bold: the item's largest loading. “weak”: largest |loading| below "
            f"{WEAK_LOADING:.2f}. “cross”: a second |loading| of {CROSS_LOADING:.2f} or more."
        )
    return section


def _robustness_section(results: Results) -> dict[str, Any] | None:
    r = results.robustness
    if r is None:
        return None
    is_groups = r.variants[0].n_a is not None
    rows = []
    for v in r.variants:
        changed = v.variant in r.changed_variants
        rows.append(
            {
                "label": text.VARIANT_SHORT.get(v.variant, v.variant),
                "n_excluded": text.fmt_count(v.n_excluded),
                "n": text.fmt_count(v.n),
                "estimate": text.fmt(v.estimate),
                "ci": f"{text.fmt(v.ci_low)} to {text.fmt(v.ci_high)}",
                "p": "–" if math.isnan(v.p) else text.fmt_p(v.p).removeprefix("p = "),
                "significant": "–" if v.significant is None else ("yes" if v.significant else "no"),
                "effect": text.fmt(v.effect_size),
                "note": v.note or "",
                "tint": "review" if changed else "",
            }
        )
    return {
        "description": text.analysis_description(r),
        "estimate_label": "Difference (A − B)" if is_groups else "Pearson r",
        "effect_label": "Cohen's d" if is_groups else "r",
        "rows": rows,
        "sentence": text.robustness_sentence(r),
        "status": text.robustness_status(r),
    }


def report_context(
    results: Results, source_name: str | None = None, generated_at: datetime | None = None
) -> dict[str, Any]:
    """Everything the template shows, as plain values and finished sentences."""
    generated_at = generated_at or datetime.now(UTC)
    verdict = text.overall_verdict(results)
    structure = results.structure
    headline_alpha = [f"{r.scale} {text.fmt(r.alpha)}" for r in results.reliability.values()]
    return {
        "tokens": TOKENS,
        "font_faces": _font_faces(),
        "version": __version__,
        "generated": generated_at.strftime("%d %B %Y, %H:%M UTC"),
        "source_name": source_name or "Uploaded survey",
        "verdict": verdict,
        "status_words": text.STATUS_WORDS,
        "summary": {
            "sentence": text.summary_sentence(results),
            "figures": [
                ("Respondents", text.fmt_count(results.overview.n_respondents)),
                ("Questions / scales", f"{results.overview.n_items} / {results.overview.n_scales}"),
                (
                    "Flagged (any rule / two or more)",
                    f"{text.fmt_count(results.overview.n_flagged)} / "
                    f"{text.fmt_count(results.overview.n_flagged_two_rules)}",
                ),
                ("Alpha per scale", ", ".join(headline_alpha) or "–"),
                (
                    "Factors suggested",
                    str(structure.parallel.n_suggested) if structure.parallel else "not computed",
                ),
                (
                    "Robustness",
                    results.robustness.verdict or "not computed"
                    if results.robustness is not None
                    else "not checked",
                ),
            ],  # fmt: skip
        },
        "issues": _issue_rows(results.issues),
        "careless": _careless_section(results),
        "reliability": _reliability_section(results),
        "structure": _structure_section(results),
        "sensitivity": {
            "sentences": [text.sensitivity_sentence(s) for s in results.sensitivity],
            "caveat": results.sensitivity[0].caveat if results.sensitivity else "",
        },
        "robustness": _robustness_section(results),
        "limitations": text.limitations(results),
        # The Pearson note is already a limitation (text.PEARSON_LIMITATION); don't repeat it.
        "warnings": [w for w in results.warnings if w != PEARSON_NOTE],
        "methods": METHODS,
        "references": REFERENCES,
    }


def build_report(
    results: Results, source_name: str | None = None, generated_at: datetime | None = None
) -> str:
    """Render the HTML report for ``results``.

    Args:
        results: Output of :func:`surveydoctor.pipeline.run_pipeline`.
        source_name: File name shown in the header (the upload's name); escaped.
        generated_at: Timestamp for the footer (default: now, UTC).
    """
    env = Environment(
        loader=FileSystemLoader(TEMPLATE_DIR),
        autoescape=select_autoescape(["html", "j2"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    template = env.get_template("report.html.j2")
    return template.render(**report_context(results, source_name, generated_at))
