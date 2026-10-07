"""How far the scribe of MS 2262 tilts his quill for a bar: crossbars measured in the book.

A broad quill makes its thin strokes in two ways. Moved along its edge it draws the
edge's own thickness. Tilted onto one end of its edge, it keeps that thickness but its
contact loses breadth, so it draws like a much narrower nib of the same weight, in any
direction (pen.tilt_breadth). Scribes use the tilt to any degree, and may tilt during a
stroke (the e caudata's tail). A bar across an ascender shows the degree plainly: drawn
flat, the edge makes a bar as heavy as a macron. Fully tilted, the bar is only a little
heavier than the quill's thickness. Drawn with a corner alone, it would be a fine
line.

The book has 45 recorded bars (data/hours_book_signs.jsonl): l barred for -or- or -el
(gl̄ia, ppl̄os, Kyriel̵, the litany's ł), h and b barred (ih̄s, Ioh̄s, nob̄) and đ. On each,
in the line straightened and rescaled to f. 12r's x-height, the bar is the longest run of
columns right of the ascender with a single short ink run above the x-height. Its
thickness is that run's median length. The same measurement is made on bars drawn by
the renderer with the page's pen at every tilt, at sub-pixel offsets, and the page's
bars are read off that curve.

Run:  python3 quill_tilt.py PDF_PAGE_DIR   → out/hours_tilt.json, out/hours_tilt.png
"""
import json
import sys
from pathlib import Path

import cv2
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

import book_signs as BS
import letterforms as LF
import minims as M
import textura as TX

HERE = Path(__file__).resolve().parent
OUT = HERE / "out"
SURFACE, INK_TEXT, MUTED, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#ecebe8"
BARS = ("l_stroke", "h_stroke", "b_stroke", "d_stroke")
MIN_COLS = 6            # a bar measured over fewer columns is left out
TILTS = np.round(np.arange(0.0, 1.01, 0.05), 2)


def bar_runs(img, a, b):
    """(column, run length, run top) for columns a … b of a straightened line holding one
    short ink run between 1.08 and 2.0 x-heights (a bar, not an ascender)."""
    v = np.full(img.shape[0], np.nan)
    v[TX.PAD:TX.PAD + len(TX.HS)] = TX.HS / TX.XH
    band = (v >= 1.08) & (v <= 2.0)
    nb = int(band.sum())
    out = []
    for c in range(max(0, a), min(img.shape[1], b)):
        col = img[band, c] > 0
        if not col.any():
            continue
        r = np.nonzero(np.diff(np.r_[0, col.astype(int), 0]))[0].reshape(-1, 2)
        if len(r) == 1 and r[0, 1] - r[0, 0] < 0.3 * TX.XH and r[0, 1] < nb - 1:
            out.append((c, int(r[0, 1] - r[0, 0]), int(r[0, 0])))
    return out


def longest_chain(runs):
    if not runs:
        return []
    cs = np.array([r[0] for r in runs])
    chains = np.split(np.arange(len(cs)), np.nonzero(np.diff(cs) > 1)[0] + 1)
    return [runs[k] for k in max(chains, key=len)]


def measure(pdf_dir):
    recs = [json.loads(l) for l in (HERE / "data" / "hours_book_signs.jsonl").read_text(encoding="utf-8").splitlines()
            if l.strip()]
    out = []
    for r in recs:
        if r["sign"] not in BARS:
            continue
        mask, red, lines = BS.page(pdf_dir, r["page"])
        line = BS.line_of(lines, r["box"])
        if line is None:
            continue
        x0, y0, x1, y1 = r["box"]
        in_red = red[y0:y1, x0:x1].sum() > mask[y0:y1, x0:x1].sum()
        img, us, s = BS.straighten(red if in_red else mask, line, span=(x0 - 60, x1 + 60))
        yb, _ = LF.guide(line, (x0 + x1) / 2)
        t = np.tan(np.radians(line["slant_deg"]))
        hc = yb - (y0 + y1) / 2
        a = int(round((x0 - hc * t) / s)) - us[0] + TX.PAD - 8
        b = int(round((x1 - hc * t) / s)) - us[0] + TX.PAD + 25
        ch = longest_chain(bar_runs(img, a, b))
        W = np.array([w for _, w, _ in ch], float)
        out.append(dict(page=r["page"], folio=r["folio"], word=r["word"], sign=r["sign"], red=bool(in_red),
                        box=r["box"], n=len(W), thickness=float(np.median(W)) if len(W) else None))
    return out


