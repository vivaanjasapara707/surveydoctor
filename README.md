# SurveyDoctor

SurveyDoctor checks the quality of rating-scale survey data (careless responding, reliability, factor structure, sample sensitivity, robustness) before anyone draws conclusions from it.

**Status:** under construction. See `BLUEPRINT.md` for the full plan. No evaluation results are reported yet; they will be copied here from generated files in `backend/results/` once they exist.

**Reference validation against R:** run for the careless-response indices only (longstring, IRV, Mahalanobis, even-odd, psychometric synonyms). Reliability and factor-structure comparisons are not built yet. Results and documented differences: `docs/validation.md`.

## Run the backend tests locally

Requires [uv](https://docs.astral.sh/uv/) (or any Python 3.11 installation).

```bash
cd backend
uv venv --seed --python 3.11 .venv
# Windows:  .venv\Scripts\activate      macOS/Linux:  source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
python scripts/download_data.py
pytest
```

## Regenerate the R reference values (optional)

Requires R with the packages `careless`, `psych`, `GPArotation` and `jsonlite`. Without R, the reference tests skip.

```bash
cd backend
Rscript validation/reference_careless.R
pytest tests/test_reference_r.py
```

On Windows, if `Rscript` is not on PATH, use its full path, e.g. `"C:\Program Files\R\R-4.6.1in\Rscript.exe"`.
