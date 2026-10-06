"""Tests for schema.py, io.py and scripts/download_data.py (Stage 1)."""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from scripts.download_data import BFI_COLUMNS, BFI_ITEMS, tidy_bfi, validate_bfi
from surveydoctor.io import (
    DataError,
    apply_short_codes,
    assign_short_codes,
    convert_answers,
    convert_durations,
    detect_label_scale,
    detect_personal_columns,
    inspect_columns,
    is_rating_like,
    load_csv,
    normalize_label,
    prepare_data,
    preview_rows,
    reverse_score,
    scale_scores,
)
from surveydoctor.schema import SchemaError, SurveySchema
from tests.conftest import BFI_SCHEMA, GOOGLE_FORMS_CSV


def make_schema(**overrides) -> SurveySchema:
    """A small valid schema: two 3-item scales on a 1-5 scale."""
    base = dict(
        items=["q1", "q2", "q3", "q4", "q5", "q6"],
        scales={"S1": ["q1", "q2", "q3"], "S2": ["q4", "q5", "q6"]},
        reverse_items=["q2"],
        scale_min=1,
        scale_max=5,
    )
    base.update(overrides)
    return SurveySchema(**base)


# ---------------------------------------------------------------------------- schema


class TestSchemaValidation:
    def test_valid_schema(self):
        schema = make_schema()
        assert schema.scale_max == 5

    def test_scale_item_not_in_items(self):
        with pytest.raises(SchemaError, match="not selected as items: q9"):
            make_schema(scales={"S1": ["q1", "q9"]})

    def test_reverse_item_not_in_items(self):
        with pytest.raises(SchemaError, match="reverse-scored items are not selected"):
            make_schema(reverse_items=["zz"])

    @pytest.mark.parametrize("lo,hi", [(5, 5), (5, 1)])
    def test_min_not_below_max(self, lo, hi):
        with pytest.raises(SchemaError, match="must be smaller"):
            make_schema(scale_min=lo, scale_max=hi)

    def test_scale_with_one_item(self):
        with pytest.raises(SchemaError, match="at least 2 items"):
            make_schema(scales={"S1": ["q1"]})

    def test_duplicate_items(self):
        with pytest.raises(SchemaError, match="more than once"):
            make_schema(items=["q1", "q1", "q2"], scales={}, reverse_items=[])

    def test_no_items(self):
        with pytest.raises(SchemaError, match="no items"):
            make_schema(items=[], scales={}, reverse_items=[])

    def test_id_column_cannot_be_item(self):
        with pytest.raises(SchemaError, match="cannot be both"):
            make_schema(id_column="q1")

    def test_bad_duration_unit(self):
        with pytest.raises(SchemaError, match="Duration unit"):
            make_schema(duration_unit="hours")

    def test_label_map_value_out_of_range(self):
        with pytest.raises(SchemaError, match="outside the scale range"):
            make_schema(label_map={"agree": 7})

    def test_non_integer_scale_bounds(self):
        with pytest.raises(SchemaError, match="whole number"):
            make_schema(scale_min=1.5)


class TestSchemaJson:
    def test_round_trip(self, tmp_path):
        schema = make_schema(label_map={"agree": 4}, question_text={"Q1": "Long header?"})
        assert SurveySchema.from_json(schema.to_json()) == schema
        path = tmp_path / "schema.json"
        schema.save(path)
        assert SurveySchema.load(path) == schema

    def test_invalid_json(self):
        with pytest.raises(SchemaError, match="not valid JSON"):
            SurveySchema.from_json("{not json")

    def test_missing_field(self):
        with pytest.raises(SchemaError, match="missing required fields: scale_max"):
            SurveySchema.from_json(
                json.dumps({"items": ["a", "b"], "scales": {}, "reverse_items": [], "scale_min": 1})
            )

    def test_unknown_field(self):
        data = make_schema().to_dict() | {"colour": "red"}
        with pytest.raises(SchemaError, match="Unknown schema fields: colour"):
            SurveySchema.from_dict(data)

    def test_bfi_schema_file(self):
        schema = SurveySchema.load(BFI_SCHEMA)
        assert len(schema.items) == 25
        assert set(schema.scales) == {
            "Agreeableness",
            "Conscientiousness",
            "Extraversion",
            "Neuroticism",
            "Openness",
        }
        assert all(len(items) == 5 for items in schema.scales.values())
        assert schema.reverse_items == ["A1", "C4", "C5", "E1", "E2", "O2", "O5"]
        assert (schema.scale_min, schema.scale_max) == (1, 6)


