"""Letterforms: an atlas of one textura hand, and the minim rhythm of the three Latin hands.

1. Atlas (out/hours_atlas.png). Letters from Clermont-Ferrand MS 2262, f. 12r, cut out
   at the same scale and the same vertical window (from the line's own guides), grouped
   by how they are built: minim letters, round letters, fused (biting) pairs, the two r's,
   the two s's, ascender and descender letters, a and v, and abbreviation signs. The
   horizontal extent of each letter was read from gridded close-ups (±2 px).

2. Minim rhythm (out/minim_rhythm.png). Textura is built from upright strokes of equal
   weight, and the white between them is part of the design. For every text line the
   x-band is sheared upright by the line's slant, and the columns that are ink from the
   top of the band to the bottom are the stems. Stem width, the white gap between stems
   inside a word, and the stem pitch are measured in x-heights and compared across the
   Gothic textura (MS 2262), the Italian rotunda (Chigi) and the humanist cursive
   (Lucretius).

Run:  python3 letterforms.py
"""
import json
from pathlib import Path

import cv2
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

import ink
import latin_lines as LL

from matplotlib import font_manager

HERE = Path(__file__).resolve().parent
# FreeSerif has the medieval Latin letters (ꝛ ꝙ ꝓ ꝫ ſ) that DejaVu lacks
SERIF = "FreeSerif" if any("FreeSerif" in f for f in font_manager.findSystemFonts()) else "DejaVu Serif"
OUT = HERE / "out"
SURFACE, INK_TEXT, MUTED, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#ecebe8"
HANDS = [("hours", "French textura — MS 2262", "#6b5bd2"),
         ("chigi", "Italian rotunda — Chig. L.VIII.305", "#1baf7a"),
         ("lucretius", "Humanist cursive — Lucretius", "#eb6834")]

# (letter, line, x0, x1, word) on f. 12r, grouped by construction
ATLAS = [
    ("Minim letters: built from upright strokes with lozenge heads and feet", [
        ("i", 19, 483, 494, "piſces"), ("n", 1, 252, 283, "nomen"), ("m", 1, 312, 356, "nomen"),
        ("u", 7, 818, 845, "tuos"), ("u", 14, 850, 880, "euꝫ"),
        ("n final", 1, 381, 413, "nomen")]),
    ("Round letters: the bowl is two upright strokes broken at top and bottom", [
        ("o", 1, 284, 306, "nomen"), ("o", 7, 738, 758, "celos"), ("o", 10, 580, 610, "homo"),
        ("c", 7, 692, 708, "celos"), ("c", 5, 734, 752, "īimicos"), ("e", 1, 800, 822, "terra"),
        ("e", 7, 706, 722, "celos"), ("e", 14, 826, 850, "euꝫ")]),
    ("Biting curves: facing bowls share one stroke", [
        ("de", 6, 303, 352, "deſtruas"), ("de", 7, 580, 625, "videbo"), ("bo", 7, 628, 680, "videbo")]),
    ("Two r's: straight r after straight letters, r rotunda after o", [
        ("r", 1, 822, 840, "terra"), ("r", 1, 840, 860, "terra"), ("ꝛ", 6, 869, 888, "vltoꝛē")]),
    ("Two s's: long ſ inside words, round s at the end", [
        ("ſ", 1, 716, 738, "vniuſa"), ("ſ", 6, 350, 365, "deſtruas"), ("ſ", 9, 418, 432, "ſtellas"),
        ("s", 7, 757, 783, "celos"), ("s", 7, 862, 888, "tuos"),
        ("s", 9, 520, 548, "ſtellas")]),
    ("Ascender letters", [
        ("l", 6, 810, 826, "vltoꝛē"), ("l", 7, 726, 739, "celos"), ("b", 13, 282, 305, "ab"),
        ("h", 10, 488, 520, "homo"), ("d", 6, 299, 334, "deſtruas"), ("t", 1, 775, 800, "terra"),
        ("t", 6, 826, 846, "vltoꝛē"), ("t", 9, 432, 452, "ſtellas")]),
    ("Descender letters", [
        ("p", 19, 446, 477, "piſces"), ("q", 19, 742, 776, "qui"),
        ("g", 13, 515, 540, "glīa")]),
    ("a and v", [
        ("a", 1, 738, 772, "vniuſa"), ("a", 1, 860, 905, "terra"), ("a", 6, 421, 445, "deſtruas"),
        ("a", 9, 498, 520, "ſtellas"), ("a", 13, 255, 282, "ab"), ("a", 13, 315, 345, "angelis"),
        ("v", 1, 596, 632, "vniuſa"), ("v", 6, 786, 810, "vltoꝛē"), ("v", 7, 540, 565, "videbo")]),
    ("Abbreviation signs", [
        ("ꝙ quod", 10, 618, 655, "ꝙ"), ("ꝓ pro", 5, 522, 556, "ꝓpter"), ("ꝫ -m", 14, 880, 900, "euꝫ"),
        ("ē -em", 6, 887, 912, "vltoꝛē"), ("ī -in-", 5, 643, 658, "īimicos")]),
]


