"""Was MS 2262 written by more than one scribe?

A book of hours was often shared out among several scribes trained in the same tradition;
each scribe's habits then hold across their stint and change at its boundary, usually at a
quire. This script measures every text page of the book the same way and looks for such
changes. Per page (the scan resolution is the same throughout the PDF, so pixels compare):

  x_height, line_pitch        size of the writing and of the ruling (px)
  xh_over_pitch               how much of the ruled line the letters fill
  slant                       of the upright strokes (deg)
  stem_pitch, pitch_spread    minim rhythm: stem centre to centre inside words (x-heights),
                              and its regularity (interquartile range / median)
  stem_width                  weight of the stems (x-heights)
  pen_angle, pen_contrast     the nib fitted to stroke width by direction (nib.py)
  ascender, descender         reach above and below (x-heights)
  ink_L, ink_b                lightness and yellowness of the ink (ink batches, not scribes)
  lines, block_width          lines per page and width of the text column (px): the layout

Red ink is removed before measuring, so rubrics do not count as the scribe's text. Pages
laid out as lists (the litany, ff. 42r–45r: short invocations, each line closed by a
painted line-filler, five or more fillers per page in capitals.py's survey) measure
differently for reasons of layout, not hand: the fillers' outlines and the stacked
initials pull the fitted pen to 9–25° and its contrast to 9–13, and the descender reach
up. They are marked and left out of the change scores. Changes along the book are found
by comparing, at every page boundary, the pages before and after it (median of 8 pages
each side) in units of the page-to-page spread of each measure.

Run:  python3 hands.py PDF_PAGE_DIR   → out/hours_hands.json, out/hours_hands.png
      python3 hands.py --replot       (scores and figure again from the saved measures)
"""
import json
import sys
from pathlib import Path

import cv2
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

import capitals as C
import ink
import latin_lines as LL
import letterforms as LF
import nib

HERE = Path(__file__).resolve().parent
OUT = HERE / "out"
SURFACE, INK_TEXT, MUTED, DATA, MODEL = "#fcfcfb", "#0b0b0b", "#52514e", "#2a78d6", "#eb6834"
MIN_GAP, HALF = 40, 34
LIST_FILLERS = 5                # line-fillers on a page that mark a list layout (the litany)
FEATURES = ["x_height", "line_pitch", "xh_over_pitch", "slant", "stem_pitch", "pitch_spread", "stem_width",
            "pen_angle", "pen_contrast", "ascender", "descender", "ink_L", "ink_b", "lines", "block_width"]


def pages(pdf_dir):
    """Text pages in book order, with their folio (f. 11r is the first: p1/pg-024)."""
    out = []
    for part, rng in (("p1", range(24, 59)), ("p2", range(0, 46)), ("p3", range(0, 27))):
        for i in rng:
            f = Path(pdf_dir) / part / f"pg-{i:03d}.jpg"
            if f.exists():
                g = len(out)
                out.append(dict(page=f"{part}/pg-{i:03d}", path=str(f), folio=f"{11 + g // 2}{'rv'[g % 2]}"))
    return out


def page_ink(path):
    """The scribe's ink on a page (painted initials and red ink removed), the darkness
    map, the RGB image, and the text block (x0, y0, x1, y1), or None."""
    rgb = ink.load_rgb(path)
    lab = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB).astype(np.float32)
    mask, dark = ink.ink_mask(rgb)
    mask[ink.paint_boxes(rgb, mask)] = 0
    mask = ((mask > 0) & ~ink.red_mask(rgb, mask)).astype(np.uint8)
    return rgb, mask, dark, C.text_block(mask, C.parchment_box(lab))


