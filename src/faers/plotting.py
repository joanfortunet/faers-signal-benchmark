"""Shared chart style for every figure of the project.

One place for fonts, colours and the small helpers that make the charts read
well: a headline title with a subtitle underneath, direct labels at the end
of lines, value labels on bars and a source note. Notebooks call
apply_style() once and then use these helpers.
"""

from pathlib import Path

import matplotlib as mpl
from matplotlib.ticker import FuncFormatter

# Surfaces and text
SURFACE = "#fcfcfb"
INK = "#0b0b0b"
MUTED = "#52514e"
FAINT = "#8a8984"
GRID = "#e8e7e3"

# One fixed colour per method, the same in every chart (validated for colour blindness).
METHOD_COLORS = {
    "PRR": "#2a78d6", "ROR": "#eb6834", "BCPNN": "#1baf7a", "EBGM": "#eda100",
    "Logistic regression": "#e87ba4", "Gradient boosting": "#6250d6",
}
ACCENT = "#2a78d6"  # single-series charts
HIGHLIGHT = "#eb6834"  # the one bar or segment a chart is about
NEUTRAL = "#c9c7c0"  # context, baselines, everything that is not the point

SOURCE = "Source: FDA FAERS 2014 Q3 – 2026 Q2, deduplicated cases"


def apply_style():
    mpl.rcParams.update({
        "font.family": "sans-serif",
        "font.sans-serif": ["Inter", "Helvetica Neue", "Arial", "DejaVu Sans"],
        "font.size": 10,
        "figure.facecolor": SURFACE, "axes.facecolor": SURFACE,
        "savefig.facecolor": SURFACE, "figure.dpi": 110, "savefig.dpi": 200,
        "axes.edgecolor": GRID, "axes.linewidth": 0.8,
        "axes.labelcolor": MUTED, "axes.labelsize": 9.5,
        "axes.titlesize": 13, "axes.titleweight": "bold", "axes.titlecolor": INK,
        "axes.titlelocation": "left", "axes.titlepad": 26,
        "axes.spines.top": False, "axes.spines.right": False, "axes.spines.left": False,
        "axes.axisbelow": True, "axes.grid": True, "axes.grid.axis": "y",
        "grid.color": GRID, "grid.linewidth": 0.8,
        "xtick.color": MUTED, "ytick.color": MUTED,
        "xtick.labelsize": 9, "ytick.labelsize": 9,
        "xtick.major.size": 0, "ytick.major.size": 0,
        "xtick.minor.size": 0, "ytick.minor.size": 0,
        "xtick.major.pad": 6, "ytick.major.pad": 6,
        "legend.frameon": False, "legend.fontsize": 9,
        "lines.linewidth": 2.2, "lines.solid_capstyle": "round",
    })


def headline(ax, title, subtitle=None):
    """Bold title stating the finding, with a muted one-line subtitle under it."""
    ax.set_title(title, loc="left")
    if subtitle:
        ax.annotate(subtitle, xy=(0, 1), xycoords="axes fraction", xytext=(0, 9),
                    textcoords="offset points", fontsize=9.5, color=MUTED, va="bottom")


def source_note(fig, text=SOURCE):
    fig.text(0.01, -0.02, text, fontsize=8, color=FAINT, ha="left", va="top")


def horizontal_bars(ax):
    """Grid lines along x only, for horizontal bar charts."""
    ax.grid(axis="y", visible=False)
    ax.grid(axis="x", visible=True)
    ax.spines["left"].set_visible(True)
    ax.spines["left"].set_color(GRID)


def label_bars(ax, bars, horizontal=False, fmt="{:,.0f}", color=MUTED, fontsize=8.5):
    """Write each bar's value just past its end."""
    for bar in bars:
        if horizontal:
            value = bar.get_width()
            ax.annotate(fmt.format(value), (value, bar.get_y() + bar.get_height() / 2),
                        xytext=(4, 0), textcoords="offset points", ha="left", va="center",
                        fontsize=fontsize, color=color)
        else:
            value = bar.get_height()
            ax.annotate(fmt.format(value), (bar.get_x() + bar.get_width() / 2, value),
                        xytext=(0, 3), textcoords="offset points", ha="center", va="bottom",
                        fontsize=fontsize, color=color)


def end_labels(ax, x, series, colors, min_gap=None, fmt=None):
    """Label each line at its right end, nudged apart so labels never overlap.

    series: {label: y values}; fmt: optional formatter for the last value.
    """
    ends = sorted(((ys[-1], name) for name, ys in series.items()))
    span = ax.get_ylim()[1] - ax.get_ylim()[0]
    gap = min_gap if min_gap is not None else span * 0.05
    placed = []
    for y, name in ends:
        target = y if not placed or y - placed[-1] >= gap else placed[-1] + gap
        placed.append(target)
        text = name if fmt is None else f"{name}  {fmt(y)}"
        # The colour sits on a small marker at the line end; the text stays in ink.
        ax.plot(x, y, "o", color=colors[name], markersize=5, clip_on=False, zorder=5)
        ax.annotate(text, (x, target), xytext=(9, 0), textcoords="offset points",
                    va="center", fontsize=9, fontweight="semibold", color=INK)


def value_tag(ax, x, y, text, side="left"):
    """A small value label with a surface-coloured halo, so lines never cross it."""
    ax.annotate(text, (x, y), xytext=(-9 if side == "left" else 9, 0),
                textcoords="offset points", ha="right" if side == "left" else "left",
                va="center", fontsize=8.5, color=INK,
                bbox={"boxstyle": "round,pad=0.15", "fc": SURFACE, "ec": "none", "alpha": 0.9})


def thousands(ax, axis="y"):
    formatter = FuncFormatter(lambda v, _: f"{v:,.0f}")
    (ax.yaxis if axis == "y" else ax.xaxis).set_major_formatter(formatter)


def percent(ax, axis="y", decimals=0):
    formatter = FuncFormatter(lambda v, _: f"{v:.{decimals}f}%")
    (ax.yaxis if axis == "y" else ax.xaxis).set_major_formatter(formatter)


def plain_log(ax, axis="y"):
    """Log axis with 1, 10, 100 instead of 10^0, 10^1, 10^2."""
    formatter = FuncFormatter(lambda v, _: f"{v:,.0f}" if v >= 1 else f"{v:g}")
    (ax.yaxis if axis == "y" else ax.xaxis).set_major_formatter(formatter)


def save(fig, name, folder="../reports/figures"):
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    fig.savefig(folder / f"{name}.png", bbox_inches="tight", pad_inches=0.25)
