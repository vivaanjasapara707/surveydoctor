# SurveyDoctor v1 — Build Blueprint

Version 1.1 · 6 October 2026 · Owner: Vivaan Jasapara

This is the single source of truth for building SurveyDoctor v1. Claude Code implements it stage by stage. If something in the code disagrees with this file, either fix the code or update this file deliberately — never let them drift silently.

Items marked **[VERIFY]** were written from memory without web access. Check them against the official source before relying on them, and record the result in `docs/verification_log.md`.

---

## 1. What we are building

SurveyDoctor is a web app that checks the quality of rating-scale survey data (e.g. answers from 1 to 5) before anyone draws conclusions from it.

The user uploads a CSV, tells the app which columns are questions and which questions belong to which scale, and receives:

1. **Careless-response screening** — which respondents likely answered without reading, and the evidence for each flag.
2. **Reliability** — whether each scale's questions agree with each other (alpha, omega).
3. **Factor structure** — whether questions group the way the researcher intended (EFA).
4. **Sample sensitivity** — the smallest effect the sample can reliably detect.
5. **Robustness check** — whether one declared conclusion (a group difference or a correlation) survives removing flagged respondents.
6. **A downloadable HTML report** in which every sentence is generated from computed numbers.

**Primary user:** students running survey-based projects, and the supervisors who review them.

### 1.1 In scope for v1

| Area | Included |
|---|---|
| Input | CSV upload; schema defined in the app or uploaded as JSON; built-in sample dataset |
| Careless indices | Longstring, IRV, Mahalanobis distance, even-odd consistency, psychometric synonyms, person-total correlation, response time (only if a duration column exists) |
| Flagging | Rule-based flags with reasons; composite relative score |
| Reliability | Cronbach's alpha with 95% CI, McDonald's omega total, corrected item-total correlations, alpha-if-deleted, possible reverse-item warnings |
| Structure | KMO, Bartlett's test, parallel analysis, EFA (minres, oblimin), loading flags, scale-alignment check |
| Sample size | Sensitivity analysis for two-group t-test, correlation, one-way ANOVA |
| Robustness | One declared analysis, rerun under 3 flagging variants |
| Evaluation | Simulation study (5 careless patterns × 3 contamination rates); real-data proxy evaluation if the DASS dataset is available |
| Validation | Automated comparison against R (`psych`, `careless`) and G*Power reference values |
| Output | React website backed by a FastAPI API; HTML report; flagged-respondents CSV; schema JSON |
| Delivery | Tests, README, deployment (Render for the API, Vercel for the website) |

### 1.2 Out of scope (v2 or later)

Polychoric correlations · CFA · probabilistic (mixture-model) carelessness scoring · questionnaire audit before fielding · measurement invariance · public benchmark dataset · faculty batch mode · PDF reports · automatic test recommendation · LLM-written text · accounts, payments, database.

Do not build any of these in v1, even if they seem quick.

---

## 2. Non-negotiable rules

1. **No fabricated results.** Never write a number, test outcome, accuracy figure or "passed" claim that was not produced by actually running code. Results in the README are copied from generated files in `results/`.
2. **Every statistic is tested.** Each function has unit tests with hand-checkable cases. Core statistics also have reference tests against R or G*Power.
3. **Reference mismatches are documented, not hidden.** If our output differs from R beyond tolerance, record the cause in `docs/validation.md`. Do not loosen tolerances just to make a test pass.
4. **Report text is templated.** Sentences are fixed templates filled with computed values. No LLM generates interpretations.
5. **Never auto-reverse items.** The tool may warn that an item looks reverse-coded; only the user decides.
6. **Never silently drop data.** Any exclusion (missing values, invalid answers) is counted and reported.
7. **No uploaded data is stored.** Processing is in memory only; the app says so.
8. **Scope discipline.** Section 1.2 features are not built in v1.

---

## 3. Tech stack

### 3.1 Backend (Python)

| Tool | Purpose |
|---|---|
| Python 3.11 | Language |
| pandas, NumPy | Data handling and per-respondent calculations |
| SciPy | Distributions (chi-square, normal), correlations, Mann–Whitney, Welch t-test, `linear_sum_assignment` for factor matching |
| statsmodels | Power/sensitivity calculations |
| pingouin | Cronbach's alpha with confidence interval |
| factor_analyzer | EFA, KMO, Bartlett's test, oblimin rotation |
| scikit-learn | ROC-AUC, PR-AUC, precision, recall |
| matplotlib | Charts embedded in the HTML report as base64 PNG |
| Jinja2 | HTML report templates |
| FastAPI + Uvicorn | HTTP API that exposes the pipeline to the website |
| python-multipart | CSV file uploads in FastAPI |
| pytest + httpx | Tests, including API tests via FastAPI's TestClient |
| ruff | Linting |
| R + `psych`, `careless`, `GPArotation`, `jsonlite` | Reference values only (local, never deployed) |
| G*Power | Reference values for sensitivity analysis (entered manually) |

### 3.2 Frontend (website)

