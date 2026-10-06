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
| KMO overall | `psych::KMO` MSA | 1e-3 | Pass (diff 5.6e-16) | 2026-10-06 | |
| KMO per item | `psych::KMO` MSAi | 1e-3 | Pass (25 items; max diff 7.8e-16) | 2026-10-06 | |
| Bartlett chi-square | `psych::cortest.bartlett` | 1e-2 | Pass (diff 4.0e-11; df 300 in both) | 2026-10-06 | p-value is 0 in both (below double precision) |
| Correlation eigenvalues | `eigen(cor(x))` | 1e-6 | Pass (25 values; max diff 5.8e-15) | 2026-10-06 | Tolerance not in §8.2; see `docs/decisions.md` |
| EFA loadings (5 factors) | `psych::fa(nfactors = 5, rotate = "oblimin", fm = "minres")` | 0.02 | Pass (125 loadings; max diff 3.3e-6) | 2026-10-06 | After matching factor order and sign |
| EFA communalities | `psych::fa` communality | 0.02 | Pass (25 items; max diff 2.1e-6) | 2026-10-06 | Computed as diag(LΦLᵀ), not with factor_analyzer's `get_communalities`; see below |
| EFA factor correlations | `psych::fa` Phi | 0.02 | Pass (5 × 5; max diff 3.9e-6) | 2026-10-06 | factor_analyzer's `phi_` is misordered; see below |
| Parallel analysis: suggested number | `psych::fa.parallel(cor(x), n.obs, fa = "pc", n.iter = 100, quant = 0.95)` ncomp | exact | Pass (5 in both) | 2026-10-06 | Different random numbers, so only the count is compared; see below |

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

## Stage 5: factor structure — 6 October 2026

**Setup.** R 4.6.1 with psych 2.6.9, GPArotation 2026.8.2 and jsonlite 2.0.0. `validation/reference_structure.R` reads `data/sample/bfi.csv` and `bfi_schema.json`, reverse-scores the declared items, and keeps the 2,436 respondents who answered all 25 items. On those it runs `psych::KMO`, `psych::cortest.bartlett(cor(x), n)`, `eigen(cor(x))`, `psych::fa.parallel` and `psych::fa(nfactors = 5, rotate = "oblimin", fm = "minres")`, then writes `tests/fixtures/reference_structure.json`. `tests/test_reference_r.py` checks that both sides use the same respondents (row ids) before comparing the numbers. SurveyDoctor's EFA is fixed at the fixture's 5 factors for this comparison.

All 8 structure reference tests passed. The maximum differences in the table were measured in this session by running SurveyDoctor against the fixture.

| Quantity (R) | Value |
|---|---|
| N used | 2436 |
| KMO overall | 0.8486 |
| Bartlett χ² (df) | 18146.07 (300), p = 0 |
| First 6 eigenvalues | 5.1343, 2.7519, 2.1427, 1.8523, 1.5482, 1.0736 |

(Values copied from the output of `Rscript validation/reference_structure.R`, run 6 October 2026.)

In the committed fixture, factor matching paired psych's MR1, MR3, MR5, MR2 and MR4 with SurveyDoctor's F1, F3, F2, F4 and F5, all with the same sign. These are the Neuroticism, Extraversion, Conscientiousness, Agreeableness and Openness factors respectively.

**psych's factor labels change between runs.** Running the script five times in this session gave a different MR order almost every time for the same factors (e.g. MR2 MR5 MR4 MR3 MR1, then MR4 MR5 MR3 MR2 MR1). Its loadings also moved by about 1e-6 between runs: the maximum loading difference against SurveyDoctor ranged from 1.9e-6 to 3.3e-6 across runs. The likely cause is randomness in psych/GPArotation's fitting or rotation, but this was not confirmed. The tests match factors by their loadings, not by name, so they do not depend on the labels. The differences reported here are for the committed fixture.

### Two factor_analyzer 0.5.1 problems, with evidence

Both problems can be re-checked from `backend/` with:

```
python validation/factor_analyzer_issues.py
```

The script fits the same 5-factor model with `FactorAnalyzer(n_factors=5, rotation="oblimin", method="minres")` and prints the library's own output next to psych's values (from the committed fixture) and SurveyDoctor's corrected values. Factors are matched to psych's by loadings. The library's `loadings_` are identical to SurveyDoctor's, so one matching applies to all three columns. The numbers below are copied from its output in this session.

**1. Factor correlations: `phi_` is in the wrong order.** `FactorAnalyzer.fit` sorts factors by explained variance after rotation. It reorders `loadings_` and `structure_`, but not `phi_`. For an oblique rotation, structure = loadings × Φ must hold. With the library's `phi_` it misses by up to **0.3904**; with SurveyDoctor's Φ it misses by 1.0e-15. SurveyDoctor recovers Φ by solving structure = LΦ.

| Pair (psych labels) | factor_analyzer `phi_` | psych Phi | SurveyDoctor | \|library − psych\| | \|ours − psych\| |
|---|---|---|---|---|---|
| MR1–MR3 | 0.2365 | −0.2169 | −0.2169 | 0.4535 | 0.0000 |
| MR1–MR5 | −0.2169 | −0.1909 | −0.1909 | 0.0260 | 0.0000 |
| MR1–MR2 | 0.1664 | −0.0462 | −0.0462 | 0.2126 | 0.0000 |
| MR1–MR4 | 0.3297 | −0.0015 | −0.0015 | 0.3312 | 0.0000 |
| MR3–MR5 | −0.1909 | 0.2365 | 0.2365 | 0.4274 | 0.0000 |
| MR3–MR2 | 0.1979 | 0.3297 | 0.3297 | 0.1318 | 0.0000 |
| MR3–MR4 | 0.2021 | 0.1664 | 0.1664 | 0.0357 | 0.0000 |
| MR5–MR2 | −0.0015 | 0.2021 | 0.2021 | 0.2035 | 0.0000 |
| MR5–MR4 | −0.0462 | 0.1979 | 0.1979 | 0.2442 | 0.0000 |
| MR2–MR4 | 0.1955 | 0.1955 | 0.1955 | 0.0000 | 0.0000 |

