"""Charts for the HTML report: matplotlib figures returned as base64 PNG (report only).

Two charts, following docs/design.md §7: the composite-score histogram and the scree plot
with the parallel-analysis threshold. Each comes with alt text that states what the chart
shows in numbers. The palette and font are the approved design tokens; the website draws
its own charts from the API data.
"""

from __future__ import annotations

import base64
import io
from dataclasses import dataclass
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # no display needed; must come before pyplot is imported

import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib import font_manager  # noqa: E402

from surveydoctor.structure import ParallelAnalysis  # noqa: E402

# Approved palette (docs/design.md §2). The report's CSS uses the same values.
TOKENS: dict[str, str] = {
    "ink": "#18212B",
    "graphite": "#4A5562",
    "slate": "#67717C",
    "paper": "#FFFFFF",
    "mist": "#F4F5F3",
    "rule": "#D5D9DD",
    "field": "#8A939C",
    "signal": "#1F5F99",
    "copper": "#C2581F",
    "clear": "#1E6B35",
    "clear-tint": "#E6F2E9",
    "review": "#8A5300",
    "review-tint": "#FBF0D9",
    "problem": "#A6261F",
    "problem-tint": "#FAE6E4",
}

FONT_DIR = Path(__file__).resolve().parent / "templates" / "fonts"
_CHART_FONT = FONT_DIR / "IBMPlexSans-Regular.ttf"
_FONT_FAMILY = "IBM Plex Sans"

WIDTH_IN, HEIGHT_IN, DPI = 6.8, 3.0, 200  # fills the 720 px report column at 2x


@dataclass
class Chart:
    """A rendered chart: base64-encoded PNG and its alt text."""

    png_base64: str
    alt: str

    @property
    def data_uri(self) -> str:
        return f"data:image/png;base64,{self.png_base64}"


def _style() -> dict:
    """Matplotlib settings for every chart: Plex Sans, Graphite axes, y grid only."""
    if _CHART_FONT.exists() and _FONT_FAMILY not in {
        f.name for f in font_manager.fontManager.ttflist
    }:
        font_manager.fontManager.addfont(str(_CHART_FONT))
    return {
        "font.family": [_FONT_FAMILY, "DejaVu Sans"],
        "font.size": 9,
        "axes.edgecolor": TOKENS["rule"],
        "axes.labelcolor": TOKENS["graphite"],
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.grid": True,
        "axes.grid.axis": "y",
        "grid.color": TOKENS["rule"],
        "grid.linewidth": 0.6,
        "xtick.color": TOKENS["graphite"],
        "ytick.color": TOKENS["graphite"],
        "figure.facecolor": TOKENS["paper"],
        "axes.facecolor": TOKENS["paper"],
    }


def _encode(fig: plt.Figure) -> str:
    buffer = io.BytesIO()
    fig.savefig(buffer, format="png", dpi=DPI, bbox_inches="tight", facecolor=TOKENS["paper"])
    plt.close(fig)
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def composite_histogram(composite: pd.Series, bins: int = 20) -> Chart:
    """Histogram of composite scores (0 to 1), one series, no legend (the title names it)."""
    values = composite.dropna()
    with plt.rc_context(_style()):
        fig, ax = plt.subplots(figsize=(WIDTH_IN, HEIGHT_IN))
        counts, edges, _ = ax.hist(
            values, bins=bins, range=(0, 1), color=TOKENS["signal"],
            edgecolor=TOKENS["paper"], linewidth=1.0,
        )  # fmt: skip
        ax.set_xlim(0, 1)
        ax.set_xlabel("Composite score (higher = more unusual in this file)")
        ax.set_ylabel("Respondents")
        ax.set_axisbelow(True)
        png = _encode(fig)
    peak = int(counts.argmax())
    alt = (
        f"Histogram of composite scores for {len(values):,} respondents in {bins} bins from 0 "
        f"to 1. The largest bin is {edges[peak]:.2f} to {edges[peak + 1]:.2f} with "
        f"{int(counts[peak]):,} respondents; {int((values >= 0.8).sum()):,} respondents score "
        "0.80 or more."
    )
    return Chart(png, alt)


def scree_plot(parallel: ParallelAnalysis) -> Chart:
    """Observed eigenvalues (Signal, solid) against the parallel-analysis threshold (Copper,
    dashed), with the suggested number of factors marked. Labels sit at the line ends."""
    scree = parallel.scree
    positions = scree.index.to_numpy()
    with plt.rc_context(_style()):
        fig, ax = plt.subplots(figsize=(WIDTH_IN, HEIGHT_IN))
        ax.plot(positions, scree["observed"], color=TOKENS["signal"], linewidth=2,
                marker="o", markersize=5, label="Observed eigenvalues")  # fmt: skip
        threshold_label = f"Random-data threshold ({parallel.percentile:.0f}th percentile)"
        ax.plot(positions, scree["threshold"], color=TOKENS["copper"], linewidth=2,
                linestyle=(0, (4, 2)), label=threshold_label)  # fmt: skip
        if parallel.n_suggested > 0:
            ax.axvline(parallel.n_suggested, color=TOKENS["graphite"], linewidth=0.8)
            ax.annotate(
                f"Suggested: {parallel.n_suggested}", xy=(parallel.n_suggested, ax.get_ylim()[1]),
                xytext=(4, -12), textcoords="offset points", color=TOKENS["graphite"],
            )  # fmt: skip
        last = positions[-1]
        for column, name in (("observed", "Observed"), ("threshold", "Threshold")):
            ax.annotate(name, xy=(last, scree[column].iloc[-1]), xytext=(6, 0),
                        textcoords="offset points", va="center", color=TOKENS["ink"])  # fmt: skip
        ax.set_xlim(positions[0] - 0.5, last + 2)
        ax.set_xlabel("Factor position")
        ax.set_ylabel("Eigenvalue")
        ax.legend(frameon=False, loc="upper right")
        ax.set_axisbelow(True)
        png = _encode(fig)
    k = parallel.n_suggested
    alt = (
        f"Scree plot of {len(positions)} eigenvalues. The first observed eigenvalue is "
        f"{scree['observed'].iloc[0]:.2f}. "
        + (
            f"Observed eigenvalues stay above the random-data threshold up to position {k} "
            f"({scree['observed'].iloc[k - 1]:.2f} against {scree['threshold'].iloc[k - 1]:.2f}), "
            f"so {k} factors are suggested."
            if k > 0
            else "No observed eigenvalue is above the random-data threshold."
        )
    )
    return Chart(png, alt)