# ---------------------------------------------------------------------------- scoring


class TestScoring:
    def test_reverse_scoring_1_to_5(self):
        items = pd.DataFrame({"q1": [1.0, 4.0, 3.0, np.nan], "q2": [1.0, 4.0, 3.0, np.nan]})
        scored = reverse_score(items, ["q1"], 1, 5)
        assert scored["q1"].tolist()[:3] == [5.0, 2.0, 3.0]
        assert np.isnan(scored["q1"].iloc[3])
        assert scored["q2"].tolist()[:3] == [1.0, 4.0, 3.0]  # undeclared item untouched
        assert items["q1"].tolist()[:3] == [1.0, 4.0, 3.0]  # input not modified

    def test_reverse_scoring_1_to_6(self):
        scored = reverse_score(pd.DataFrame({"x": [1.0, 6.0, 2.0]}), ["x"], 1, 6)
        assert scored["x"].tolist() == [6.0, 1.0, 5.0]

    def test_scale_score_needs_80_percent_answered(self):
        scored = pd.DataFrame(
            {
                "a": [1.0, 1.0, 1.0],
                "b": [2.0, 2.0, np.nan],
                "c": [3.0, 3.0, np.nan],
                "d": [4.0, 4.0, 4.0],
                "e": [5.0, np.nan, 5.0],
            }
        )
        scores = scale_scores(scored, {"S": ["a", "b", "c", "d", "e"]})
        assert scores["S"].iloc[0] == pytest.approx(3.0)
        assert scores["S"].iloc[1] == pytest.approx(2.5)  # 4 of 5 answered = 80%: scored
        assert np.isnan(scores["S"].iloc[2])  # 3 of 5 answered = 60%: not scored


# ---------------------------------------------------------------------------- labels


class TestLabels:
    def test_normalize(self):
        assert normalize_label("  Strongly   AGREE ") == "strongly agree"

    def test_strongly_agree_variants_map_to_5(self):
        df = pd.DataFrame({"q": ["Strongly agree", " strongly AGREE ", "Disagree", "Agree"]})
        detection = detect_label_scale(df, ["q"])
        assert detection.label_set == "agreement_5"
        assert (detection.scale_min, detection.scale_max) == (1, 5)
        numeric, invalid = convert_answers(df["q"], 1, 5, detection.label_map)
        assert numeric.tolist() == [5.0, 5.0, 2.0, 4.0]
        assert not invalid.any()

    def test_unrecognised_label_reported_not_guessed(self):
        df = pd.DataFrame({"q": ["Agree", "Strongly agre", "Disagree"]})
        detection = detect_label_scale(df, ["q"])
        assert detection.unrecognised == ["Strongly agre"]
        assert "strongly agre" not in detection.label_map
        numeric, invalid = convert_answers(df["q"], 1, 5, detection.label_map)
        assert np.isnan(numeric.iloc[1])
        assert invalid.tolist() == [False, True, False]

    def test_seven_point_agreement(self):
        df = pd.DataFrame({"q": ["Somewhat agree", "Agree", "Strongly disagree"]})
        detection = detect_label_scale(df, ["q"])
        assert detection.label_set == "agreement_7"
        assert detection.label_map["somewhat agree"] == 5
        assert detection.label_map["agree"] == 6

    def test_ambiguous_5_vs_7_prefers_5_and_lists_alternative(self):
        df = pd.DataFrame({"q": ["Agree", "Disagree"]})
        detection = detect_label_scale(df, ["q"])
        assert detection.label_set == "agreement_5"
        assert "agreement_7" in detection.alternatives

    def test_frequency_and_satisfaction(self):
        freq = detect_label_scale(pd.DataFrame({"q": ["Never", "Often", "Always"]}), ["q"])
        assert freq.label_set == "frequency_5" and freq.label_map["often"] == 4
        sat = detect_label_scale(pd.DataFrame({"q": ["Very satisfied", "Dissatisfied"]}), ["q"])
        assert sat.label_set == "satisfaction_5" and sat.label_map["very satisfied"] == 5

    def test_numbers_only_gives_no_label_map(self):
        detection = detect_label_scale(pd.DataFrame({"q": ["1", "2", "5"]}), ["q"])
        assert detection.label_map is None and detection.unrecognised == []

    def test_completely_unknown_labels(self):
        detection = detect_label_scale(pd.DataFrame({"q": ["Yes", "No"]}), ["q"])
        assert detection.label_map is None
        assert detection.unrecognised == ["No", "Yes"]

    def test_convert_rejects_out_of_range_and_fractions(self):
        values = pd.Series(["1", "5", "6", "0", "2.5", "3.0", "abc", None])
        numeric, invalid = convert_answers(values, 1, 5)
        assert numeric.iloc[:2].tolist() == [1.0, 5.0]
        assert numeric.iloc[5] == 3.0
        assert numeric.iloc[[2, 3, 4, 6, 7]].isna().all()
        assert invalid.tolist() == [False, False, True, True, True, False, True, False]