| Tool | Purpose |
|---|---|
| Node.js 20 LTS | Runs the frontend build tools |
| Vite | Dev server and production build |
| React + TypeScript | The website; TypeScript catches data-shape mistakes before they reach the browser |
| Tailwind CSS | Styling, configured with the design tokens from `docs/design.md` |
| Recharts | Interactive charts (score distribution, scree plot) |
| Framer Motion | At most one or two purposeful animations (§7.13) |
| openapi-typescript | Generates TypeScript types from the API's OpenAPI schema, so frontend and backend can't silently disagree |
| Vitest + React Testing Library | Component tests |
| ESLint + Prettier | Code quality and formatting |

### 3.3 Hosting

- **Backend:** Render free web service **[VERIFY current free-tier limits]**. Free services sleep after inactivity, so the first request can be slow; the website shows a clear "starting the analysis server" state.
- **Frontend:** Vercel free tier, static build **[VERIFY]**.
- The frontend reads the API address from `VITE_API_URL`. The backend allows requests only from the frontend's domain (`ALLOWED_ORIGINS` environment variable).

**Version policy:** install the latest compatible versions in Stage 1 (backend) and Stage 12 (frontend), confirm tests pass, then pin exact versions (`pip freeze`, `package-lock.json`). **Known risk [VERIFY]:** `factor_analyzer` has had compatibility issues with newer scikit-learn releases. If imports fail, pin scikit-learn to the newest version that works and record it in `docs/decisions.md`.

---

## 4. Repository structure

One repository with two parts: `backend/` (Python statistics + API) and `frontend/` (React website).

```text
surveydoctor/
├── CLAUDE.md                       # Rules for Claude Code (short)
├── BLUEPRINT.md                    # This file
├── README.md
├── .gitignore                      # .venv/, node_modules/, backend/data/raw/, dist/, caches
├── .claude/skills/                 # Claude Code skills installed by the owner (e.g. frontend-design)
├── docs/
│   ├── decisions.md                # Technical decisions and why
│   ├── validation.md               # Reference comparison results and mismatches
│   ├── verification_log.md         # [VERIFY] items checked and outcomes
│   ├── design.md                   # Approved design plan (palette, type, layout, principles)
│   └── qa_checklist.md             # Manual click-through checklist for the website
├── backend/
│   ├── requirements.txt            # Runtime deps, pinned (used by Render)
│   ├── requirements-dev.txt        # pytest, httpx, ruff
│   ├── surveydoctor/               # The statistics package (no web code here)
│   │   ├── __init__.py
│   │   ├── schema.py               # SurveySchema dataclass, JSON load/save
│   │   ├── io.py                   # Load CSV, label mapping, validation, scoring
│   │   ├── careless.py             # Careless-response indices
│   │   ├── flagging.py             # Flag rules, composite score, flag variants
│   │   ├── reliability.py          # Alpha, omega, item statistics
│   │   ├── structure.py            # KMO, Bartlett, parallel analysis, EFA
│   │   ├── power.py                # Sensitivity analysis
│   │   ├── robustness.py           # Declared analysis under flag variants
│   │   ├── pipeline.py             # Runs all modules, returns one Results object
│   │   ├── report.py               # Builds HTML report from Results
│   │   ├── charts.py               # matplotlib figures → base64 (report only)
│   │   ├── text.py                 # Sentence templates (§7.10)
│   │   └── templates/report.html.j2
│   ├── api/
│   │   ├── main.py                 # FastAPI app, CORS, routes
│   │   ├── models.py               # Pydantic request/response models
│   │   └── errors.py               # Error codes → plain-English messages
│   ├── evaluation/
│   │   ├── simulate.py
│   │   ├── run_simulation.py
│   │   └── run_proxy_eval.py
│   ├── validation/
│   │   ├── reference_careless.R
│   │   ├── reference_reliability.R
│   │   └── reference_structure.R
│   ├── scripts/download_data.py
│   ├── data/
│   │   ├── sample/bfi.csv          # Committed sample dataset
│   │   ├── sample/bfi_schema.json
│   │   └── raw/                    # Not committed (DASS etc.)
│   ├── results/                    # Generated evaluation outputs (committed)
│   └── tests/
│       ├── fixtures/               # Reference JSON, gpower_reference.json, google_forms_sample.csv
│       ├── test_schema_io.py
│       ├── test_careless.py
│       ├── test_flagging.py
│       ├── test_reliability.py
│       ├── test_structure.py
│       ├── test_power.py
│       ├── test_robustness.py
│       ├── test_report.py
│       ├── test_reference_r.py     # Skips cleanly if fixtures are missing
│       ├── test_pipeline_e2e.py
│       └── test_api.py
└── frontend/
    ├── package.json
    ├── vite.config.ts
    ├── tailwind.config.ts          # Design tokens from docs/design.md
    ├── index.html
    └── src/
        ├── main.tsx
        ├── App.tsx                 # Step flow and top-level state
        ├── api/
        │   ├── client.ts           # fetch wrappers, error handling, server wake-up
        │   └── schema.ts           # Generated by openapi-typescript (never hand-edited)
        ├── screens/                # Landing, Upload, LabelMapping, ScaleBuilder, Results, Robustness
        ├── components/             # VerdictHeader, FlagTable, ScoreHistogram, ScreePlot, LoadingsTable, ...
        └── styles/                 # Global CSS and fonts
```

