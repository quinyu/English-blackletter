"""Writing whole lines: the scribe's word space, and a test line set beside the page.

The word space is the white between the ink of the last letter of one word and the first
of the next, in the middle of the x-height band (0.2–0.8 x-heights), where descender
flourishes and marks do not reach. It is measured on f. 12r and on the pages read in
the book (find_letters.py), on lines straightened to f. 12r's x-height; the writer uses
f. 12r's (the other pages' rougher boxes and bolder ink mask close up gaps). The writer
(scribe.Scribe.write_line) starts each word that far after the ink of the word before,
varied by the measured spread.

The letters inside a word are spaced the same way: by the white between neighbours
(scribe.ink_gaps, ink_spacing), not by the distance between the letter finder's boxes,
whose conventions differ from letter to letter. That white is taken from f. 12r, whose
letter boxes were checked and whose letters were fitted.

The test writes a line of the book directly under its photograph at the same scale, and
then any text. The text step applies the scribe's rules for letter forms
(hand.py: v at the start of a word and u inside it, ſ inside a word and s at its end,
ꝛ after o); abbreviations are given by hand.

Run:  python3 lines.py PDF_PAGE_DIR ["text" ...]   → out/hours_word_space.json, out/hours_line_test.png
"""
import json
import re
import sys
from pathlib import Path

import cv2
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

import anchors as AN
import find_letters as FL
import hands as H
import scribe as SC
import textura as TX

HERE = Path(__file__).resolve().parent
OUT = HERE / "out"
SURFACE, INK_TEXT, MUTED = "#fcfcfb", "#0b0b0b", "#52514e"
PAGE_LINE = ("p1/pg-039", 20)          # f. 18v, line 20: et ſuper exaltate eum ī ſecula:
TEXTS = [("vexilla regis prodeunt", "in full"), ("vexilla regis ꝓdeunt", "with the scribe's pro sign (ꝓximo, ꝓximos)")]


# ---- the word space ---------------------------------------------------------------------

def word_gaps(img, us, F):
    """White between neighbouring words on one straightened, padded line (x-heights)."""
    hs = TX.HS / TX.XH
    rows = np.nonzero((hs >= 0.2) & (hs <= 0.8))[0] + TX.PAD
    out = []
    F = sorted([f for f in F if not f.get("skipped")], key=lambda f: f["index"])
    for a, b in zip(F, F[1:]):
        if b["word"] != a["word"] + 1 or a["char"] in ":,." or b["char"] in ":,." or b["char"].isupper():
            continue
        c0, c1 = a["u1"] - us[0] + TX.PAD - 8, b["u0"] - us[0] + TX.PAD + 8
        best = run = 0
        for ink in (img[rows][:, c0:c1] > 0).any(0):
            run = 0 if ink else run + 1
            best = max(best, run)
        out.append(best / TX.XH)
    return out


def measure(pdf_dir):
    """The white between words, and between letters inside words (scribe.ink_gaps), on
    f. 12r and the read pages."""
    env = TX.setup()
    by = {}
    for f in env["found"]:
        by.setdefault(f["line"], []).append(f)
    g12 = [g for n, F in by.items() for g in word_gaps(*env["straight"][n], F)]
    letters = SC.ink_gaps(env["found"], env["straight"])
    book_letters = []
    found = json.loads((HERE / "data" / "hours_pages_found.json").read_text(encoding="utf-8"))
    R = json.loads((HERE / "data" / "hours_readings.json").read_text(encoding="utf-8"))
    L = json.loads((OUT / "hours_book_lines.json").read_text(encoding="utf-8"))
    gbook = []
    for page, d in found.items():
        mask = H.page_ink(Path(pdf_dir) / f"{page}.jpg")[1]
        m = FL.match_lines(R[page]["lines"], L[page]["lines"])
        byl, straight = {}, {}
        for f in d["letters"]:
            byl.setdefault(f["line"], []).append(f)
        for n, F in byl.items():
            img, us = FL.straighten(mask, m[n])
            straight[n] = (np.pad(img, TX.PAD), us)
            gbook += word_gaps(*straight[n], F)
        book_letters += SC.ink_gaps(d["letters"], straight)

    def summ(g):
        g = np.asarray(g)
        q1, med, q3 = np.percentile(g, [25, 50, 75])
        return dict(n=len(g), median=round(float(med), 3), quartiles=[round(float(q1), 3), round(float(q3), 3)],
                    sd=round(float((q3 - q1) / 1.349), 3))
    allg = summ(g12)             # the writer's: f. 12r's, for the same reason as the letters' (below)
    white = lambda G: dict(n=len(G), median=round(float(np.median([g for *_, g in G])), 3),
                           touching=round(float(np.mean([g == 0 for *_, g in G])), 3))
    # the letters are spaced by f. 12r's white: its boxes are the checked ones and its letters
    # the fitted ones; on the other pages the rougher boxes and the bolder ink mask close up
    # the gaps (a third or more of the pairs touch, against a fifth on f. 12r)
    return dict(summary=allg, f12r=summ(g12), book=summ(gbook), pooled=summ(g12 + gbook),
                letters=dict(f12r=white(letters), book=white(book_letters))), letters


