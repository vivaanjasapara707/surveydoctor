"""Download the bfi sample dataset into data/sample/bfi.csv.

Usage (from backend/):
    python scripts/download_data.py          # download if missing, otherwise re-check
    python scripts/download_data.py --force  # download again and overwrite

The CSV comes from the Rdatasets copy of the R package `psych` dataset `bfi`
(BLUEPRINT.md §5.1; URL and licence marked [VERIFY]). The Rdatasets row-name column is
renamed to `id`. All values are saved exactly as downloaded (missing answers stay blank).

The DASS proxy-evaluation dataset is not downloaded here: it must be obtained manually
(see BLUEPRINT.md §5.2) and placed in data/raw/dass/.
"""

from __future__ import annotations

import argparse
import io
import sys
import urllib.error
import urllib.request
from pathlib import Path

import pandas as pd

BFI_URL = "https://raw.githubusercontent.com/vincentarelbundock/Rdatasets/master/csv/psych/bfi.csv"
BACKEND_DIR = Path(__file__).resolve().parents[1]
BFI_PATH = BACKEND_DIR / "data" / "sample" / "bfi.csv"

BFI_ITEMS = [f"{trait}{i}" for trait in "ACENO" for i in range(1, 6)]
BFI_COLUMNS = ["id", *BFI_ITEMS, "gender", "education", "age"]
# The blueprint says "about 2,800 respondents"; accept a generous range and print the count.
BFI_ROW_RANGE = (2500, 3100)

DASS_NOTE = (
    "The DASS dataset (optional, for the proxy evaluation) is not downloaded automatically.\n"
    "Get it from the openpsychometrics.org raw data page, check its licence and codebook,\n"
    f"and unzip it into {BACKEND_DIR / 'data' / 'raw' / 'dass'} (never commit it)."
)


def tidy_bfi(df: pd.DataFrame) -> pd.DataFrame:
    """Rename the Rdatasets row-name column (first column) to `id`."""
    first = df.columns[0]
    if first in ("rownames", "") or str(first).startswith("Unnamed"):
        df = df.rename(columns={first: "id"})
    return df


def validate_bfi(df: pd.DataFrame) -> list[str]:
    """Return a list of problems with a bfi table (empty list means it looks right)."""
    problems: list[str] = []
    if list(df.columns) != BFI_COLUMNS:
        problems.append(f"Unexpected columns: {list(df.columns)}; expected {BFI_COLUMNS}.")
        return problems
    low, high = BFI_ROW_RANGE
    if not low <= len(df) <= high:
        problems.append(f"Unexpected number of rows: {len(df)} (expected {low}-{high}).")
    items = df[BFI_ITEMS].apply(pd.to_numeric, errors="coerce")
    non_numeric = int((items.isna() & df[BFI_ITEMS].notna()).sum().sum())
    if non_numeric:
        problems.append(f"{non_numeric} item answers are not numbers.")
    out_of_range = int(((items < 1) | (items > 6)).sum().sum())
    if out_of_range:
        problems.append(f"{out_of_range} item answers are outside 1-6.")
    gender = pd.to_numeric(df["gender"], errors="coerce").dropna()
    if not set(gender.unique()) <= {1, 2}:
        problems.append(f"gender has values other than 1 and 2: {sorted(gender.unique())}.")
    if df["id"].duplicated().any():
        problems.append("The id column has duplicate values.")
    return problems


def summarise(df: pd.DataFrame) -> str:
    """One-paragraph summary of the dataset for the console."""
    complete = int(df[BFI_ITEMS].notna().all(axis=1).sum())
    missing = int(df[BFI_ITEMS].isna().sum().sum())
    return (
        f"{len(df)} respondents, {len(BFI_ITEMS)} items; {complete} with every item answered; "
        f"{missing} missing item answers in total."
    )


def download_bfi(url: str = BFI_URL, timeout: float = 60.0) -> pd.DataFrame:
    """Download the bfi CSV and return it as text columns (values unchanged)."""
    with urllib.request.urlopen(url, timeout=timeout) as response:
        raw = response.read()
    return tidy_bfi(pd.read_csv(io.BytesIO(raw), dtype=str, keep_default_na=False, na_values=[""]))


def main(argv: list[str] | None = None) -> int:
    """Command-line entry point; returns the process exit code."""
    parser = argparse.ArgumentParser(description="Download the bfi sample dataset.")
    parser.add_argument("--force", action="store_true", help="download again and overwrite")
    args = parser.parse_args(argv)

    if BFI_PATH.exists() and not args.force:
        df = pd.read_csv(BFI_PATH, dtype=str, keep_default_na=False, na_values=[""])
        problems = validate_bfi(df)
        if problems:
            print(f"{BFI_PATH} exists but has problems:\n- " + "\n- ".join(problems))
            print("Run again with --force to download a fresh copy.")
            return 1
        print(f"{BFI_PATH} already present and valid: {summarise(df)}")
        print(DASS_NOTE)
        return 0

    print(f"Downloading {BFI_URL} ...")
    try:
        df = download_bfi()
    except (urllib.error.URLError, TimeoutError) as exc:
        print(f"Download failed: {exc}. Check your internet connection and try again.")
        return 1

    problems = validate_bfi(df)
    if problems:
        print(
            "The downloaded file does not look like bfi; nothing was saved:\n- "
            + "\n- ".join(problems)
        )
        return 1

    BFI_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(BFI_PATH, index=False)
    print(f"Saved {BFI_PATH}: {summarise(df)}")
    print(DASS_NOTE)
    return 0


if __name__ == "__main__":
    sys.exit(main())
