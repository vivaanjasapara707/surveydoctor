# Validation against reference software

This file records every comparison between SurveyDoctor and its reference implementations (R `psych`, R `careless`, G*Power), including any mismatch and its likely cause. Tolerances are defined in BLUEPRINT.md §8.2 and are never loosened to force a pass.

| Quantity | Reference | Tolerance | Result | Date run | Notes |
|---|---|---|---|---|---|
| Longstring | `careless::longstring` | exact | Pass (2,800 / 2,800 identical) | 2026-10-06 | |
| IRV | `careless::irv` | 1e-6 | Pass (2,800 respondents) | 2026-10-06 | |
| Mahalanobis D² | `careless::mahad` on complete cases | 1e-4 | Pass (2,436 respondents) | 2026-10-06 | Default `mahad` on all rows uses a different definition; see below |
| Even-odd (Spearman–Brown) | `careless::evenodd` (sign flipped back) | 1e-4 | Pass (2,564 respondents with raw r ≥ 0) | 2026-10-06 | 230 with raw r < 0 differ by design; see below |
| Even-odd (raw r) | `careless::evenodd`, correction undone | 1e-4 | Pass (2,696 respondents) | 2026-10-06 | 98 not recoverable because R clamps at −1 |
| Psychometric synonyms, critval 0.60 | `careless::psychsyn(resample_na = FALSE)` | 1e-4 | Pass: 1 pair in both, missing for every respondent in both | 2026-10-06 | No numeric comparison possible at 0.60 |
| Psychometric synonyms, critval 0.50 | `careless::psychsyn(resample_na = FALSE)` | 1e-4 | Pass (same 5 pairs; 2,628 values; same missing pattern) | 2026-10-06 | Default `resample_na = TRUE` differs; see below |
| Cronbach's alpha | `psych::alpha` raw_alpha, complete cases per scale | 1e-3 | Pass (5 scales; max diff 3.3e-16) | 2026-10-06 | |
| Alpha 95% CI | `psych::alpha` Feldt CI | 1e-3 | Pass (5 scales; max diff 4.6e-4) | 2026-10-06 | Difference comes from pingouin rounding bounds to 3 decimals; see below |
| Alpha if item deleted | `psych::alpha` alpha.drop raw_alpha | 1e-3 | Pass (25 items; max diff 7.8e-16) | 2026-10-06 | |
| Corrected item-total r | `psych::alpha` item.stats r.drop | 1e-3 | Pass (25 items; max diff 1.1e-15) | 2026-10-06 | |
| One-factor loadings | `psych::fa(nfactors = 1, fm = "minres")` | 1e-3 | Pass (25 items; max diff 5.6e-6) | 2026-10-06 | Sign oriented to a non-negative sum on both sides |
| Omega total | `psych::fa` loadings + same formula | 1e-3 | Pass (5 scales; max diff 2.5e-7) | 2026-10-06 | |

## Stage 3: careless-response indices — 6 October 2026

**Setup.** R 4.6.1 with careless 1.2.2, psych 2.6.9, GPArotation 2026.8.2 and jsonlite 2.0.0. `validation/reference_careless.R` reads `data/sample/bfi.csv` and `bfi_schema.json` and writes `tests/fixtures/reference_careless.json`. `tests/test_reference_r.py` compares that file with `surveydoctor.careless` on the same 2,800 respondents (row ids checked to match). The R script stops if the CSV has answers outside 1–6 or respondents with no answers. Either would make the Python data preparation differ from R's. bfi has neither.

All 10 reference tests passed. Mismatches against the packages' *default* behaviour are documented below. In every case the definitions differ; no tolerance was changed.

### Mahalanobis: `careless::mahad` defaults use a different definition

- `mahad` calls `psych::outlier`. That function uses a **pairwise** covariance matrix and column means from every respondent. For a respondent with missing answers it computes a partial D², dropping the missing terms.
- SurveyDoctor (BLUEPRINT §7.1) estimates the means and covariance from **complete cases** only, and gives respondents with any missing answer no value.
- Running `mahad` on the complete cases computes exactly the §7.1 definition. That is the tested comparison, and it agrees to about 2e-13.
- Running `mahad` with defaults on all 2,800 rows gives different values for all 2,436 complete respondents: maximum |difference| 2.0093 and median 0.2203 in D², because the mean and covariance come from different respondents. It also gives values to the 364 respondents with missing answers. That comparison is recorded in the fixture (`mahad_all_rows`) for reference but is not tested, since it compares two different definitions.
- `mahad` returns **D²**, not D: on complete cases it agrees with `stats::mahalanobis` (which returns squared distances) to 2.8e-14.

### Even-odd: `careless::evenodd` reports a transformed value

