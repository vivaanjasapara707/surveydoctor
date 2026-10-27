"""Generate the HTML report for the bfi sample, with the gender comparison on Neuroticism.

Usage (from backend/):
    python scripts/report_bfi.py                 # writes reports/bfi_report.html
    python scripts/report_bfi.py --out my.html   # somewhere else

Open the file in a browser; use the browser's Print to check the A4 layout. The reports/
folder is gitignored.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from surveydoctor.io import load_csv  # noqa: E402
from surveydoctor.pipeline import run_pipeline  # noqa: E402
from surveydoctor.report import build_report  # noqa: E402
from surveydoctor.robustness import GroupComparison  # noqa: E402
from surveydoctor.schema import SurveySchema  # noqa: E402

BFI_CSV = BACKEND_DIR / "data" / "sample" / "bfi.csv"
BFI_SCHEMA = BACKEND_DIR / "data" / "sample" / "bfi_schema.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=BACKEND_DIR / "reports" / "bfi_report.html")
    args = parser.parse_args(argv)
    if not BFI_CSV.exists():
        sys.exit("data/sample/bfi.csv not found. Run: python scripts/download_data.py")

    schema = SurveySchema.load(BFI_SCHEMA)
    analysis = GroupComparison(scale="Neuroticism", group_column="gender", group_a=1, group_b=2)
    results = run_pipeline(load_csv(BFI_CSV), schema, analysis=analysis)
    html = build_report(results, source_name=BFI_CSV.name)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(html, encoding="utf-8")
    print(f"Wrote {args.out} ({len(html.encode('utf-8')) / 1024:.0f} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