def guides(mask, tb):
    """Every text line of the block: baseline and x-line (one slope for the page), slant,
    x-height, ends. [] when fewer than four lines can be fitted."""
    block = dict(x0=tb[0], y0=tb[1], x1=tb[2], y1=tb[3])
    peaks, _ = LL.line_bands(mask, block, MIN_GAP)
    first = []
    for y in peaks:
        band = mask[y - 10:y + 10, block["x0"]:block["x1"]]
        cols = np.nonzero(band.sum(0) > 0)[0]
        if len(cols) < 20:
            continue
        x0, x1 = int(cols.min() + block["x0"]), int(cols.max() + block["x0"])
        g = LL.fit_guides(mask, y, x0, x1, half=HALF)
        if g is not None:
            first.append((y, x0, x1, g["baseline"][0]))
    if len(first) < 4:
        return []
    slope = float(np.median([f[3] for f in first]))
    lines = []
    for y, x0, x1, _ in first:
        g = LL.fit_guides(mask, y, x0, x1, half=HALF, fixed_slope=slope)
        xm = (x0 + x1) / 2
        xh = (g["baseline"][0] * xm + g["baseline"][1]) - (g["xline"][0] * xm + g["xline"][1])
        if not (18 < xh < 40):
            continue
        slant, _ = LL.line_slant(mask, g, x0, x1, xh)
        lines.append(dict(x0=x0, x1=x1, g=g, x_height=float(xh), slant_deg=slant,
                          baseline=[[x0, g["baseline"][0] * x0 + g["baseline"][1]],
                                    [x1, g["baseline"][0] * x1 + g["baseline"][1]]],
                          xline=[[x0, g["xline"][0] * x0 + g["xline"][1]], [x1, g["xline"][0] * x1 + g["xline"][1]]]))
    return lines if len(lines) >= 4 else []


def measure(path):
    rgb, mask, dark, tb = page_ink(path)
    if tb is None:
        return None
    block = dict(x0=tb[0], y0=tb[1], x1=tb[2], y1=tb[3])
    lab = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB).astype(np.float32)
    lines = guides(mask, tb)
    if not lines:
        return None
    for i, l in enumerate(lines):
        pb = (lambda x, gg=lines[i - 1]["g"]: gg["baseline"][0] * x + gg["baseline"][1]) if i else None
        nx = (lambda x, gg=lines[i + 1]["g"]: gg["xline"][0] * x + gg["xline"][1]) if i + 1 < len(lines) else None
        up, down, _, _ = LL.extents(mask, l["g"], l["x0"], l["x1"], l["x_height"], pb, nx)
        l.update(ascender_xh=up, descender_xh=down)
    # minim rhythm and stem weight
    P, Wd, spreads = [], [], []
    for l in lines:
        if l["slant_deg"] is None or not np.isfinite(l["slant_deg"]):
            continue
        w, gp, p, xh = LF.line_stems(mask, l)
        inside = gp <= 0.9 * xh
        P += list(p[inside] / xh)
        Wd += list(w / xh)
        if inside.sum() >= 5:
            q1, q2, q3 = np.percentile(p[inside], [25, 50, 75])
            spreads.append((q3 - q1) / q2)
    # pen
    m = mask.copy()
    m[:block["y0"]] = 0; m[block["y1"]:] = 0; m[:, :block["x0"]] = 0; m[:, block["x1"]:] = 0
    dirs, widths = nib.mass_width_samples(m, dark)
    pen = nib.fit_nib(dirs, widths) if len(dirs) > 500 else None
    inkpx = lab[mask > 0]
    base = [l["baseline"][0][1] for l in lines]
    fin = lambda v: [x for x in v if x is not None and np.isfinite(x)]
    return dict(
        x_height=float(np.median([l["x_height"] for l in lines])),
        line_pitch=float(np.median(np.diff(sorted(base)))) if len(base) > 2 else None,
        slant=float(np.median(fin([l["slant_deg"] for l in lines]))) if fin([l["slant_deg"] for l in lines]) else None,
        stem_pitch=float(np.median(P)) if P else None,
        pitch_spread=float(np.median(spreads)) if spreads else None,
        stem_width=float(np.median(Wd)) if Wd else None,
        pen_angle=pen["theta_deg"] if pen else None, pen_contrast=pen["contrast"] if pen else None,
        ascender=float(np.median(fin([l["ascender_xh"] for l in lines]))) if fin([l["ascender_xh"] for l in lines]) else None,
        descender=float(np.median(fin([l["descender_xh"] for l in lines]))) if fin([l["descender_xh"] for l in lines]) else None,
        ink_L=float(np.median(inkpx[:, 0])), ink_b=float(np.median(inkpx[:, 2]) - 128),
        lines=len(lines), block_width=float(tb[2] - tb[0]))


