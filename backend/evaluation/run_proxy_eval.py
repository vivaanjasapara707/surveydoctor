"""Real-data proxy evaluation on the DASS dataset (BLUEPRINT §5.2, §7.8).

The DASS online survey ended with a vocabulary checklist that included three made-up words
(VCL6, VCL9, VCL12). A respondent who ticked "I know this word" for any of them gets
``careless_proxy = 1``. This script checks how well SurveyDoctor's indices, composite and
flags agree with that proxy.

Claiming fake words measures overclaiming, which overlaps with careless responding but is
not the same thing. The results are agreement with a validity proxy, not accuracy.

Run from backend/ (the dataset is never committed; see BLUEPRINT §5.2):

    python evaluation/run_proxy_eval.py

Writes ``results/proxy_eval.csv`` and ``results/proxy_eval_summary.md``. If
``data/raw/dass/`` does not exist, prints how to obtain the data and exits with code 0.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from evaluation.run_simulation import MEASURE_LABELS  # noqa: E402
from evaluation.simulate import (  # noqa: E402
    FLAG_MEASURE,
    RULE_PREFIX,
    SCORE_MEASURES,
    evaluate_indices,
)
from surveydoctor.careless import compute_indices, longstring  # noqa: E402
from surveydoctor.flagging import DEFAULT_RULES  # noqa: E402
from surveydoctor.io import prepare_data  # noqa: E402
from surveydoctor.schema import SurveySchema  # noqa: E402

DASS_DIR = BACKEND_DIR / "data" / "raw" / "dass"
RESULTS_DIR = BACKEND_DIR / "results"

N_ITEMS = 42
ITEMS = [f"Q{i}A" for i in range(1, N_ITEMS + 1)]
POSITIONS = [f"Q{i}I" for i in range(1, N_ITEMS + 1)]
ELAPSED_MS = [f"Q{i}E" for i in range(1, N_ITEMS + 1)]
FAKE_WORDS = ("VCL6", "VCL9", "VCL12")

# Item numbers per scale, from the official DASS scoring template (BLUEPRINT §5.2).
DASS_SCALES: dict[str, list[int]] = {
    "Depression": [3, 5, 10, 13, 16, 17, 21, 24, 26, 31, 34, 37, 38, 42],
    "Anxiety": [2, 4, 7, 9, 15, 19, 20, 23, 25, 28, 30, 36, 40, 41],
    "Stress": [1, 6, 8, 11, 12, 14, 18, 22, 27, 29, 32, 33, 35, 39],
}

HOW_TO_GET_DATA = f"""The DASS dataset was not found in {DASS_DIR}.
The proxy evaluation is optional. To run it:
  1. Download DASS_data_21.02.19.zip from https://openpsychometrics.org/_rawdata/
  2. Check the licence and the codebook (docs/verification_log.md, items 6-8).
  3. Unzip it into {DASS_DIR} (it is gitignored; never commit it).
  4. Run again: python evaluation/run_proxy_eval.py"""


def find_data_file(root: Path) -> Path | None:
    """The first ``data.csv`` anywhere under ``root`` (the zip unpacks into a subfolder)."""
    if not root.is_dir():
        return None
    matches = sorted(root.rglob("data.csv"))
    return matches[0] if matches else None


def dass_schema() -> SurveySchema:
    """DASS-42 as a SurveySchema: 42 items on a 1-4 scale, three scales, no reverse items,
    total item time in seconds as the duration column."""
    return SurveySchema(
        items=list(ITEMS),
        scales={name: [f"Q{i}A" for i in numbers] for name, numbers in DASS_SCALES.items()},
        reverse_items=[],
        scale_min=1,
        scale_max=4,
        id_column="id",
        duration_column="duration_seconds",
        duration_unit="seconds",
    )


def careless_proxy(raw: pd.DataFrame) -> pd.Series:
    """1 if the respondent ticked at least one of the three fake words, else 0."""
    return (raw[list(FAKE_WORDS)] == 1).any(axis=1).astype(int).rename("careless_proxy")


def duration_seconds(raw: pd.DataFrame) -> pd.Series:
    """Total time on the 42 items: the sum of the per-item times (milliseconds) / 1000."""
    return (raw[ELAPSED_MS].sum(axis=1, min_count=N_ITEMS) / 1000).rename("duration_seconds")


def survey_frame(raw: pd.DataFrame) -> pd.DataFrame:
    """The columns SurveyDoctor needs: row-number ID, the 42 answers, and the duration."""
    frame = raw[ITEMS].copy()
    frame.insert(0, "id", np.arange(1, len(raw) + 1))
    frame["duration_seconds"] = duration_seconds(raw)
    return frame


def presentation_order(raw: pd.DataFrame) -> pd.DataFrame:
    """Each respondent's answers in the order they were shown (the survey shuffled items).

    Column ``pos1`` holds the answer to the item shown first, and so on. Raises ValueError
    if a respondent's positions are not exactly 1 to 42.
    """
    positions = raw[POSITIONS].to_numpy()
    expected = np.arange(1, N_ITEMS + 1)
    valid = (np.sort(positions, axis=1) == expected).all(axis=1)
    if not valid.all():
        raise ValueError(
            f"{int((~valid).sum())} respondents do not have positions 1 to {N_ITEMS} in the "
            "Q#I columns, so their presentation order is unknown."
        )
    ordered = np.empty(positions.shape, dtype=float)
    rows = np.arange(len(raw))[:, None]
    ordered[rows, positions.astype(int) - 1] = raw[ITEMS].to_numpy(dtype=float)
    return pd.DataFrame(ordered, index=raw.index, columns=[f"pos{j}" for j in expected])


def run_proxy_eval(raw: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Compute the indices on DASS, with longstring in presentation order, and score them
    against the fake-word proxy.

    Returns one row per measure (as in the simulation) and a dict of descriptive counts.
    """
    schema = dass_schema()
    prepared = prepare_data(survey_frame(raw), schema)
    labels = careless_proxy(raw).loc[prepared.raw_items.index]
    indices = compute_indices(prepared, schema)
    indices["longstring"] = longstring(presentation_order(raw.loc[prepared.raw_items.index]))
    results = pd.DataFrame(evaluate_indices(indices, labels, n_items=N_ITEMS))
    info = {
        "n_file": len(raw),
        "n_respondents": len(prepared.raw_items),
        "n_proxy": int(labels.sum()),
        "base_rate": float(labels.mean()),
        "median_seconds": float(prepared.durations_seconds.median()),
    }
    results.insert(0, "n_respondents", info["n_respondents"])
    results.insert(1, "n_proxy", info["n_proxy"])
    return results, info


