"""Survey schema: which columns are items, how they group into scales, and how to score them.

The schema is the user's description of their questionnaire. Every later module reads it,
so it is validated strictly here and every problem is reported in plain English.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any, Literal, get_args

DurationUnit = Literal["seconds", "minutes", "milliseconds"]
DURATION_UNITS: tuple[str, ...] = get_args(DurationUnit)


class SchemaError(ValueError):
    """Raised when a survey schema is invalid. The message explains the problem and the fix."""


@dataclass
class SurveySchema:
    """Description of a rating-scale questionnaire.

    Attributes:
        items: Item columns, in questionnaire order. Order matters: longstring and
            even-odd consistency depend on it.
        scales: Scale name -> item columns (each a subset of ``items``, at least 2 items).
        reverse_items: Items to reverse-score (subset of ``items``). Never inferred
            automatically; only the user declares them.
        scale_min: Lowest valid answer, e.g. 1.
        scale_max: Highest valid answer, e.g. 5.
        id_column: Optional column identifying respondents.
        duration_column: Optional column holding total completion time.
        duration_unit: Unit of ``duration_column``.
        label_map: Optional text label -> number mapping, e.g. {"strongly agree": 5}.
        question_text: Optional short code -> original column header, e.g. {"Q1": "I enjoy..."}.
    """

    items: list[str]
    scales: dict[str, list[str]]
    reverse_items: list[str]
    scale_min: int
    scale_max: int
    id_column: str | None = None
    duration_column: str | None = None
    duration_unit: DurationUnit = "seconds"
    label_map: dict[str, int] | None = None
    question_text: dict[str, str] | None = field(default=None)

    def __post_init__(self) -> None:
        self.validate()

    def validate(self) -> None:
        """Check the schema is internally consistent; raise SchemaError if not."""
        if not isinstance(self.items, list) or not all(isinstance(i, str) for i in self.items):
            raise SchemaError("'items' must be a list of column names.")
        if not self.items:
            raise SchemaError("The schema has no items. Select at least two question columns.")
        duplicates = sorted({i for i in self.items if self.items.count(i) > 1})
        if duplicates:
            raise SchemaError(f"These items are listed more than once: {', '.join(duplicates)}.")

        for name, value in (("scale_min", self.scale_min), ("scale_max", self.scale_max)):
            if isinstance(value, bool) or not isinstance(value, int):
                raise SchemaError(f"'{name}' must be a whole number, got {value!r}.")
        if self.scale_min >= self.scale_max:
            raise SchemaError(
                f"The lowest answer ({self.scale_min}) must be smaller than the highest "
                f"answer ({self.scale_max})."
            )

        item_set = set(self.items)
        if not isinstance(self.scales, dict):
            raise SchemaError("'scales' must map scale names to lists of items.")
        for scale, scale_items in self.scales.items():
            if not isinstance(scale_items, list):
                raise SchemaError(f"Scale '{scale}' must be a list of items.")
            missing = [i for i in scale_items if i not in item_set]
            if missing:
                raise SchemaError(
                    f"Scale '{scale}' uses columns that are not selected as items: "
                    f"{', '.join(missing)}. Add them to the items or remove them from the scale."
                )
            if len(set(scale_items)) != len(scale_items):
                raise SchemaError(f"Scale '{scale}' lists the same item more than once.")
            if len(scale_items) < 2:
                raise SchemaError(
                    f"Scale '{scale}' has {len(scale_items)} item(s). "
                    "A scale needs at least 2 items."
                )

        if not isinstance(self.reverse_items, list):
            raise SchemaError("'reverse_items' must be a list of items.")
        bad_reverse = [i for i in self.reverse_items if i not in item_set]
        if bad_reverse:
            raise SchemaError(
                f"These reverse-scored items are not selected as items: {', '.join(bad_reverse)}."
            )

        for name, column in (("ID", self.id_column), ("duration", self.duration_column)):
            if column is not None and column in item_set:
                raise SchemaError(
                    f"The {name} column '{column}' is also selected as an item. "
                    "A column cannot be both."
                )
        if self.duration_unit not in DURATION_UNITS:
            raise SchemaError(
                f"Duration unit must be one of {', '.join(DURATION_UNITS)}; "
                f"got '{self.duration_unit}'."
            )

        if self.label_map is not None:
            for label, value in self.label_map.items():
                if isinstance(value, bool) or not isinstance(value, int):
                    raise SchemaError(f"Label '{label}' must map to a whole number, got {value!r}.")
                if not self.scale_min <= value <= self.scale_max:
                    raise SchemaError(
                        f"Label '{label}' maps to {value}, which is outside the scale range "
                        f"{self.scale_min}–{self.scale_max}."
                    )

        if self.question_text is not None:
            if not all(
                isinstance(k, str) and isinstance(v, str) for k, v in self.question_text.items()
            ):
                raise SchemaError("'question_text' must map short codes to column headers (text).")
            headers = list(self.question_text.values())
            repeated = sorted({h for h in headers if headers.count(h) > 1})
            if repeated:
                raise SchemaError(
                    f"These column headers have more than one short code: {', '.join(repeated)}."
                )

    def to_dict(self) -> dict[str, Any]:
        """Return the schema as a plain dictionary."""
        return asdict(self)

    def to_json(self, indent: int = 2) -> str:
        """Return the schema as a JSON string."""
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SurveySchema:
        """Build and validate a schema from a dictionary (e.g. parsed JSON)."""
        if not isinstance(data, dict):
            raise SchemaError("The schema must be a JSON object.")
        known = {f.name for f in fields(cls)}
        unknown = sorted(set(data) - known)
        if unknown:
            raise SchemaError(f"Unknown schema fields: {', '.join(unknown)}.")
        required = ["items", "scales", "reverse_items", "scale_min", "scale_max"]
        missing = [name for name in required if name not in data]
        if missing:
            raise SchemaError(f"The schema is missing required fields: {', '.join(missing)}.")
        return cls(**data)

    @classmethod
    def from_json(cls, text: str) -> SurveySchema:
        """Parse and validate a schema from a JSON string."""
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise SchemaError(
                f"The schema file is not valid JSON (line {exc.lineno}, column {exc.colno}): "
                f"{exc.msg}."
            ) from exc
        return cls.from_dict(data)

    def save(self, path: str | Path) -> None:
        """Write the schema to a JSON file (UTF-8)."""
        Path(path).write_text(self.to_json() + "\n", encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path) -> SurveySchema:
        """Read and validate a schema from a JSON file."""
        return cls.from_json(Path(path).read_text(encoding="utf-8"))
