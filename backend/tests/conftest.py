"""Shared test fixtures and paths."""

from __future__ import annotations

from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).resolve().parent / "fixtures"
SAMPLE_DIR = BACKEND_DIR / "data" / "sample"
BFI_CSV = SAMPLE_DIR / "bfi.csv"
BFI_SCHEMA = SAMPLE_DIR / "bfi_schema.json"
GOOGLE_FORMS_CSV = FIXTURES / "google_forms_sample.csv"


@pytest.fixture
def bfi_csv_path() -> Path:
    """Path to the bfi sample; skips the test if it has not been downloaded yet."""
    if not BFI_CSV.exists():
        pytest.skip("data/sample/bfi.csv not found. Run: python scripts/download_data.py")
    return BFI_CSV