Max |library − psych| = **0.4535**; max |ours − psych| = **3.86e-6**. The library's values are psych's values in the wrong cells: for example, its MR1–MR4 entry (0.3297) is psych's MR3–MR2 correlation.

**2. Communalities: `get_communalities()` ignores the factor correlations.** It returns row sums of squared pattern loadings, which is only correct when the factors are uncorrelated. After an oblique rotation the communality is diag(LΦLᵀ), which SurveyDoctor uses.

| Item | factor_analyzer `get_communalities()` | psych communality | SurveyDoctor diag(LΦLᵀ) | \|library − psych\| | \|ours − psych\| |
|---|---|---|---|---|---|
| A1 | 0.2696 | 0.2039 | 0.2039 | 0.0657 | 0.0000 |
| A2 | 0.4360 | 0.4628 | 0.4628 | 0.0268 | 0.0000 |
| A3 | 0.4732 | 0.5397 | 0.5397 | 0.0665 | 0.0000 |
| A4 | 0.2707 | 0.3019 | 0.3019 | 0.0312 | 0.0000 |
| A5 | 0.3569 | 0.4700 | 0.4700 | 0.1131 | 0.0000 |
| C1 | 0.3391 | 0.3484 | 0.3484 | 0.0093 | 0.0000 |
| C2 | 0.4869 | 0.4539 | 0.4539 | 0.0330 | 0.0000 |
| C3 | 0.3466 | 0.3243 | 0.3243 | 0.0223 | 0.0000 |
| C4 | 0.4413 | 0.4767 | 0.4767 | 0.0354 | 0.0000 |
| C5 | 0.3795 | 0.4354 | 0.4354 | 0.0559 | 0.0000 |
| E1 | 0.3401 | 0.3478 | 0.3478 | 0.0077 | 0.0000 |
| E2 | 0.4632 | 0.5455 | 0.5455 | 0.0823 | 0.0000 |
| E3 | 0.3236 | 0.4411 | 0.4411 | 0.1175 | 0.0000 |
| E4 | 0.4380 | 0.5413 | 0.5413 | 0.1033 | 0.0000 |
| E5 | 0.3199 | 0.4071 | 0.4071 | 0.0872 | 0.0000 |
| N1 | 0.7178 | 0.6814 | 0.6814 | 0.0364 | 0.0000 |
| N2 | 0.6184 | 0.6080 | 0.6080 | 0.0104 | 0.0000 |
| N3 | 0.5136 | 0.5445 | 0.5445 | 0.0308 | 0.0000 |
| N4 | 0.4219 | 0.5058 | 0.5058 | 0.0839 | 0.0000 |
| N5 | 0.3430 | 0.3493 | 0.3493 | 0.0063 | 0.0000 |
| O1 | 0.2812 | 0.3173 | 0.3173 | 0.0362 | 0.0000 |
| O2 | 0.2949 | 0.2675 | 0.2675 | 0.0274 | 0.0000 |
| O3 | 0.4143 | 0.4746 | 0.4746 | 0.0603 | 0.0000 |
| O4 | 0.2863 | 0.2460 | 0.2460 | 0.0402 | 0.0000 |
| O5 | 0.3214 | 0.2963 | 0.2963 | 0.0251 | 0.0000 |

Max |library − psych| = **0.1175** (item E3), above the 0.02 tolerance for 21 of 25 items; max |ours − psych| = **2.10e-6**.

### Parallel analysis: suggested number of factors

BLUEPRINT §8.2 has no reference for parallel analysis. One was added at the owner's request (Stage 5 follow-up). `psych::fa.parallel` is run with `fa = "pc"`, 100 iterations, `quant = 0.95` and `set.seed(42)`. It is given the **correlation matrix and `n.obs`**, because then it compares against simulated standard-normal data, which is SurveyDoctor's definition. Given raw data, it would compare against *resampled* data instead, a different method. The two implementations use different random number generators, so their thresholds differ slightly, and only the suggested number is compared (exactly).

| | SurveyDoctor (numpy, seed 42) | psych (R, seed 42) |
|---|---|---|
| Thresholds, positions 1–6 | 1.2170, 1.1798, 1.1575, 1.1357, 1.1157, 1.1002 | 1.2061, 1.1773, 1.1554, 1.1352, 1.1158, 1.1036 |
| Suggested number | **5** | **5** |

Observed eigenvalues 5 and 6 are 1.5482 and 1.0736. The decision at position 6 (1.0736 against a threshold of about 1.10) is the same in both. psych's default run on raw data (resampling) also suggests 5; this is recorded in the fixture as `ncomp_resampled_default` but not tested. (SurveyDoctor thresholds from running `structure` on bfi; psych values from the output of `Rscript validation/reference_structure.R`, both in this session.)

### Test-helper bug found during the comparison

The first run of the factor-correlation test failed: 12 of 25 entries differed by up to 0.13. All the values were present but in the wrong rows. `factor_matching` returned factor pairs in SurveyDoctor's order rather than the reference's order. The helper now returns pairs in reference order, a unit test pins that behaviour, and the comparison passes. No tolerance was changed.
