"""Letters f. 12r lacks, fitted from the pages read in the rest of the book.

f. 12r has a single x. The pages read for the biting study (data/hours_readings.json, the
letters found by find_letters.py) have 42. The letter finder had no x template and
used c in its place, so its x boxes are narrow and often start a little off the letter.
Each box is therefore first moved onto the letter with the drawn plan, over ±10 px,
and widened to the plan's width; the fit then proceeds as for f. 12r's letters
(textura.fit_letter), with the variation in width and height measured the same way.

  x   seen in close-up (exaltet, exaudi, ex hoc): a heavy stroke from a headed top
      left corner down to a foot at the lower right; a small flag at the upper right
      (the next letter tucks in close to it: exu, benediximus), from which a thin stroke
      crosses down to the left and runs on below the line. With
      this nib a stroke in that direction is thin only if the quill is tilted, and it
      is drawn so (quill_tilt.py).

Run:  python3 book_letters.py PDF_PAGE_DIR   → out/hours_book_letters.json, out/hours_book_letters.png
"""
import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

import find_letters as FL
import hands as H
import textura as TX

HERE = Path(__file__).resolve().parent
OUT = HERE / "out"
SURFACE, INK_TEXT, MUTED = "#fcfcfb", "#0b0b0b", "#52514e"
TILTED = {"tilt": 1.0}

PLANS = {
    # proportions from close-ups (ff. 29r, 52v, 62v: exaltet, exaudi, ex); held near the
    # plan, as the tilde is: in the ink mask the x's faint thin stroke drops out and its
    # neighbours crowd it, and a free fit turns the diagonal upright into an r
    "x": dict(zone=(-0.75, 1.3), move=0.06, ties=[((1, 2), (2, 0))], strokes=[
        ("stroke", [(0.02, 0.95), (0.1, 0.9), (0.45, 0.35), (0.6, 0.06), (0.72, 0.02)], None),
        ("head", [(0.58, 0.93), (0.66, 0.98), (0.72, 0.92)], None),
        ("thin stroke", [(0.72, 0.92), (0.46, 0.5), (0.15, 0.02), (-0.08, -0.35)], TILTED)]),
}
SHIFT = range(-10, 11)          # px: moving a finder's box onto its letter
WIDTH = 0.9                     # x-heights: a moved box's width


def examples(pdf_dir, ch):
    """The read pages' examples of ch, each box moved onto the letter by the drawn plan
    and widened to it."""
    found = json.loads((HERE / "data" / "hours_pages_found.json").read_text(encoding="utf-8"))
    R = json.loads((HERE / "data" / "hours_readings.json").read_text(encoding="utf-8"))
    L = json.loads((OUT / "hours_book_lines.json").read_text(encoding="utf-8"))
    fp = TX.FastPen(TX.M.nib_for([1.0]), 0.0)
    TX.PLANS[ch] = PLANS[ch]
    model = fp.draw(TX.unpack(PLANS[ch], TX.pack(PLANS[ch])), (TX.H, TX.W), (TX.OX, TX.ROW0))
    win = TX.plan_window(ch, fp)
    exs, cache = [], {}
    for page, d in found.items():
        F = [f for f in d["letters"] if f["char"] == ch and not f["skipped"]]
        if not F:
            continue
        mask = H.page_ink(Path(pdf_dir) / f"{page}.jpg")[1]
        m = FL.match_lines(R[page]["lines"], L[page]["lines"])
        for f in F:
            key = (page, f["line"])
            if key not in cache:
                img, us = FL.straighten(mask, m[f["line"]])
                cache[key] = (np.pad(img, TX.PAD), us)
            img, us = cache[key]
            f = dict(f, u1=f["u0"] + int(round(WIDTH * TX.XH)), folio=d["folio"])
            ex = dict(f=f, img=img, us=us, dx=0, dy=0)
            best = max((TX.score_one(model, ex, win, dx, dy), dx) for dx in SHIFT for dy in range(-4, 5))
            ex["f"] = dict(f, u0=f["u0"] + best[1], u1=f["u1"] + best[1])
            exs.append(ex)
    return exs, fp


def fit(pdf_dir, letters=("x",)):
    fits = {}
    for ch in letters:
        exs, fp = examples(pdf_dir, ch)
        x, per, keep, aside = TX.fit_letter(ch, exs, fp)
        var = TX.variation(ch, x, keep, fp)
        fits[ch] = dict(x=x, exs=keep, score=per, var=var, aside=aside)
    return fits, fp


def neighbours(F):
    """For each example: the letters written before and after it in its word on the page."""
    found = json.loads((HERE / "data" / "hours_pages_found.json").read_text(encoding="utf-8"))
    idx = {(f["page"], f["line"], f["index"]): f for d in found.values() for f in d["letters"]}
    out = []
    for e in F["exs"]:
        f = e["f"]
        a = idx.get((f["page"], f["line"], f["index"] - 1))
        b = idx.get((f["page"], f["line"], f["index"] + 1))
        out.append((a["char"] if a and a["word"] == f["word"] else None, b["char"] if b and b["word"] == f["word"] else None))
    return out


