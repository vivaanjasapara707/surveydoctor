# Reference values for fsQCA (BLUEPRINT.md §7.14, §8.2): calibration and necessity (part 1),
# truth table and minimisation (part 2, see the second half of this script).
#
# Reference case: bfi, conditions Agreeableness, Conscientiousness, Extraversion and
# Openness, outcome Neuroticism, default percentile anchors (95th, 50th, 5th). Scale scores
# are the mean of reverse-scored items for respondents who answered at least 80% of a
# scale's items, as in surveydoctor.io.scale_scores; respondents without a score on every
# scale are left out, as in surveydoctor.fsqca.fsqca. Then:
#   * anchors: quantile(type = 7), the same as numpy's default percentile;
#   * memberships: QCA::calibrate(type = "fuzzy", method = "direct", thresholds = c(e, c, i));
#   * necessity: QCA::pof(relation = "necessity") for each condition and its negation;
#   * truth table: QCA::truthTable with frequency 1, consistency 0.8, PRI 0.7;
#   * solutions: QCA::minimize (complex and parsimonious) on extra cases with outcome-1 rows.
# Writes tests/fixtures/reference_fsqca.json, which tests/test_reference_r.py compares with
# surveydoctor.fsqca. This is a technical check of the calculations, not a finding.
#
# Run from backend/:
#   Rscript validation/reference_fsqca.R
# (On Windows, if Rscript is not on PATH: "C:\Program Files\R\R-4.6.1\bin\Rscript.exe")
#
# Needs the R packages QCA and jsonlite.

suppressPackageStartupMessages({
  library(QCA)
  library(jsonlite)
})

data_path <- file.path("data", "sample", "bfi.csv")
schema_path <- file.path("data", "sample", "bfi_schema.json")
out_path <- file.path("tests", "fixtures", "reference_fsqca.json")
if (!file.exists(data_path) || !file.exists(schema_path)) {
  stop("Run this script from the backend/ folder, after scripts/download_data.py.")
}

conditions <- c("Agreeableness", "Conscientiousness", "Extraversion", "Openness")
outcome <- "Neuroticism"
percentiles <- c(full = 0.95, crossover = 0.50, non = 0.05)

schema <- fromJSON(schema_path, simplifyVector = FALSE)
items <- unlist(schema$items)
reverse_items <- unlist(schema$reverse_items)
scale_min <- schema$scale_min
scale_max <- schema$scale_max

bfi <- read.csv(data_path, check.names = FALSE)
raw <- as.matrix(bfi[, items])
storage.mode(raw) <- "double"
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

# Scale score: mean of answered items if at least 80% of the scale's items are answered.
scale_score <- function(scale_items) {
  block <- scored[, scale_items, drop = FALSE]
  answered <- rowSums(!is.na(block))
  score <- rowMeans(block, na.rm = TRUE)
  score[answered / length(scale_items) < 0.8 - 1e-12] <- NA
  score
}
scales <- c(conditions, outcome)
scores <- sapply(scales, function(s) scale_score(unlist(schema$scales[[s]])))
complete <- stats::complete.cases(scores)
scores <- scores[complete, , drop = FALSE]

anchors <- list()
memberships <- list()
for (s in scales) {
  q <- unname(stats::quantile(scores[, s], probs = percentiles, type = 7))
  anchors[[s]] <- list(full = q[1], crossover = q[2], non = q[3])
  memberships[[s]] <- calibrate(scores[, s], type = "fuzzy", method = "direct",
                                thresholds = c(q[3], q[2], q[1]))
}
calibrated <- as.data.frame(memberships)

necessity <- list()
for (cond in conditions) {
  for (negated in c(FALSE, TRUE)) {
    x <- if (negated) 1 - calibrated[[cond]] else calibrated[[cond]]
    p <- pof(x, calibrated[[outcome]], relation = "necessity")
    row <- p$incl.cov[1, ]
    necessity[[length(necessity) + 1]] <- list(
      condition = if (negated) paste0("~", cond) else cond,
      consistency = row[["inclN"]],
      relevance = row[["RoN"]],
      coverage = row[["covN"]]
    )
  }
}

