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