def layout(rows):
    """Mark list pages (LIST_FILLERS or more painted line-fillers, from capitals.py) and
    add the measures derived from others."""
    cap = OUT / "hours_capitals.json"
    fillers = {}
    if cap.exists():
        for p in json.loads(cap.read_text(encoding="utf-8")):
            fillers[p["page"]] = sum(i["kind"] == "line-filler" for i in p["initials"])
    for r in rows:
        r["fillers"] = fillers.get(r["page"])
        r["layout"] = "list" if (r["fillers"] or 0) >= LIST_FILLERS else "text"
        if r.get("x_height") and r.get("line_pitch"):
            r["xh_over_pitch"] = r["x_height"] / r["line_pitch"]
    return rows


def change_scores(rows, k=8):
    """At each boundary i (between page i-1 and i): |median after − median before| over the
    measure's typical page-to-page spread, per measure."""
    X = {f: np.array([r[f] if r.get(f) is not None and r.get("layout") != "list" else np.nan for r in rows], float)
         for f in FEATURES}
    out = []
    for i in range(k, len(rows) - k + 1):
        sc = {}
        for f, v in X.items():
            a, b = v[i - k:i], v[i:i + k]
            a, b = a[np.isfinite(a)], b[np.isfinite(b)]
            spread = np.nanmedian(np.abs(np.diff(v[np.isfinite(v)])))
            if len(a) >= 4 and len(b) >= 4 and spread > 0:
                sc[f] = float(abs(np.median(b) - np.median(a)) / spread)
        out.append(dict(at=i, folio=rows[i]["folio"], scores=sc))
    return out


def main(pdf_dir):
    OUT.mkdir(exist_ok=True)
    if pdf_dir == "--replot":
        rows = json.loads((OUT / "hours_hands.json").read_text(encoding="utf-8"))["pages"]
    else:
        rows = []
        for p in pages(pdf_dir):
            m = measure(p["path"])
            rows.append(dict(p, **(m or {})))
            if m:
                print(f"{p['folio']:>5} {p['page']}: xh {m['x_height']:.1f} pitch {m['line_pitch'] or 0:.1f} "
                      f"slant {m['slant'] or 0:.1f} stems {m['stem_pitch'] or 0:.3f} pen {m['pen_angle'] or 0:.0f}°/"
                      f"{m['pen_contrast'] or 0:.2f} lines {m['lines']}", flush=True)
            else:
                print(f"{p['folio']:>5} {p['page']}: not measured", flush=True)
    rows = layout(rows)
    changes = change_scores(rows)
    summary = summarise(rows, changes)
    (OUT / "hours_hands.json").write_text(json.dumps(dict(summary=summary, pages=rows, changes=changes), indent=1,
                                                     default=float), encoding="utf-8")
    plot(rows, changes, OUT / "hours_hands.png")
    print(json.dumps(summary, indent=1, default=float))
    return rows, changes


