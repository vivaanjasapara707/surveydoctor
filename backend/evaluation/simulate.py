"""Simulation study: how well the careless-response indices find known careless respondents.

Real survey data has no labels saying who was careless. The simulation creates them: it
takes real answers (bfi complete cases), replaces the answers of randomly chosen respondents
with a known careless pattern, labels those respondents 1 and everyone else 0, and checks
how well each index, the composite score and the default flag rule pick out the label-1 rows.

Patterns (BLUEPRINT §7.7):

* random       - every answer drawn uniformly from the scale;
* straightline - one random answer repeated for every item;
* patterned    - the sequence min, min+1, ..., max repeated, starting at a random point;
* midpoint     - the middle answer everywhere (on an even-point scale, the lower or upper
                 middle, chosen at random per respondent);
* partial      - the first half of the items kept, the rest answered at random.

Limitations: simulated careless patterns are cleaner than real ones, so the results show
what the indices *can* detect, not how well they work on real careless respondents. The
base data also contains some genuinely careless respondents labelled 0, which slightly
understates precision.
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, precision_score, recall_score, roc_auc_score

from surveydoctor.careless import INDEX_DIRECTIONS, compute_indices
from surveydoctor.flagging import (
    COMPOSITE_INDICES,
    DEFAULT_RULES,
    apply_flags,
    composite_score,
)
from surveydoctor.io import load_csv, prepare_data
from surveydoctor.schema import SurveySchema

PATTERNS: tuple[str, ...] = ("random", "straightline", "patterned", "midpoint", "partial")
RATES: tuple[float, ...] = (0.05, 0.10, 0.20)
N_REPS = 20

# Scores evaluated with ROC-AUC and PR-AUC, in report order: the composite, then each index
# that enters it. IRV is left out because its careless direction is ambiguous.
SCORE_MEASURES: tuple[str, ...] = ("composite", *COMPOSITE_INDICES)
FLAG_MEASURE = "flagged"
# Each flag rule is also evaluated on its own, as measure "rule_<name>".
RULE_PREFIX = "rule_"


def base_data(csv_path: str | Path, schema: SurveySchema) -> pd.DataFrame:
    """Respondents who answered every item, with the ID column and the items as given.

    The answers are the raw (not reverse-scored) values. The careless patterns replace raw
    answers, because that is what a careless respondent would type.
    """
    prepared = prepare_data(load_csv(csv_path), schema)
    raw = prepared.raw_items[schema.items].dropna()
    if schema.id_column is not None:
        raw.insert(0, schema.id_column, prepared.meta.loc[raw.index, schema.id_column])
    return raw.reset_index(drop=True)


def careless_answers(
    pattern: str,
    original: np.ndarray,
    scale_min: int,
    scale_max: int,
    rng: np.random.Generator,
) -> np.ndarray:
    """Replacement answers for the selected respondents (rows of ``original``) in item order.

    ``original`` is only used by ``partial``, which keeps the first floor(k / 2) of the k
    items and answers the rest at random.
    """
    n_rows, n_items = original.shape
    n_points = scale_max - scale_min + 1
    if pattern == "random":
        return rng.integers(scale_min, scale_max + 1, size=(n_rows, n_items))
    if pattern == "straightline":
        constant = rng.integers(scale_min, scale_max + 1, size=(n_rows, 1))
        return np.repeat(constant, n_items, axis=1)
    if pattern == "patterned":
        offset = rng.integers(0, n_points, size=(n_rows, 1))
        return scale_min + (offset + np.arange(n_items)) % n_points
    if pattern == "midpoint":
        lower_middle = scale_min + (n_points - 1) // 2
        if n_points % 2 == 1:
            middle = np.full((n_rows, 1), lower_middle)
        else:
            middle = lower_middle + rng.integers(0, 2, size=(n_rows, 1))
        return np.repeat(middle, n_items, axis=1)
    if pattern == "partial":
        kept = n_items // 2
        answers = original.copy()
        answers[:, kept:] = rng.integers(scale_min, scale_max + 1, size=(n_rows, n_items - kept))
        return answers
    raise ValueError(f"Unknown pattern '{pattern}'. Use one of: {', '.join(PATTERNS)}.")


def n_contaminated(n_rows: int, rate: float) -> int:
    """Number of respondents to replace: rate × n, rounded half up."""
    return math.floor(rate * n_rows + 0.5)


def contaminate(
    base: pd.DataFrame,
    schema: SurveySchema,
    pattern: str,
    rate: float,
    rng: np.random.Generator,
) -> tuple[pd.DataFrame, pd.Series]:
    """Replace a random share of respondents with a careless pattern.

    The respondents are chosen first (without replacement), then their answers are
    generated, both from ``rng``. With a fresh generator from the same seed, the same
    respondents are chosen for every pattern at a given rate.

    Returns:
        The contaminated data (same columns as ``base``) and the labels (1 = replaced).
    """
    if not 0 < rate < 1:
        raise ValueError(f"rate must be between 0 and 1, got {rate}.")
    rows = rng.choice(len(base), size=n_contaminated(len(base), rate), replace=False)
    data = base.copy()
    items = list(schema.items)
    original = data.loc[rows, items].to_numpy(dtype=float)
    data.loc[rows, items] = careless_answers(
        pattern, original, schema.scale_min, schema.scale_max, rng
    ).astype(float)
    labels = pd.Series(0, index=data.index, name="careless")
    labels[rows] = 1
    return data, labels


def oriented_score(values: pd.Series, measure: str) -> pd.Series:
    """Scores turned so that higher means more careless; NaN becomes the least careless.

    A respondent whose index cannot be computed is never flagged by that index, so for
    detection they rank below everyone with a value.
    """
    if measure == "composite":
        oriented = values.astype(float)
    elif INDEX_DIRECTIONS[measure] == "high":
        oriented = values.astype(float)
    elif INDEX_DIRECTIONS[measure] == "low":
        oriented = -values.astype(float)
    else:
        raise ValueError(f"Index '{measure}' has no single careless direction.")
    lowest = oriented.min() if oriented.notna().any() else 0.0
    return oriented.fillna(lowest - 1.0)


def score_metrics(values: pd.Series, labels: pd.Series, measure: str) -> dict[str, float]:
    """ROC-AUC and PR-AUC of one score against the labels.

    ROC-AUC: the probability that a random careless respondent scores higher than a random
    attentive one (0.5 = no better than chance). PR-AUC (average precision, scikit-learn's
    estimate): the average precision over all recall levels; chance level is the share of
    careless respondents, so it is read against the contamination rate. Also returns
    ``missing_careless``, the share of careless respondents without a value for this score.
    """
    score = oriented_score(values, measure)
    careless = labels == 1
    return {
        "roc_auc": float(roc_auc_score(labels, score)),
        "pr_auc": float(average_precision_score(labels, score)),
        "missing_careless": float(values[careless].isna().mean()),
    }


def flag_metrics(flagged: pd.Series, labels: pd.Series) -> dict[str, float]:
    """Recall (share of careless respondents flagged) and precision (share of flagged
    respondents who are careless) of a yes/no flag. Precision is 0 if nobody is flagged."""
    predicted = flagged.astype(bool).astype(int)
    return {
        "recall": float(recall_score(labels, predicted, zero_division=0)),
        "precision": float(precision_score(labels, predicted, zero_division=0)),
        "share_flagged": float(predicted.mean()),
    }


def evaluate(data: pd.DataFrame, labels: pd.Series, schema: SurveySchema) -> list[dict]:
    """Run the app's own index, composite and flag code on contaminated data and score it.

    Returns one record per measure: every index in :data:`SCORE_MEASURES` that was computed
    for at least one respondent (with ROC-AUC, PR-AUC and the share of careless respondents
    it has no value for), the default flag rule (with recall and precision), and each
    applied rule on its own (``rule_<name>``, also recall and precision).
    """
    prepared = prepare_data(data, schema)
    labels = labels.loc[prepared.raw_items.index]
    indices = compute_indices(prepared, schema)
    scores = indices.assign(composite=composite_score(indices))
    flags = apply_flags(indices, n_items=len(schema.items))

    records: list[dict] = []
    for measure in SCORE_MEASURES:
        if measure in scores and scores[measure].notna().any():
            records.append({"measure": measure, **score_metrics(scores[measure], labels, measure)})
    records.append({"measure": FLAG_MEASURE, **flag_metrics(flags["flagged"], labels)})
    for rule in DEFAULT_RULES:
        if rule in flags:
            records.append({"measure": RULE_PREFIX + rule, **flag_metrics(flags[rule], labels)})
    return records


def run_condition(
    base: pd.DataFrame, schema: SurveySchema, pattern: str, rate: float, seed: int
) -> list[dict]:
    """One repetition of one pattern at one contamination rate, with its own seed."""
    rng = np.random.default_rng(seed)
    data, labels = contaminate(base, schema, pattern, rate, rng)
    condition = {
        "pattern": pattern,
        "rate": rate,
        "seed": seed,
        "n_respondents": len(data),
        "n_careless": int(labels.sum()),
    }
    return [{**condition, **record} for record in evaluate(data, labels, schema)]