---

## 5. Data

### 5.1 Sample and reference dataset: `bfi`

- 25 Big Five personality items (A1–A5, C1–C5, E1–E5, N1–N5, O1–O5), 6-point scale (1–6), about 2,800 respondents, plus `gender`, `education`, `age`.
- Source: R package `psych`. CSV copy via Rdatasets: `https://raw.githubusercontent.com/vincentarelbundock/Rdatasets/master/csv/psych/bfi.csv` **[VERIFY URL and licence]**.
- Reverse-keyed items: A1, C4, C5, E1, E2, O2, O5 **[VERIFY against `psych::bfi.keys` documentation]**.
- `gender` (1/2) supports the robustness demo (two-group comparison).
- `data/sample/bfi_schema.json` defines the five scales and reverse items.

### 5.2 Proxy evaluation dataset: DASS (optional, downloaded manually)

- Source: openpsychometrics.org raw data page, DASS-42 dataset **[VERIFY availability and licence; believed non-commercial]**.
- Expected contents **[VERIFY with codebook]**: items Q1A–Q42A (1–4 scale), per-item elapsed time columns (Q1E–Q42E, milliseconds), a vocabulary checklist VCL1–VCL16 where VCL6, VCL9 and VCL12 are fake words.
- Proxy label: `careless_proxy = 1` if the respondent claimed to know at least one fake word.
- Scales **[VERIFY item mapping with codebook]**: Depression (3, 5, 10, 13, 16, 17, 21, 24, 26, 31, 34, 37, 38, 42), Anxiety (2, 4, 7, 9, 15, 19, 20, 23, 25, 28, 30, 36, 40, 41), Stress (1, 6, 8, 11, 12, 14, 18, 22, 27, 29, 32, 33, 35, 39). No reverse items.
- Stored in `data/raw/` and never committed. The README describes it as a methods-evaluation dataset only.
- Limitation to state everywhere: claiming fake words measures overclaiming, which overlaps with careless responding but is not identical. Results are "agreement with a validity proxy", not "accuracy".

### 5.3 Input format for users

SurveyDoctor does not host forms or receive submissions. Responses stay in the user's survey platform (Google Forms, Microsoft Forms, etc.). After collection, the user exports a CSV and uploads it to the app.

- CSV, one row per respondent, one column per question; header row required.
- Answers may be **numbers** (1–5) **or text labels** ("Strongly agree"). Google Forms exports text labels for multiple-choice and grid questions, so text-label support is required, not optional.
- Exports typically include extra columns (e.g. `Timestamp`, email address, name). These are never treated as items. Columns that look like emails or names are excluded from analysis and from all downloads by default.
- Column headers are often full question text. The app assigns short codes (Q1, Q2, …) and keeps a code → full-question table for the report.
- Grid questions export as one column per row of the grid (e.g. "Rate the course [Content]"); each becomes one item.
- Missing answers may be blank or NA.
- Google Forms exports a submission timestamp only, with no start time **[VERIFY]**, so response-time screening is usually unavailable for Google Forms data; the report says so.

---

## 6. Data model

### 6.1 `SurveySchema` (`schema.py`)

```python
@dataclass
class SurveySchema:
    items: list[str]                 # item columns, in questionnaire order
    scales: dict[str, list[str]]     # scale name -> item columns (subset of items)
    reverse_items: list[str]         # items to reverse-score (subset of items)
    scale_min: int                   # e.g. 1
    scale_max: int                   # e.g. 5
    id_column: str | None = None
    duration_column: str | None = None
    duration_unit: Literal["seconds", "minutes", "milliseconds"] = "seconds"
    label_map: dict[str, int] | None = None      # e.g. {"strongly disagree": 1, ..., "strongly agree": 5}
    question_text: dict[str, str] | None = None  # short code -> original column header
```

- `io.py` provides `detect_label_scale(df, columns)`, which recognises common agreement, frequency and satisfaction label sets (5- and 7-point; matching is case- and whitespace-insensitive) and proposes a `label_map`. The user confirms or edits it in the app. Unrecognised labels are reported, never guessed.

- `to_json()` / `from_json()`; validation raises `SchemaError` with a plain-English message if a scale or reverse item is not in `items`, if `scale_min >= scale_max`, or if a scale has fewer than 2 items.
- Item order matters: longstring and even-odd depend on it.

### 6.2 `PreparedData` (`io.py`)

```python
@dataclass
class PreparedData:
    raw_items: pd.DataFrame          # item answers as given (numeric, NaN for missing/invalid)
    scored_items: pd.DataFrame       # reverse items recoded: scale_min + scale_max - x
    meta: pd.DataFrame               # all non-item columns
    durations_seconds: pd.Series | None
    issues: list[DataIssue]          # counts of invalid/missing values, dropped rows, etc.
```

