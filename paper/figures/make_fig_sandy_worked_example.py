#!/usr/bin/env python3
"""
Worked example figure: one document through the whole pipeline.

Stage 1  the truncated source text, with the spans the model later returned as
         evidence snippets shaded;
Stage 2  the extracted record as it lands in event_extractions.jsonl;
Stage 3  the resolved footprint, fig_sandy_footprint.pdf, with each location
         string labelled at the geometry it resolved to.

Inputs (same directory): fig_sandy_extraction.json, fig_sandy_source_text.txt,
fig_sandy_footprint.pdf. The map is rasterised at 300 dpi with pdftoppm into a
temporary directory and cropped in memory, so no intermediate files are left
behind. Requires poppler-utils on PATH.

Output: fig_sandy_worked_example.pdf / .png  (single column, 3.15 x 6.25 in)
"""

import json
import subprocess
import tempfile
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Rectangle
import matplotlib.patheffects as pe
from PIL import Image

HERE = Path(__file__).resolve().parent
W, H = 3.15, 6.60          # inches; one ACL column is ~3.17in
M = 0.06                   # side margin

# ---------------------------------------------------------------- palette
BLUE      = "#0072B2"   # stage 2: the model
VERMILION = "#D55E00"   # stage 3: the geometry
BLUE_TINT = "#DCEAF4"
VERM_TINT = "#F7E2D5"
INK       = "#1a1a1a"
MUTED     = "#6b7075"
RULE      = "#C9CDD2"
PANEL     = "#FBFBFA"

plt.rcParams.update({
    "font.family": "serif",
    "font.serif": ["Nimbus Roman", "Times New Roman", "DejaVu Serif"],
    "font.monospace": ["Nimbus Mono PS", "DejaVu Sans Mono"],
    "text.color": INK,
    "pdf.fonttype": 42,
    "ps.fonttype": 42,
})

# ---------------------------------------------------------------- source text
# Two passages from the 12,000-character window. Tuples are (text, shaded),
# where shaded marks the span the model returned as an evidence snippet.
PASSAGE = [
    ("[…] ", False),
    ("Its arrival on the evening of October 29 coincided almost exactly with "
     "high tide and generated a massive surge", True),
    (" on the Atlantic Ocean and in New York Harbor. […] For example, ", False),
    ("approximately 8,500,000 customers lost power at peak during Sandy", True),
    (" (U.S. Department of Energy, 2013). ", False),
    ("As of November 6 2012, two refineries in the path of Sandy, i.e. Hess "
     "Port Reading Refinery in Port Reading, New Jersey and Bayway Refinery "
     "Phillips 66 in Linden, New Jersey, were shut down.", True),
    (" […] ", False),
    ("Gas stations in NJ could not operate because of the outage.", True),
    (" ", False),
    ("Three health care facilities in Manhattan and Brooklyn had to emergently "
     "evacuate all patients due to the outage.", True),
]

RECORD = [
    ("event_hazard",        ["Cyclone, Hurricane and Typhoon"], False),
    ("event_dates",         ["2012-10-29"], False),
    ("event_confidence",    ["high"], False),
    ("affected_locations",  ["New York City   (city)",
                             "Manhattan   (admin2)",
                             "Brooklyn   (admin2)",
                             "Port Reading, New Jersey   (neighbourhood)",
                             "Linden, New Jersey   (city)"], True),
    ("key_impacts",         ["5 statements"], False),
    ("evidence_snippets",   ["5 quotations (shaded above)"], False),
    ("missing_information", ["2 items"], False),
]

# Label anchors, as fractions of the cropped map (x from left, y from top).
# Admin levels are in the record panel already; the map carries names only.
CALLOUTS = [
    ("New York City",     (0.756, 0.502), (0.900, 0.200), "right"),
    ("Manhattan",         (0.519, 0.401), (0.340, 0.255), "right"),
    ("Brooklyn",          (0.571, 0.625), (0.520, 0.910), "center"),
    ("Linden, NJ",        (0.130, 0.691), (0.030, 0.545), "left"),
    ("Port Reading, NJ",  (0.129, 0.804), (0.030, 0.950), "left"),
]

