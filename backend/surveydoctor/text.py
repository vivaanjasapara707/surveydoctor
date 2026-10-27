"""Templated wording for the report and the API (BLUEPRINT §7.10).

Every sentence here is a fixed template filled with computed values: no free text, and no
language model. This module also decides the status of each check and the overall verdict
shown at the top of the results, using the rules the owner approved in docs/design.md §5:

* Careless responding: Review if anyone is flagged by 2 or more rules; never Problem.
* Reliability: Review if any alpha is below 0.70 (or not computable) or an item looks
  reverse-worded; never Problem.
* Structure: Review if KMO is below 0.60, a scale shares its factor, or the analysis was
  skipped; never Problem.
* Robustness: "stable" -> Clear, "sensitive" -> Review, "unstable" -> Problem.

The overall status is the worst check status. Checks that did not run are "not_checked"
and never count as clear evidence.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from surveydoctor.power import SensitivityResult
from surveydoctor.reliability import ScaleReliability
from surveydoctor.robustness import GroupComparison, RobustnessResult
from surveydoctor.structure import MIN_KMO, MIN_N_PER_ITEM, MIN_N_STABLE, StructureResults

if TYPE_CHECKING:
    from surveydoctor.pipeline import Results

Status = Literal["clear", "review", "problem", "not_checked"]

ALPHA_ACCEPTABLE = 0.70  # BLUEPRINT §7.10: "commonly treated as acceptable"

STATUS_WORDS: dict[str, str] = {
    "clear": "No concerns",
    "review": "Review",
    "problem": "Serious concern",
    "not_checked": "Not checked",
}
STATUS_ICONS: dict[str, str] = {"clear": "✓", "review": "⚠", "problem": "✕", "not_checked": "–"}
HEADLINES: dict[str, str] = {
    "clear": "No concerns found by these checks",
    "review": "Review before drawing conclusions",
    "problem": "Serious concern",
}
_SEVERITY = {"not_checked": 0, "clear": 1, "review": 2, "problem": 3}

VARIANT_SHORT: dict[str, str] = {  # table rows; the Excluded column gives the count
    "all": "All respondents",
    "any_rule": "Without flagged (any rule)",
    "two_rules": "Without flagged (2+ rules)",
    "composite_top10": "Without top 10% composite",
}
VARIANT_LABELS: dict[str, str] = {
    "all": "All respondents",
    "any_rule": "Excluding respondents flagged by any rule",
    "two_rules": "Excluding respondents flagged by two or more rules",
    "composite_top10": "Excluding the top 10% composite scores",
}

CONVENIENCE_SAMPLE = (
    "Statistical checks cannot fix who was sampled. If respondents were recruited through "
    "personal networks or social media, results may not generalise."
)
FLAGS_ARE_HEURISTICS = (
    "Flag thresholds are heuristics and conventions, not proven cut-offs. A flag is a reason "
    "to look at a respondent, not proof that they answered carelessly."
)
COMPOSITE_NOTE = (
    "The composite score is a relative ranking within this file, not a probability. In "
    "SurveyDoctor's simulation study it separated straightlining and midpoint responding "
    "poorly; the longstring index is the one that catches those patterns."
)
ITEM_ORDER_NOTE = (
    "Longstring assumes every respondent saw the questions in the order given in the schema. "
    "If the survey shuffled the question order, treat longstring results with caution."
)
ALPHA_CAVEAT = "High alpha does not prove that a scale measures a single concept."
PEARSON_LIMITATION = (
    "Factor analysis uses Pearson correlations, which treat ordinal answers (such as 1–5 "
    "ratings) as continuous. This can understate how strongly items are related."
)
NO_DURATION = (
    "The data has no completion-time column, so response-time screening was not performed."
)


@dataclass
class CheckStatus:
    """One chip of the verdict band: which check, its status and a one-line reason."""

    check: str
    label: str
    status: Status
    reason: str


@dataclass
class Verdict:
    """The verdict band: overall status, headline, one sentence, and one chip per check."""

    status: Status
    headline: str
    sentence: str
    checks: list[CheckStatus]


# --- Number formatting --------------------------------------------------------------------


def fmt(value: float, decimals: int = 2) -> str:
    """A number with a fixed number of decimals, or an en dash if it is missing."""
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return "–"
    text = f"{value:.{decimals}f}"
    return text[1:] if text.startswith("-") and float(text) == 0 else text  # no "-0.00"


def fmt_p(p: float) -> str:
    """p-value text: "p < 0.001" for very small values, otherwise three decimals."""
    if p is None or math.isnan(p):
        return "p not computed"
    return "p < 0.001" if p < 0.001 else f"p = {p:.3f}"


def fmt_count(n: int) -> str:
    """A count with thousands separators, e.g. 2,800."""
    return f"{n:,}"


def fmt_share(part: int, whole: int) -> str:
    """A share as a percentage with one decimal, e.g. 24.5%."""
    return "–" if whole == 0 else f"{100 * part / whole:.1f}%"


def join_names(names: list[str]) -> str:
    """'A', 'A and B', 'A, B and C'."""
    if len(names) <= 1:
        return "".join(names)
    return ", ".join(names[:-1]) + " and " + names[-1]


# --- Check statuses -----------------------------------------------------------------------


def careless_status(results: Results) -> CheckStatus:
    """Review if anyone is flagged by two or more rules; never Problem (flags are heuristics)."""
    n2 = results.overview.n_flagged_two_rules
    if n2 > 0:
        reason = f"{fmt_count(n2)} respondents were flagged by two or more rules."
        return CheckStatus("careless", "Careless responding", "review", reason)
    reason = "Nobody was flagged by two or more rules."
    return CheckStatus("careless", "Careless responding", "clear", reason)


def reliability_status(reliability: dict[str, ScaleReliability]) -> CheckStatus:
    """Review if any scale's alpha is below 0.70 or not computable, or an item looks reversed."""
    if not reliability:
        return CheckStatus("reliability", "Reliability", "not_checked", "No scales were declared.")
    low = [r.scale for r in reliability.values() if r.alpha < ALPHA_ACCEPTABLE]
    missing = [r.scale for r in reliability.values() if math.isnan(r.alpha)]
    reversed_items = [w.item for r in reliability.values() for w in r.reverse_warnings]
    problems = []
    if low:
        problems.append(f"alpha is below {ALPHA_ACCEPTABLE:.2f} for {join_names(low)}")
    if missing:
        problems.append(f"alpha could not be computed for {join_names(missing)}")
    if reversed_items:
        problems.append(f"possibly reverse-worded items: {join_names(reversed_items)}")
    if problems:
        reason = "; ".join(problems)
        return CheckStatus(
            "reliability", "Reliability", "review", reason[0].upper() + reason[1:] + "."
        )
    return CheckStatus(
        "reliability", "Reliability", "clear",
        f"Every scale has alpha of {ALPHA_ACCEPTABLE:.2f} or more.",
    )  # fmt: skip