MATCH_XH = 14.0  # px: the x-height of the two lower-resolution scans


def load_page(page, match_xh=None):
    """Page, text-ink mask and line guides. With match_xh the scan is first resized so
    its mean x-height is match_xh px: stroke edges blur by about the same number of
    pixels at any size, so stroke-width ratios are only comparable at equal resolution."""
    P = LL.PAGES[page]
    rgb = ink.load_rgb(HERE / "data" / P["image"])
    lines = json.loads((HERE / "data" / P["out"]).read_text(encoding="utf-8"))["lines"]
    k = 1.0
    if match_xh:
        xh = np.mean([l["x_height"] for l in lines if l.get("kind") == "text"])
        k = match_xh / xh
    if abs(k - 1.0) > 0.02:
        rgb = cv2.resize(rgb, None, fx=k, fy=k, interpolation=cv2.INTER_AREA)
        for l in lines:
            for key in ("baseline", "xline"):
                l[key] = [[x * k, y * k] for x, y in l[key]]
            l["x_height"] *= k
        P = dict(P, exclude=[tuple(int(v * k) for v in e) for e in P["exclude"]])
    mask, dark = ink.ink_mask(rgb)
    for x0, y0, x1, y1 in P["exclude"]:
        mask[y0:y1, x0:x1] = 0
    if P.get("mask_paint"):
        mask[ink.paint_boxes(rgb, mask)] = 0
    if P.get("separate_red"):
        mask = ((mask > 0) & ~ink.red_mask(rgb, mask)).astype(np.uint8)
    return rgb, mask, lines


def guide(line, x):
    (x0, b0), (x1, b1) = line["baseline"]
    (_, t0), (_, t1) = line["xline"]
    f = (x - x0) / ((x1 - x0) or 1)
    yb = b0 + f * (b1 - b0)
    return yb, yb - (t0 + f * (t1 - t0))