def letter_spacing(gaps):
    """The writer's spacing by the white between letters (scribe.ink_spacing), with each
    letter's ink edges in the band as the writer draws it."""
    TX.M.load()
    w = AN.writer()
    edges = {}
    for ch in sorted({c for c in w.L if len(c) == 1 and not c.isspace()} | set(SC.MINIM_LETTERS)):
        st = AN.letter_strokes(w, ch)
        px = [(n, [(u * TX.XH, -v * TX.XH) for u, v in pts], k) for n, pts, k in st]
        l, r = w.band_edges(px, 0.0, TX.XH)
        edges[ch] = (l / TX.XH, r / TX.XH)
    sp = SC.ink_spacing(gaps, edges, w.sp)
    W = sp["white"]
    return dict(advance={c: round(v, 3) for c, v in sp["advance"].items() if c in edges and c in W["right"]},
                approach={c: round(v, 3) for c, v in sp["approach"].items() if c in edges and c in W["left"]},
                white={k: (round(v, 3) if isinstance(v, float) else v) for k, v in sp["white"].items()
                       if k in ("mean", "sd", "n")},
                edges={c: [round(a, 3), round(b, 3)] for c, (a, b) in edges.items()})


# ---- text -------------------------------------------------------------------------------

def diplomatic(text):
    """The scribe's letter forms for a plain Latin text: v at the start of a word and u
    inside it, ſ inside a word and s at its end, ꝛ after o."""
    out = []
    for w in text.split():
        w = re.sub(r"^u", "v", w)
        w = w[:1] + w[1:].replace("v", "u")
        w = re.sub(r"s(?=.)", "ſ", w)
        w = w.replace("or", "oꝛ")
        out.append(w)
    return " ".join(out)


# ---- the test figure --------------------------------------------------------------------

def page_line(pdf_dir, page, n):
    """The photograph of a book line, its reading and its line guide."""
    R = json.loads((HERE / "data" / "hours_readings.json").read_text(encoding="utf-8"))
    L = json.loads((OUT / "hours_book_lines.json").read_text(encoding="utf-8"))
    reading = next(l for l in R[page]["lines"] if l["n"] == n)
    guide = FL.match_lines([reading], L[page]["lines"])[n]
    rgb = cv2.cvtColor(cv2.imread(str(Path(pdf_dir) / f"{page}.jpg")), cv2.COLOR_BGR2RGB)
    return rgb, reading, guide, R[page]["folio"]


def plot(pdf_dir, texts, path, seeds=(None, 11, 29)):
    M = TX.M
    M.load()
    an = SC.load_anchors()
    rgb, reading, g, folio = page_line(pdf_dir, *PAGE_LINE)
    xh = g["x_height"]
    w = AN.writer(slant=g["slant_deg"], anchors=an)
    (bx0, by0), (bx1, by1) = g["baseline"]
    x0, x1 = int(bx0 - 0.6 * xh), int(bx1 + 0.6 * xh)
    width = x1 - x0
    rows = [("photo", None, f"The scribe: f. {folio}, line {reading['n']}")]
    rows.append(("text", (reading["diplomatic"], None), "The same line, written from the fitted hand"))
    for t, note in texts:
        for seed in seeds:
            label = f"{t}  ({note}; " + ("no variation)" if seed is None else f"the scribe's variation, seed {seed})")
            rows.append(("text", (t, seed), label))
    fig, axes = plt.subplots(len(rows), 1, figsize=(width / xh * 0.42, len(rows) * 1.25), dpi=200, facecolor=SURFACE)
    for ax, (kind, arg, title) in zip(axes, rows):
        if kind == "photo":
            yb = (by0 + by1) / 2
            y0, y1 = int(yb - 2.0 * xh), int(yb + 1.0 * xh)
            ax.imshow(rgb[y0:y1, x0:x1], extent=(0, width, 1.0 * xh, -2.0 * xh), interpolation="lanczos")
        else:
            text, seed = arg
            rng = None if seed is None else np.random.default_rng(seed)
            first = text.split()[0]
            lead = w.band_edges(w.write(first, 0.0, 0.0, xh), 0.0, xh)[0]
            SC.fill(ax, w.render(w.write_line(text, (bx0 - x0) - lead + 0.1 * xh, 0.0, xh, rng)))
        ax.set_xlim(0, width); ax.set_ylim(1.0 * xh, -2.0 * xh); ax.set_aspect("equal"); ax.axis("off")
        ax.set_title(title, fontsize=7, color=MUTED, loc="left", pad=2, fontfamily="FreeSerif")
    fig.subplots_adjust(left=0.01, right=0.99, top=0.97, bottom=0.01, hspace=0.3)
    fig.savefig(path, facecolor=SURFACE)
    plt.close(fig)


def main(pdf_dir, texts=None):
    ws, gaps = measure(pdf_dir)
    (OUT / "hours_word_space.json").write_text(json.dumps(ws, indent=1), encoding="utf-8")
    print("word space:", ws)
    sp = letter_spacing(gaps)
    (OUT / "hours_ink_spacing.json").write_text(json.dumps(sp, ensure_ascii=False, indent=1), encoding="utf-8")
    print("white between letters:", sp["white"])
    texts = [(diplomatic(t), "the scribe's letter forms") for t in texts] if texts else TEXTS
    plot(pdf_dir, texts, OUT / "hours_line_test.png")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2:] or None)
