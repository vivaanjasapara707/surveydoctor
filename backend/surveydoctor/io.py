"""Loading, cleaning and scoring survey data.

This module turns an uploaded CSV into clean numeric item answers:

* reads the CSV robustly (UTF-8 or Windows encoding, blank/NA as missing);
* recognises common text answer labels ("Strongly agree") and proposes a label -> number map;
* detects columns holding personal information (emails, names) so they are never analysed
  or downloaded;
* assigns short codes (Q1, Q2, ...) to long question headers;
* converts answers to numbers, counting (never silently dropping) blank and invalid answers;
* reverse-scores the items the user declared, and computes scale scores.
"""

from __future__ import annotations

import csv
import io
import math
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import BinaryIO, Literal

import numpy as np
import pandas as pd

from surveydoctor.schema import SurveySchema


class DataError(ValueError):
    """Raised when uploaded data cannot be used. The message explains the problem and the fix."""


# Cell values treated as missing (after trimming whitespace). "None" is deliberately not
# included because it can be a genuine free-text answer.
NA_VALUES: tuple[str, ...] = ("", "NA", "N/A", "n/a", "na", "NaN", "nan", "null", "NULL", "#N/A")

IssueKind = Literal[
    "missing_answers",
    "invalid_answers",
    "empty_rows_removed",
    "personal_columns_excluded",
    "invalid_durations",
]


@dataclass
class DataIssue:
    """A counted data problem, reported to the user (nothing is dropped silently)."""

    kind: IssueKind
    count: int
    message: str
    column: str | None = None
    examples: list[str] = field(default_factory=list)


@dataclass
class PreparedData:
    """Survey data ready for analysis.

    Attributes:
        raw_items: Item answers as given (numeric; NaN for missing or invalid answers).
        scored_items: Same answers with reverse items recoded as scale_min + scale_max - x.
        meta: All non-item columns, minus columns that look like personal information.
        durations_seconds: Completion time in seconds, if a duration column was declared.
        issues: Counts of missing/invalid answers, removed rows and excluded columns.

    The index of every frame is the respondent's 0-based row position in the uploaded CSV
    (data rows only, header excluded), so results can always be traced back to the file.
    """

    raw_items: pd.DataFrame
    scored_items: pd.DataFrame
    meta: pd.DataFrame
    durations_seconds: pd.Series | None
    issues: list[DataIssue]


# --------------------------------------------------------------------------------------
# Answer labels
# --------------------------------------------------------------------------------------

# Each label set lists its points from lowest to highest. A point is a tuple of accepted
# spellings (already normalised); the first spelling is the canonical one.
LABEL_SETS: dict[str, list[tuple[str, ...]]] = {
    "agreement_5": [
        ("strongly disagree",),
        ("disagree",),
        ("neither agree nor disagree", "neither agree or disagree", "neutral"),
        ("agree",),
        ("strongly agree",),
    ],
    "frequency_5": [
        ("never",),
        ("rarely",),
        ("sometimes",),
        ("often",),
        ("always",),
    ],
    "satisfaction_5": [
        ("very dissatisfied",),
        ("dissatisfied",),
        ("neither satisfied nor dissatisfied", "neither satisfied or dissatisfied", "neutral"),
        ("satisfied",),
        ("very satisfied",),
    ],
    "agreement_7": [
        ("strongly disagree",),
        ("disagree",),
        ("somewhat disagree", "slightly disagree"),
        ("neither agree nor disagree", "neither agree or disagree", "neutral"),
        ("somewhat agree", "slightly agree"),
        ("agree",),
        ("strongly agree",),
    ],
    "frequency_7": [
        ("never",),
        ("rarely",),
        ("occasionally",),
        ("sometimes",),
        ("frequently",),
        ("usually",),
        ("always", "every time"),
    ],
    "satisfaction_7": [
        ("very dissatisfied",),
        ("dissatisfied",),
        ("somewhat dissatisfied", "slightly dissatisfied"),
        ("neither satisfied nor dissatisfied", "neither satisfied or dissatisfied", "neutral"),
        ("somewhat satisfied", "slightly satisfied"),
        ("satisfied",),
        ("very satisfied",),
    ],
}