def structure_status(structure: StructureResults) -> CheckStatus:
    """Review if KMO < 0.60, a scale shares its factor or the analysis was skipped."""
    label = "Factor structure"
    if structure.skipped_reason is not None or structure.kmo is None:
        return CheckStatus("structure", label, "review", "The factor analysis could not be run.")
    problems = []
    if structure.kmo.overall < MIN_KMO:
        problems.append(f"KMO is {fmt(structure.kmo.overall)}, below {MIN_KMO:.2f}")
    if structure.efa is None:
        problems.append("no factors were extracted")
    shared = sorted(a.scale for a in structure.alignment.values() if a.shared_with)
    if shared:
        problems.append(f"{join_names(shared)} do not have a factor of their own")
    if problems:
        reason = "; ".join(problems)
        return CheckStatus("structure", label, "review", reason[0].upper() + reason[1:] + ".")
    return CheckStatus(
        "structure", label, "clear",
        f"KMO is {fmt(structure.kmo.overall)} and every scale has a factor of its own.",
    )  # fmt: skip


def robustness_status(robustness: RobustnessResult | None) -> CheckStatus:
    """Clear for "stable", Review for "sensitive", Problem for "unstable"."""
    label = "Robustness"
    if robustness is None:
        return CheckStatus("robustness", label, "not_checked", "No analysis was declared.")
    if robustness.verdict is None:
        return CheckStatus(
            "robustness", label, "not_checked",
            "The declared analysis could not be computed.",
        )  # fmt: skip
    status: Status = {"stable": "clear", "sensitive": "review", "unstable": "problem"}[
        robustness.verdict
    ]
    reasons = {
        "stable": "The declared result does not depend on excluding flagged respondents.",
        "sensitive": "Whether the declared result is significant depends on exclusions.",
        "unstable": "The declared result reverses direction when respondents are excluded.",
    }
    return CheckStatus("robustness", label, status, reasons[robustness.verdict])


