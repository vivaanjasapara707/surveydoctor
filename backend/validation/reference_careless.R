# Reference values for the careless-response indices (BLUEPRINT.md §8.2).
#
# Computes careless::longstring, irv, mahad, evenodd and psychsyn on data/sample/bfi.csv
# and writes them to tests/fixtures/reference_careless.json, which tests/test_reference_r.py
# compares with surveydoctor.careless.
#
# Run from backend/:
#   Rscript validation/reference_careless.R
# (On Windows, if Rscript is not on PATH: "C:\Program Files\R\R-4.6.1\bin\Rscript.exe")
#
# Needs the R packages careless, psych and jsonlite.

suppressPackageStartupMessages({
  library(careless)
  library(psych)
  library(jsonlite)
})

data_path <- file.path("data", "sample", "bfi.csv")
schema_path <- file.path("data", "sample", "bfi_schema.json")
out_path <- file.path("tests", "fixtures", "reference_careless.json")
if (!file.exists(data_path) || !file.exists(schema_path)) {
  stop("Run this script from the backend/ folder, after scripts/download_data.py.")
}

schema <- fromJSON(schema_path, simplifyVector = TRUE)
items <- schema$items
reverse_items <- schema$reverse_items
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

# Scale sizes in questionnaire order. careless::evenodd needs each scale's items to be
# adjacent columns, which is true for bfi (A1-A5, C1-C5, ...).
scale_items <- schema$scales
starts <- match(sapply(scale_items, `[`, 1), items)
for (k in seq_along(scale_items)) {
  span <- items[starts[k]:(starts[k] + length(scale_items[[k]]) - 1)]
  if (!identical(span, scale_items[[k]])) stop("Scale items are not adjacent columns.")
}
factors <- as.integer(sapply(scale_items, length)[order(starts)])

complete <- complete.cases(raw)

# Synonym pairs at a critical value, as careless finds them (lower triangle of the
# pairwise-complete correlation matrix, strictly above critval).
synonym_pairs <- function(x, critval) {
  r <- cor(x, use = "pairwise.complete.obs")
  r[upper.tri(r, diag = TRUE)] <- NA
  idx <- which(r > critval, arr.ind = TRUE)
  data.frame(
    first = colnames(x)[pmin(idx[, 1], idx[, 2])],
    second = colnames(x)[pmax(idx[, 1], idx[, 2])],
    r = r[idx]
  )
}

# careless::evenodd warns about its changed sign convention on every call. It must be given
# a data frame: with a matrix, x[i, start:end] loses its column names, the function's
# seq(1:length(colnames(s))) becomes c(1, 0), and only the first two items of each scale
# are used.
evenodd_values <- suppressWarnings(evenodd(as.data.frame(scored), factors = factors))

# psychsyn: resample_na = FALSE is the deterministic definition. The package default
# (resample_na = TRUE) randomly swaps the two items of each pair, up to 10 times, when a
# respondent's correlation is undefined; that is recorded only as a count, with a fixed seed.
psychsyn_060 <- psychsyn(raw, critval = 0.60, resample_na = FALSE)
psychsyn_050 <- psychsyn(raw, critval = 0.50, resample_na = FALSE)
set.seed(42)
psychsyn_050_resampled <- psychsyn(raw, critval = 0.50, resample_na = TRUE)

result <- list(
  generated_by = "validation/reference_careless.R",
  generated_at = format(Sys.time(), "%Y-%m-%d %H:%M:%S %Z"),
  r_version = R.version.string,
  packages = list(
    careless = as.character(packageVersion("careless")),
    psych = as.character(packageVersion("psych")),
    jsonlite = as.character(packageVersion("jsonlite"))
  ),
  data = data_path,
  items = items,
  reverse_items = reverse_items,
  evenodd_factors = factors,
  id = bfi$id,
  longstring = longstring(raw),
  irv = irv(raw),
  # Same definition as SurveyDoctor: means and covariance from complete cases only.
  mahad_complete_cases = list(
    id = bfi$id[complete],
    d_sq = mahad(raw[complete, ], plot = FALSE),
    stats_mahalanobis = mahalanobis(
      raw[complete, ], colMeans(raw[complete, ]), cov(raw[complete, ])
    )
  ),
  # careless default on all rows: pairwise covariance from every respondent, and a partial
  # D² (missing terms dropped) for respondents with missing answers. Documentation only.
  mahad_all_rows = mahad(raw, plot = FALSE),
  evenodd = evenodd_values,
  psychsyn_060 = list(
    n_pairs = nrow(synonym_pairs(raw, 0.60)),
    values = psychsyn_060
  ),
  psychsyn_050 = list(
    n_pairs = nrow(synonym_pairs(raw, 0.50)),
    pairs = synonym_pairs(raw, 0.50),
    values = psychsyn_050,
    n_values_only_with_resample_na = sum(is.na(psychsyn_050) & !is.na(psychsyn_050_resampled))
  )
)

write_json(result, out_path, digits = NA, na = "null", auto_unbox = TRUE, pretty = TRUE)
cat("Wrote", out_path, "\n")
cat("Respondents:", nrow(raw), " complete cases:", sum(complete), "\n")
cat("psychsyn pairs at 0.60:", result$psychsyn_060$n_pairs,
    " at 0.50:", result$psychsyn_050$n_pairs, "\n")
cat("max |mahad - stats::mahalanobis| on complete cases:",
    max(abs(result$mahad_complete_cases$d_sq - result$mahad_complete_cases$stats_mahalanobis)),
    "\n")