def summarise(rows, changes):
    """Book-wide spread of each measure on text pages, and the strongest boundaries."""
    text = [r for r in rows if r.get("layout") == "text" and r.get("x_height")]
    spread = {}
    for f in FEATURES:
        v = np.array([r[f] for r in text if r.get(f) is not None], float)
        if len(v):
            q1, q2, q3 = np.percentile(v, [25, 50, 75])
            spread[f] = dict(median=round(q2, 3), iqr=round(q3 - q1, 3), min=round(v.min(), 3), max=round(v.max(), 3))
    hand = ["x_height", "slant", "stem_pitch", "pitch_spread", "stem_width", "pen_angle", "pen_contrast",
            "ascender", "descender"]
    top = sorted(changes, key=lambda c: -max([c["scores"].get(f, 0) for f in hand] or [0]))[:5]
    return dict(pages=len(rows), measured=len([r for r in rows if r.get("x_height")]), text_pages=len(text),
                list_pages=[r["folio"] for r in rows if r.get("layout") == "list"], spread=spread,
                strongest_boundaries=[dict(folio=c["folio"], **{f: round(c["scores"][f], 2) for f in hand
                                                                 if c["scores"].get(f, 0) >= 2}) for c in top])


PANELS = [("x_height", "x-height (px)"), ("slant", "slant (°)"), ("stem_pitch", "stem pitch (x-heights)"),
          ("stem_width", "stem width (x-heights)"), ("pen_angle", "pen angle (°)"), ("pen_contrast", "pen contrast"),
          ("ascender", "ascender (x-heights)"), ("descender", "descender (x-heights)"), ("ink_L", "ink lightness L*")]


def plot(rows, changes, path):
    """Each measure along the book, one dot per page; list pages (the litany) shaded, their
    values left out of the running median of 8 pages (and below the panel for the pen
    angle, at 9–25°)."""
    fig, axes = plt.subplots(len(PANELS), 1, figsize=(10, 1.15 * len(PANELS)), dpi=170, facecolor=SURFACE, sharex=True)
    xs = np.arange(len(rows))
    lst = [i for i, r in enumerate(rows) if r.get("layout") == "list"]
    for ax, (f, label) in zip(axes, PANELS):
        ax.set_facecolor(SURFACE)
        v = np.array([r.get(f) if r.get(f) is not None else np.nan for r in rows], float)
        if lst:
            ax.axvspan(min(lst) - 0.5, max(lst) + 0.5, color="#ece9e2", lw=0)
        t = np.array([r.get("layout") != "list" for r in rows])
        ax.plot(xs[t], v[t], "o", ms=2.2, color=DATA)
        ax.plot(xs[~t], v[~t], "o", ms=2.2, color=MUTED, mfc="none", mew=0.6)
        vt = np.where(t, v, np.nan)
        run = [np.nanmedian(vt[max(0, i - 4):i + 4]) if np.isfinite(vt[max(0, i - 4):i + 4]).any() else np.nan
               for i in range(len(rows))]
        ax.plot(xs, np.where(t, run, np.nan), "-", lw=1.0, color=MODEL)
        lo, hi = np.nanpercentile(vt, [1, 99])
        pad = 0.35 * (hi - lo)
        ax.set_ylim(lo - pad, hi + pad)
        ax.set_ylabel(label, fontsize=6.5, color=INK_TEXT, rotation=0, ha="right", va="center")
        ax.tick_params(labelsize=6, colors=MUTED)
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)
        for s in ("left", "bottom"):
            ax.spines[s].set_color("#bdbab3")
    ticks = list(range(0, len(rows), 6))
    axes[-1].set_xticks(ticks)
    axes[-1].set_xticklabels([f"f. {rows[i]['folio']}" for i in ticks], fontsize=6)
    if lst:
        axes[0].text((min(lst) + max(lst)) / 2, 1.02, "litany (list layout)", transform=axes[0].get_xaxis_transform(),
                     ha="center", va="bottom", fontsize=6, color=MUTED)
    fig.suptitle("MS 2262, ff. 11r–64v: the hand page by page (dots; open dots: list pages), running median "
                 "of 8 text pages (line)", fontsize=8.5, color=INK_TEXT, x=0.01, ha="left")
    fig.tight_layout(rect=(0, 0, 1, 0.97))
    fig.savefig(path, facecolor=SURFACE)
    plt.close(fig)


if __name__ == "__main__":
    main(sys.argv[1])