# --- Part 2: truth table and minimisation (Stage 10B) ------------------------------------
#
# Truth table on the bfi memberships with the default thresholds (frequency 1, raw
# consistency 0.8, PRI 0.7). QCA numbers rows 1..2^k with the first condition as the most
# significant bit, the same as surveydoctor.fsqca. A case with any condition at exactly 0.5
# is in no row (row 0 below).
incl_cut <- 0.8
pri_cut <- 0.7
n_cut <- 1

tt_rows <- function(tt) {
  t <- tt$tt
  lapply(seq_len(nrow(t)), function(i) list(
    row = as.integer(rownames(t)[i]),
    config = as.integer(unlist(t[i, tt$options$conditions])),
    n = as.integer(t$n[i]),
    consistency = as.numeric(t$incl[i]),
    pri = as.numeric(t$PRI[i]),
    outcome = as.character(t$OUT[i])
  ))
}

case_rows <- function(tt, n_cases) {
  rows <- integer(n_cases)
  t <- tt$tt
  for (i in seq_len(nrow(t))) {
    if (nzchar(t$cases[i])) {
      rows[as.integer(strsplit(t$cases[i], ",")[[1]])] <- as.integer(rownames(t)[i])
    }
  }
  rows
}

# Models of a minimize() result: each model's paths with consistency (inclS), raw coverage
# (covS) and unique coverage within that model (covU), and the model's own fit.
models_of <- function(s) {
  lapply(seq_along(s$solution), function(m) {
    ic <- if (length(s$solution) == 1) s$IC else s$IC$individual[[m]]
    fit <- ic$incl.cov
    list(
      paths = lapply(s$solution[[m]], function(p) list(
        expression = p,
        consistency = fit[p, "inclS"],
        raw_coverage = fit[p, "covS"],
        unique_coverage = fit[p, "covU"]
      )),
      consistency = ic$sol.incl.cov[1, "inclS"],
      coverage = ic$sol.incl.cov[1, "covS"]
    )
  })
}

# NULL when minimize() stops because no truth-table row has outcome 1.
solve <- function(tt, include) {
  tryCatch(models_of(minimize(tt, include = include)), error = function(e) NULL)
}

reference_case <- function(name, source, data, conditions, outcome, incl, pri, n, store_data) {
  rownames(data) <- NULL  # cases are numbered 1..n, as in case_rows()
  tt <- suppressWarnings(truthTable(data, outcome = outcome, conditions = conditions,
                                    incl.cut = incl, pri.cut = pri, n.cut = n))
  list(
    name = name,
    source = source,
    conditions = conditions,
    outcome = outcome,
    thresholds = list(frequency = n, consistency = incl, pri = pri),
    data = if (store_data) lapply(data[, c(conditions, outcome)], unname) else NULL,
    truth_table = tt_rows(tt),
    case_rows = case_rows(tt, nrow(data)),
    complex = solve(tt, ""),
    parsimonious = solve(tt, "?")
  )
}

bfi_tt <- suppressWarnings(truthTable(calibrated, outcome = outcome, conditions = conditions,
                                      incl.cut = incl_cut, pri.cut = pri_cut, n.cut = n_cut))
bfi_truth_table <- list(
  thresholds = list(frequency = n_cut, consistency = incl_cut, pri = pri_cut),
  rows = tt_rows(bfi_tt),
  case_rows = case_rows(bfi_tt, nrow(calibrated)),
  complex = solve(bfi_tt, ""),
  parsimonious = solve(bfi_tt, "?")
)