- careless 1.2.x returns **−(2r/(1+r))**: Spearman–Brown corrected, with the corrected value clamped at −1, then negated so that higher means more careless. SurveyDoctor reports raw r (`even_odd`) and the corrected value (`even_odd_sb`) as separate columns. The corrected value is missing when raw r < 0 (owner decision, Stage 2).
- Corrected values match wherever SurveyDoctor defines one (2,564 respondents). The other 230 respondents all have raw r < 0. R still reports a corrected value for them, and SurveyDoctor deliberately leaves it missing.
- Raw r was recovered from R's output as r = v/(2 − v) and matches for 2,696 respondents. For the other 98, R clamped the value at −1, so raw r cannot be recovered. The test checks that SurveyDoctor's raw r is ≤ −1/3 for all of them, which is exactly when 2r/(1+r) ≤ −1.
- Both sides give no value for the same 6 respondents.
- **Pitfall found while writing the script:** `careless::evenodd` must be given a **data frame**. Given a matrix, `x[i, start:end]` loses its column names, `seq(1:length(colnames(s)))` becomes `c(1, 0)`, and only the first two items of each scale are used. The first run of the script made this mistake, and even-odd disagreed by up to 1.99. Passing `as.data.frame(...)` fixed it. The script's comment explains why.

### Psychometric synonyms: the default `resample_na = TRUE` adds random values

- When a respondent's correlation is undefined (one side of the pairs has no variance), `careless::psychsyn` by default randomly swaps the two items within each pair, up to 10 times, until a correlation exists. SurveyDoctor does not do this: an undefined correlation stays missing.
- With `resample_na = FALSE` the definitions are the same, and that is the tested comparison.
- At critval 0.50 on bfi, the default would give a (random) value to 63 more respondents (seed 42 in the script).
- At the default critval 0.60, bfi has a single synonym pair (N1–N2), so both implementations return missing values for everyone. This is why the comparison is also run at 0.50 (owner decision, Stage 2).

### Not compared

- Person-total correlation and seconds per item have no `careless` equivalent listed in BLUEPRINT §8.2. They are covered by the hand-checked unit tests in `tests/test_careless.py`.

## Stage 4: reliability — 6 October 2026

**Setup.** R 4.6.1 with psych 2.6.9, GPArotation 2026.8.2 and jsonlite 2.0.0. `validation/reference_reliability.R` reads `data/sample/bfi.csv` and `bfi_schema.json`, reverse-scores the declared items, and for each of the five scales takes the respondents who answered all of that scale's items. It runs `psych::alpha(check.keys = FALSE)` and `psych::fa(nfactors = 1, fm = "minres", rotate = "none")`, computes omega total from the loadings with SurveyDoctor's formula, and writes `tests/fixtures/reference_reliability.json`. `tests/test_reference_r.py` checks that both sides use the same respondents (row ids), then compares every quantity.

All 16 reliability reference tests passed. The maximum differences in the table were measured by running SurveyDoctor against the fixture in this session.

| Scale | N used | alpha (R) | Feldt 95% CI (R) | omega total (R) |
|---|---|---|---|---|
| Agreeableness | 2709 | 0.7038 | 0.6857–0.7210 | 0.7240 |
| Conscientiousness | 2707 | 0.7293 | 0.7128–0.7451 | 0.7338 |
| Extraversion | 2713 | 0.7609 | 0.7464–0.7749 | 0.7634 |
| Neuroticism | 2694 | 0.8133 | 0.8019–0.8242 | 0.8183 |
| Openness | 2726 | 0.6025 | 0.5785–0.6257 | 0.6181 |

(Values copied from the output of `Rscript validation/reference_reliability.R`, run 6 October 2026.)

### Why complete cases on both sides

`psych::alpha` and `psych::fa` use a **pairwise** correlation or covariance matrix when answers are missing. SurveyDoctor (BLUEPRINT §7.3) uses **listwise** complete cases per scale, and reports how many respondents were left out. The R script is given the same complete cases, so it computes the same definition. Pairwise results on all rows were not compared.

### Alpha confidence interval: rounding, not a different method

Both sides use Feldt's F-distribution interval. pingouin 0.7.0 rounds the bounds to 3 decimals, so they can differ from R by up to 5e-4 (observed maximum 4.6e-4). This is within the 1e-3 tolerance. The point estimate of alpha is not rounded.

A second pingouin detail, which does not affect these results: `pingouin.cronbach_alpha` takes the sample size for the interval **before** its own listwise deletion. With missing values it would compute the interval with too many respondents. SurveyDoctor therefore removes incomplete rows itself before calling pingouin (`cronbach_alpha` refuses data with missing values).

### Factor sign

The sign of a factor is arbitrary. factor_analyzer returned all-negative loadings for Agreeableness on this data, and psych returned all-positive ones. Both sides flip the loadings, when needed, so that their sum is non-negative. Omega is unaffected by the flip because it uses (Σλ)².