def _fmt(value: float) -> str:
    return "–" if pd.isna(value) else f"{value:.3f}"


def summary_markdown(results: pd.DataFrame, info: dict, data_file: str) -> str:
    """The results/proxy_eval_summary.md text, built only from ``results`` and ``info``."""
    by_measure = results.set_index("measure")
    score_lines = [
        "| Measure | ROC-AUC | PR-AUC | Proxy-positive respondents without a value |",
        "|---|---|---|---|",
    ]
    for measure in SCORE_MEASURES:
        if measure in by_measure.index:
            row = by_measure.loc[measure]
            score_lines.append(
                f"| {MEASURE_LABELS[measure]} | {_fmt(row['roc_auc'])} | {_fmt(row['pr_auc'])} "
                f"| {row['missing_careless']:.1%} |"
            )
    flag_lines = [
        "| Flag | Recall | Precision | Share of all respondents flagged |",
        "|---|---|---|---|",
    ]
    flag_rows = [(FLAG_MEASURE, MEASURE_LABELS[FLAG_MEASURE])] + [
        (RULE_PREFIX + rule, f"{MEASURE_LABELS[rule]} rule only") for rule in DEFAULT_RULES
    ]
    for measure, label in flag_rows:
        if measure in by_measure.index:
            row = by_measure.loc[measure]
            flag_lines.append(
                f"| {label} | {_fmt(row['recall'])} | {_fmt(row['precision'])} "
                f"| {row['share_flagged']:.1%} |"
            )
    not_evaluated = [MEASURE_LABELS[m] for m in SCORE_MEASURES if m not in by_measure.index]

    parts = [
        "# Proxy evaluation on the DASS dataset",
        "",
        "Generated by `python evaluation/run_proxy_eval.py` (from `backend/`). Do not edit by "
        "hand; rerun the script instead. Raw rows: `results/proxy_eval.csv`.",
        "",
        "**What this measures:** agreement between SurveyDoctor's careless-response indices and "
        "a validity proxy (claiming to know at least one of three made-up words). Claiming fake "
        "words measures overclaiming, which overlaps with careless responding but is not the "
        "same thing. These numbers are agreement with a proxy, not accuracy.",
        "",
        "## Setup",
        "",
        f"- Data: `{data_file}` (openpsychometrics.org DASS dataset, 2017–2019), "
        f"{info['n_file']} rows; {info['n_respondents']} respondents analysed.",
        f"- Proxy: {info['n_proxy']} respondents ({info['base_rate']:.1%}) claimed at least one "
        f"fake word ({', '.join(FAKE_WORDS)}). This base rate is the chance level for PR-AUC.",
        "- Scales: Depression, Anxiety and Stress, 14 items each, 1–4 answers, no reverse items "
        "(item mapping from the official DASS scoring template).",
        "- Longstring is computed in the order each respondent saw the items. The survey "
        "showed the 42 items in a different random order to each person (columns Q#I).",
        f"- Response time: the sum of the per-item times; median {info['median_seconds']:.0f} s "
        "for all 42 items.",
    ]
    if not_evaluated:
        parts.append("- Not computed on this data: " + ", ".join(not_evaluated) + ".")
    parts += [
        "",
        "## Scores",
        "",
        "ROC-AUC: the chance that a proxy-positive respondent scores as more suspicious than "
        "a proxy-negative one (0.5 = chance). A respondent whose index could not be computed "
        "is ranked as least suspicious for that index.",
        "",
        *score_lines,
        "",
        "## Flags",
        "",
        "Recall: share of proxy-positive respondents flagged. Precision: share of flagged "
        "respondents who are proxy-positive.",
        "",
        *flag_lines,
        "",
        "## Limitations",
        "",
        "- The proxy is imperfect in both directions: a careful respondent can overclaim "
        "knowing a word, and a careless respondent can leave the fake words unticked. The "
        "checklist also came after the DASS items, so it captures attention at a later point.",
        "- The dataset only contains people who said their answers were accurate and could be "
        "used for research, so the most openly careless respondents are already excluded.",
        "- Even-odd consistency rests on only 3 scales per respondent here, so it is noisy.",
        "- Results are for one survey (42 items, 4-point scale, self-selected online sample).",
        "",
    ]
    return "\n".join(parts)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--data-dir", type=Path, default=DASS_DIR, help="folder with data.csv")
    parser.add_argument("--out", type=Path, default=RESULTS_DIR, help="output directory")
    args = parser.parse_args(argv)

    data_file = find_data_file(args.data_dir)
    if data_file is None:
        print(HOW_TO_GET_DATA)
        return 0

    raw = pd.read_csv(data_file, sep="\t")
    print(f"Evaluating {len(raw)} respondents from {data_file.name}...")
    results, info = run_proxy_eval(raw)
    try:
        shown_path = data_file.relative_to(BACKEND_DIR).as_posix()
    except ValueError:
        shown_path = data_file.name

    args.out.mkdir(parents=True, exist_ok=True)
    csv_path = args.out / "proxy_eval.csv"
    md_path = args.out / "proxy_eval_summary.md"
    results.to_csv(csv_path, index=False, float_format="%.6f", lineterminator="\n")
    md_path.write_text(summary_markdown(results, info, shown_path), encoding="utf-8", newline="\n")
    print(f"Wrote {csv_path} ({len(results)} rows)")
    print(f"Wrote {md_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
