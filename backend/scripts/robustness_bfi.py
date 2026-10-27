"""Run the robustness check on the bfi sample: gender 1 vs 2 on each scale (or one scale).

Usage (from backend/):
    python scripts/robustness_bfi.py                       # every scale
    python scripts/robustness_bfi.py --scale Neuroticism   # one scale

In bfi, gender 1 = male and 2 = female, so a negative difference means women score higher.
The script runs the full pipeline (with fewer parallel-analysis iterations, which only
affect the factor-structure section) and prints the variant table and verdict.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from surveydoctor.io import load_csv  # noqa: E402
from surveydoctor.pipeline import run_pipeline  # noqa: E402
from surveydoctor.robustness import GroupComparison  # noqa: E402
from surveydoctor.schema import SurveySchema  # noqa: E402

BFI_CSV = BACKEND_DIR / "data" / "sample" / "bfi.csv"
BFI_SCHEMA = BACKEND_DIR / "data" / "sample" / "bfi_schema.json"
COLUMNS = ["variant", "n_excluded", "n", "estimate", "ci_low", "ci_high", "p", "significant",
           "direction", "effect_size"]  # fmt: skip


def main(argv: list[str] | None = None) -> int:
    schema = SurveySchema.load(BFI_SCHEMA)
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--scale", choices=list(schema.scales), help="one scale (default: all)")
    args = parser.parse_args(argv)
    if not BFI_CSV.exists():
        sys.exit("data/sample/bfi.csv not found. Run: python scripts/download_data.py")

    df = load_csv(BFI_CSV)
    pd.set_option("display.width", 200)
    for scale in [args.scale] if args.scale else list(schema.scales):
        analysis = GroupComparison(scale=scale, group_column="gender", group_a=1, group_b=2)
        result = run_pipeline(df, schema, analysis=analysis, pa_iterations=20).robustness
        print(f"\n{scale}: gender 1 (male) minus gender 2 (female)")
        table = result.table()[COLUMNS]
        print(table.to_string(index=False, float_format=lambda v: f"{v:.4f}"))
        changed = (
            f" (changed: {', '.join(result.changed_variants)})" if result.changed_variants else ""
        )
        print(f"Verdict: {result.verdict}{changed}")
    print(f"\n{result.caveat}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