# ----------------------------------------------------------------------------- atlas
def plot_atlas(path):
    rgb, mask, lines = load_page("hours")
    by_n = {str(l["n"]): l for l in lines}
    S = 3
    rows = len(ATLAS)
    fig = plt.figure(figsize=(12.5, 1.55 * rows + 0.4), dpi=150, facecolor=SURFACE)
    gs = fig.add_gridspec(rows, 1, hspace=0.75)
    for r, (title, items) in enumerate(ATLAS):
        sub = gs[r].subgridspec(1, 10, wspace=0.08)
        for k, (ch, n, x0, x1, word) in enumerate(items[:10]):
            ax = fig.add_subplot(sub[0, k])
            yb, xh = guide(by_n[str(n)], (x0 + x1) / 2)
            y0, y1 = int(round(yb - xh - 0.85 * xh)), int(round(yb + 0.8 * xh))
            pad = 3
            crop = rgb[y0:y1, x0 - pad:x1 + pad]
            ax.imshow(crop, interpolation="lanczos", extent=(x0 - pad, x1 + pad, y1, y0))
            ax.axhline(yb, color="#2a78d6", lw=0.6, alpha=0.7)
            ax.axhline(yb - xh, color="#eb6834", lw=0.6, alpha=0.7)
            ax.set_xticks([]); ax.set_yticks([])
            for s_ in ax.spines.values():
                s_.set_visible(False)
            ax.set_title(ch, fontsize=10, color=INK_TEXT, pad=2, fontfamily=SERIF)
            ax.set_xlabel(f"{word} · l.{n}", fontsize=7, color=MUTED, labelpad=1, fontfamily=SERIF)
            ax.set_aspect("equal")
        fig.text(0.125, gs[r].get_position(fig).y1 + 0.012, title, fontsize=9, color=INK_TEXT, ha="left")
    top = gs[0].get_position(fig).y1 + 0.04
    fig.text(0.125, top, "Letterforms of Clermont-Ferrand MS 2262, f. 12r — all at the same scale; blue = baseline, orange = x-height",
             fontsize=10, color=INK_TEXT, ha="left")
    fig.savefig(path, facecolor=SURFACE, bbox_inches="tight")
    plt.close(fig)


# ----------------------------------------------------------------------------- minim rhythm
def line_stems(mask, line, core=0.3, fill=0.7):
    """Stems and gaps on one line. The x-band (minus `core` of its height at top and
    bottom, where heads and feet spread) is sheared upright by the line's slant; a
    column that is ink over `fill` of the band is part of a stem."""
    (x0, _), (x1, _) = line["baseline"]
    xs = np.arange(int(x0), int(x1) + 1)
    t = np.tan(np.radians(line["slant_deg"] or 0.0))
    yb0, xh = guide(line, (x0 + x1) / 2)
    rows = np.arange(int(yb0 - xh + core * xh), int(yb0 - core * xh) + 1)
    cols = np.zeros(len(xs))
    for y in rows:
        yb, _ = guide(line, xs.mean())
        sx = np.clip(np.round(xs + (yb - y) * t).astype(int), 0, mask.shape[1] - 1)
        cols += mask[np.clip(y, 0, mask.shape[0] - 1), sx] > 0
    cols /= len(rows)
    on = cols >= fill
    runs, start = [], None
    for i, v in enumerate(on):
        if v and start is None:
            start = i
        if not v and start is not None:
            runs.append((start, i - 1)); start = None
    if start is not None:
        runs.append((start, len(on) - 1))
    stems = [(xs[a], xs[b] + 1) for a, b in runs if (b - a + 1) >= 2]
    widths = [b - a for a, b in stems]
    gaps = [stems[i + 1][0] - stems[i][1] for i in range(len(stems) - 1)]
    pitches = [((stems[i + 1][0] + stems[i + 1][1]) - (stems[i][0] + stems[i][1])) / 2 for i in range(len(stems) - 1)]
    return np.array(widths, float), np.array(gaps, float), np.array(pitches, float), xh


def rhythm(page, match_xh=MATCH_XH):
    rgb, mask, lines = load_page(page, match_xh)
    W, G, Pp, per_line = [], [], [], []
    for l in lines:
        if l.get("kind") != "text":
            continue
        w, g, p, xh = line_stems(mask, l)
        inside = g <= 0.9 * xh   # white inside a word; wider gaps are between words
        W += list(w / xh); G += list(g[inside] / xh); Pp += list(p[inside] / xh)
        if inside.sum() >= 5:  # robust spread: interquartile range / median
            q1, q2, q3 = np.percentile(p[inside], [25, 50, 75])
            per_line.append(float((q3 - q1) / q2))
    W, G, Pp = map(np.array, (W, G, Pp))
    return {"stem_xh": float(np.median(W)), "gap_xh": float(np.median(G)), "pitch_xh": float(np.median(Pp)),
            "gap_over_stem": float(np.median(G) / np.median(W)), "pitch_spread": float(np.median(per_line)),
            "n_stems": int(len(W)), "n_gaps": int(len(G)), "gaps": G.tolist(), "widths": W.tolist(),
            "pitches": Pp.tolist()}


