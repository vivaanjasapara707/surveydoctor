"""Run the simulation study and write its results (BLUEPRINT §7.7).

Run from backend/:

    python evaluation/run_simulation.py

Writes ``results/simulation_results.csv`` (one row per repetition and measure) and
``results/simulation_summary.md`` (mean ± SD per pattern, contamination rate and measure).
Every number in the summary is computed from the CSV rows written in the same run.
``--reps 10`` halves the run (BLUEPRINT §9 slip rule); the summary states the number used.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from evaluation.simulate import (  # noqa: E402
    FLAG_MEASURE,
    N_REPS,
    PATTERNS,
    RATES,
    RULE_PREFIX,
    SCORE_MEASURES,
    base_data,
    run_condition,
)
from surveydoctor.flagging import DEFAULT_RULES  # noqa: E402
from surveydoctor.schema import SurveySchema  # noqa: E402

BFI_CSV = BACKEND_DIR / "data" / "sample" / "bfi.csv"
BFI_SCHEMA = BACKEND_DIR / "data" / "sample" / "bfi_schema.json"
RESULTS_DIR = BACKEND_DIR / "results"

MEASURE_LABELS: dict[str, str] = {
    "composite": "Composite score",
    "longstring": "Longstring",
    "mahalanobis": "Mahalanobis D²",
    "even_odd": "Even-odd consistency",
    "psychsyn": "Psychometric synonyms",
    "person_total": "Person-total correlation",
    "seconds_per_item": "Seconds per item",
    FLAG_MEASURE: "Default flag rule (any rule fires)",
}


def run_all(base: pd.DataFrame, schema: SurveySchema, n_reps: int = N_REPS) -> pd.DataFrame:
    """Every pattern × rate × repetition (seeds 0 to n_reps − 1), one row per measure."""
    rows = [
        record
        for pattern in PATTERNS
        for rate in RATES
        for seed in range(n_reps)
        for record in run_condition(base, schema, pattern, rate, seed)
    ]
    return pd.DataFrame(rows)


def _mean_sd(values: pd.Series) -> str:
    """'mean ± SD' to 3 decimals (SD with ddof = 1; '–' if there are no values)."""
    values = values.dropna()
    if values.empty:
        return "–"
    sd = values.std(ddof=1) if len(values) > 1 else 0.0
    return f"{values.mean():.3f} ± {sd:.3f}"


def _rate_label(rate: float) -> str:
    return f"{rate:.0%}"


def score_table(results: pd.DataFrame, pattern: str, metric: str) -> str:
    """Markdown table for one pattern: one row per score measure, one column per rate."""
    rates = sorted(results["rate"].unique())
    subset = results[results["pattern"] == pattern]
    lines = [
        "| Measure | " + " | ".join(_rate_label(r) for r in rates) + " |",
        "|---|" + "---|" * len(rates),
    ]
    for measure in SCORE_MEASURES:
        rows = subset[subset["measure"] == measure]
        if rows.empty:
            continue
        cells = [_mean_sd(rows.loc[rows["rate"] == r, metric]) for r in rates]
        lines.append(f"| {MEASURE_LABELS[measure]} | " + " | ".join(cells) + " |")
    return "\n".join(lines)


def flag_table(results: pd.DataFrame, measure: str = FLAG_MEASURE) -> str:
    """Markdown table of a yes/no flag (the default flag rule, or one ``rule_<name>``):
    recall and precision per pattern and rate."""
    rates = sorted(results["rate"].unique())
    flags = results[results["measure"] == measure]
    header = " | ".join(f"Recall {_rate_label(r)} | Precision {_rate_label(r)}" for r in rates)
    lines = [f"| Pattern | {header} |", "|---|" + "---|" * (2 * len(rates))]
    for pattern in PATTERNS:
        rows = flags[flags["pattern"] == pattern]
        if rows.empty:
            continue
        cells: list[str] = []
        for r in rates:
            at_rate = rows[rows["rate"] == r]
            cells += [_mean_sd(at_rate["recall"]), _mean_sd(at_rate["precision"])]
        lines.append(f"| {pattern} | " + " | ".join(cells) + " |")
    return "\n".join(lines)


def _share(value: float) -> str:
    """A share as a whole percentage; '<1%' for small non-zero shares; NaN = not computed."""
    if pd.isna(value):
        return "not computed"
    if 0 < value < 0.005:
        return "<1%"
    return f"{value:.0%}"


def missing_table(results: pd.DataFrame) -> str:
    """Markdown table: share of careless respondents an index had no value for (mean over
    the runs in which the index was computed). Only measures that ever had a missing value
    are listed."""
    scores = results[results["measure"].isin(SCORE_MEASURES)]
    means = scores.groupby(["measure", "pattern"])["missing_careless"].mean().unstack("pattern")
    means = means.reindex(index=[m for m in SCORE_MEASURES if m in means.index])
    means = means[(means > 0).any(axis=1)]
    if means.empty:
        return "Every evaluated score had a value for every careless respondent."
    patterns = [p for p in PATTERNS if p in means.columns]
    lines = ["| Measure | " + " | ".join(patterns) + " |", "|---|" + "---|" * len(patterns)]
    for measure, row in means.iterrows():
        cells = [_share(row[p]) for p in patterns]
        lines.append(f"| {MEASURE_LABELS[measure]} | " + " | ".join(cells) + " |")
    return "\n".join(lines)


def partial_availability(results: pd.DataFrame) -> list[str]:
    """One sentence per score that was computed in some runs but not all, naming where."""
    runs = results[["pattern", "rate", "seed"]].drop_duplicates()
    sentences: list[str] = []
    for measure in SCORE_MEASURES:
        present = results[results["measure"] == measure]
        if present.empty or len(present) == len(runs):
            continue
        where = present.groupby(["pattern", "rate"]).size()
        conditions = ", ".join(f"{p} at {_rate_label(r)}" for p, r in where.index)
        sentences.append(
            f"{MEASURE_LABELS[measure]} was computed in {len(present)} of {len(runs)} runs "
            f"({conditions}). In the other runs it could not be computed, so it is not "
            "evaluated there."
        )
    return sentences


def summary_markdown(results: pd.DataFrame, n_reps: int) -> str:
    """The full results/simulation_summary.md text, built only from ``results``."""
    n_respondents = int(results["n_respondents"].iloc[0])
    careless_counts = results.drop_duplicates("rate").set_index("rate")["n_careless"]
    counts = ", ".join(
        f"{_rate_label(rate)} = {int(n)}" for rate, n in careless_counts.sort_index().items()
    )
    evaluated = [m for m in SCORE_MEASURES if m in set(results["measure"])]
    not_computed = [m for m in SCORE_MEASURES if m not in set(results["measure"])]

    parts = [
        "# Simulation study results",
        "",
        "Generated by `python evaluation/run_simulation.py` (from `backend/`). Do not edit by "
        "hand; rerun the script instead. Raw rows: `results/simulation_results.csv`.",
        "",
        "## Setup",
        "",
        f"- Base data: bfi complete cases on the 25 items, **{n_respondents}** respondents.",
        f"- Patterns: {', '.join(PATTERNS)} (definitions in `evaluation/simulate.py`).",
        f"- Contamination rates: {', '.join(_rate_label(r) for r in RATES)} "
        f"(careless respondents: {counts}).",
        f"- Repetitions: {n_reps} per pattern and rate, seeds 0–{n_reps - 1}. Cells show the "
        "mean ± SD (ddof = 1) over repetitions.",
        f"- Scores evaluated: {', '.join(MEASURE_LABELS[m] for m in evaluated)}.",
    ]
    if not_computed:
        parts.append(
            "- Not computed on this data, so not evaluated: "
            + ", ".join(MEASURE_LABELS[m] for m in not_computed)
            + "."
        )
    parts += [f"- {sentence}" for sentence in partial_availability(results)]
    parts += [
        "",
        "How to read the numbers:",
        "",
        "- **ROC-AUC**: the chance that a randomly chosen careless respondent scores as more "
        "suspicious than a randomly chosen attentive one. 0.5 is chance, 1 is perfect.",
        "- **PR-AUC** (average precision): how precise the ranking stays as more careless "
        "respondents are found. Chance level equals the contamination rate (0.05, 0.10 or "
        "0.20), so the same PR-AUC means more at a lower rate.",
        "- A respondent whose index could not be computed is ranked as least suspicious for "
        "that index, because the index cannot flag them. See the last table for how often "
        "this happened.",
        "",
    ]
    for pattern in PATTERNS:
        if pattern not in set(results["pattern"]):
            continue
        parts += [
            f"## Pattern: {pattern}",
            "",
            "**PR-AUC**",
            "",
            score_table(results, pattern, "pr_auc"),
            "",
            "**ROC-AUC**",
            "",
            score_table(results, pattern, "roc_auc"),
            "",
        ]
    parts += [
        "## Default flag rule",
        "",
        "Recall: share of careless respondents flagged by at least one rule. Precision: share "
        "of flagged respondents who were careless.",
        "",
        flag_table(results),
        "",
        "## Each flag rule on its own",
        "",
        "The same recall and precision for each rule separately, at its default threshold. "
        "Precision is low for a rule that also fires on many attentive respondents.",
        "",
    ]
    for rule in DEFAULT_RULES:
        measure = RULE_PREFIX + rule
        if measure in set(results["measure"]):
            parts += [f"### {MEASURE_LABELS[rule]} rule", "", flag_table(results, measure), ""]
    parts += [
        "## Careless respondents an index could not score",
        "",
        "Mean share over the rates and repetitions in which the index was computed.",
        "",
        missing_table(results),
        "",
        "## Limitations",
        "",
        "- The base data contains some genuinely careless respondents, labelled 0 here. "
        "Flagging them counts as a false positive, which slightly understates precision.",
        "- Simulated patterns are cleaner than real careless responding (real respondents "
        "drift in and out of attention). These results show what the indices can detect, not "
        "how well they work on real careless respondents.",
        "- Results are for one dataset (25 items, 6-point scale, five 5-item scales). Other "
        "surveys can give different results.",
        "",
    ]
    return "\n".join(parts)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--reps", type=int, default=N_REPS, help="repetitions per condition")
    parser.add_argument("--out", type=Path, default=RESULTS_DIR, help="output directory")
    args = parser.parse_args(argv)
    if args.reps < 2:
        parser.error("--reps must be at least 2, so that a standard deviation exists.")
    if not BFI_CSV.exists():
        sys.exit("data/sample/bfi.csv not found. Run: python scripts/download_data.py")

    schema = SurveySchema.load(BFI_SCHEMA)
    base = base_data(BFI_CSV, schema)
    n_runs = len(PATTERNS) * len(RATES) * args.reps
    print(f"Running {n_runs} simulations on {len(base)} respondents...")
    results = run_all(base, schema, args.reps)

    args.out.mkdir(parents=True, exist_ok=True)
    csv_path = args.out / "simulation_results.csv"
    md_path = args.out / "simulation_summary.md"
    results.to_csv(csv_path, index=False, float_format="%.6f", lineterminator="\n")
    md_path.write_text(summary_markdown(results, args.reps), encoding="utf-8", newline="\n")
    print(f"Wrote {csv_path.relative_to(BACKEND_DIR)} ({len(results)} rows)")
    print(f"Wrote {md_path.relative_to(BACKEND_DIR)}")


if __name__ == "__main__":
    main()