# Minimisation needs truth tables with outcome-1 rows, which the bfi reference case does not
# have at the default thresholds. These extra cases check the minimisation itself:
#   * bfi with PRI 0.55 (two paths; every row observed, so complex = parsimonious);
#   * Ragin's Lipset data (LF) and Cebotari & Vink's data (CVF) shipped with QCA, which have
#     logical remainders; CVF gives several equally short parsimonious models (M1, M2, ...);
#   * random fuzzy data sets with few cases and many remainders (fixed seeds).
data(LF, package = "QCA")
data(CVF, package = "QCA")
lf_conditions <- c("DEV", "URB", "LIT", "IND", "STB")
cvf_conditions <- c("DEMOC", "ETHFRACT", "GEOCON", "POLDIS", "NATPRIDE")
cases <- list(
  reference_case("bfi_pri_0.55", "bfi memberships above, PRI 0.55", calibrated, conditions,
                 outcome, 0.8, 0.55, 1, FALSE),
  reference_case("LF_SURV", "QCA::LF", LF, lf_conditions, "SURV", 0.8, 0, 1, TRUE),
  reference_case("CVF_PROTEST_0.85", "QCA::CVF", CVF, cvf_conditions, "PROTEST", 0.85, 0, 1,
                 TRUE),
  reference_case("CVF_PROTEST_0.80", "QCA::CVF", CVF, cvf_conditions, "PROTEST", 0.8, 0, 1,
                 TRUE)
)
for (seed in 1:8) {
  set.seed(seed)
  k <- 4 + seed %% 3
  n_cases <- 12 + 3 * seed
  letters_k <- LETTERS[seq_len(k)]
  random <- as.data.frame(matrix(round(runif(n_cases * k), 2), ncol = k,
                                 dimnames = list(NULL, letters_k)))
  y <- pmax(pmin(random$A, random$B), pmin(1 - random$C, random[[letters_k[k]]]))
  random$Y <- round(pmin(1, pmax(0, y + rnorm(n_cases, sd = 0.1))), 2)
  cases[[length(cases) + 1]] <- reference_case(
    paste0("random_", seed), paste("runif, set.seed", seed), random, letters_k, "Y",
    0.8, 0.5, 1, TRUE
  )
}

fixture <- list(
  source = paste("QCA::calibrate, QCA::pof, QCA::truthTable and QCA::minimize on bfi and",
                 "QCA's example data; generated by validation/reference_fsqca.R"),
  r_version = R.version.string,
  qca_version = as.character(packageVersion("QCA")),
  conditions = conditions,
  outcome = outcome,
  percentiles = unname(percentiles * 100),
  row_ids = as.integer(which(complete) - 1),  # 0-based row positions in bfi.csv
  n_used = nrow(scores),
  n_excluded = sum(!complete),
  anchors = anchors,
  memberships = lapply(calibrated, function(v) round(v, 12)),
  n_at_crossover = sum(apply(calibrated[, conditions], 1, function(r) any(r == 0.5))),
  necessity = necessity,
  truth_table = bfi_truth_table,
  minimisation_cases = cases
)
write(toJSON(fixture, auto_unbox = TRUE, digits = NA, pretty = FALSE, null = "null", na = "null"),
      out_path)

cat("n =", nrow(scores), " excluded =", sum(!complete), "\n")
for (s in scales) {
  a <- anchors[[s]]
  cat(sprintf("%-18s anchors %.4f / %.4f / %.4f\n", s, a$full, a$crossover, a$non))
}
for (r in necessity) {
  cat(sprintf("%-20s consistency %.4f  coverage %.4f  RoN %.4f\n",
              r$condition, r$consistency, r$coverage, r$relevance))
}
cat(sprintf("bfi truth table: %d rows observed, %d with outcome 1, %d cases in rows\n",
            length(bfi_truth_table$rows),
            sum(sapply(bfi_truth_table$rows, function(r) r$outcome == "1")),
            sum(bfi_truth_table$case_rows > 0)))
for (case in cases) {
  for (kind in c("complex", "parsimonious")) {
    models <- case[[kind]]
    text <- if (is.null(models)) "no solution" else paste(
      sapply(models, function(m) paste(sapply(m$paths, `[[`, "expression"), collapse = " + ")),
      collapse = "  |  ")
    cat(sprintf("%-18s %-12s %s\n", case$name, kind, text))
  }
}
cat("Wrote", out_path, "\n")