# ---------------------------------------------------------------------------- personal columns


class TestPersonalColumns:
    def test_email_and_name_columns_detected(self):
        df = pd.DataFrame(
            {
                "Email Address": ["a@example.com", "b@example.com"],
                "Your name": ["Ann", "Bo"],
                "Contact": ["c@example.com", "d@example.com"],  # detected from values
                "I enjoy teamwork.": ["Agree", "Disagree"],
                "How often do you check your email?": ["Often", "Never"],  # rating, kept
                "age": ["20", "21"],
            }
        )
        assert detect_personal_columns(df) == ["Email Address", "Your name", "Contact"]

    def test_personal_columns_excluded_from_items_and_downloads(self):
        df = load_csv(GOOGLE_FORMS_CSV)
        infos = {info.header: info for info in inspect_columns(df)}
        for header in ("Email Address", "Your name"):
            assert infos[header].looks_personal
            assert not infos[header].suggested_item
            assert infos[header].code is None
            assert infos[header].distinct_values == []  # values never shown
        preview = preview_rows(df)
        assert "Email Address" not in preview.columns and "Your name" not in preview.columns
        assert len(preview) == 10

    def test_personal_id_column_refused(self):
        df = pd.DataFrame(
            {
                "email": ["a@example.com", "b@example.com"],
                "q1": ["1", "2"],
                "q2": ["2", "3"],
            }
        )
        schema = SurveySchema(
            items=["q1", "q2"],
            scales={},
            reverse_items=[],
            scale_min=1,
            scale_max=5,
            id_column="email",
        )
        with pytest.raises(DataError, match="personal information"):
            prepare_data(df, schema)


# ---------------------------------------------------------------------------- short codes


class TestShortCodes:
    def test_long_headers_get_q_codes_short_ones_keep_name(self):
        codes = assign_short_codes(["Timestamp", "I enjoy teams.", "Q1", "Rate [Content]"])
        assert codes == {
            "Timestamp": "Timestamp",
            "Q2": "I enjoy teams.",
            "Q1": "Q1",
            "Q3": "Rate [Content]",
        }

    def test_apply_short_codes(self):
        df = pd.DataFrame({"I enjoy teams.": [1], "age": [20]})
        renamed = apply_short_codes(df, {"Q1": "I enjoy teams.", "age": "age"})
        assert list(renamed.columns) == ["Q1", "age"]

    def test_apply_short_codes_clash(self):
        df = pd.DataFrame({"I enjoy teams.": [1], "Q1": [2]})
        with pytest.raises(DataError, match="already used"):
            apply_short_codes(df, {"Q1": "I enjoy teams."})


# ---------------------------------------------------------------------------- CSV loading