# ---------------------------------------------------------------- map raster
with tempfile.TemporaryDirectory() as td:
    subprocess.run(["pdftoppm", "-png", "-r", "300", "-f", "1", "-l", "1",
                    str(HERE / "fig_sandy_footprint.pdf"),
                    str(Path(td) / "page")], check=True)
    im = Image.open(next(Path(td).glob("page*.png")))
    w, h = im.size
    c = im.crop((int(0.12 * w), int(0.11 * h), int(0.87 * w), int(0.91 * h)))
    w2, h2 = c.size
    MAP = c.crop((0, int(0.02 * h2), w2, int(0.90 * h2))).copy()
MAP_ASPECT = MAP.size[0] / MAP.size[1]

# ---------------------------------------------------------------- canvas
fig = plt.figure(figsize=(W, H))
ax = fig.add_axes([0, 0, 1, 1])
ax.set_xlim(0, W)
ax.set_ylim(H, 0)          # y measured downward, in inches
ax.set_aspect("equal")
ax.axis("off")
fig.canvas.draw()
R = fig.canvas.get_renderer()


def text_w(s, size, family="serif", weight="normal", style="normal"):
    """Width of s in inches."""
    t = ax.text(0, 0, s, fontsize=size, family=family, fontweight=weight,
                fontstyle=style)
    bb = t.get_window_extent(renderer=R)
    t.remove()
    return bb.width / fig.dpi


def stage_header(y, num, label, note):
    ax.text(M, y, num, fontsize=7.5, fontweight="bold", color=VERMILION,
            va="baseline")
    ax.text(M + 0.16, y, label, fontsize=7.5, fontweight="bold", va="baseline")
    ax.text(W - M, y, note, fontsize=5.6, style="italic", color=MUTED,
            ha="right", va="baseline")
    ax.plot([M, W - M], [y + 0.055, y + 0.055], color=RULE, lw=0.6,
            solid_capstyle="butt")


def panel(y0, y1, x0=M, x1=W - M, fc=PANEL, ec=RULE):
    ax.add_patch(FancyBboxPatch(
        (x0 + 0.02, y0 + 0.02), x1 - x0 - 0.04, y1 - y0 - 0.04,
        boxstyle="round,pad=0.02,rounding_size=0.035",
        linewidth=0.5, edgecolor=ec, facecolor=fc, zorder=1))


def stage_arrow(y0, y1):
    xm = W / 2
    ax.add_patch(FancyArrowPatch((xm, y0), (xm, y1), arrowstyle="-|>",
                                 mutation_scale=6, linewidth=0.9,
                                 color=MUTED, zorder=3))


def rich_paragraph(x0, y0, width, runs, size=6.3, leading=0.098,
                   tint=BLUE_TINT):
    """Greedy-wrap (text, shaded) runs; shade the runs that are marked."""
    space = text_w("n n", size) - text_w("nn", size)
    tokens = []
    for txt, hl in runs:
        for i, wtok in enumerate(txt.split(" ")):
            if wtok:
                tokens.append([wtok, hl, text_w(wtok, size)])
    lines, cur, curw = [], [], 0.0
    for tok in tokens:
        add = tok[2] + (space if cur else 0.0)
        if curw + add > width and cur:
            lines.append(cur)
            cur, curw = [tok], tok[2]
        else:
            cur.append(tok)
            curw += add
    if cur:
        lines.append(cur)
    y = y0
    for line in lines:
        x = x0
        run_start, prev_hl = None, False
        for tok in line:
            if tok[1] and not prev_hl:
                run_start = x
            if prev_hl and not tok[1] and run_start is not None:
                ax.add_patch(Rectangle((run_start - 0.012, y - 0.062),
                                       x - run_start - space + 0.024, 0.083,
                                       facecolor=tint, edgecolor="none",
                                       zorder=2))
                run_start = None
            prev_hl = tok[1]
            x += tok[2] + space
        if prev_hl and run_start is not None:
            ax.add_patch(Rectangle((run_start - 0.012, y - 0.062),
                                   x - run_start - space + 0.024, 0.083,
                                   facecolor=tint, edgecolor="none", zorder=2))
        x = x0
        for tok in line:
            ax.text(x, y, tok[0], fontsize=size, va="baseline", zorder=4)
            x += tok[2] + space
        y += leading
    return y