_KNOWN_LABELS: frozenset[str] = frozenset(
    spelling for points in LABEL_SETS.values() for point in points for spelling in point
)


@dataclass
class LabelDetection:
    """Result of looking for text answer labels in item columns.

    Attributes:
        label_set: Name of the recognised label set (e.g. "agreement_5"), or None.
        label_map: Proposed label -> number map for the user to confirm, or None.
        scale_min: Lowest value implied by the label set (always 1), or None.
        scale_max: Highest value implied by the label set (5 or 7), or None.
        unrecognised: Text answers that are not part of the chosen label set. These are
            reported for the user to map; they are never guessed.
        alternatives: Other label sets that fit the observed labels equally well (e.g. a
            5-point and a 7-point agreement scale when "somewhat" never occurs).
    """

    label_set: str | None
    label_map: dict[str, int] | None
    scale_min: int | None
    scale_max: int | None
    unrecognised: list[str]
    alternatives: list[str]


def normalize_label(value: object) -> str:
    """Lower-case a label and collapse whitespace: " Strongly  AGREE " -> "strongly agree"."""
    return " ".join(str(value).split()).lower()


def _parse_number(text: str) -> float | None:
    """Return text as a finite float, or None if it is not a number."""
    try:
        number = float(text)
    except ValueError:
        return None
    return number if math.isfinite(number) else None


def _text_values(series: pd.Series) -> list[str]:
    """Distinct non-missing, non-numeric values of a column, trimmed."""
    values: list[str] = []
    for value in series.dropna().unique():
        if isinstance(value, (int, float, np.number)) and not isinstance(value, bool):
            continue
        text = str(value).strip()
        if text and _parse_number(text) is None:
            values.append(text)
    return values


def detect_label_scale(df: pd.DataFrame, columns: list[str]) -> LabelDetection:
    """Recognise common text answer labels in the given columns and propose a label map.

    Supports agreement, frequency and satisfaction labels on 5- and 7-point scales;
    matching ignores case and extra whitespace. Numeric answers are ignored here.

    The label set matching the most distinct observed labels wins. On a tie the shorter
    (5-point) set is preferred and the others are listed in ``alternatives`` so the user
    can switch. Labels outside the chosen set are listed in ``unrecognised``; they are
    never guessed.
    """
    observed: dict[str, str] = {}
    for column in columns:
        for text in _text_values(df[column]):
            observed.setdefault(normalize_label(text), text)

    if not observed:
        return LabelDetection(None, None, None, None, [], [])

    scores: dict[str, int] = {}
    for name, points in LABEL_SETS.items():
        spellings = {s for point in points for s in point}
        scores[name] = sum(1 for label in observed if label in spellings)

    best = max(scores.values())
    if best == 0:
        return LabelDetection(None, None, None, None, sorted(observed.values()), [])

    # LABEL_SETS lists 5-point sets first, so a stable sort on size keeps that preference.
    tied = sorted((n for n, s in scores.items() if s == best), key=lambda n: len(LABEL_SETS[n]))
    chosen = tied[0]
    points = LABEL_SETS[chosen]

    label_map: dict[str, int] = {}
    lookup: dict[str, int] = {}
    for value, point in enumerate(points, start=1):
        label_map[point[0]] = value
        for spelling in point:
            lookup[spelling] = value
    for label in observed:
        if label in lookup:
            label_map[label] = lookup[label]

    unrecognised = sorted(text for label, text in observed.items() if label not in lookup)
    return LabelDetection(
        label_set=chosen,
        label_map=label_map,
        scale_min=1,
        scale_max=len(points),
        unrecognised=unrecognised,
        alternatives=tied[1:],
    )