class TestLoadCsv:
    def test_blank_and_na_become_missing_and_cells_are_trimmed(self):
        df = load_csv(b"a,b,c\n 1 ,NA,\nx,  ,N/A\n")
        assert df["a"].tolist() == ["1", "x"]
        assert df["b"].isna().all() and df["c"].isna().all()

    def test_utf8_bom_and_cp1252(self):
        assert list(load_csv("﻿q1,q2\n1,2\n".encode()).columns) == ["q1", "q2"]
        df = load_csv("caf\xe9,q2\n1,2\n".encode("cp1252"))
        assert list(df.columns) == ["caf\xe9", "q2"]

    def test_empty_file(self):
        with pytest.raises(DataError, match="empty"):
            load_csv(b"   \n")

    def test_header_only(self):
        with pytest.raises(DataError, match="no responses"):
            load_csv(b"q1,q2\n")

    def test_duplicate_headers(self):
        with pytest.raises(DataError, match="more than once: q1"):
            load_csv(b"q1, q1 ,q2\n1,2,3\n")

    def test_trailing_empty_unnamed_column_ignored(self):
        df = load_csv(b"q1,q2,\n1,2,\n3,4,\n")
        assert list(df.columns) == ["q1", "q2"]

    def test_unnamed_column_with_data_rejected(self):
        with pytest.raises(DataError, match="Column 2 has no header"):
            load_csv(b"q1,,q3\n1,2,3\n")

    def test_row_with_extra_fields_rejected(self):
        with pytest.raises(DataError, match="Line 2 has 4 values but the header has 2"):
            load_csv(b"q1,q2\n1,2,3,4\n")

    def test_short_row_padded_and_blank_lines_skipped(self):
        df = load_csv(b"q1,q2,q3\n1,2\n\n4,5,6\n")
        assert len(df) == 2
        assert df["q3"].isna().tolist() == [True, False]

    def test_quoted_comma_and_newline_in_answer(self):
        df = load_csv(b'q1,comment\n1,"Great, thanks\nsee you"\n')
        assert df.loc[0, "comment"] == "Great, thanks\nsee you"

    def test_rating_like_tolerates_occasional_typo_but_not_ages(self):
        assert is_rating_like(pd.Series(["Agree"] * 9 + ["Agre"]))
        assert not is_rating_like(pd.Series(["19", "20", "21", "24"]))
        assert not is_rating_like(pd.Series(["fine", "ok", "good"]))


# ---------------------------------------------------------------------------- prepare_data


class TestPrepareData:
    def test_invalid_and_empty_rows_counted_not_silent(self):
        df = pd.DataFrame(
            {
                "q1": ["1", "2", None, "7"],
                "q2": ["5", "x", None, "4"],
                "group": ["a", "b", "a", "b"],
            }
        )
        schema = SurveySchema(
            items=["q1", "q2"],
            scales={"S": ["q1", "q2"]},
            reverse_items=["q2"],
            scale_min=1,
            scale_max=5,
        )
        prepared = prepare_data(df, schema)
        assert prepared.raw_items.index.tolist() == [0, 1, 3]  # row 2 removed, positions kept
        assert prepared.raw_items["q2"].tolist()[0] == 5.0
        assert prepared.scored_items["q2"].tolist()[0] == 1.0  # reversed
        kinds = {(i.kind, i.column): i for i in prepared.issues}
        assert kinds[("empty_rows_removed", None)].count == 1
        assert kinds[("invalid_answers", "q1")].count == 1
        assert kinds[("invalid_answers", "q1")].examples == ["7"]
        assert kinds[("invalid_answers", "q2")].examples == ["x"]
        assert prepared.meta.columns.tolist() == ["group"]
        assert prepared.durations_seconds is None

    def test_missing_schema_columns(self):
        df = pd.DataFrame({"q1": ["1"]})
        schema = SurveySchema(
            items=["q1", "q2"], scales={}, reverse_items=[], scale_min=1, scale_max=5
        )
        with pytest.raises(DataError, match="not in the CSV: q2"):
            prepare_data(df, schema)

    def test_nothing_valid(self):
        df = pd.DataFrame({"q1": ["Yes", "No"], "q2": ["No", "No"]})
        schema = SurveySchema(
            items=["q1", "q2"], scales={}, reverse_items=[], scale_min=1, scale_max=5
        )
        with pytest.raises(DataError, match="No respondent has a single valid answer.*No, Yes"):
            prepare_data(df, schema)

    def test_durations_converted_to_seconds(self):
        seconds, issue = convert_durations(
            pd.Series(["1500", "x", "-3", None], name="t"), "milliseconds"
        )
        assert seconds.iloc[0] == pytest.approx(1.5)
        assert seconds.iloc[1:].isna().all()
        assert issue is not None and issue.count == 3
        minutes, issue = convert_durations(pd.Series(["2"], name="t"), "minutes")
        assert minutes.iloc[0] == 120.0 and issue is None


