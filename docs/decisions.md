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
