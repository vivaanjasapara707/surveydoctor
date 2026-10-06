# SurveyDoctor

SurveyDoctor checks the quality of rating-scale survey data (careless responding, reliability, factor structure, sample sensitivity, robustness) before anyone draws conclusions from it.

**Status:** under construction. See `BLUEPRINT.md` for the full plan. No validation or evaluation results are reported yet; they will be copied here from generated files in `backend/results/` once they exist.

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
