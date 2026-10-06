# Reference values for reliability (BLUEPRINT.md §8.2).
#
# For each bfi scale, on reverse-scored answers and respondents who answered all of the
# scale's items, computes psych::alpha (raw alpha, Feldt CI, alpha if item deleted, corrected
# item-total correlation) and psych::fa(nfactors = 1, fm = "minres") loadings with omega
# total from the same formula SurveyDoctor uses. Writes
# tests/fixtures/reference_reliability.json, which tests/test_reference_r.py compares with
# surveydoctor.reliability.
#
# Run from backend/:
#   Rscript validation/reference_reliability.R
# (On Windows, if Rscript is not on PATH: "C:\Program Files\R\R-4.6.1\bin\Rscript.exe")
#
# Needs the R packages psych, GPArotation and jsonlite.

suppressPackageStartupMessages({
  library(psych)
  library(jsonlite)
})

data_path <- file.path("data", "sample", "bfi.csv")
schema_path <- file.path("data", "sample", "bfi_schema.json")
out_path <- file.path("tests", "fixtures", "reference_reliability.json")
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

# Omega total from standardized one-factor loadings, as in
# surveydoctor.reliability.omega_from_loadings.
omega_from_loadings <- function(lambda) {
  common <- sum(lambda)^2
  common / (common + sum(1 - lambda^2))
}

scale_reference <- function(scale_items) {
  x <- as.data.frame(scored[, scale_items])
  complete <- complete.cases(x)
  x <- x[complete, , drop = FALSE]
  # check.keys = FALSE (the default) so psych never reverses items on its own; data are
  # already reverse-scored as declared in the schema.
  a <- psych::alpha(x, check.keys = FALSE)
  f <- psych::fa(x, nfactors = 1, fm = "minres", rotate = "none")
  lambda <- as.numeric(f$loadings[, 1])
  # A factor's sign is arbitrary; SurveyDoctor makes the loadings' sum non-negative.
  if (sum(lambda) < 0) lambda <- -lambda
  list(
    items = scale_items,
    id = bfi$id[complete],
    n_used = nrow(x),
    raw_alpha = a$total$raw_alpha,
    feldt_lower = a$feldt$lower.ci$raw_alpha,
    feldt_upper = a$feldt$upper.ci$raw_alpha,
    alpha_if_deleted = setNames(as.list(a$alpha.drop$raw_alpha), scale_items),
    corrected_item_total = setNames(as.list(a$item.stats$r.drop), scale_items),
    fa_loadings = setNames(as.list(lambda), scale_items),
    fa_communality = setNames(as.list(as.numeric(f$communality)), scale_items),
    omega_total = omega_from_loadings(lambda)
  )
}

scales <- lapply(schema$scales, function(s) scale_reference(unlist(s)))

result <- list(
  generated_by = "validation/reference_reliability.R",
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
  scales = scales
)

write_json(result, out_path, digits = NA, na = "null", auto_unbox = TRUE, pretty = TRUE)
cat("Wrote", out_path, "\n")
for (name in names(scales)) {
  s <- scales[[name]]
  cat(sprintf(
    "%-18s n = %d  alpha = %.4f [%.4f, %.4f]  omega = %.4f\n",
    name, s$n_used, s$raw_alpha, s$feldt_lower, s$feldt_upper, s$omega_total
  ))
}