def overall_verdict(results: Results) -> Verdict:
    """The verdict band: the worst check status, with a sentence naming what to review."""
    checks = [
        careless_status(results),
        reliability_status(results.reliability),
        structure_status(results.structure),
        robustness_status(results.robustness),
    ]
    worst = max(checks, key=lambda c: _SEVERITY[c.status]).status
    status: Status = "clear" if worst == "not_checked" else worst
    flagged = [c.label.lower() for c in checks if c.status in ("review", "problem")]
    if flagged:
        sentence = f"Look at {join_names(flagged)} before drawing conclusions."
        if status == "problem":
            sentence = (
                "The declared result reverses when flagged respondents are excluded. "
                f"Look at {join_names(flagged)} before drawing conclusions."
            )
    else:
        sentence = "None of the checks that ran raised a concern."
    not_run = [c.label.lower() for c in checks if c.status == "not_checked"]
    if not_run:
        sentence += f" Not checked: {join_names(not_run)}."
    return Verdict(status, HEADLINES[status], sentence, checks)


# --- Section sentences --------------------------------------------------------------------


def summary_sentence(results: Results) -> str:
    o = results.overview
    return (
        f"{fmt_count(o.n_respondents)} respondents, {o.n_items} questions in {o.n_scales} scales."
    )


def careless_sentence(results: Results) -> str:
    o = results.overview
    return (
        f"{fmt_count(o.n_flagged)} of {fmt_count(o.n_respondents)} respondents "
        f"({fmt_share(o.n_flagged, o.n_respondents)}) were flagged by at least one rule; "
        f"{fmt_count(o.n_flagged_two_rules)} "
        f"({fmt_share(o.n_flagged_two_rules, o.n_respondents)}) by two or more."
    )


def alpha_sentence(r: ScaleReliability) -> str:
    """Alpha with its CI, the 0.70 convention and the one-concept caveat."""
    if math.isnan(r.alpha):
        return f"Alpha could not be computed for {r.scale}."
    low, high = r.alpha_ci
    judgement = (
        "which is commonly treated as acceptable"
        if r.alpha >= ALPHA_ACCEPTABLE
        else f"which is below the {ALPHA_ACCEPTABLE:.2f} commonly treated as acceptable"
    )
    return (
        f"Alpha for {r.scale} is {fmt(r.alpha)} (95% CI {fmt(low)} to {fmt(high)}, "
        f"N = {fmt_count(r.n_used)}), {judgement}. {ALPHA_CAVEAT}"
    )


