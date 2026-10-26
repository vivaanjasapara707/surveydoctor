"""Sample sensitivity: the smallest effect a sample of this size can reliably detect.

For a given sample size, significance level (alpha) and target power, each function
returns the smallest true effect that a test would detect with that power:

* min_d_two_groups  - Cohen's d for an independent-samples t-test (two groups);
* min_r_correlation - |r| for a test of a Pearson correlation (Fisher z approximation);
* min_f_anova       - Cohen's f for a one-way ANOVA with k groups.

This is a sensitivity analysis, not post-hoc power. It is computed from the sample size
alone, before looking at any result. Nothing here takes an observed effect: power computed
from an observed effect adds no information beyond the p-value and is not reported.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from scipy import optimize, stats
from statsmodels.stats.power import FTestAnovaPower, TTestIndPower

DEFAULT_ALPHA = 0.05
DEFAULT_POWER = 0.80

# Cohen's conventional small / medium / large benchmarks for each effect measure.
BENCHMARKS: dict[str, tuple[float, float, float]] = {
    "d": (0.2, 0.5, 0.8),
    "r": (0.1, 0.3, 0.5),
    "f": (0.1, 0.25, 0.4),
}

BENCHMARK_CAVEAT = (
    "The small, medium and large labels are Cohen's rough conventions. What counts as a "
    "meaningful effect depends on the field and the question."
)

# statsmodels' ANOVA effect-size solver only searches f below 1. When a small sample needs
# a larger f, the same power equation is solved over this wider range instead.
_F_SEARCH_UPPER = 100.0


@dataclass
class SensitivityResult:
    """The smallest detectable effect for one kind of test.

    Attributes:
        test: "two_groups", "correlation" or "anova".
        effect_measure: "d" (Cohen's d), "r" (correlation) or "f" (Cohen's f).
        min_effect: Smallest true effect detected with the target power.
        label: Where ``min_effect`` falls on Cohen's benchmarks (see ``benchmark_label``).
        n_total: Total number of respondents.
        alpha: Two-sided significance level.
        power: Target power.
        details: Test-specific inputs: ``n1``/``n2`` or ``k_groups``.
        caveat: Reminder that the benchmarks are rough.
    """

    test: str
    effect_measure: str
    min_effect: float
    label: str
    n_total: int
    alpha: float
    power: float
    details: dict[str, int] = field(default_factory=dict)
    caveat: str = BENCHMARK_CAVEAT


def _check_levels(alpha: float, power: float) -> None:
    """Raise ValueError unless 0 < alpha < power < 1."""
    if not 0 < alpha < 1:
        raise ValueError(f"alpha must be between 0 and 1, got {alpha}.")
    if not 0 < power < 1:
        raise ValueError(f"power must be between 0 and 1, got {power}.")
    if power <= alpha:
        raise ValueError(
            f"power ({power}) must be larger than alpha ({alpha}); a test with no real "
            "effect already rejects with probability alpha."
        )


def benchmark_label(value: float, measure: str) -> str:
    """Place an effect size on Cohen's small / medium / large benchmarks.

    Returns "below small", "small to medium", "medium to large" or "large or above". For
    a smallest detectable effect, a higher label means a less sensitive sample: it can only
    detect bigger effects. The benchmarks are rough (see ``BENCHMARK_CAVEAT``).
    """
    if measure not in BENCHMARKS:
        raise ValueError(f"Unknown effect measure '{measure}'. Use one of: d, r, f.")
    small, medium, large = BENCHMARKS[measure]
    value = abs(value)
    if value < small:
        return "below small"
    if value < medium:
        return "small to medium"
    if value < large:
        return "medium to large"
    return "large or above"


def min_d_two_groups(
    n1: int, n2: int, alpha: float = DEFAULT_ALPHA, power: float = DEFAULT_POWER
) -> SensitivityResult:
    """Smallest Cohen's d an independent-samples t-test detects with groups of n1 and n2.

    Cohen's d is the difference between the two group means in standard-deviation units.
    A larger minimum d is worse: only bigger differences between the groups would be
    detected. Assumes a two-sided t-test with equal variances and roughly normal scores.
    Uses statsmodels ``TTestIndPower``.
    """
    _check_levels(alpha, power)
    if n1 < 2 or n2 < 2:
        raise ValueError(f"Each group needs at least 2 respondents, got {n1} and {n2}.")
    d = TTestIndPower().solve_power(
        effect_size=None, nobs1=n1, ratio=n2 / n1, alpha=alpha, power=power
    )
    d = float(d)
    return SensitivityResult(
        test="two_groups",
        effect_measure="d",
        min_effect=d,
        label=benchmark_label(d, "d"),
        n_total=n1 + n2,
        alpha=alpha,
        power=power,
        details={"n1": n1, "n2": n2},
    )


def min_r_correlation(
    n: int, alpha: float = DEFAULT_ALPHA, power: float = DEFAULT_POWER
) -> SensitivityResult:
    """Smallest |r| a two-sided test of a Pearson correlation detects with n respondents.

    Uses the Fisher z approximation: z = (z_{1-alpha/2} + z_power) / sqrt(n - 3), and
    r = tanh(z). A larger minimum |r| is worse: only stronger relationships would be
    detected. The approximation is close for moderate and large n. For very small n it can
    differ slightly from exact methods (such as G*Power's exact bivariate normal test).
    """
    _check_levels(alpha, power)
    if n < 4:
        raise ValueError(f"A correlation test needs at least 4 respondents, got {n}.")
    z = (stats.norm.ppf(1 - alpha / 2) + stats.norm.ppf(power)) / math.sqrt(n - 3)
    r = math.tanh(z)
    return SensitivityResult(
        test="correlation",
        effect_measure="r",
        min_effect=r,
        label=benchmark_label(r, "r"),
        n_total=n,
        alpha=alpha,
        power=power,
    )


def min_f_anova(
    n_total: int, k_groups: int, alpha: float = DEFAULT_ALPHA, power: float = DEFAULT_POWER
) -> SensitivityResult:
    """Smallest Cohen's f a one-way ANOVA detects with n_total respondents in k_groups groups.

    Cohen's f is the spread of the group means in standard-deviation units. A larger
    minimum f is worse. Assumes equal group sizes, equal variances and roughly normal
    scores; with unequal groups the test is usually somewhat less sensitive than this.
    Uses statsmodels ``FTestAnovaPower``, whose ``nobs`` is the total sample size over all
    groups. Its effect-size solver only searches f below 1, so if that fails, the same
    statsmodels power function is solved over a wider range.
    """
    _check_levels(alpha, power)
    if k_groups < 2:
        raise ValueError(f"An ANOVA needs at least 2 groups, got {k_groups}.")
    if n_total <= k_groups:
        raise ValueError(
            f"An ANOVA with {k_groups} groups needs more than {k_groups} respondents, "
            f"got {n_total}."
        )
    anova = FTestAnovaPower()
    try:
        f = anova.solve_power(
            effect_size=None, nobs=n_total, k_groups=k_groups, alpha=alpha, power=power
        )
    except ValueError:
        f = optimize.brentq(
            lambda x: anova.power(x, n_total, alpha, k_groups) - power,
            1e-8,
            _F_SEARCH_UPPER,
        )
    f = float(f)
    return SensitivityResult(
        test="anova",
        effect_measure="f",
        min_effect=f,
        label=benchmark_label(f, "f"),
        n_total=n_total,
        alpha=alpha,
        power=power,
        details={"k_groups": k_groups},
    )


def sample_sensitivity(
    n_total: int,
    k_groups: int = 3,
    alpha: float = DEFAULT_ALPHA,
    power: float = DEFAULT_POWER,
) -> list[SensitivityResult]:
    """The three sensitivity results for a sample of n_total respondents.

    The two-group result assumes the sample is split as evenly as possible (the most
    sensitive split; unequal groups detect less). The ANOVA result assumes k_groups equal
    groups. The correlation uses all respondents.
    """
    n1 = n_total // 2
    return [
        min_d_two_groups(n1, n_total - n1, alpha, power),
        min_r_correlation(n_total, alpha, power),
        min_f_anova(n_total, k_groups, alpha, power),
    ]