def plot_rhythm(results, path):
    """Stem pitch (centre to centre) is used for the comparison: blur widens strokes and
    narrows gaps by the same amount, so their ratio depends on scan resolution, but the
    distance between stem centres does not."""
    fig, axes = plt.subplots(1, 2, figsize=(10, 3.6), dpi=160, facecolor=SURFACE)
    bins = np.linspace(0.2, 1.4, 49)
    for page, name, col in HANDS:
        r = results[page]
        axes[0].hist(r["pitches"], bins=bins, histtype="step", lw=2, color=col, density=True,
                     label=f"{name}: {r['pitch_xh']:.2f}")
    axes[0].set_xlabel("distance between neighbouring stems inside a word (x-heights)", color=MUTED, fontsize=8)
    axes[0].set_ylabel("share of stem pairs", color=MUTED, fontsize=8)
    axes[0].set_title("Stem pitch: how close the upright strokes stand", fontsize=9.5, color=INK_TEXT, loc="left")
    axes[0].legend(frameon=False, fontsize=7, loc="upper right", labelcolor=INK_TEXT, title="median pitch", title_fontsize=7)
    names = [n.split(" — ")[0] for _, n, _ in HANDS]
    vals = [results[p]["pitch_spread"] for p, _, _ in HANDS]
    cols = [c for _, _, c in HANDS]
    bars = axes[1].barh(names[::-1], vals[::-1], color=cols[::-1], height=0.5)
    for b_, v in zip(bars, vals[::-1]):
        axes[1].text(v + 0.006, b_.get_y() + b_.get_height() / 2, f"{v:.2f}", va="center", fontsize=8, color=INK_TEXT)
    axes[1].set_xlabel("spread of stem pitch within a line (interquartile range ÷ median)", color=MUTED, fontsize=8)
    axes[1].set_title("Regularity of the rhythm (lower = more even)", fontsize=9.5, color=INK_TEXT, loc="left")
    axes[1].set_xlim(0, max(vals) * 1.3)
    for ax in axes:
        ax.set_facecolor(SURFACE)
        for s_ in ("top", "right"):
            ax.spines[s_].set_visible(False)
        for s_ in ("left", "bottom"):
            ax.spines[s_].set_color("#c9c8c3")
        ax.tick_params(colors=MUTED, labelsize=8)
    axes[0].grid(axis="y", color=GRID, lw=0.8)
    fig.tight_layout()
    fig.savefig(path, facecolor=SURFACE)
    plt.close(fig)


def main():
    OUT.mkdir(exist_ok=True)
    plot_atlas(OUT / "hours_atlas.png")
    results = {page: rhythm(page) for page, _, _ in HANDS}
    native = rhythm("hours", match_xh=None)
    print("hours at native resolution (x-height 30 px):", {k: round(v, 3) for k, v in native.items() if isinstance(v, float)})
    plot_rhythm(results, OUT / "minim_rhythm.png")
    summary = {p: {k: v for k, v in r.items() if k not in ("gaps", "widths", "pitches")} for p, r in results.items()}
    summary["matched_x_height_px"] = MATCH_XH
    summary["hours_native_resolution"] = {k: v for k, v in native.items() if k not in ("gaps", "widths", "pitches")}
    (OUT / "minim_rhythm.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    for p, r in summary.items():
        if isinstance(r, dict):
            print(p, {k: round(v, 3) if isinstance(v, float) else v for k, v in r.items()})


if __name__ == "__main__":
    main()