class TestGoogleFormsFixture:
    """End-to-end Stage 1 flow on the messy Google Forms-style export."""

    def test_full_flow(self):
        df = load_csv(GOOGLE_FORMS_CSV)
        assert df.shape == (12, 12)

        infos = inspect_columns(df)
        by_header = {i.header: i for i in infos}
        assert by_header["Timestamp"].code == "Timestamp"
        assert not by_header["Timestamp"].suggested_item
        assert by_header["Any other comments?"].suggested_item is False
        assert by_header["Rate the course [Content]"].suggested_item  # grid row = one item
        items_headers = [i.header for i in infos if i.suggested_item]
        assert items_headers == [
            "I enjoy working in teams.",
            "I prefer to work alone.",
            "Group projects help me learn.",
            "I contribute actively in group discussions.",
            "Rate the course [Content]",
            "Rate the course [Teaching]",
            "Rate the course [Assessment]",
        ]
        codes = {i.code: i.header for i in infos if i.code is not None}
        assert codes["Q1"] == "I enjoy working in teams."
        assert codes["Q7"] == "Rate the course [Assessment]"

        detection = detect_label_scale(df, items_headers)
        assert detection.label_set == "agreement_5"
        assert detection.unrecognised == ["Strongly agre"]

        item_codes = [f"Q{i}" for i in range(1, 8)]
        schema = SurveySchema(
            items=item_codes,
            scales={"Teamwork": ["Q1", "Q2", "Q3", "Q4"], "Course": ["Q5", "Q6", "Q7"]},
            reverse_items=["Q2"],
            scale_min=1,
            scale_max=5,
            label_map=detection.label_map,
            question_text=codes,
        )
        schema = SurveySchema.from_json(schema.to_json())
        prepared = prepare_data(df, schema)

        assert len(prepared.raw_items) == 11  # Nia O answered nothing
        assert prepared.raw_items.loc[2, "Q1"] == 5.0  # " strongly AGREE "
        assert prepared.raw_items.loc[2, "Q2"] == 2.0  # "disagree " with trailing space
        assert prepared.scored_items.loc[2, "Q2"] == 4.0  # reversed
        assert np.isnan(prepared.raw_items.loc[4, "Q1"])  # "Strongly agre" not guessed
        assert np.isnan(prepared.raw_items.loc[7, "Q5"])  # 6 is out of range
        assert "Email Address" not in prepared.meta.columns
        assert "Your name" not in prepared.meta.columns

        counts = {(i.kind, i.column): i.count for i in prepared.issues}
        assert counts[("empty_rows_removed", None)] == 1
        assert counts[("invalid_answers", "Q1")] == 1
        assert counts[("invalid_answers", "Q5")] == 1
        assert counts[("missing_answers", "Q2")] == 1
        assert counts[("missing_answers", "Q3")] == 1  # "N/A"
        assert counts[("missing_answers", "Q7")] == 1
        assert counts[("personal_columns_excluded", None)] == 2


# ---------------------------------------------------------------------------- bfi sample


class TestBfiSample:
    def test_download_validation_helpers(self):
        good = pd.DataFrame(
            [["1", *["3"] * 25, "1", "", "20"], ["2", *["6"] * 25, "2", "3", "30"]],
            columns=["rownames", *BFI_ITEMS, "gender", "education", "age"],
        )
        tidy = tidy_bfi(good)
        assert list(tidy.columns) == BFI_COLUMNS
        problems = validate_bfi(tidy)
        assert problems == ["Unexpected number of rows: 2 (expected 2500-3100)."]
        bad = tidy.copy()
        bad.loc[0, "A1"] = "7"
        assert any("outside 1-6" in p for p in validate_bfi(bad))

    def test_bfi_loads_and_prepares(self, bfi_csv_path):
        df = load_csv(bfi_csv_path)
        assert validate_bfi(df) == []
        schema = SurveySchema.load(BFI_SCHEMA)
        prepared = prepare_data(df, schema)
        assert list(prepared.raw_items.columns) == schema.items
        assert not any(i.kind == "invalid_answers" for i in prepared.issues)
        assert prepared.meta.columns.tolist() == ["id", "gender", "education", "age"]
        answered = prepared.raw_items["A1"].notna()
        assert (
            prepared.scored_items["A1"][answered] == 7 - prepared.raw_items["A1"][answered]
        ).all()
        n_missing = sum(i.count for i in prepared.issues if i.kind == "missing_answers")
        n_removed = sum(i.count for i in prepared.issues if i.kind == "empty_rows_removed")
        assert n_missing + n_removed * 25 == int(df[schema.items].isna().sum().sum())