# --------------------------------------------------------------------------------------
# Personal columns, short codes, inspection
# --------------------------------------------------------------------------------------

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_PERSONAL_HEADER_RE = re.compile(
    r"\b(e-?mail|name|names|surname|username|phone|mobile|address)\b", re.IGNORECASE
)
_SHORT_CODE_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_.]{0,15}$")
_MAX_RATING_POINTS = 11
_MAX_RATING_ABS = 10


def is_rating_like(series: pd.Series, min_share: float = 0.8) -> bool:
    """True if at least ``min_share`` of the non-missing answers look like rating answers.

    A rating answer is a known text label or a whole number from -10 to 10; the column may
    hold at most 11 distinct numbers (this covers 0-10 scales and excludes e.g. ages). The
    share rule lets a column with an occasional typo still count. Used to suggest item
    columns and to stop a rating question that mentions e.g. "email" in its wording from
    being mistaken for a personal-information column.
    """
    counts = series.dropna().value_counts()
    if counts.empty:
        return False
    numbers: set[float] = set()
    n_rating = 0
    for value, count in counts.items():
        text = str(value).strip()
        number = _parse_number(text)
        if number is not None:
            if number == round(number) and abs(number) <= _MAX_RATING_ABS:
                numbers.add(number)
                n_rating += int(count)
        elif normalize_label(text) in _KNOWN_LABELS:
            n_rating += int(count)
    return bool(len(numbers) <= _MAX_RATING_POINTS and n_rating >= min_share * counts.sum())


def looks_personal(header: str, series: pd.Series) -> bool:
    """True if a column looks like personal information (emails or names).

    A column is personal if at least half of its non-missing values are email addresses,
    or if its header mentions email, name, phone, etc. and its values are not rating answers.
    """
    values = [str(v).strip() for v in series.dropna()]
    if values and sum(bool(_EMAIL_RE.match(v)) for v in values) >= 0.5 * len(values):
        return True
    return bool(_PERSONAL_HEADER_RE.search(str(header))) and not is_rating_like(series)


def detect_personal_columns(df: pd.DataFrame) -> list[str]:
    """Columns that look like personal information, in file order."""
    return [str(c) for c in df.columns if looks_personal(str(c), df[c])]


def assign_short_codes(columns: list[str]) -> dict[str, str]:
    """Give each column a short code; return code -> original header, in column order.

    Headers that are already short identifiers (e.g. "A1", "age", "Timestamp") keep their
    name. Other headers (usually full question text) get Q1, Q2, ... in order, skipping
    any code already used by another column.
    """
    used = {c for c in columns if _SHORT_CODE_RE.match(c)}
    codes: dict[str, str] = {}
    counter = 1
    for column in columns:
        if _SHORT_CODE_RE.match(column):
            codes[column] = column
            continue
        while f"Q{counter}" in used:
            counter += 1
        code = f"Q{counter}"
        used.add(code)
        codes[code] = column
        counter += 1
    return codes


def apply_short_codes(df: pd.DataFrame, question_text: dict[str, str]) -> pd.DataFrame:
    """Rename columns from original headers to short codes using a code -> header map."""
    renames = {h: c for c, h in question_text.items() if h in df.columns and h != c}
    clashes = [c for c in renames.values() if c in df.columns and c not in renames]
    if clashes:
        raise DataError(
            f"The short code(s) {', '.join(clashes)} are already used as column headers in the "
            "CSV. Choose different codes."
        )
    return df.rename(columns=renames)


@dataclass
class ColumnInfo:
    """Summary of one uploaded column, shown to the user before they build the schema."""

    code: str | None
    header: str
    n_missing: int
    n_distinct: int
    distinct_values: list[str]
    suggested_item: bool
    looks_personal: bool


