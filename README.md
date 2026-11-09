# SurveyDoctor

SurveyDoctor checks the quality of rating-scale survey data (careless responding, reliability, factor structure, sample sensitivity, robustness) before anyone draws conclusions from it.

**Status:** under construction. See `BLUEPRINT.md` for the full plan. No evaluation results are reported yet; they will be copied here from generated files in `backend/results/` once they exist.

**Reference validation against R:** run for the careless-response indices (longstring, IRV, Mahalanobis, even-odd, psychometric synonyms), reliability (alpha with CI, alpha if deleted, corrected item-total correlation, omega total) factor structure (KMO, Bartlett's test, correlation eigenvalues, 5-factor EFA loadings, communalities and factor correlations) and fsQCA (calibration, necessity, truth table, and complex and parsimonious solutions with their fit; QCA package). Results and documented differences: `docs/validation.md`.

**Reference validation against G*Power:** the sample-sensitivity calculations (smallest detectable d, r and f) match G*Power 3.1.9.7 within 0.01 on 5 cases. See `docs/validation.md`.

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

## Run the API locally

```bash
cd backend
uvicorn api.main:app --reload
```

Then open http://localhost:8000/docs to try every endpoint. The API is stateless: each request carries its CSV, which is processed in memory and discarded. Limits: 10 MB and 50,000 rows per file. Set `ALLOWED_ORIGINS` (comma-separated) to the website's address when deploying.

## Run the website locally

Requires Node.js 20 or newer. Start the API first (above), then in a second terminal:

```bash
cd frontend
npm install        # first time only
npm run dev        # open the address it prints, usually http://localhost:5173
npm test           # component tests
```

The website reads the API address from `VITE_API_URL` (default `http://localhost:8000`; see `frontend/.env.example`). After a change to the API's models, regenerate the TypeScript types with the API running: `npm run gen:api`.

Before a release, click through `docs/qa_checklist.md` on a laptop-width and a phone-width window.

## Regenerate the R reference values (optional)

Requires R with the packages `careless`, `psych`, `GPArotation`, `QCA` and `jsonlite`. Without R, the reference tests skip.

```bash
cd backend
Rscript validation/reference_careless.R
Rscript validation/reference_reliability.R
Rscript validation/reference_structure.R
Rscript validation/reference_fsqca.R
pytest tests/test_reference_r.py
```

On Windows, if `Rscript` is not on PATH, use its full path, e.g. `"C:\Program Files\R\R-4.6.1\bin\Rscript.exe"`.
