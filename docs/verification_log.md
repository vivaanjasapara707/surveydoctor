# Verification log

Every item marked **[VERIFY]** in BLUEPRINT.md is listed here. The owner checks each item against the official source and fills in the outcome. Until an item has an outcome recorded here, it is treated as unconfirmed.

| # | Blueprint § | Item | Source to check | Status | Outcome / notes | Checked by, date |
|---|---|---|---|---|---|---|
| 1 | 3.3 | Render free-tier limits | render.com pricing/docs | Not yet verified | | |
| 2 | 3.3 | Vercel free tier for a static build | vercel.com pricing/docs | Not yet verified | | |
| 3 | 3.3 | `factor_analyzer` compatibility with current scikit-learn | PyPI / GitHub issues | Confirmed | Observed crash with scikit-learn 1.9.1 in Stage 1; pinned to 1.7.2 | Vivaan, 2026-10-06 |
| 4 | 5.1 | bfi Rdatasets URL and licence | Rdatasets repo; `psych` documentation | Not yet verified | Partial evidence only: in R, `data/sample/bfi.csv` has the same dimensions, row ids and values as `psych::bfi` from psych 2.6.9 (`all.equal` TRUE). The URL and licence are still unchecked. | Claude Code (Rscript), 2026-10-06 |
| 5 | 5.1 | bfi reverse-keyed items: A1, C4, C5, E1, E2, O2, O5 | `psych::bfi.keys` documentation | Confirmed | `psych::bfi.keys` (psych 2.6.9) marks exactly -A1, -C4, -C5, -E1, -E2, -O2, -O5 as reverse-keyed, identical to `reverse_items` in `bfi_schema.json`. Its five key lists (agree, conscientious, extraversion, neuroticism, openness) contain the same items as the schema's five scales. Command and output: see note 5 below. | Claude Code (Rscript), 2026-10-06; Vivaan, 2026-10-06 |
| 6 | 5.2 | DASS-42 availability and licence | openpsychometrics.org | Not yet verified | | |
| 7 | 5.2 | DASS file contents (Q1A–Q42A, Q1E–Q42E, VCL1–VCL16; fake words VCL6, VCL9, VCL12) | DASS codebook | Not yet verified | | |
| 8 | 5.2 | DASS item → scale mapping | DASS codebook | Not yet verified | | |
| 9 | 5.3 | Google Forms CSV export has a submission timestamp only (no start time) | Google Forms help | Not yet verified | | |
| 10 | 7.2 | Mahalanobis p < 0.001 convention citation | Methods literature | Not yet verified | | |
| 11 | 7.2 | Even-odd r < 0.30 threshold, Johnson (2005) | Johnson (2005) | Not yet verified | | |
| 12 | 7.2 | Seconds per item < 2, Huang et al. (2012) | Huang et al. (2012) | Not yet verified | | |
| 13 | 7.5 | statsmodels `FTestAnovaPower` `nobs` is total N | statsmodels docs | Not yet verified | | |
| 14 | 8.2 | `careless::mahad` returns D or D² | `careless` docs | Confirmed | **D².** careless 1.2.2 `mahad` returns `psych::outlier(...)`, which computes D². On bfi complete cases it matches `stats::mahalanobis` (squared distances) to 2.8e-14. Note: by default it uses a pairwise covariance and partial D² for rows with missing answers (see `docs/validation.md`). | Claude Code (Rscript, package source), 2026-10-06; Vivaan, 2026-10-06 |
| 15 | 8.2 | `careless::evenodd` applies Spearman–Brown or not | `careless` docs | Confirmed | **Yes.** careless 1.2.2 `evenodd` applies 2r/(1+r), clamps the result at −1, then negates it (higher = more careless; the sign change came in version 1.2.0, per the function's own warning). Matches SurveyDoctor's `even_odd_sb` to 1e-4 where raw r ≥ 0. | Claude Code (Rscript, package source), 2026-10-06; Vivaan, 2026-10-06 |

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