- Out-of-range or non-numeric answers become NaN and are counted in `issues`.
- Rows with every item missing are removed and counted.
- `scored_items` is used for scale scores, even-odd, reliability, structure, robustness. `raw_items` is used for longstring, IRV, Mahalanobis, psychometric synonyms, person-total.

### 6.3 `Results` (`pipeline.py`)

A single dataclass holding every module's output plus `warnings: list[str]`. The report and the app read only from this object.

---

## 7. Module specifications

Every public function has type hints and a docstring explaining the statistic in plain English, its direction (what "worse" looks like), and its limitations.

### 7.1 `careless.py`

All indices return a `pd.Series` indexed like the input; NaN where not computable (with a reason recorded in warnings).

| Index | Data | Definition | Careless direction |
|---|---|---|---|
| `longstring` | raw | Longest run of identical consecutive answers in item order. A missing value breaks a run. | High |
| `irv` | raw | Standard deviation (ddof=1) of the respondent's non-missing answers. Reported only; not used in flags or composite because both very low and very high values can indicate carelessness. | Ambiguous |
| `mahalanobis` | raw | D² = (x − μ)ᵀ Σ⁻¹ (x − μ), μ and Σ from complete cases, Σ⁻¹ via pseudo-inverse. Also returns p-value from chi-square with df = number of items. Rows with missing values → NaN. | High (low p) |
| `even_odd` | scored | For each scale with ≥ 4 items, mean of odd-position items and mean of even-position items. Per respondent, Pearson correlation between odd-half and even-half means across scales. Needs ≥ 3 eligible scales, else NaN for everyone with a warning. Return raw r; also provide Spearman–Brown corrected value 2r/(1+r) as a separate column. | Low |
| `psychsyn` | raw | Item pairs with sample correlation > 0.60 (pairwise complete) are "synonyms". Per respondent, Pearson correlation between first-item and second-item answers across pairs. Needs ≥ 3 usable pairs, else NaN with warning reporting how many pairs were found. | Low |
| `person_total` | raw | Per respondent, Pearson correlation between their answers and the leave-one-out item means (means computed from all other respondents). Zero-variance respondents → NaN (longstring covers them). | Low |
| `seconds_per_item` | duration | duration_seconds ÷ number of items. Only if a duration column is declared. | Low |

`compute_indices(prepared, schema) -> pd.DataFrame` returns all available indices as columns.

### 7.2 `flagging.py`

Default rules (all configurable in the app; defaults stored in one dict `DEFAULT_RULES`):

| Rule | Default | Source |
|---|---|---|
| Longstring | ≥ ceil(0.5 × number of items) | Heuristic; longstring cut-offs are dataset-specific — state this in the report |
| Mahalanobis | p < 0.001 | Common convention **[VERIFY citation]** |
| Even-odd | raw r < 0.30 | Johnson (2005) **[VERIFY]** |
| Psychometric synonyms | r < 0 | Heuristic |
| Person-total | r < 0 | Heuristic |
| Seconds per item | < 2 | Huang et al. (2012) **[VERIFY]** |

- `apply_flags(indices, rules) -> pd.DataFrame` with one boolean column per rule, `n_rules_triggered`, `flagged` (≥ 1 rule), and `reasons` (readable string, e.g. "Longstring 25 (threshold 13); Mahalanobis p < 0.001").
- `composite_score(indices) -> pd.Series`: for each available index except IRV, convert to its careless direction, take the percentile rank within the dataset (0–1), and average across available indices. This is a **relative ranking score**, not a probability; the report says so.
- `flag_variants(flags, composite) -> dict[str, pd.Series]` returning three exclusion masks used by robustness:
  - `any_rule`: ≥ 1 rule triggered
  - `two_rules`: ≥ 2 rules triggered
  - `composite_top10`: top 10% composite score

### 7.3 `reliability.py`

Per scale, on `scored_items`, listwise complete cases (count reported):

- `cronbach_alpha`: via `pingouin.cronbach_alpha`, with 95% CI.
- `omega_total`: fit a one-factor model (`factor_analyzer`, method `minres`, no rotation) on the scale's items; standardized loadings λ, uniquenesses ψ = 1 − h². ω = (Σλ)² / ((Σλ)² + Σψ). Requires ≥ 3 items, else NaN with warning.
- `item_stats`: per item — corrected item-total correlation (item vs sum of the other items) and alpha if item deleted.
- `reverse_warnings`: items with corrected item-total correlation < 0 on scored data → "may be reverse-coded but not declared, or poorly worded". Never auto-reverse.
- Also report: number of items, N used.

### 7.4 `structure.py`

On all `scored_items` (or a user-selected subset), listwise complete cases:

- `kmo`: overall KMO and per-item MSA (`factor_analyzer.calculate_kmo`).
- `bartlett`: chi-square, df, p (`calculate_bartlett_sphericity`).
- `parallel_analysis`: Horn's method on the Pearson correlation matrix. Generate 100 random standard-normal datasets of the same n × k (fixed seed 42), compute eigenvalues of each correlation matrix, take the 95th percentile per position. Suggested number of factors = count of leading observed eigenvalues above the threshold. Also report the eigenvalue > 1 count for contrast. Return data for the scree chart.
- `efa`: `FactorAnalyzer(n_factors, rotation="oblimin", method="minres")`, where `n_factors` = parallel-analysis suggestion unless the user overrides. Return loadings, communalities, factor correlation matrix (if available from the library; otherwise compute from rotated scores and document).
- Flags: item max |loading| < 0.30 → weak; second-highest |loading| ≥ 0.30 → cross-loading.
- `scale_alignment`: for each declared scale, which factor most of its items load on, and the share of items whose primary factor matches that factor.
- Warnings: N < 200, or N/items < 5 → "factor solution may be unstable"; KMO < 0.6 → "data may be unsuitable for factor analysis"; always note "correlations treat ordinal answers as continuous (Pearson); polychoric correlations are planned for v2".

### 7.5 `power.py` — sensitivity analysis

All at α = 0.05 (two-sided) and power = 0.80 by default; both configurable.

- `min_d_two_groups(n1, n2)`: smallest Cohen's d, via `statsmodels.stats.power.TTestIndPower().solve_power(effect_size=None, nobs1=n1, ratio=n2/n1, alpha, power)`.
- `min_r_correlation(n)`: smallest |r| via Fisher z: z = (z₁₋α/₂ + z_power) / √(n − 3); r = tanh(z).
- `min_f_anova(n_total, k_groups)`: smallest Cohen's f via `FTestAnovaPower().solve_power(effect_size=None, nobs=n_total, k_groups=k, alpha, power)` **[VERIFY that `nobs` is total N in statsmodels]**.
- Each result includes a verbal label using Cohen's conventional benchmarks (small/medium/large) with the caveat that benchmarks are rough.
- Never compute post-hoc power from an observed effect.

### 7.6 `robustness.py`

The user declares exactly one analysis:

- **Group comparison:** a scale score compared between two groups of a chosen column (user picks the two group values). Welch's t-test, mean difference with 95% CI, Cohen's d (pooled SD), plus Mann–Whitney U as a companion.
- **Correlation:** between two scale scores. Pearson r with 95% CI (Fisher z) and p; Spearman ρ as a companion.

Scale score = mean of scored items, computed only if ≥ 80% of the scale's items are answered.

Run on: all respondents, then excluding each of the three flag variants (§7.2). Output table: variant, N, estimate, 95% CI, p, significant at 0.05, direction.

Verdict logic (templated):
- Same significance and same direction in all variants → "stable".
- Significance changes in any variant → "sensitive to careless responses" and name the variant(s).
- Direction changes → "unstable" (strongest warning).

Always add: "This shows sensitivity to exclusion choices. It does not prove which respondents should be excluded."

### 7.7 `evaluation/` — simulation study

- Base data: `bfi` complete cases on the 25 items.
- Patterns (each replaces the answers of randomly selected rows; those rows get label 1):
  - `random`: uniform integers in range
  - `straightline`: one random constant per respondent
  - `patterned`: repeating sequence min…max starting at a random offset
  - `midpoint`: middle value (for even-point scales, randomly the lower or upper middle per respondent)
  - `partial`: first half of items kept, second half uniform random
- Contamination rates: 5%, 10%, 20%. Repetitions: 20 per condition, seeds 0–19.
- Metrics per index and composite: ROC-AUC and PR-AUC (scores oriented so higher = more careless); recall and precision of the default `flagged` rule.
- Outputs: `results/simulation_results.csv` (every rep) and `results/simulation_summary.md` (mean ± SD per pattern × rate × index), both generated by the script.
- Limitation to state: the base data contains some genuinely careless respondents labelled 0, which slightly understates precision.

### 7.8 `evaluation/run_proxy_eval.py`

- Runs only if `data/raw/dass/` exists; otherwise prints how to obtain it and exits with code 0.
- Uses the DASS schema (§5.2) including per-item time (sum of elapsed ms → seconds).
- Metrics per index and composite against `careless_proxy`: ROC-AUC, PR-AUC, recall/precision of default flags, proxy base rate.
- Outputs: `results/proxy_eval.csv`, `results/proxy_eval_summary.md`.

### 7.9 `report.py`, `charts.py`, `templates/report.html.j2`

Self-contained HTML (inline CSS, base64 images, no external requests). Sections:

1. Summary — N, items, scales, number flagged, headline reliability, factor suggestion, robustness verdict.
2. Data checks — issues from `PreparedData`.
3. Careless responding — rules used, counts per rule, table of flagged respondents with reasons (top 50, full list in the CSV download), composite-score histogram.
4. Reliability — table per scale (alpha with CI, omega, N), item warnings.
5. Factor structure — KMO, Bartlett, scree plot with parallel-analysis line, loadings table with weak/cross-loading highlights, scale alignment.
6. Sample sensitivity — the three sensitivity results.
7. Robustness — table and verdict (if declared).
8. Limitations — auto-generated (§7.10).
9. Methods and references — short descriptions of each method; reference list marked "verify before citing".

Footer: SurveyDoctor version, timestamp, and "No data was stored."

### 7.10 `text.py` — wording rules

