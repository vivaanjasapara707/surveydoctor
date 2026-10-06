# Technical decisions

Each entry records a choice the blueprint left open (or a forced deviation) and why. Newest stage last.

## Stage 1 — 6 October 2026

### Environment and versions
- **Python 3.11 via uv.** The machine had Python 3.13/3.14 but not 3.11, so the venv is created with `uv venv --seed --python 3.11 .venv` (uv downloads CPython 3.11.15).
- **scikit-learn pinned to 1.7.2 (below 1.8).** With scikit-learn 1.9.1, `FactorAnalyzer.fit` failed with `TypeError: check_array() got an unexpected keyword argument 'force_all_finite'` (factor_analyzer 0.5.1 uses an argument that scikit-learn removed). This is the risk named in BLUEPRINT §3/§13. With 1.7.2, EFA, KMO and Bartlett ran in a smoke test.
- **Plain `uvicorn`, without the `[standard]` extras**, to avoid adding packages that §3 doesn't list. `requirements.txt` was installed into a clean venv and the tests passed there.
- **pandas 3.0** (the latest release) is used. Its string dtype and copy-on-write behaviour are handled in `io.py`.

### CSV loading (`io.load_csv`)
- Every cell is read as text. Conversion to numbers happens only for item columns, in `prepare_data`, so text labels and numbers are handled the same way.
- These values count as missing after trimming: `"", NA, N/A, n/a, na, NaN, nan, null, NULL, #N/A`. "None" is not on the list because it can be a genuine free-text answer.
- Encoding: UTF-8 (with or without BOM) first, then Windows-1252 (Excel's default on Windows).
- Rows are parsed with Python's `csv` module, not `pandas.read_csv`. pandas silently drops extra fields when a row is longer than the header. A longer row is now an error naming the line, and a shorter row is padded with missing values.
- A column with an empty header and no data is ignored. Excel adds one for a trailing comma, and it holds nothing. An empty header over data is an error.

### Answers and labels
- A valid answer is a **whole number** from `scale_min` to `scale_max`. Fractions (2.5), out-of-range values and unknown labels become missing and are counted per item, with up to 5 example values.
- If a `label_map` exists, numeric answers are still accepted. Forms can mix linear-scale questions, which export numbers, with labelled multiple-choice questions.
- **Label detection:** the set (agreement, frequency or satisfaction; 5 or 7 points) that matches the most distinct observed labels wins. On a tie, the 5-point set is chosen and the other sets are returned as `alternatives`. Example: only "Agree" and "Disagree" appear, so it could be 5- or 7-point. The user confirms in the app. Unknown labels are reported, never guessed.
- "Neutral" counts as a spelling of the midpoint in the agreement and satisfaction sets.

### Personal columns
- A column is treated as personal if **at least half its values are email addresses**, or if **its header mentions email, name, surname, username, phone, mobile or address and its values are not rating answers**. The second condition stops a rating question such as "How often do you check your email?" being excluded.
- Personal columns are left out of item suggestions, short codes, value listings, previews and `PreparedData.meta`, so they cannot reach any download. Each exclusion is reported as a data issue.
- If the declared ID column looks personal, `prepare_data` raises an error instead of exposing it. Respondents are then identified by row number.

### Item suggestions
- A column is suggested as an item if at least **80%** of its non-missing answers are rating-like (a known label, or a whole number from −10 to 10, with at most 11 distinct numbers) and it has at least 2 distinct values. The 80% rule keeps a column with one typo; the ±10 bound excludes ages. This is only a suggestion; the user chooses the items.

### Short codes
- Headers that are already short identifiers (letter first; letters, digits, `_` or `.`; at most 16 characters, e.g. `A1`, `age`, `Timestamp`) keep their name. Other headers become Q1, Q2, … in column order, skipping codes already taken. `question_text` stores code → original header, and `prepare_data` renames columns with it.

### Rows and scoring
- The index of `PreparedData` frames is the respondent's 0-based position among the CSV's data rows. Removed rows keep their gaps, so flags can always be traced back to the file.
- Blank and invalid answers are counted among the respondents who were kept. Respondents with no valid answer at all are removed and counted once, in their own issue, so nothing is counted twice.
- `scale_scores` (the mean of a scale's scored items, given only when at least 80% of its items are answered, per §7.6) lives in `io.py` because it is scoring. Later stages (robustness) reuse it.
- Durations: missing, non-numeric and negative values become missing and are counted in one issue.

### Sample data
- The Rdatasets row-name column of bfi is renamed to `id`, and `id` is declared as `id_column` in `bfi_schema.json`. All values are saved exactly as downloaded.

## Stage 2 — 6 October 2026

### Environment
- `backend/.venv` was missing at the start of this session. It was recreated as the README describes (`uv venv --seed --python 3.11 .venv`, then the pinned `requirements.txt` and `requirements-dev.txt`). No new dependencies.

### Careless-response indices (`careless.py`)
- **Warnings.** Each index function takes an optional `warnings: list[str]` and appends a plain-English reason for anything it could not compute (a whole index, or a count of respondents). `compute_indices(prepared, schema, warnings=None)` keeps the blueprint's return type (`pd.DataFrame`), and the pipeline will pass its `Results.warnings` list.
- **Two-column indices.** `mahalanobis` returns `mahalanobis` (D²) and `mahalanobis_p`. `even_odd` returns `even_odd` (raw r) and `even_odd_sb` (Spearman–Brown). All other indices return one Series. `INDEX_DIRECTIONS` records the careless direction of every column, for flagging and the composite in Stage 3.
- **Minimum data for per-respondent correlations.** Even-odd, psychometric synonyms and person-total use one shared helper (`rowwise_pearson`). It returns NaN when a respondent has fewer than 3 usable points (scales, pairs or items) or no variance on either side, because a correlation from 2 points is always ±1. "Usable" means both values are present.
- **Even-odd halves** follow questionnaire order (the order of `schema.items`), not the order a scale's items are listed in. Half means use the answered items of each half. A scale counts for a respondent only if both halves have at least one answer.
- **Spearman–Brown is missing (NaN) whenever the raw even-odd r is negative.** The correction 2r/(1+r) estimates full-length reliability from a half-length correlation, which only makes sense for r ≥ 0. For negative r the formula falls below −1 (on bfi it reached about −94, at r = −0.979) and is undefined at r = −1, so the number would look like a correlation but not behave like one. The raw r is always kept, and flag rules use the raw r (§7.2), so no respondent loses evidence. On bfi, 230 respondents have a negative raw r and therefore no corrected value. Owner decision, 6 October 2026.
- **Mahalanobis** needs more complete respondents than items; otherwise the whole index is NaN with a warning. Negative D² from rounding is clipped to 0. Degrees of freedom stay equal to the number of items even when Σ is singular (pseudo-inverse), as specified.
- **Psychometric synonyms.** Pairs are taken from the upper triangle in questionnaire order (earlier item first), with correlation strictly greater than the critical value. The ≥ 3 rule applies to the pairs found in the data and to each respondent's fully answered pairs.
- **The psychsyn critical value is a parameter** (`critval` in `psychsyn`, `psychsyn_critval` in `compute_indices`), default 0.60 as in §7.1.
- **Stage 3 compares psychsyn against R (`careless::psychsyn`) at both critval 0.60 and 0.50.** bfi has only one pair above 0.60, so at the default both implementations return missing values for everyone and the comparison would check nothing. At 0.50, running `synonym_pairs` on bfi finds 5 pairs (A3–A5 0.504, N1–N2 0.707, N1–N3 0.556, N2–N3 0.549, N3–N4 0.520), and psychsyn is computed for 2,628 of 2,800 respondents, so there is a real numeric comparison. Owner decision, 6 October 2026.
- **Person-total.** A respondent's leave-one-out mean for an item they skipped is the ordinary item mean (their answer is not in it).
- **No duration column.** `seconds_per_item` is left out of the table. The "response-time screening not performed" limitation will be written by `text.py` (§7.10).

### Observed on the bfi sample (from running `compute_indices`)
- Only one item pair correlates above 0.60 (N1–N2, r = 0.707), so psychometric synonyms are NaN for everyone, with a warning, under the default rule. This follows the spec; the report will need to explain it.
- 364 respondents have at least one missing answer, so they have no Mahalanobis distance.

## Stage 3 — 6 October 2026

### R setup
- R 4.6.1 is installed at `C:\Program Files\R\R-4.6.1` and is not on PATH, so scripts are run with the full path to `Rscript.exe`. The packages (careless 1.2.2, psych 2.6.9, GPArotation 2026.8.2, jsonlite 2.0.0) were installed into R's per-user library (`R_LIBS_USER`, under `%LOCALAPPDATA%\R\win-library\4.6`), because the system library in Program Files needs administrator rights. Rscript finds that library automatically.

### Flag rules (`flagging.py`)
- **`DEFAULT_RULES`** maps each rule to `{"enabled": bool, <threshold>: number}`. The threshold keys are `share_of_items` (longstring), `p_below` (Mahalanobis), `r_below` (even-odd, psychsyn, person-total) and `seconds_below` (seconds per item). `merge_rules` lays user settings over the defaults and rejects unknown names or out-of-range values with a plain-English message.
- **`apply_flags(indices, rules=None, *, n_items, warnings=None)`.** The blueprint's `apply_flags(indices, rules)` cannot compute the longstring threshold (ceil(0.5 × number of items)) from the index table alone, so `n_items` is a required keyword argument.
- **Boundaries.** Longstring fires at or above its threshold (the blueprint writes "≥"); every other rule fires strictly below its threshold (the blueprint writes "<"). Example: p = 0.001 exactly is not flagged.
- **Missing index values never fire a rule.** A respondent with no Mahalanobis distance (a missing answer) cannot be flagged by that rule. Missing evidence is treated as no evidence, not as suspicious.
- **Rules that cannot be applied are left out**, not reported as flagging nobody. If a rule's index is missing for every respondent (e.g. psychsyn on bfi), the rule has no column in the flag table and a warning is added. A missing duration column drops the speed rule silently; `text.py` will state the limitation (§7.10).
- **Reasons** are fixed templates: "Longstring 25 (threshold 13)", "Mahalanobis D² 63.2, p < 0.001 (threshold p < 0.001)", "Even-odd r = 0.27 (threshold < 0.30)", "Person-total r = -0.06 (threshold < 0.00)", "1.5 seconds per item (threshold < 2)", joined with "; ".

### Composite score
- **Indices used:** longstring, Mahalanobis D², raw even-odd r, psychsyn, person-total and seconds per item (`COMPOSITE_INDICES`), whichever are present and computed for at least one respondent. Left out: IRV (ambiguous direction, as §7.1 says), Mahalanobis p, and the Spearman–Brown even-odd value. The last two carry the same ranking as D² and raw r, so including them would count those indices twice.
- **Percentile rank** = pandas `rank(method="average", pct=True)` on values oriented so that higher means more careless: the rank divided by the number of respondents with a value. Ties share the average rank. Values lie in (0, 1].
- A respondent's composite is the mean of the ranks they have. Indices missing for them are skipped. No computable index → missing.

### Flag variants
- **`composite_top10`** selects the k = ceil(10% × respondents with a composite) highest scores. Everyone tied with the k-th highest is included, so slightly more than 10% can be selected; ties are never broken arbitrarily. Respondents without a composite are never selected.

### R reference comparison
- The reference calls are chosen to match SurveyDoctor's definitions: `mahad` on complete cases, `psychsyn(resample_na = FALSE)`, and `evenodd` with its Spearman–Brown correction and sign flip undone in the test. The package defaults and how they differ are documented with numbers in `docs/validation.md`.

### Observed on the bfi sample (from running `apply_flags` with default rules)
- 686 of 2,800 respondents (24.5%) trigger at least one rule; 72 trigger two or more; `composite_top10` selects 280.
- Per rule: even-odd 490, person-total 184, Mahalanobis 84, longstring 4. Psychsyn is not applied (one synonym pair at 0.60).
- Even-odd r < 0.30 accounts for most flags. With only 5 scales, each respondent's even-odd r rests on 5 points, so it is noisy. The threshold is unchanged (it is the blueprint default, marked [VERIFY]). The owner may want to review it once the simulation study (Stage 7) shows how this rule performs.

### Follow-up: review the even-odd flag threshold after Stage 7
- The even-odd threshold (raw r < 0.30) will be reviewed after the Stage 7 simulation study. With bfi's 5 scales, each respondent's even-odd correlation rests on only 5 points (one odd-half and one even-half score per scale), so it is noisy. On bfi this rule flags 490 of 2,800 respondents, more than any other rule. Until the review, the blueprint default stays. Owner decision, 6 October 2026.

## Stage 4 — 6 October 2026

### Reliability (`reliability.py`)
- **Results shape.** `reliability(prepared, schema, warnings=None)` returns `{scale name: ScaleReliability}` in schema order. Each `ScaleReliability` holds the items, `n_items`, `n_used`, `n_excluded`, `alpha`, `alpha_ci`, `omega_total`, the one-factor `loadings`, an `item_stats` table (`corrected_item_total`, `alpha_if_deleted`) and `reverse_warnings`. `summary_table` gives one row per scale for the report and API.
- **Listwise deletion per scale.** Each scale uses the respondents who answered all of *its* items, so different scales can have different N. Every exclusion is counted (`n_excluded`) and also added to warnings, as `careless.py` does.
- **Alpha via pingouin, but complete cases are passed in.** `pingouin.cronbach_alpha` computes its CI from the row count *before* its own listwise deletion, so passing incomplete data would give a wrong interval. `cronbach_alpha` therefore refuses missing values; `scale_reliability` removes them first. pingouin rounds the CI bounds to 3 decimals; this is kept (it matches R within 1e-3, see `docs/validation.md`).
- **When alpha is missing (NaN):** fewer than 2 items, fewer than 2 complete respondents, or a total score that never varies. pingouin would otherwise fail with an assertion or divide by zero.
- **Alpha if item deleted** is computed with the same `cronbach_alpha` (pingouin) on the remaining items. It is missing for 2-item scales, where one item would remain.
- **Corrected item-total r** is missing when the item or the rest-score does not vary.
- **Omega conditions.** Besides the blueprint's "at least 3 items", omega is missing (with a warning) if there are not more complete respondents than items, or if an item is constant. Both make the correlation matrix unusable for the factor model.
- **Loadings are flipped to a non-negative sum.** A factor's sign is arbitrary; factor_analyzer returned all-negative loadings for Agreeableness on bfi. Flipping keeps loadings readable in the report and does not change omega. The R reference does the same.
- **Heywood warning.** factor_analyzer keeps uniquenesses at or above 0.005. If an item's uniqueness reaches that bound, a warning says omega may be overstated.
- **Omega uses ψ = 1 − λ²** from the fitted loadings (blueprint formula), not factor_analyzer's separately stored uniquenesses. For one factor they are the same quantity.
- **Reverse warnings are wording, not decisions.** A negative corrected item-total r adds a `ReverseWarning` with a fixed message and nothing else; the data are never changed. Observed limitation: on bfi with *no* reverse items declared, 13 items get the warning — all 7 truly reverse-keyed items plus C2, C3, E3, E4, E5 and O3. When two of five items are mis-keyed, the rest-score is pulled the wrong way and correctly keyed items can look negative too. With the correct reverse items declared, **no** warnings fire on bfi (lowest corrected item-total r: O4, 0.22). Both counts are pinned in `tests/test_reliability.py`.
- **Warning text says "check this question", not "reversed".** BLUEPRINT §7.3 suggests the wording "may be reverse-coded but not declared, or poorly worded". Because the warning also fires on correctly keyed items (above), the message no longer suggests a cause. It reads: "Check this question: it disagrees with the rest of its scale. Item X has a corrected item-total correlation of r with the other items of scale 'S'. SurveyDoctor does not change answers automatically." Owner decision, 6 October 2026. The `ReverseWarning` class and `reverse_warnings` function keep the blueprint's names.
- **Both omega warning paths are tested with realistic data, not mocks.** Two near-identical questions push a uniqueness to factor_analyzer's 0.005 bound and trigger the Heywood warning. Two identical columns (e.g. a question exported twice) make the correlation matrix singular, and factor_analyzer raises `LinAlgError("Singular matrix")`, which becomes a plain-English warning (wording changed in Stage 5, see below).

### Pre-existing doc typo fixed
- `README.md` and note 5 of `docs/verification_log.md` contained a backspace character instead of `\b` in `R-4.6.1\bin`, so the Rscript path displayed as `R-4.6.1in`. Both now read `C:\Program Files\R\R-4.6.1\bin\Rscript.exe`.

## Stage 5 — 6 October 2026

### Follow-up to Stage 4: plain-English omega failure message
- When the one-factor model behind omega fails because the correlation matrix is singular, the warning no longer quotes the library's error text ("Singular matrix"). It now reads: "Two or more questions in scale 'X' have identical or nearly identical answers, so omega could not be calculated." Constant items are ruled out before the fit, so near-duplicate questions are the remaining cause. Any other fitting error gives "Omega was not computed for scale 'X': the one-factor model could not be fitted to its answers." Owner request, 6 October 2026.

### Factor structure (`structure.py`)
- **Results shape.** `structure(prepared, schema, items=None, n_factors=None, warnings=None, pa_iterations=100)` returns a `StructureResults` with `kmo`, `bartlett`, `parallel` and `efa` (each `None` when not computed), plus `alignment` (scale name → `ScaleAlignment`), `n_used`/`n_excluded`, `n_factors`, `n_factors_source` ("parallel analysis" or "user") and `skipped_reason`. `alignment_table` gives one row per scale for the report and API.
- **Listwise deletion over all analysed items.** A respondent with any missing answer among the analysed items is left out of the whole analysis. The count is added to warnings.
- **When nothing is computed** (`skipped_reason`, also added to warnings): fewer than 3 items; no more complete respondents than items; an item with the same answer from everyone; or a singular correlation matrix (smallest eigenvalue < 1e-10). In the singular case, item pairs with |r| ≥ 0.999 are named so the user can find a question exported twice. If no such pair exists, the message points to derived columns such as a total score.
- **Bad user input raises `ValueError`** with a plain-English message. This covers unknown items and an `n_factors` outside 1 to (items − 1). Problems in the data produce warnings instead.
- **Parallel analysis.** `numpy.random.default_rng(42)` generates 100 standard-normal datasets of size n × k. The threshold at each position is `numpy.percentile(..., 95)` (linear interpolation) of the random eigenvalues. Counting stops at the first observed eigenvalue that is not strictly above its threshold. The eigenvalues are those of the Pearson correlation matrix (PCA-style), as the blueprint specifies.
- **If parallel analysis suggests 0 factors** (no eigenvalue beats random data), the EFA is not run and a warning says so. It is also skipped, with a warning, in the practically impossible case where as many factors as items are suggested.
- **The EFA uses `FactorAnalyzer(n_factors, rotation="oblimin", method="minres")`** as specified, with two corrections for factor_analyzer 0.5.1. Both problems were seen on bfi in this session:
  - **Factor correlations (Φ).** After rotation the library sorts factors by variance and reorders the loadings and structure matrix, but not `phi_`. On bfi, `loadings_ @ phi_` differed from `structure_` by up to 0.39. Φ is therefore recovered exactly from the library's own matrices: structure = LΦ, solved by least squares, with a residual of about 1e-15. The result matches `psych::fa`'s Phi (see `docs/validation.md`). The blueprint's fallback ("compute from rotated scores") was not needed.
  - **Communalities.** The library's `get_communalities()` sums squared pattern loadings, which is only correct for orthogonal rotations. On bfi it gave 0.27 for A1 instead of 0.20. Communalities are computed as diag(LΦLᵀ) instead. These equal the unrotated communalities to 4e-16 and match `psych::fa`.
- **A one-factor EFA** is allowed, although a single factor cannot be rotated. Φ is then [[1]], and the loadings are signed to a positive sum, as in `reliability.py`.
- **Heywood warning.** A warning names any item whose communality reaches 1 − 0.005 (factor_analyzer's bound on uniqueness).
- **Loading flags.** An item's primary factor is the one with its largest |loading|. Weak: largest |loading| < 0.30. Cross-loading: second-largest |loading| ≥ 0.30. With an oblique rotation these are pattern loadings.
- **Scale alignment.** A scale's factor is the most common primary factor among its analysed items. A tie goes to the factor with the larger sum of |loadings| over the scale's items. `shared_with` lists other scales that ended up on the same factor, the clearest sign that the data do not separate two intended scales. Scales with fewer than 2 analysed items are skipped.
- **Factor matching** (`factor_matching`, `match_factors`, `match_factor_correlations`) lives in `structure.py` rather than only in the tests, so later stages can reuse it. It applies `linear_sum_assignment` to the absolute correlations between loading columns, then fixes signs (BLUEPRINT §8.2). Pairs are returned in the reference's factor order.
- **Warnings** are added in this order: the Pearson note (always), excluded respondents, skipped analysis, small sample (N < 200 or fewer than 5 per item), KMO < 0.60, no factors suggested, EFA fit failure, Heywood case.
- **`kmo()` silences one factor_analyzer warning.** With many items the covariance determinant is tiny even when the matrix is fine, so the library warns that it used a pseudo-inverse. For a non-singular matrix that is identical to the inverse. Real singularity is caught before KMO is computed.

### R reference comparison
- `validation/reference_structure.R` runs `psych::KMO`, `psych::cortest.bartlett`, `eigen(cor(x))` and `psych::fa(nfactors = 5, rotate = "oblimin", fm = "minres")` on the same complete cases of the reverse-scored items.
- **Tolerances.** KMO, Bartlett and loadings use the §8.2 values. Per-item KMO uses the overall KMO tolerance. Communalities and factor correlations come from the same fitted solution as the loadings, so they use the loadings' tolerance (0.02), as Stage 4 did for the one-factor loadings. Eigenvalues are not in §8.2; they are compared at 1e-6 because they are plain linear algebra.
- The reference test fixes the EFA at 5 factors (`n_factors` from the fixture), so the comparison does not depend on parallel analysis.
- **Parallel analysis is compared with `psych::fa.parallel` (owner request, Stage 5 follow-up).** §8.2 lists no reference for it. psych is given the correlation matrix and `n.obs`, so it simulates standard-normal data, which is SurveyDoctor's method. Given raw data, it would resample the observed data instead. Settings: `fa = "pc"`, `n.iter = 100`, `quant = 0.95`, `set.seed(42)`. R and numpy produce different random numbers, so only the suggested number of components is compared, and it must match exactly. On bfi both suggest 5.
- **Evidence for the two factor_analyzer problems** is reproducible with `python validation/factor_analyzer_issues.py`. The script prints the library's raw `phi_` and `get_communalities()` next to psych's and SurveyDoctor's values. Its output is copied into `docs/validation.md`.

### Observed on the bfi sample (from running `structure` with defaults)
- 2,436 of 2,800 respondents answered all 25 items; 364 were left out.
- Overall KMO 0.849. Bartlett χ² = 18,146.07 (df = 300, p < 0.001).
- Parallel analysis suggests **5** factors: the 5th eigenvalue is 1.548 against a threshold of 1.116, and the 6th is 1.074 against 1.100. Kaiser's rule would say 6.
- With 5 factors, all 25 items have their primary loading on their own scale's factor. Each of the five scales has its own factor with a 100% match, and no item is weak. Three items cross-load (second |loading| ≥ 0.30): E3 (also on the Openness factor), N4 (also on the Extraversion factor, negatively) and O4 (also on the Extraversion factor, negatively).
