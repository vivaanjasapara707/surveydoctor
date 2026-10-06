# Reference values for factor structure (BLUEPRINT.md §8.2).
#
# On the 25 reverse-scored bfi items, for respondents who answered all of them, computes
# psych::KMO (overall and per item), psych::cortest.bartlett, the eigenvalues of the
# Pearson correlation matrix, psych::fa.parallel's suggested number of components, and
# psych::fa(nfactors = 5, rotate = "oblimin",
# fm = "minres") pattern loadings, communalities and factor correlations. Writes
# tests/fixtures/reference_structure.json, which tests/test_reference_r.py compares with
# surveydoctor.structure.
#
# Run from backend/:
#   Rscript validation/reference_structure.R
# (On Windows, if Rscript is not on PATH: "C:\Program Files\R\R-4.6.1\bin\Rscript.exe")
#
# Needs the R packages psych, GPArotation and jsonlite.

suppressPackageStartupMessages({
  library(psych)
  library(GPArotation)
  library(jsonlite)
})

data_path <- file.path("data", "sample", "bfi.csv")
schema_path <- file.path("data", "sample", "bfi_schema.json")
out_path <- file.path("tests", "fixtures", "reference_structure.json")
if (!file.exists(data_path) || !file.exists(schema_path)) {
  stop("Run this script from the backend/ folder, after scripts/download_data.py.")
}

schema <- fromJSON(schema_path, simplifyVector = FALSE)
items <- unlist(schema$items)
reverse_items <- unlist(schema$reverse_items)
scale_min <- schema$scale_min
scale_max <- schema$scale_max

bfi <- read.csv(data_path, check.names = FALSE)
raw <- as.matrix(bfi[, items])
storage.mode(raw) <- "double"

# The Python side turns out-of-range answers into missing values and drops rows with no
# answers. Stop if that would happen here, so both sides use exactly the same data.
present <- raw[!is.na(raw)]
if (any(present < scale_min | present > scale_max | present != round(present))) {
  stop("bfi.csv has answers outside the scale; the comparison would not be like for like.")
}
if (any(rowSums(!is.na(raw)) == 0)) {
  stop("bfi.csv has respondents with no answers; the comparison would not be like for like.")
}

# Reverse-scored answers (scale_min + scale_max - x), as in surveydoctor.io.reverse_score.
scored <- raw
scored[, reverse_items] <- scale_min + scale_max - scored[, reverse_items]

# Listwise complete cases, as in surveydoctor.structure. psych would otherwise use pairwise
# correlations, which is a different definition.
complete <- complete.cases(scored)
x <- as.data.frame(scored[complete, , drop = FALSE])
r <- cor(x)
n_factors <- 5

# Parallel analysis on principal-component eigenvalues. Given raw data, fa.parallel compares
# against *resampled* data; given the correlation matrix and n.obs it compares against
# simulated standard-normal data, which is SurveyDoctor's definition (BLUEPRINT §7.4):
# 100 datasets, 95th percentile. The random numbers differ from numpy's, so only the
# suggested number of components is compared. The default (resampling) run is recorded
# for reference.
pa_iterations <- 100
set.seed(42)
pa <- psych::fa.parallel(r, n.obs = nrow(x), fa = "pc", n.iter = pa_iterations,
                         quant = 0.95, plot = FALSE)
pa_threshold <- apply(pa$values[, seq_len(ncol(x)), drop = FALSE], 2, quantile, 0.95)
set.seed(42)
pa_default <- psych::fa.parallel(x, fa = "pc", n.iter = pa_iterations, quant = 0.95,
                                 plot = FALSE)

kmo <- psych::KMO(x)
bartlett <- psych::cortest.bartlett(r, n = nrow(x))
f <- psych::fa(x, nfactors = n_factors, rotate = "oblimin", fm = "minres")

loadings <- unclass(f$loadings)
factor_names <- colnames(loadings)
phi <- f$Phi
dimnames(phi) <- list(factor_names, factor_names)

# Columns as named lists (factor -> item -> value), so the JSON keeps every label.
by_column <- function(m) {
  out <- lapply(seq_len(ncol(m)), function(j) setNames(as.list(m[, j]), rownames(m)))
  setNames(out, colnames(m))
}

result <- list(
  generated_by = "validation/reference_structure.R",
  generated_at = format(Sys.time(), "%Y-%m-%d %H:%M:%S %Z"),
  r_version = R.version.string,
  packages = list(
    psych = as.character(packageVersion("psych")),
    GPArotation = as.character(packageVersion("GPArotation")),
    jsonlite = as.character(packageVersion("jsonlite"))
  ),
  data = data_path,
  items = items,
  reverse_items = reverse_items,
  id = bfi$id[complete],
  n_used = nrow(x),
  kmo_overall = kmo$MSA,
  kmo_per_item = setNames(as.list(as.numeric(kmo$MSAi)), items),
  bartlett = list(
    chi_square = bartlett$chisq,
    df = bartlett$df,
    p_value = bartlett$p.value
  ),
  eigenvalues = eigen(r, symmetric = TRUE, only.values = TRUE)$values,
  parallel = list(
    function_call = "fa.parallel(cor(x), n.obs, fa = 'pc', n.iter = 100, quant = 0.95)",
    seed = 42,
    n_iterations = pa_iterations,
    quant = 0.95,
    ncomp = pa$ncomp,
    threshold = as.numeric(pa_threshold),
    ncomp_resampled_default = pa_default$ncomp
  ),
  efa = list(
    n_factors = n_factors,
    fm = "minres",
    rotate = "oblimin",
    factors = factor_names,
    loadings = by_column(loadings),
    communality = setNames(as.list(as.numeric(f$communality)), items),
    phi = by_column(phi)
  )
)

write_json(result, out_path, digits = NA, na = "null", auto_unbox = TRUE, pretty = TRUE)
cat("Wrote", out_path, "\n")
cat(sprintf("n = %d  KMO = %.4f  Bartlett chi2 = %.2f (df = %d, p = %.3g)\n",
            nrow(x), kmo$MSA, bartlett$chisq, as.integer(bartlett$df), bartlett$p.value))
cat("First 6 eigenvalues:", sprintf("%.4f", head(result$eigenvalues, 6)), "\n")
cat("Parallel analysis (simulated normal data, 95th percentile) thresholds 1-6:",
    sprintf("%.4f", head(pa_threshold, 6)), "\n")
cat(sprintf("fa.parallel suggested components: %d (simulated); %d (default, resampled)\n",
            pa$ncomp, pa_default$ncomp))
cat("EFA (5 factors, minres, oblimin) pattern loadings:\n")
print(round(loadings, 2))
cat("Factor correlations:\n")
print(round(phi, 2))