- Every sentence template takes computed values as arguments; no free text.
- Alpha/omega wording: report the value and CI; describe ≥ 0.70 as "commonly treated as acceptable", always with the caveat that high alpha does not prove the scale measures a single concept.
- Always include these limitations when they apply:
  - Convenience sample warning (always): "Statistical checks cannot fix who was sampled. If respondents were recruited through personal networks or social media, results may not generalise."
  - No duration column → response-time screening not performed.
  - Small N or low KMO → factor results may be unstable.
  - Pearson correlations on ordinal answers.
  - Flag thresholds are heuristics.

### 7.11 `api/` — FastAPI backend

The API is a thin layer: it validates requests, calls `surveydoctor.pipeline`, and converts results to JSON. No statistics are computed in `api/`.

**Stateless by design:** nothing is stored on the server. Each request carries the CSV (and schema), is processed in memory, and is discarded. Limits: 10 MB and 50,000 rows; larger uploads get a clear 413 error.

| Endpoint | Input | Output |
|---|---|---|
| `GET /api/health` | — | `{status, version}` (used for the wake-up check) |
| `GET /api/sample` | — | Sample CSV text + bfi schema JSON |
| `POST /api/inspect` | CSV file | Row/column counts; per column: short code, original header, distinct values, suggested-item flag, looks-personal flag; 10-row preview with personal columns removed; proposed label map; unrecognised labels |
| `POST /api/analyze` | CSV + schema JSON (+ optional rules, n_factors) | Full results JSON: overview, data issues, flag counts per rule, flagged respondents (top 200, with reasons), composite scores for the histogram, reliability, structure (eigenvalues, parallel threshold, loadings, alignment), sensitivity, warnings |
| `POST /api/robustness` | CSV + schema + analysis spec | Variant table + verdict |
| `POST /api/report` | CSV + schema (+ optional analysis spec) | HTML report file download |
| `POST /api/export/flags` | CSV + schema | Respondent-level indices, flags and reasons as CSV (personal columns excluded) |

- Request/response shapes are Pydantic models in `api/models.py`. FastAPI publishes them at `/openapi.json` and interactive docs at `/docs`.
- Errors return `{code, message}` with 400/413/422. Messages say what went wrong and how to fix it. Never return stack traces. Logs never contain uploaded data.
- `tests/test_api.py` covers every endpoint with the sample data and the messy Google Forms fixture, including error cases.

### 7.12 `frontend/` — React website

**Screens (one guided flow):**

1. **Landing:** what the tool does in one sentence, two actions ("Try with sample data", "Upload your survey"), a short "How to export from Google Forms / Microsoft Forms" guide, and the privacy statement.
2. **Upload:** drag-and-drop CSV; shows counts, a preview, and which personal columns were excluded.
3. **Answer labels** (only if needed): confirm the proposed text → number mapping; unrecognised labels must be mapped.
4. **Scales:** pick item columns, create scales and assign questions, mark reverse-worded items, set the scale range; import/export schema JSON.
5. **Results:** the data-quality verdict at the top (the memorable element), then sections for Careless responses (sortable flag table with reasons, score distribution), Reliability, Structure (scree plot with parallel-analysis line, loadings table with weak/cross-loading highlights), and Sample size.
6. **Robustness:** choose a group comparison or a correlation, see the variant table and verdict.
7. **Downloads:** HTML report, flags CSV, schema JSON.

**Rules:**

- The frontend computes no statistics; it only displays API results.
- Types come from `src/api/schema.ts`, generated from the backend's OpenAPI schema. Regenerate whenever API models change.
- All data lives in React state only. Refreshing the page clears it, and the UI says so.
- Every screen has loading, empty and error states. Errors show the API's message plus the fix.
- Server wake-up: if `/api/health` is slow, show "Starting the analysis server — this can take up to a minute on the free plan."
- Responsive down to 375 px width; keyboard accessible; respects reduced-motion settings.
- Component tests (Vitest) for the label-mapping screen, the scale builder, and the flag table.

### 7.13 UI and report design

**Design brief (give this to the frontend-design skill):** SurveyDoctor is a quality-control instrument for research data, used by students and their supervisors. Its job is to make a verdict on data quality obvious at a glance and to let a careful reader drill into the evidence. It should feel trustworthy, precise and calm — closer to a well-made lab instrument or audit report than a marketing dashboard. The memorable element is the data-quality verdict at the top of the results. Everything else stays quiet and disciplined.

Rules:
- The design plan (palette as named hex values, typefaces, layout with wireframes, principles) is written to `docs/design.md` and approved by the owner **before** any styling code.
- The plan is turned into Tailwind design tokens; components use tokens, not one-off colours.
- The HTML report uses the same palette and typefaces, prints cleanly to A4, and reads well on mobile.
- Accessibility floor: sufficient colour contrast, never use colour alone to signal a flag (always text too), visible keyboard focus.
- Copy is plain and active: buttons say what they do ("Run checks", "Download report"); errors say what went wrong and how to fix it.
---

## 8. Testing and validation

### 8.1 Unit tests (hand-checkable)