# ================================================================ 1. source
ax.text(M, 0.10, "Haraguchi & Kim (2014), “Critical infrastructure systems: "
        "a case study of the", fontsize=5.4, style="italic", color=MUTED,
        va="baseline")
ax.text(M, 0.215, "interconnectedness of risks posed by Hurricane Sandy for "
        "New York City” · PreventionWeb", fontsize=5.4, style="italic",
        color=MUTED, va="baseline")

stage_header(0.40, "1", "SOURCE DOCUMENT", "")
panel(0.48, 1.62)
end_y = rich_paragraph(M + 0.09, 0.63, W - 2 * M - 0.18, PASSAGE)

stage_arrow(1.68, 1.87)

# ================================================================ 2. record
stage_header(2.06, "2", "EXTRACTED RECORD", "1 of 1 event · verifiable")
panel(2.14, 3.40)
y = 2.30
name_x, val_x = M + 0.09, 1.02
for name, values, tinted in RECORD:
    ax.text(name_x, y, name, fontsize=5.3, family="monospace", color=BLUE,
            va="baseline", zorder=4)
    for j, v in enumerate(values):
        if tinted:
            ax.add_patch(Rectangle((val_x - 0.014, y + j * 0.098 - 0.061),
                                   text_w(v, 5.8) + 0.028, 0.082,
                                   facecolor=VERM_TINT, edgecolor="none",
                                   zorder=2))
        ax.text(val_x, y + j * 0.098, v, fontsize=5.8, va="baseline", zorder=4)
    y += 0.098 * len(values)

stage_arrow(3.46, 3.65)

# ================================================================ 3. map
stage_header(3.84, "3", "RESOLVED FOOTPRINT", "5 mentions → 5 geometries")

map_w = 2.60
map_h = map_w / MAP_ASPECT
map_x = (W - map_w) / 2
map_y = 3.94
mx = fig.add_axes([map_x / W, (H - map_y - map_h) / H, map_w / W, map_h / H])
mx.imshow(MAP, extent=(0, 1, 1, 0), interpolation="antialiased")
mx.set_xlim(0, 1)
mx.set_ylim(1, 0)
mx.set_xticks([])
mx.set_yticks([])
for s in mx.spines.values():
    s.set_linewidth(0.5)
    s.set_edgecolor(MUTED)

halo = [pe.withStroke(linewidth=1.6, foreground="white")]
for label, (ax_, ay_), (lx, ly), ha in CALLOUTS:
    mx.annotate(label, xy=(ax_, ay_), xytext=(lx, ly), fontsize=5.2,
                ha=ha, va="center", color=INK, path_effects=halo, zorder=6,
                arrowprops=dict(arrowstyle="-", lw=0.45, color="#3a3a3a",
                                shrinkA=1.5, shrinkB=1.5,
                                path_effects=[pe.withStroke(linewidth=1.5,
                                                            foreground="white")]))

# ================================================================ footer
fy = map_y + map_h + 0.15
ax.plot([M, W - M], [fy - 0.10, fy - 0.10], color=RULE, lw=0.6)
ax.text(M, fy, "Human judgement: ", fontsize=5.6, color=MUTED, va="baseline")
ax.text(M + text_w("Human judgement: ", 5.6), fy, "correct", fontsize=5.6,
        fontweight="bold", color=INK, va="baseline")
ax.text(W - M, fy, "basemap © OpenStreetMap contributors", fontsize=5.0,
        color=MUTED, ha="right", va="baseline")

fig.savefig(HERE / "fig_sandy_worked_example.pdf")
fig.savefig(HERE / "fig_sandy_worked_example.png", dpi=400)
plt.close(fig)
print("wrote fig_sandy_worked_example.{pdf,png}  "
      f"({W} x {H} in; text block ends at y={end_y:.2f})")

meta = json.loads((HERE / "fig_sandy_extraction.json").read_text())
print("asset:", meta["_provenance"]["asset_key"][:12],
      "| verdict:", meta["_provenance"]["human_verdict"])