def inspect_columns(df: pd.DataFrame, max_values: int = 20) -> list[ColumnInfo]:
    """Describe every column: short code, distinct values, item suggestion, personal flag.

    Personal columns get no short code and their values are never listed.
    """
    personal = set(detect_personal_columns(df))
    codes = assign_short_codes([str(c) for c in df.columns if str(c) not in personal])
    header_to_code = {h: c for c, h in codes.items()}
    infos: list[ColumnInfo] = []
    for column in df.columns:
        header = str(column)
        series = df[column]
        is_personal = header in personal
        distinct = series.dropna().unique()
        shown = [] if is_personal else sorted(str(v) for v in distinct)[:max_values]
        infos.append(
            ColumnInfo(
                code=header_to_code.get(header),
                header=header,
                n_missing=int(series.isna().sum()),
                n_distinct=len(distinct),
                distinct_values=shown,
                suggested_item=not is_personal and len(distinct) >= 2 and is_rating_like(series),
                looks_personal=is_personal,
            )
        )
    return infos


def preview_rows(df: pd.DataFrame, n: int = 10) -> pd.DataFrame:
    """First n rows with personal columns removed."""
    return df.drop(columns=detect_personal_columns(df)).head(n)


# --------------------------------------------------------------------------------------
# CSV loading
# --------------------------------------------------------------------------------------


def _read_bytes(source: str | Path | bytes | BinaryIO) -> bytes:
    if isinstance(source, bytes):
        return source
    if isinstance(source, (str, Path)):
        return Path(source).read_bytes()
    return source.read()


def _decode(raw: bytes) -> str:
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise DataError(
        "The file's text encoding could not be read. Save it as 'CSV UTF-8' and upload it again."
    )


def load_csv(source: str | Path | bytes | BinaryIO) -> pd.DataFrame:
    """Read a survey CSV into a DataFrame of text values.

    * A header row is required; headers are trimmed and must be unique.
    * Every cell is kept as text (labels and numbers alike); conversion happens later.
    * Cells are trimmed; blank cells and NA-style values become missing (NaN).
    * Columns with no header and no data (e.g. a trailing comma in Excel exports) are
      ignored because they hold nothing; a header-less column with data is an error.
    * A row with more fields than the header is an error (its extra answers would be lost);
      a row with fewer fields is padded with missing values. Blank lines are skipped.
    """
    text = _decode(_read_bytes(source))
    if not text.strip():
        raise DataError("The file is empty. Export your responses as CSV and upload that file.")

    reader = csv.reader(io.StringIO(text, newline=""))
    try:
        header = next(reader)
        rows: list[list[str]] = []
        for row in reader:
            if not row:
                continue
            if len(row) > len(header):
                raise DataError(
                    f"Line {reader.line_num} has {len(row)} values but the header has "
                    f"{len(header)} columns. The file could not be read as a CSV table; check "
                    "for unquoted commas inside answers."
                )
            rows.append(row + [""] * (len(header) - len(row)))
    except csv.Error as exc:
        raise DataError(f"The file could not be read as a CSV table: {exc}.") from exc

    names = [h.strip() for h in header]
    duplicates = sorted(h for h, n in Counter(names).items() if h and n > 1)
    if duplicates:
        raise DataError(
            f"These column headers appear more than once: {', '.join(duplicates)}. "
            "Rename them so every header is unique."
        )
    placeholder = [h or f"__unnamed_{i}" for i, h in enumerate(names)]
    df = pd.DataFrame(rows, columns=placeholder, dtype=str)

    for column in df.columns:
        stripped = df[column].str.strip()
        df[column] = stripped.where(~stripped.isin(NA_VALUES))

    for i, column in enumerate(placeholder):
        if column.startswith("__unnamed_"):
            if df[column].notna().any():
                raise DataError(
                    f"Column {i + 1} has no header but contains answers. Add a header to it."
                )
            df = df.drop(columns=column)

    if df.shape[1] == 0:
        raise DataError("The file has no named columns. The first row must contain headers.")
    if df.shape[0] == 0:
        raise DataError("The file has a header row but no responses.")
    return df


# --------------------------------------------------------------------------------------
# Conversion and scoring
# --------------------------------------------------------------------------------------