Examples the suite must include:
- Longstring of `[3,3,3,1,2]` = 3; a missing value breaks a run.
- IRV of `[1,2,3,4,5]` = sample SD ≈ 1.5811.
- A straightliner has longstring = number of items.
- Reverse scoring: on a 1–5 scale, 1 → 5 and 4 → 2.
- Alpha of perfectly correlated items is 1 (within tolerance); alpha drops when a random item is added.
- Parallel analysis on data generated with a known 3-factor structure suggests 3 factors (fixed seed).
- Fisher-z minimum r for n = 100 matches the formula computed independently in the test.
- Robustness verdict logic on constructed results ("stable", "sensitive", "unstable").
- Schema validation errors for bad input.
- Label mapping: "Strongly agree" / " strongly AGREE " → 5 on a 5-point agreement scale; an unrecognised label is reported, not guessed.
- Email and name columns are excluded from items and from downloads.

### 8.2 Reference tests against R (`tests/test_reference_r.py`)

- R scripts in `validation/` compute values on `data/sample/bfi.csv` and write JSON fixtures.
- Tests skip with a clear message if a fixture is missing (so the suite runs without R), and the README states whether reference validation was run.

| Quantity | R reference | Tolerance |
|---|---|---|
| Longstring | `careless::longstring` | exact |
| IRV | `careless::irv` | 1e-6 |
| Mahalanobis D² | `careless::mahad` (confirm D vs D² output) **[VERIFY]** | 1e-4 |
| Even-odd | `careless::evenodd` (confirm whether Spearman–Brown is applied) **[VERIFY]** | 1e-4 |
| Psychometric synonyms | `careless::psychsyn` (critval 0.60) | 1e-4 |
| Alpha | `psych::alpha` raw_alpha | 1e-3 |
| Omega total | `psych::fa(nfactors=1, fm="minres")` loadings + same formula | 1e-3 |
| KMO | `psych::KMO` overall | 1e-3 |
| Bartlett | `psych::cortest.bartlett` | chi-square 1e-2 |
| EFA loadings | `psych::fa(nfactors=5, rotate="oblimin", fm="minres")` after matching factor order and sign | 0.02 |

Factor matching: align factors with `scipy.optimize.linear_sum_assignment` on absolute loading correlations, then fix signs.

### 8.3 G*Power reference

The owner computes 5 sensitivity cases in G*Power and saves them to `tests/fixtures/gpower_reference.json` (inputs and output effect sizes). Tests compare with tolerance 0.01. Claude Code never invents these values.

### 8.4 End-to-end tests

- `tests/test_pipeline_e2e.py` runs the full pipeline on the bfi sample with a declared gender comparison and asserts that every section of `Results` is populated and the HTML report renders.
- `tests/test_api.py` exercises every endpoint, including the Google Forms-style fixture and error cases.
- Frontend: Vitest component tests (§7.12) plus the manual checklist in `docs/qa_checklist.md`, run before deployment.

---

## 9. Build plan (16 stages)

Claude Code does the implementation. The owner runs, checks, decides and understands. Pace: at about 2 hours a day (two stages), roughly 8–10 days; at 1 hour a day, about 16 days. Start a fresh Claude Code session for each stage.

Standard prompt (replace N):
> Implement Stage N from BLUEPRINT.md, following CLAUDE.md. Run the tests and show me the real output. Then explain what you built in plain English in under 15 lines, and list anything you could not verify.

Common commands:
- Backend tests: `cd backend` → `pytest`
- API locally: `cd backend` → `uvicorn api.main:app --reload` → open `http://localhost:8000/docs`
- Website locally: `cd frontend` → `npm install` (first time) → `npm run dev` → open the address it prints (usually `http://localhost:5173`)