def structure_sentence(structure: StructureResults) -> str:
    if structure.skipped_reason is not None:
        return f"The factor analysis was not run: {structure.skipped_reason}"
    parts = [
        f"KMO = {fmt(structure.kmo.overall)} ({MIN_KMO:.2f} or more is the usual minimum for "
        "factor analysis).",
    ]
    if structure.parallel is not None:
        parts.append(
            f"Parallel analysis suggests {structure.parallel.n_suggested} factor"
            f"{'' if structure.parallel.n_suggested == 1 else 's'}."
        )
    if structure.efa is not None:
        own = sum(1 for a in structure.alignment.values() if not a.shared_with)
        source = (
            "as suggested" if structure.n_factors_source == "parallel analysis" else "as chosen"
        )
        parts.append(
            f"With {structure.n_factors} factors ({source}), {own} of "
            f"{len(structure.alignment)} scales have a factor of their own."
        )
    return " ".join(parts)


_TEST_WORDING = {
    "two_groups": "a comparison of two groups (t-test)",
    "correlation": "a correlation",
    "anova": "a comparison of {k} groups (one-way ANOVA)",
}


def sensitivity_sentence(s: SensitivityResult) -> str:
    """The smallest effect detectable with the target power, with its benchmark label."""
    test = _TEST_WORDING[s.test].format(k=s.details.get("k_groups", ""))
    if s.test == "two_groups":
        sizes = f"with groups of {fmt_count(s.details['n1'])} and {fmt_count(s.details['n2'])}"
    elif s.test == "anova":
        sizes = f"with {fmt_count(s.n_total)} respondents in equal groups"
    else:
        sizes = f"with {fmt_count(s.n_total)} respondents"
    symbol = {"d": "d", "r": "|r|", "f": "f"}[s.effect_measure]
    return (
        f"For {test} {sizes}, the smallest effect detected with {s.power:.0%} power at "
        f"α = {s.alpha:.2f} is {symbol} = {fmt(s.min_effect)} ({s.label} on Cohen's scale)."
    )


def analysis_description(robustness: RobustnessResult) -> str:
    a = robustness.analysis
    if isinstance(a, GroupComparison):
        return (
            f"the difference in {a.scale} between {a.group_column} = {a.group_a} and "
            f"{a.group_column} = {a.group_b}"
        )
    return f"the correlation between {a.scale_x} and {a.scale_y}"


def robustness_sentence(robustness: RobustnessResult) -> str:
    """The verdict in words, naming the variants that changed, plus the fixed caveat."""
    what = analysis_description(robustness)
    changed = join_names([VARIANT_LABELS[v].lower() for v in robustness.changed_variants])
    if robustness.verdict is None:
        text = f"The robustness check could not compute {what} on all respondents."
    elif robustness.verdict == "stable":
        text = (
            f"Stable: {what} keeps the same direction and significance in every exclusion variant."
        )
    elif robustness.verdict == "sensitive":
        text = (
            f"Sensitive to careless responses: whether {what} is significant changes when "
            f"{changed}."
        )
    else:
        text = f"Unstable: {what} is significant in the opposite direction when {changed}."
    return f"{text} {robustness.caveat}"


# --- Limitations --------------------------------------------------------------------------


def limitations(results: Results) -> list[str]:
    """Limitations that apply to these results, always starting with the sampling warning."""
    items = [CONVENIENCE_SAMPLE]
    if results.schema.duration_column is None:
        items.append(NO_DURATION)
    s = results.structure
    small_n = s.n_used < MIN_N_STABLE or s.n_used < MIN_N_PER_ITEM * max(len(s.items), 1)
    low_kmo = s.kmo is not None and s.kmo.overall < MIN_KMO
    if s.skipped_reason is None and (small_n or low_kmo):
        why = []
        if small_n:
            why.append(f"only {fmt_count(s.n_used)} complete respondents")
        if low_kmo:
            why.append(f"KMO of {fmt(s.kmo.overall)}")
        items.append(f"Factor results may be unstable ({join_names(why)}).")
    if s.skipped_reason is None:
        items.append(PEARSON_LIMITATION)
    items += [FLAGS_ARE_HEURISTICS, COMPOSITE_NOTE, ITEM_ORDER_NOTE]
    return items