def convert_answers(
    values: pd.Series,
    scale_min: int,
    scale_max: int,
    label_map: dict[str, int] | None = None,
) -> tuple[pd.Series, pd.Series]:
    """Convert one item's answers to numbers.

    Text labels are looked up in ``label_map`` (case/whitespace-insensitive); anything else
    is parsed as a number. A valid answer is a whole number between scale_min and scale_max.

    Returns:
        (numeric, invalid): numeric answers (NaN where missing or invalid) and a boolean
        mask of answers that were present but unusable (unknown label, non-number,
        fraction, out of range).
    """
    lookup = {normalize_label(k): v for k, v in (label_map or {}).items()}

    def to_number(value: object) -> float:
        if isinstance(value, (int, float, np.number)) and not isinstance(value, bool):
            number: float | None = float(value)
        else:
            key = normalize_label(value)
            number = float(lookup[key]) if key in lookup else _parse_number(str(value).strip())
        if number is None or not math.isfinite(number) or number != round(number):
            return np.nan
        return number if scale_min <= number <= scale_max else np.nan

    present = values.notna()
    mapping = {v: to_number(v) for v in values[present].unique()}
    numeric = values.map(mapping).astype(float)
    numeric[~present] = np.nan
    invalid = present & numeric.isna()
    return numeric, invalid


def reverse_score(
    items: pd.DataFrame, reverse_items: list[str], scale_min: int, scale_max: int
) -> pd.DataFrame:
    """Recode reverse-worded items so that higher always means more of the trait.

    Each reverse item x becomes scale_min + scale_max - x (on 1–5: 1→5, 2→4, 4→2, 5→1).
    Missing answers stay missing. Only items the user declared are reversed; this function
    never decides on its own that an item is reverse-worded.
    """
    scored = items.copy()
    for item in reverse_items:
        scored[item] = scale_min + scale_max - scored[item]
    return scored


def scale_scores(
    scored_items: pd.DataFrame, scales: dict[str, list[str]], min_answered: float = 0.8
) -> pd.DataFrame:
    """Mean of each scale's (reverse-scored) items per respondent.

    A respondent gets a score only if they answered at least ``min_answered`` (default 80%)
    of that scale's items; otherwise their score is NaN. Higher scores mean more of what the
    scale measures, assuming reverse items were declared correctly.
    """
    scores = pd.DataFrame(index=scored_items.index)
    for scale, items in scales.items():
        block = scored_items[items]
        answered = block.notna().sum(axis=1)
        enough = answered / len(items) >= min_answered - 1e-12
        scores[scale] = block.mean(axis=1).where(enough)
    return scores


_SECONDS_PER_UNIT = {"seconds": 1.0, "minutes": 60.0, "milliseconds": 0.001}


def convert_durations(values: pd.Series, unit: str) -> tuple[pd.Series, DataIssue | None]:
    """Convert a completion-time column to seconds.

    Missing, non-numeric and negative values become NaN and are counted in one issue.
    """
    numbers = pd.to_numeric(values, errors="coerce").astype(float)
    numbers = numbers.where(numbers >= 0)
    seconds = numbers * _SECONDS_PER_UNIT[unit]
    n_unusable = int(seconds.isna().sum())
    issue = None
    if n_unusable:
        issue = DataIssue(
            kind="invalid_durations",
            count=n_unusable,
            column=str(values.name),
            message=(
                f"{n_unusable} respondent(s) have a missing or unusable completion time in "
                f"'{values.name}'; response-time screening skips them."
            ),
        )
    return seconds, issue