| Stage | Claude Code builds | Owner runs and checks | Success looks like | Understand |
|---|---|---|---|---|
| 1 | Repo skeleton, backend requirements, `.gitignore`, `scripts/download_data.py`, `schema.py`, `io.py` (label mapping, personal-column exclusion), bfi schema JSON, Google Forms-style fixture, tests | Create venv, install, `python scripts/download_data.py`, `pytest` | bfi.csv saved; all tests pass; versions pinned | Why reverse scoring and label mapping are needed |
| 2 | `careless.py` + unit tests | `pytest tests/test_careless.py`; view indices for 10 bfi rows | Tests pass; values plausible | Longstring vs Mahalanobis |
| 3 | `flagging.py`; `validation/reference_careless.R`; reference tests | Install R + packages; run the R script; `pytest tests/test_reference_r.py` | Reference tests pass or mismatches documented | Why the composite is a ranking, not a probability |
| 4 | `reliability.py`; R reference script; tests | Run R script and tests | Matches `psych` within tolerance | Alpha vs omega |
| 5 | `structure.py`; R reference script; tests | Run R script and tests | Loadings match `psych::fa`; 5 bfi scales mostly align | PCA vs EFA; parallel analysis |
| 6 | `power.py` + tests | Compute 5 G*Power cases; save fixture; run tests | G*Power tests pass | Sensitivity vs post-hoc power |
| 7 | `evaluation/simulate.py`, `run_simulation.py` | Run the simulation; open `results/simulation_summary.md` | Results generated by the script | ROC-AUC vs PR-AUC |
| 8 | `run_proxy_eval.py` | Download DASS, check codebook, log [VERIFY] items; run script | Proxy results generated, or skip documented | Limits of the fake-word proxy |
| 9 | `robustness.py`, `pipeline.py` + tests | `pytest`; run the gender comparison on bfi | Variant table and verdict produced | What robustness does and doesn't prove |
| 10 | Design plan in `docs/design.md` (frontend-design skill) → **owner approves** → `report.py`, `charts.py`, `text.py`, report template + tests | Approve or revise the design plan; open the generated bfi report in a browser | Every section renders with real numbers in the approved style | Why templated text instead of an LLM |
| 11 | FastAPI `api/` + `tests/test_api.py` | Start the API; try every endpoint at `/docs` with the sample file | All API tests pass; `/docs` works | How the website talks to the Python code |
| 12 | Frontend scaffold, Tailwind tokens, generated API types, Landing, Upload and Answer-labels screens | `npm run dev`; upload the sample and the Google Forms fixture | Screens match the design plan; labels map correctly | What the frontend does vs the backend |
| 13 | Scales screen, Results screen, charts, component tests | Full flow on the sample data | Results match the API output; charts render | How charts are drawn from API data |
| 14 | Robustness screen, downloads, loading/empty/error/wake-up states, responsive and accessibility pass, `docs/qa_checklist.md` | Run the checklist, on desktop and a phone-width window, with the messy CSV | No crashes, clear messages, downloads work | How errors flow from API to screen |
| 15 | Deployment: Render (backend), Vercel (frontend), CORS and environment variables; README with results copied from `results/` and screenshots | Create Render and Vercel accounts, connect GitHub, set environment variables as instructed | Public website works end to end with the sample data | Architecture walkthrough in your own words |
| 16 | Final review and fix list | Full test run, checklist on the live site, 2-minute demo recording, interview questions (§11) | Definition of done (§10) met | Rehearse the explanation |

**If you fall behind:** first reduce simulation repetitions (20 → 10), then drop the proxy evaluation (document why), then postpone component tests to after launch. Never drop reference tests, the robustness check, or error handling.

---

## 10. Definition of done (v1)

- [ ] `pytest` passes locally; reference tests either pass or have documented, explained mismatches.
- [ ] Simulation results generated by script and committed in `results/`.
- [ ] Proxy evaluation run and committed, or its absence documented.
- [ ] Website and API deployed; full flow works on the sample dataset and the messy Google Forms-style CSV.
- [ ] `docs/qa_checklist.md` completed on the live site, including phone width.
- [ ] HTML report renders all sections with templated text only.
- [ ] README includes: problem, demo link, screenshots, how it works, validation results (copied from generated files), limitations, how to run locally, roadmap (v2 list).
- [ ] `docs/decisions.md`, `docs/validation.md`, `docs/verification_log.md` filled in.
- [ ] Owner can answer every question in §11 without notes.

---

## 11. Interview defence questions

1. What is the difference between PCA and EFA, and which did you use for what?
2. Why are Pearson correlations a limitation for Likert items, and what would you use instead?
3. Alpha is 0.91. Does that mean the scale is one-dimensional?
4. Why is post-hoc power meaningless, and what do you report instead?
5. How did you choose the number of factors?
6. Someone answered "4" to everything. How do you know they were careless and not genuinely neutral?
7. What was your ground truth for careless responses, and what are its limits?
8. Why PR-AUC rather than accuracy?
9. What does the robustness check prove, and what doesn't it prove?
10. Why should anyone trust your tool over asking an LLM to analyse the CSV?

---

## 12. README results template

Fill only with numbers from `results/` and test output:

> Built SurveyDoctor, a survey data-quality tool combining six careless-response indices, reliability (α, ω), and exploratory factor analysis. Statistical outputs verified against R reference packages ([X] of [Y] quantities within tolerance). In a simulation study, the composite score achieved PR-AUC of [x] for random responding and [y] for straightlining at 10% contamination. Deployed as a React + FastAPI web app with downloadable reports.

Never claim user adoption, accuracy on real users, or validation that was not run.

---

## 13. Risks and fallbacks

| Risk | Fallback |
|---|---|
| `factor_analyzer` incompatible with current scikit-learn | Pin a compatible scikit-learn; document in `decisions.md` |
| R or an R package won't install | Reference tests skip; README states reference validation was not completed for those quantities |
| `careless` package definitions differ from §7.1 | Match R where the published definition supports it; otherwise document the difference |
| DASS dataset unavailable or different from expected | Skip proxy evaluation; document |
| Render free tier is slow to wake or low on memory | Wake-up state in the UI; reduce parallel-analysis iterations for large uploads; enforce the upload cap |
| Frontend and backend data shapes drift apart | Regenerate `schema.ts` from `/openapi.json` after every API change; API tests pin the response shapes |
| CORS errors after deployment | `ALLOWED_ORIGINS` must exactly match the Vercel URL; Stage 15 documents the check |
| Owner misses days | Follow the slip rule in §9 |
