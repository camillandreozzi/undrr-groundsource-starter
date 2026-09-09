#!/usr/bin/env python3
"""
Figure: temporal profile of the production corpus (10,000 documents) and of the
3,572 verifiable events extracted from it.

Panel A -- when the documents were written: documents per publication year
           (bars) with the events attributed to that publication year (line).
Panel B -- when the events actually happened: events by event date.

Only the yearly range 1990-2021 is drawn. Everything outside it is reported in
the caption, not the axes (see EXCLUDED below).

Output: fig_corpus_temporal.pdf (vector, for the paper) and .png (for slides
and quick viewing), written next to this script.
"""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import MultipleLocator

# --------------------------------------------------------------------------
# Data. year -> (documents published, events by doc publication year,
#                events by event date)
# --------------------------------------------------------------------------
YEARLY = {
    1990: (1, 0, 14),
    1991: (1, 1, 26),
    1992: (2, 0, 16),
    1993: (4, 4, 18),
    1994: (14, 0, 24),
    1995: (4, 2, 60),
    1996: (2, 0, 12),
    1997: (10, 2, 28),
    1998: (11, 0, 61),
    1999: (16, 8, 80),
    2000: (33, 29, 46),
    2001: (57, 31, 86),
    2002: (37, 70, 50),
    2003: (63, 28, 121),
    2004: (111, 48, 231),
    2005: (196, 113, 157),
    2006: (195, 80, 80),
    2007: (245, 124, 98),
    2008: (259, 104, 155),
    2009: (434, 172, 122),
    2010: (394, 185, 236),
    2011: (375, 103, 322),
    2012: (369, 172, 114),
    2013: (430, 173, 141),
    2014: (612, 153, 100),
    2015: (389, 177, 122),
    2016: (301, 163, 94),
    2017: (454, 224, 133),
    2018: (411, 183, 99),
    2019: (359, 249, 80),
    2020: (393, 224, 109),
    2021: (210, 87, 11),
}

# Bins deliberately left off the axes; reported in the caption instead.
EXCLUDED = {
    "pre-1900":  (0, 0, 76),
    "1900-1949": (0, 0, 89),
    "1950-1979": (0, 0, 141),
    "1980-1989": (2, 0, 133),
    "2022-2025": (32, 1, 0),
    "no year":   (3574, 662, 87),
}

TOTALS = (10_000, 3_572, 3_572)

# --------------------------------------------------------------------------
# Style. Okabe-Ito hues (colourblind-safe, and distinct in greyscale print);
# validated for CVD separation before use.
# --------------------------------------------------------------------------
DOCS_FILL = "#C9CDD2"   # neutral, recessive: documents are the backdrop
DOCS_EDGE = "#AEB3B9"
BLUE      = "#0072B2"   # events, attributed to publication year
VERMILION = "#D55E00"   # events, by event date
INK       = "#1a1a1a"
INK_MUTED = "#6b7075"
GRID      = "#E3E5E8"

plt.rcParams.update({
    "font.family": "serif",
    "font.serif": ["Nimbus Roman", "Times New Roman", "DejaVu Serif"],
    "font.size": 8,
    "axes.labelsize": 8,
    "axes.titlesize": 8,
    "xtick.labelsize": 7.5,
    "ytick.labelsize": 7.5,
    "legend.fontsize": 7.5,
    "axes.edgecolor": INK_MUTED,
    "axes.linewidth": 0.6,
    "xtick.color": INK_MUTED,
    "ytick.color": INK_MUTED,
    "xtick.major.width": 0.6,
    "ytick.major.width": 0.6,
    "xtick.major.size": 2.5,
    "ytick.major.size": 2.5,
    "text.color": INK,
    "axes.labelcolor": INK,
    "pdf.fonttype": 42,   # embed TrueType, not Type 3 (ACL requirement)
    "ps.fonttype": 42,
    "savefig.bbox": "tight",
    "savefig.pad_inches": 0.02,
})

years = sorted(YEARLY)
docs      = [YEARLY[y][0] for y in years]
ev_pub    = [YEARLY[y][1] for y in years]
ev_date   = [YEARLY[y][2] for y in years]

fig, (axA, axB) = plt.subplots(
    2, 1, figsize=(6.3, 3.9), sharex=True,
    gridspec_kw={"height_ratios": [1.15, 1.0], "hspace": 0.16},
)

def tidy(ax):
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.set_axisbelow(True)
    ax.yaxis.grid(True, color=GRID, linewidth=0.6)
    ax.xaxis.grid(False)

# ---- Panel A: publication timeline -------------------------------------
axA.bar(years, docs, width=0.72, color=DOCS_FILL, edgecolor=DOCS_EDGE,
        linewidth=0.4, label="Documents published", zorder=2)
axA.plot(years, ev_pub, color=BLUE, linewidth=1.4, marker="o", markersize=2.8,
         markeredgecolor="white", markeredgewidth=0.4, zorder=3,
         label="Events, by document publication year")
tidy(axA)
axA.set_ylim(0, 690)
axA.yaxis.set_major_locator(MultipleLocator(200))
axA.set_ylabel("Count")
axA.legend(loc="upper left", frameon=False, handlelength=1.6,
           borderpad=0.1, labelspacing=0.3, bbox_to_anchor=(-0.005, 1.02))
axA.text(0.995, 0.99, "(a) when documents were written", transform=axA.transAxes,
         ha="right", va="top", fontsize=7.5, style="italic", color=INK_MUTED)

# ---- Panel B: event timeline -------------------------------------------
axB.bar(years, ev_date, width=0.72, color=VERMILION, linewidth=0, zorder=2,
        label="Events, by event date")
tidy(axB)
axB.set_ylim(0, 375)
axB.yaxis.set_major_locator(MultipleLocator(100))
axB.set_ylabel("Events")
axB.set_xlabel("Year")
for yr in (2004, 2011):
    axB.annotate(str(YEARLY[yr][2]), xy=(yr, YEARLY[yr][2]),
                 xytext=(yr, YEARLY[yr][2] + 26), ha="center", fontsize=7,
                 color=INK_MUTED,
                 arrowprops=dict(arrowstyle="-", lw=0.5, color=INK_MUTED,
                                 shrinkA=1, shrinkB=1))
axB.text(0.995, 0.99, "(b) when the events happened", transform=axB.transAxes,
         ha="right", va="top", fontsize=7.5, style="italic", color=INK_MUTED)

axB.set_xlim(1989.2, 2021.8)
axB.xaxis.set_major_locator(MultipleLocator(5))
axB.xaxis.set_minor_locator(MultipleLocator(1))
axB.tick_params(axis="x", which="minor", length=1.4, color=INK_MUTED)

out = Path(__file__).resolve().parent
fig.savefig(out / "fig_corpus_temporal.pdf")
fig.savefig(out / "fig_corpus_temporal.png", dpi=400)
plt.close(fig)

# ---- Coverage the caption has to account for ---------------------------
shown = [sum(c) for c in zip(*(YEARLY[y] for y in years))]
print(f"written to {out}")
for i, name in enumerate(["documents", "events (by pub. year)", "events (by event date)"]):
    off = TOTALS[i] - shown[i]
    print(f"  {name:<24} shown 1990-2021: {shown[i]:>6,}  "
          f"({shown[i] / TOTALS[i]:5.1%})   off-axis: {off:>6,}")
for k, v in EXCLUDED.items():
    print(f"    excluded {k:<10} docs={v[0]:>5,}  ev_pub={v[1]:>4,}  ev_date={v[2]:>4,}")