def spacing(fits, fp):
    """Approach and advance of each letter, so that the writer leaves the white the page
    leaves beside it (book_signs.spacing, with the page's own neighbours)."""
    import anchors as AN
    import book_signs as BS
    w = AN.writer()
    sp = w.sp
    out = {}
    for ch, F in fits.items():
        TX.PLANS[ch] = PLANS[ch]
        w.L[ch] = dict(strokes=[dict(name=n, points=p, pen=k) for n, p, k in TX.unpack(PLANS[ch], F["x"])],
                       shift_px=[float(np.median([e["dx"] for e in F["exs"]])), 0.0], width_scale=[1, 0], height_scale=[1, 0])
        eb = BS.writer_edges(w, ch)
        app, adv = [], []
        for (gl, gr), (prev, nxt) in zip(BS.page_gaps(ch, F, fp), neighbours(F)):
            if gl is not None and prev in sp["advance"] and eb and (ea := BS.writer_edges(w, prev)):
                app.append((gl + ea[1] - eb[0]) / TX.XH - sp["advance"][prev])
            if gr is not None and nxt in sp["approach"] and eb and (en := BS.writer_edges(w, nxt)):
                adv.append((gr + eb[1] - en[0]) / TX.XH - sp["approach"][nxt])
        out[ch] = dict(approach=round(float(np.median(app)), 3) if app else None,
                       advance=round(float(np.median(adv)), 3) if adv else None, n=[len(app), len(adv)])
    return out


def save(fits, path, spacing_=None):
    out = {}
    for ch, F in fits.items():
        out[ch] = dict(strokes=[dict(name=n, points=[[round(u, 4), round(v, 4)] for u, v in p], pen=k)
                                for n, p, k in TX.unpack(PLANS[ch], F["x"])],
                       zone=PLANS[ch]["zone"], n=len(F["exs"]), overlap=float(np.mean(F["score"])),
                       shift_px=[float(np.median([e["dx"] for e in F["exs"]])),
                                 float(np.median([e["dy"] for e in F["exs"]]))],
                       width_scale=[float(np.median(F["var"][:, 0])), float(np.std(F["var"][:, 0]))],
                       height_scale=[float(np.median(F["var"][:, 1])), float(np.std(F["var"][:, 1]))],
                       set_aside=[dict(folio=e["f"]["folio"], line=e["f"]["line"], index=e["f"]["index"])
                                  for e in F["aside"]],
                       source="pages read in data/hours_readings.json (find_letters.py)",
                       spacing=(spacing_ or {}).get(ch))
    path.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")


def plot(fits, fp, path, n=12):
    """Each letter's examples (moved boxes) with the fitted letter drawn over them."""
    fig, axes = plt.subplots(len(fits), n, figsize=(n * 0.9, 1.3 * len(fits)), dpi=150, facecolor=SURFACE,
                             squeeze=False)
    for r, (ch, F) in enumerate(fits.items()):
        model = fp.draw(TX.unpack(PLANS[ch], F["x"]), (TX.H, TX.W), (TX.OX, TX.ROW0))
        order = np.argsort(F["score"])[::-1]
        for c, k in enumerate(order[np.linspace(0, len(order) - 1, n).round().astype(int)]):
            ex = F["exs"][k]
            I = TX.crop(ex, ex["dx"], ex["dy"])
            rgb = np.ones(I.shape + (3,))
            rgb[I > 0] = (0.55, 0.55, 0.55)
            rgb[(model > 0) & (I > 0)] = (0.1, 0.1, 0.1)
            rgb[(model > 0) & (I == 0)] = (0.92, 0.42, 0.2)
            ax = axes[r, c]
            ax.imshow(rgb, interpolation="nearest")
            ax.set_title(f"{ex['f']['folio']} · {F['score'][k]:.2f}", fontsize=6, color=MUTED, pad=1)
            ax.axis("off")
    fig.suptitle("x from the book: ink grey, the fitted letter black where it meets the ink, orange where not",
                 fontsize=8, color=INK_TEXT, x=0.01, ha="left")
    fig.tight_layout(rect=(0, 0, 1, 0.92))
    fig.savefig(path, facecolor=SURFACE)
    plt.close(fig)


def main(pdf_dir):
    TX.M.load()
    fits, fp = fit(pdf_dir)
    sp = spacing(fits, fp)
    print("spacing:", sp)
    save(fits, OUT / "hours_book_letters.json", sp)
    plot(fits, fp, OUT / "hours_book_letters.png")
    return fits


if __name__ == "__main__":
    main(sys.argv[1])