def model_curve(rise_deg=3.0, length=0.6, offsets=np.arange(0.0, 1.0, 0.1)):
    """The same measurement on bars the renderer draws with the page's pen at each tilt
    (and with the corner of the pen), averaged over sub-pixel positions."""
    M.load()
    fp = TX.FastPen(M.nib_for([1.0]), 0.0)
    rise = length * np.tan(np.radians(rise_deg))

    def thick(name, kind):
        vals = []
        for dv in offsets:
            v0 = 1.4 + dv / TX.XH
            m = fp.draw([(name, [(0.0, v0), (length, v0 + rise)], kind)], (TX.H, TX.W), (TX.OX, TX.ROW0))
            img = np.pad(m, TX.PAD)
            ch = longest_chain(bar_runs(img, 0, img.shape[1]))
            mid = ch[len(ch) // 4: 3 * len(ch) // 4] or ch
            vals.append(np.median([w for _, w, _ in mid]))
        return float(np.mean(vals))
    return dict(tilt=TILTS.tolist(), thickness=[thick("bar", {"tilt": float(t)}) for t in TILTS],
                corner=thick("hairline bar", None), rise_deg=rise_deg)


def tilt_of(thickness, curve):
    """Tilt whose drawn bar is this thick (the curve falls with tilt), clipped to 0 … 1."""
    th = np.asarray(curve["thickness"])[::-1]
    return float(np.interp(thickness, th, np.asarray(curve["tilt"])[::-1]))


def summarise(bars, curve):
    ok = [b for b in bars if b["n"] >= MIN_COLS]
    for b in ok:
        b["tilt"] = round(tilt_of(b["thickness"], curve), 3)
    th = np.array([b["thickness"] for b in ok])
    tl = np.array([b["tilt"] for b in ok])
    q = lambda v: [round(float(x), 3) for x in np.percentile(v, [25, 50, 75])]
    return dict(n=len(ok), n_recorded=len(bars), thickness_quartiles=q(th), tilt_quartiles=q(tl),
                bar_tilt=round(float(np.median(tl)), 2),
                bar_tilt_sd=round(float((np.percentile(tl, 75) - np.percentile(tl, 25)) / 1.349), 2),
                flat_px=round(curve["thickness"][0], 2), tilted_px=round(curve["thickness"][-1], 2),
                corner_px=round(curve["corner"], 2),
                counts=dict(corner_or_less=int((th <= curve["corner"] + 0.5).sum()),
                            tilted=int(((th > curve["corner"] + 0.5) & (th < curve["thickness"][0] - 0.5)).sum()),
                            flat=int((th >= curve["thickness"][0] - 0.5).sum())))


def plot(bars, curve, S, pdf_dir, path, show=12):
    fig = plt.figure(figsize=(11, 5.6), dpi=150, facecolor=SURFACE)
    gs = fig.add_gridspec(3, 6, width_ratios=[1, 1, 1, 1, 0.15, 3.2], hspace=0.35, wspace=0.08)
    ok = sorted([b for b in bars if b["n"] >= MIN_COLS], key=lambda b: b["thickness"])
    pick = [ok[int(round(i))] for i in np.linspace(0, len(ok) - 1, show)]
    cache = {}
    for k, b in enumerate(pick):
        ax = fig.add_subplot(gs[k // 4, k % 4])
        if b["page"] not in cache:
            cache[b["page"]] = cv2.cvtColor(cv2.imread(str(Path(pdf_dir) / f"{b['page']}.jpg")), cv2.COLOR_BGR2RGB)
        x0, y0, x1, y1 = b["box"]
        cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
        ax.imshow(cache[b["page"]][cy - 34:cy + 22, cx - 40:cx + 40], interpolation="lanczos")
        ax.set_title(f"f. {b['folio']} {b['word']}: {b['thickness']:.0f} px", fontsize=6.5, color=INK_TEXT, pad=2,
                     fontfamily="FreeSerif")
        ax.axis("off")
    ax = fig.add_subplot(gs[:, 5])
    th = np.array([b["thickness"] for b in ok])
    bins = np.arange(0.5, 9.0, 1.0)
    ax.hist(th, bins=bins, color="#2a78d6", alpha=0.8, rwidth=0.85, label=f"the scribe's bars ({len(th)})")
    for x, lab, col, ls in ((curve["corner"], "corner of the pen", "#d55181", ":"),
                            (curve["thickness"][-1], "quill fully tilted", INK_TEXT, "-"),
                            (curve["thickness"][0], "quill flat (a macron)", MUTED, "--")):
        ax.axvline(x, color=col, ls=ls, lw=1.6, label=f"{lab}: {x:.1f} px")
    ax.set_xlabel("bar thickness in the straightened line (px; x-height 29 px)", color=MUTED, fontsize=8)
    ax.set_ylabel("bars", color=MUTED, fontsize=8)
    ax.set_title(f"Bars drawn with the quill tilted: median tilt {S['bar_tilt']:.2f}", fontsize=9.5,
                 color=INK_TEXT, loc="left")
    ax.set_ylim(0, max(np.histogram(th, bins=bins)[0]) * 1.6)
    ax.legend(frameon=False, fontsize=7, loc="upper right", labelcolor=INK_TEXT)
    ax.tick_params(colors=MUTED, labelsize=8)
    ax.set_facecolor(SURFACE)
    for s_ in ("top", "right"):
        ax.spines[s_].set_visible(False)
    ax.grid(axis="y", color=GRID, lw=0.8)
    fig.suptitle("The scribe's crossbars (barred l, h, b and đ), thinnest to thickest", fontsize=9.5,
                 color=INK_TEXT, x=0.01, ha="left")
    fig.savefig(path, facecolor=SURFACE, bbox_inches="tight")
    plt.close(fig)


def load():
    """The measured tilt (bar_tilt, bar_tilt_sd), or None before this script has run."""
    p = OUT / "hours_tilt.json"
    return json.loads(p.read_text(encoding="utf-8"))["summary"] if p.exists() else None


def main(pdf_dir):
    bars = measure(pdf_dir)
    curve = model_curve()
    S = summarise(bars, curve)
    (OUT / "hours_tilt.json").write_text(json.dumps(dict(summary=S, curve=curve, bars=bars), ensure_ascii=False,
                                                    indent=1), encoding="utf-8")
    plot(bars, curve, S, pdf_dir, OUT / "hours_tilt.png")
    print(json.dumps(S, indent=1))
    return S


if __name__ == "__main__":
    main(sys.argv[1])
