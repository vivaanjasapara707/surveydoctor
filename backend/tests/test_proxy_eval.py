"""Tests for the DASS proxy evaluation (Stage 8). Synthetic DASS-shaped data is used so
the tests run without the (uncommitted) dataset; one smoke test uses the real file if
present."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from evaluation.run_proxy_eval import (
    DASS_DIR,
    ELAPSED_MS,
    FAKE_WORDS,
    ITEMS,
    N_ITEMS,
    POSITIONS,
    careless_proxy,
    dass_schema,
    duration_seconds,
    find_data_file,
    main,
    presentation_order,
    run_proxy_eval,
    summary_markdown,
)
from evaluation.simulate import FLAG_MEASURE, RULE_PREFIX


def synthetic_dass(n: int = 200, seed: int = 0) -> pd.DataFrame:
    """DASS-shaped data: random 1-4 answers, shuffled positions, 3-8 s per item, no fake
    words claimed. Every 10th respondent claims a fake word."""
    rng = np.random.default_rng(seed)
    data: dict[str, np.ndarray] = {}
    positions = np.array([rng.permutation(N_ITEMS) + 1 for _ in range(n)])
    answers = rng.integers(1, 5, size=(n, N_ITEMS))
    for j in range(N_ITEMS):
        data[ITEMS[j]] = answers[:, j]
        data[POSITIONS[j]] = positions[:, j]
        data[ELAPSED_MS[j]] = rng.integers(3000, 8000, size=n)
    for k in range(1, 17):
        data[f"VCL{k}"] = rng.integers(0, 2, size=n)
    frame = pd.DataFrame(data)
    frame[list(FAKE_WORDS)] = 0
    frame.loc[frame.index % 10 == 0, "VCL9"] = 1
    return frame


# --- Schema -------------------------------------------------------------------------------


def test_schema_matches_official_scoring_template() -> None:
    # The DASS scoring template marks items 1-21 with these letters and is applied again to
    # items 22-42 (Dass_template.pdf, www2.psy.unsw.edu.au/dass).
    template = "S A D A D S A S A D S S D S A D D S A A D".split()
    names = {"D": "Depression", "A": "Anxiety", "S": "Stress"}
    schema = dass_schema()
    for i in range(1, N_ITEMS + 1):
        scale = names[template[(i - 1) % 21]]
        assert f"Q{i}A" in schema.scales[scale]


def test_schema_shape() -> None:
    schema = dass_schema()
    assert schema.items == [f"Q{i}A" for i in range(1, 43)]
    assert {len(items) for items in schema.scales.values()} == {14}
    assert sorted(sum(schema.scales.values(), [])) == sorted(schema.items)
    assert schema.reverse_items == []
    assert (schema.scale_min, schema.scale_max) == (1, 4)
    assert schema.duration_column == "duration_seconds"


# --- Proxy label, durations, presentation order -------------------------------------------


def test_proxy_any_fake_word() -> None:
    raw = pd.DataFrame({"VCL6": [0, 1, 0, 0], "VCL9": [0, 0, 1, 0], "VCL12": [0, 0, 1, 0]})
    raw["VCL1"] = 1  # real words do not count
    assert careless_proxy(raw).tolist() == [0, 1, 1, 0]


def test_duration_is_sum_of_item_times_in_seconds() -> None:
    raw = pd.DataFrame({col: [1000, 500] for col in ELAPSED_MS})
    # 42 × 1000 ms = 42 s; 42 × 500 ms = 21 s.
    assert duration_seconds(raw).tolist() == [42.0, 21.0]
    raw.loc[1, ELAPSED_MS[0]] = np.nan
    assert np.isnan(duration_seconds(raw).iloc[1])  # incomplete timing -> no duration


def test_presentation_order_by_hand() -> None:
    raw = synthetic_dass(n=1)
    # Show the items in reverse: Q42 first, Q1 last.
    for j in range(N_ITEMS):
        raw[POSITIONS[j]] = N_ITEMS - j
    ordered = presentation_order(raw).iloc[0].tolist()
    assert ordered == raw[ITEMS].iloc[0].tolist()[::-1]


def test_presentation_order_rejects_bad_positions() -> None:
    raw = synthetic_dass(n=3)
    raw.loc[1, POSITIONS[0]] = raw.loc[1, POSITIONS[1]]  # a duplicated position
    with pytest.raises(ValueError, match="1 respondents"):
        presentation_order(raw)


def test_find_data_file(tmp_path) -> None:
    assert find_data_file(tmp_path / "missing") is None
    assert find_data_file(tmp_path) is None
    nested = tmp_path / "DASS_data_21.02.19"
    nested.mkdir()
    (nested / "data.csv").write_text("x\n1\n", encoding="utf-8")
    assert find_data_file(tmp_path) == nested / "data.csv"


def test_main_without_data_explains_and_exits_zero(tmp_path, capsys) -> None:
    out = tmp_path / "results"
    assert main(["--data-dir", str(tmp_path / "missing"), "--out", str(out)]) == 0
    assert "openpsychometrics.org" in capsys.readouterr().out
    assert not out.exists()


# --- Full evaluation on synthetic data ----------------------------------------------------


def test_run_proxy_eval_on_synthetic_data() -> None:
    raw = synthetic_dass(n=300)
    results, info = run_proxy_eval(raw)
    assert info["n_respondents"] == 300
    assert info["n_proxy"] == 30
    assert info["base_rate"] == pytest.approx(0.1)
    measures = set(results["measure"])
    assert {"composite", "longstring", "mahalanobis", "seconds_per_item", FLAG_MEASURE} <= measures
    assert (results["n_proxy"] == 30).all()


def test_longstring_uses_presentation_order() -> None:
    raw = synthetic_dass(n=300)
    # Every 5th respondent answers 4 to the first 30 items they were shown (in shuffled
    # positions) and 1 to the rest, so their run is long only in presentation order.
    for row in raw.index[::5]:
        for j in range(N_ITEMS):
            raw.loc[row, ITEMS[j]] = 4 if raw.loc[row, POSITIONS[j]] <= 30 else 1
    results, _ = run_proxy_eval(raw)
    longstring_rule = results.set_index("measure").loc[RULE_PREFIX + "longstring"]
    # The rule fires at 21 or more (half of 42 items): exactly the 60 constructed rows.
    assert longstring_rule["share_flagged"] == pytest.approx(60 / 300)


def test_summary_markdown(tmp_path) -> None:
    raw = synthetic_dass(n=300)
    results, info = run_proxy_eval(raw)
    text = summary_markdown(results, info, "data/raw/dass/x/data.csv")
    assert "300 respondents analysed" in text
    assert "30 respondents (10.0%)" in text
    assert "not accuracy" in text
    assert "| Default flag rule (any rule fires) |" in text
    assert "nan" not in text


def test_main_writes_outputs(tmp_path) -> None:
    data_dir = tmp_path / "dass" / "DASS_data_21.02.19"
    data_dir.mkdir(parents=True)
    synthetic_dass(n=150).to_csv(data_dir / "data.csv", sep="\t", index=False)
    out = tmp_path / "results"
    assert main(["--data-dir", str(tmp_path / "dass"), "--out", str(out)]) == 0
    assert len(pd.read_csv(out / "proxy_eval.csv")) >= 6
    assert (out / "proxy_eval_summary.md").read_text(encoding="utf-8").startswith("# Proxy")


# --- Real data (skipped unless downloaded) ------------------------------------------------


def test_real_dass_file_if_present() -> None:
    data_file = find_data_file(DASS_DIR)
    if data_file is None:
        pytest.skip("DASS data not downloaded (optional; see BLUEPRINT §5.2).")
    raw = pd.read_csv(data_file, sep="\t", nrows=2000)
    assert set(ITEMS + POSITIONS + ELAPSED_MS + list(FAKE_WORDS)) <= set(raw.columns)
    assert raw[ITEMS].isin([1, 2, 3, 4]).all().all()
    presentation_order(raw)  # positions are a permutation of 1-42 for every row
