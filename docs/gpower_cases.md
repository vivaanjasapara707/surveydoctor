# G*Power reference cases (Stage 6)

BLUEPRINT §8.3: the owner computes these 5 sensitivity cases in G*Power and enters the results in `backend/tests/fixtures/gpower_reference.json`. The test `test_matches_gpower` in `backend/tests/test_power.py` compares them with SurveyDoctor at a tolerance of 0.01. It skips until every `gpower_effect` is filled in. Claude Code never fills in these values.

G*Power is free from the Heinrich Heine University Düsseldorf website (search "G*Power download").

## Settings for every case

- **Type of power analysis:** "Sensitivity: Compute required effect size, given α, power, and sample size"
- **α err prob:** 0.05
- **Power (1-β err prob):** 0.80
- **Tail(s):** Two (where G*Power asks)

Click **Calculate** and copy the **Effect size** from the Output parameters, to at least 4 decimals.

## The cases

| id | Test family → Statistical test | Inputs | Copy into `gpower_effect` |
|---|---|---|---|
| `t_equal_50_50` | t tests → Means: Difference between two independent means (two groups) | Sample size group 1 = 50, group 2 = 50 | Effect size d |
| `t_unequal_30_90` | t tests → Means: Difference between two independent means (two groups) | Sample size group 1 = 30, group 2 = 90 | Effect size d |
| `r_100` | Exact → Correlation: Bivariate normal model | Correlation ρ H0 = 0, Total sample size = 100 | Correlation ρ H1 |
| `anova_150_k3` | F tests → ANOVA: Fixed effects, omnibus, one-way | Total sample size = 150, Number of groups = 3 | Effect size f |
| `anova_12_k3` | F tests → ANOVA: Fixed effects, omnibus, one-way | Total sample size = 12, Number of groups = 3 | Effect size f |

For `r_100`, G*Power may report two solutions (a negative and a positive ρ). Enter the positive one. SurveyDoctor uses the Fisher z approximation, which is close to G*Power's exact test at N = 100, though not identical.

`anova_12_k3` is deliberately small. It checks SurveyDoctor's fallback for effects above f = 1, which statsmodels' own solver cannot find.

## After entering the values

1. Also fill in `gpower_version`, `computed_by` and `date` at the top of the JSON file.
2. From `backend/`, run `pytest tests/test_power.py`.
3. Success: all tests pass with no skips. If `test_matches_gpower` fails, it lists each case with both values. Report the mismatch in `docs/validation.md` and do not change the tolerance.