def prepare_data(
    df: pd.DataFrame, schema: SurveySchema, exclude_personal: bool = True
) -> PreparedData:
    """Turn a loaded CSV into clean, scored item data according to the schema.

    Steps: rename long headers to short codes (if the schema has question_text); convert
    answers to numbers (labels via label_map); treat invalid answers as missing and count
    them; remove respondents with no valid answer at all and count them; reverse-score the
    declared items; separate non-item columns, excluding personal-information columns.

    Counts of blank and invalid answers refer to the respondents that were kept; removed
    respondents are counted once, in their own issue.
    """
    if schema.question_text:
        df = apply_short_codes(df, schema.question_text)

    required = list(schema.items)
    required += [c for c in (schema.id_column, schema.duration_column) if c is not None]
    missing_columns = [c for c in required if c not in df.columns]
    if missing_columns:
        raise DataError(
            f"These columns are in the schema but not in the CSV: {', '.join(missing_columns)}. "
            "Check that you uploaded the right file and that its headers have not changed."
        )

    item_set = set(schema.items)
    non_items = df[[c for c in df.columns if c not in item_set]]
    personal = detect_personal_columns(non_items) if exclude_personal else []
    if schema.id_column is not None and schema.id_column in personal:
        raise DataError(
            f"The ID column '{schema.id_column}' looks like it contains personal information "
            "(emails or names). Choose a different ID column or none; respondents will then be "
            "identified by row number."
        )

    converted: dict[str, pd.Series] = {}
    invalid_masks: dict[str, pd.Series] = {}
    for item in schema.items:
        converted[item], invalid_masks[item] = convert_answers(
            df[item], schema.scale_min, schema.scale_max, schema.label_map
        )
    raw = pd.DataFrame(converted, index=df.index)

    empty = raw.isna().all(axis=1)
    if empty.all():
        examples = sorted(
            {str(v) for item in schema.items for v in df.loc[invalid_masks[item], item]}
        )[:5]
        hint = f" Examples of unusable answers: {', '.join(examples)}." if examples else ""
        raise DataError(
            "No respondent has a single valid answer. Check the scale range "
            f"({schema.scale_min}–{schema.scale_max}) and the answer-label mapping.{hint}"
        )

    issues: list[DataIssue] = []
    keep = ~empty
    for item in schema.items:
        n_missing = int(df.loc[keep, item].isna().sum())
        if n_missing:
            issues.append(
                DataIssue(
                    kind="missing_answers",
                    count=n_missing,
                    column=item,
                    message=f"{n_missing} blank or NA answer(s) in '{item}'.",
                )
            )
        invalid = invalid_masks[item] & keep
        n_invalid = int(invalid.sum())
        if n_invalid:
            examples = sorted({str(v) for v in df.loc[invalid, item]})[:5]
            issues.append(
                DataIssue(
                    kind="invalid_answers",
                    count=n_invalid,
                    column=item,
                    examples=examples,
                    message=(
                        f"{n_invalid} answer(s) in '{item}' were not a recognised label or a whole "
                        f"number from {schema.scale_min} to {schema.scale_max}, and were treated "
                        f"as missing. Examples: {', '.join(examples)}."
                    ),
                )
            )
    n_empty = int(empty.sum())
    if n_empty:
        issues.append(
            DataIssue(
                kind="empty_rows_removed",
                count=n_empty,
                message=(
                    f"{n_empty} respondent(s) had no valid answer to any item (all blank, NA or "
                    "invalid) and were removed."
                ),
            )
        )
    if personal:
        issues.append(
            DataIssue(
                kind="personal_columns_excluded",
                count=len(personal),
                message=(
                    f"{len(personal)} column(s) that look like personal information were excluded "
                    f"from analysis and downloads: {', '.join(personal)}."
                ),
            )
        )

    raw = raw.loc[keep]
    scored = reverse_score(raw, schema.reverse_items, schema.scale_min, schema.scale_max)
    meta = non_items.loc[keep].drop(columns=personal)

    durations = None
    if schema.duration_column is not None:
        durations, duration_issue = convert_durations(
            df.loc[keep, schema.duration_column], schema.duration_unit
        )
        if duration_issue is not None:
            issues.append(duration_issue)

    return PreparedData(
        raw_items=raw,
        scored_items=scored,
        meta=meta,
        durations_seconds=durations,
        issues=issues,
    )
