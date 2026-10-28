# Verification log

Every item marked **[VERIFY]** in BLUEPRINT.md is listed here. The owner checks each item against the official source and fills in the outcome. Until an item has an outcome recorded here, it is treated as unconfirmed.

| # | Blueprint § | Item | Source to check | Status | Outcome / notes | Checked by, date |
|---|---|---|---|---|---|---|
| 1 | 3.3 | Render free-tier limits | render.com pricing/docs | Not yet verified | | |
| 2 | 3.3 | Vercel free tier for a static build | vercel.com pricing/docs | Not yet verified | | |
| 3 | 3.3 | `factor_analyzer` compatibility with current scikit-learn | PyPI / GitHub issues | Confirmed | Observed crash with scikit-learn 1.9.1 in Stage 1; pinned to 1.7.2 | Vivaan, 2026-10-06 |
| 4 | 5.1 | bfi Rdatasets URL and licence | Rdatasets repo; `psych` documentation | Not yet verified | Partial evidence only: in R, `data/sample/bfi.csv` has the same dimensions, row ids and values as `psych::bfi` from psych 2.6.9 (`all.equal` TRUE). The URL and licence are still unchecked. | Claude Code (Rscript), 2026-10-06 |
| 5 | 5.1 | bfi reverse-keyed items: A1, C4, C5, E1, E2, O2, O5 | `psych::bfi.keys` documentation | Confirmed | `psych::bfi.keys` (psych 2.6.9) marks exactly -A1, -C4, -C5, -E1, -E2, -O2, -O5 as reverse-keyed, identical to `reverse_items` in `bfi_schema.json`. Its five key lists (agree, conscientious, extraversion, neuroticism, openness) contain the same items as the schema's five scales. Command and output: see note 5 below. | Claude Code (Rscript), 2026-10-06; Vivaan, 2026-10-06 |
| 6 | 5.2 | DASS-42 availability and licence | openpsychometrics.org | Evidence found, owner to confirm | **Available; licence not stated.** Downloaded `DASS_data_21.02.19.zip` from openpsychometrics.org/_rawdata/ on 2026-10-27. No licence wording was found on the raw-data page text or in `codebook.txt`. The DASS questionnaire itself is "in the public domain" (DASS website). See note 6. | Claude Code (download, page text), 2026-10-27 |
| 7 | 5.2 | DASS file contents (Q1A–Q42A, Q1E–Q42E, VCL1–VCL16; fake words VCL6, VCL9, VCL12) | DASS codebook | Evidence found, owner to confirm | **As expected, plus positions.** The codebook describes Q#A (answer, 1–4), Q#E (milliseconds) and also Q#I (position shown), with items "presented one at a time in a random order for each new participant". VCL6 (cuivocal), VCL9 (florted) and VCL12 (verdid) "are not real words". The file has all these columns: 39,775 rows, answers 1–4, no missing values. See note 7. | Claude Code (codebook, data), 2026-10-27 |
| 8 | 5.2 | DASS item → scale mapping | DASS codebook | Evidence found, owner to confirm | **Matches the official scoring template.** The codebook does not give the mapping. The official DASS scoring template (`Dass_template.pdf`, www2.psy.unsw.edu.au/dass/) marks items 1–21 S A D A D S A S A D S S D S A D D S A A D and is applied again to items 22–42. This gives exactly the §5.2 lists for Depression, Anxiety and Stress (checked in code). See note 8. | Claude Code (official template), 2026-10-27 |
| 9 | 5.3 | Google Forms CSV export has a submission timestamp only (no start time) | Google Forms help | Not yet verified | | |
| 10 | 7.2 | Mahalanobis p < 0.001 convention citation | Methods literature | Not yet verified | | |
| 11 | 7.2 | Even-odd r < 0.30 threshold, Johnson (2005) | Johnson (2005) | Not yet verified | | |
| 12 | 7.2 | Seconds per item < 2, Huang et al. (2012) | Huang et al. (2012) | Not yet verified | | |
| 13 | 7.5 | statsmodels `FTestAnovaPower` `nobs` is total N | statsmodels docs | Evidence found, owner to confirm | **Total N.** In statsmodels 0.15.0, `ftest_anova_power` documents `nobs` as "Total sample size, sum over all groups" and computes `df_denom = nobs - k_groups` and noncentrality `effect_size**2 * nobs`, which only fit a total N. See note 13. | Claude Code (package source), 2026-10-26 |
| 14 | 8.2 | `careless::mahad` returns D or D² | `careless` docs | Confirmed | **D².** careless 1.2.2 `mahad` returns `psych::outlier(...)`, which computes D². On bfi complete cases it matches `stats::mahalanobis` (squared distances) to 2.8e-14. Note: by default it uses a pairwise covariance and partial D² for rows with missing answers (see `docs/validation.md`). | Claude Code (Rscript, package source), 2026-10-06; Vivaan, 2026-10-06 |
| 15 | 8.2 | `careless::evenodd` applies Spearman–Brown or not | `careless` docs | Confirmed | **Yes.** careless 1.2.2 `evenodd` applies 2r/(1+r), clamps the result at −1, then negates it (higher = more careless; the sign change came in version 1.2.0, per the function's own warning). Matches SurveyDoctor's `even_odd_sb` to 1e-4 where raw r ≥ 0. | Claude Code (Rscript, package source), 2026-10-06; Vivaan, 2026-10-06 |
| 16 | 7.14 | fsQCA necessity threshold: consistency ≥ 0.9 | Supervisor; methods text (e.g. Schneider & Wagemann 2012) | Not yet verified | | |
| 17 | 7.14 | fsQCA truth-table defaults: frequency 1, raw consistency 0.8, PRI 0.7 | Supervisor; methods text | Not yet verified | Context only, not a confirmation: these are not `QCA`'s own defaults (`args(truthTable)` in QCA 3.25: `incl.cut = 1, n.cut = 1, pri.cut = 0`). On bfi no row reaches PRI 0.7 (highest 0.654), so the PRI threshold decides whether there is a solution. | Claude Code (R), 2026-10-28 |
| 18 | 7.14 | How R's `QCA` package treats cases at exactly 0.5 membership | `QCA` documentation (`truthTable`, `calibrate`) | Evidence found, owner to confirm | **Excluded from row counts, kept in the sums.** In `QCA` 3.25, `truthTable` warns "Fuzzy causal conditions should not have values of 0.5 in the data", assigns rows with `x > 0.5`, and leaves cases with any condition at 0.5 out of each row's case list and count (`zero.five`). Consistency and PRI still use every case. Confirmed with a 6-case experiment. See note 18. | Claude Code (package source, R experiment), 2026-10-27 |
| 19 | 7.14 | `QCA::calibrate` direct method: membership at the outer anchors (its default vs Ragin's ±3 log-odds) | `QCA` documentation | Evidence found, owner to confirm | **0.95 and 0.05 (`idm = 0.95`).** `QCA` 3.25 `calibrate` defaults to `logistic = TRUE, idm = 0.95` and computes 1/(1 + exp(±(x − c)·log(idm/(1 − idm))/(anchor − c))). With thresholds 1, 3 and 5 it returned 0.05, 0.1866, 0.5, 0.8134 and 0.95. SurveyDoctor uses the same default and matches it to 4.9e-13 on bfi. See note 19. | Claude Code (package source, R run), 2026-10-27 |
| 20 | 7.14 | fsQCA calibration-sensitivity shifts: crossover 45th/55th percentile, outer anchors 90th/10th; scale-point anchors ±0.5 | Supervisor | Not yet verified | Implemented as three reruns: crossover lower, crossover higher, outer anchors closer (scale points: −0.5, +0.5, both outer anchors 0.5 inward). See decisions.md, Stage 10B. | |

## Notes

**Note 5 — bfi reverse keys (6 October 2026).** Run from `backend/`:

```
"C:\Program Files\R\R-4.6.1\bin\Rscript.exe" -e "library(psych); print(bfi.keys)"
```

Output (psych 2.6.9):

```
$agree
[1] "-A1" "A2"  "A3"  "A4"  "A5"
$conscientious
[1] "C1"  "C2"  "C3"  "-C4" "-C5"
$extraversion
[1] "-E1" "-E2" "E3"  "E4"  "E5"
$neuroticism
[1] "N1" "N2" "N3" "N4" "N5"
$openness
[1] "O1"  "-O2" "O3"  "O4"  "-O5"
```

The items with a leading "-" are A1, C4, C5, E1, E2, O2, O5. Compared in R with `bfi_schema.json`, `identical(unname(sort(...)), sort(reverse_items))` gave TRUE. A first comparison without `unname` gave FALSE only because `unlist()` names the elements (e.g. `agree1`).

**Note 13 — statsmodels `nobs` in `FTestAnovaPower` (26 October 2026).** Read with `inspect.getsource(statsmodels.stats.power.ftest_anova_power)` in the project venv (statsmodels 0.15.0):

```
    nobs : int or float
        Total sample size, sum over all groups.
    ...
    df_num = k_groups - 1
    df_denom = nobs - k_groups
    crit = stats.f.isf(alpha, df_num, df_denom)
    pow_ = ncf_sf(crit, df_num, df_denom, effect_size**2 * nobs)
```

Denominator degrees of freedom N − k and noncentrality λ = f²·N are the textbook one-way ANOVA values for a total sample size N (G*Power uses the same λ). A consistency check also passes: `min_f_anova(100, 2)` equals half of `min_d_two_groups(50, 50)` to 1e-4, as it must if 100 is the total of two groups of 50 (`test_f_two_groups_is_half_of_d`). The owner should confirm against the statsmodels documentation page for `FTestAnovaPower` and record the outcome.

**Note 6 — DASS availability and licence (27 October 2026).** The raw-data page (https://openpsychometrics.org/_rawdata/) lists `DASS_data_21.02.19.zip`. Its text says the data "is dumped here" "for general public edification" and that "All data is anonymous", but a search of the page text for licence wording (licen*, creative commons, non-commercial, attribution) found nothing. `codebook.txt` has no licence either. The DASS website (www2.psy.unsw.edu.au/dass/) says: "The DASS questionnaire is in the public domain". That covers the questionnaire, not this dataset. The owner should decide whether this is enough for a methods evaluation, or ask openpsychometrics.org.

**Note 7 — DASS file contents (27 October 2026).** From `codebook.txt`: "This response is stored in variable A (e.g. Q1A). Also recorded was the time taken in milliseconds to answer that question (E) and that question's position in the survey (I)." and "The words at VCL6, VCL9, and VCL12 are not real words and can be used as a validity check." The dataset contains only respondents who answered yes to "Have you given accurate answers and may they be used for research?". Checked in the file: 39,775 rows × 172 columns; Q1A–Q42A take only the values 1–4 with no missing values; every row's Q1I–Q42I is a permutation of 1–42; VCL1–VCL16 are 0/1.

**Note 8 — DASS scale mapping (27 October 2026).** `Dass_template.pdf` (downloaded from the DASS website's download page) lists one letter per item for one side of the form: S A D A D S A S A D S S D S A D D S A A D. Its footer says: "For the full (42-item) DASS, apply template to both sides of the sheet". Applying it to items 1–21 and 22–42 gives Depression 3, 5, 10, 13, 16, 17, 21, 24, 26, 31, 34, 37, 38, 42; Anxiety 2, 4, 7, 9, 15, 19, 20, 23, 25, 28, 30, 36, 40, 41; Stress 1, 6, 8, 11, 12, 14, 18, 22, 27, 29, 32, 33, 35, 39. These equal the BLUEPRINT §5.2 lists, compared in Python. `test_schema_matches_official_scoring_template` keeps this check in the test suite.

**Note 18 — `QCA` and cases at 0.5 (27 October 2026).** From `deparse(QCA::truthTable)` (QCA 3.25): `if (any(data[, conditions[fuzzy.cc]] == 0.5)) warning("Fuzzy causal conditions should not have values of 0.5 in the data.")`, then `condata[, fuzzy.cc] <- lapply(..., function(x) as.numeric(x > 0.5))`, and `cases <- ... rownames(data)[line.data == x & !zero.five]`, where `zero.five` marks cases with any condition equal to 0.5. Experiment with 6 cases, conditions A and B, outcome Y, where case 3 has A = 0.5: the four rows held n = 1, 1, 1, 2 (5 cases); case 3 was in no row; row ~A·B had incl = 0.75. By hand, that consistency includes case 3 (Σmin(R, Y)/ΣR = 1.5/2.0). Without it, the value would be 1.0/1.5 = 0.667.

**Note 19 — `QCA::calibrate` defaults (27 October 2026).** `args(calibrate)`: `function (x, type = "fuzzy", method = "direct", thresholds = NA, logistic = TRUE, idm = 0.95, ecdf = FALSE, below = 1, above = 1, ...)`. Logistic branch: `fs <- 1/(1 + exp(c(-1, 1)[y] * (x - thCR) * log(idm/(1 - idm))/(c(thIN, thEX)[y] - thCR)))`, with `y = (x < thCR) + 1`. `calibrate(c(1, 2, 3, 4, 5), type = "fuzzy", thresholds = c(1, 3, 5))` printed `0.0500 0.1866 0.5000 0.8134 0.9500`.
