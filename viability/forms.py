"""The same letters throughout MS 2262: does one hand write them all?

Page-wide measures (hands.py) hold steady through the book, but scribes trained in one
tradition often differ only in the details of their letters: the closing of g, the lean
of round d's back, the head of a, the round final s, r rotunda. This script finds those
letters on every text page and compares them with f. 12r.

The examples of each letter on f. 12r (cut from the letter finder's boxes; at most the
eight closest to the letter's mean) are the templates. Each is matched by normalised correlation over the ink-darkness map of each page, at three
sizes, with red ink and painted initials blanked. The match is scored band by band (the
ascender, x-height and descender bands) and the weakest band decides; a band where the
letter has no ink must be empty in the match too. So a g must have a g's tail and an a
nothing above or below it, and the minim rhythm every textura letter shares does not
decide the match. (Whole words were tried first: most words of f. 12r are absent from
most pages, and the best match was then only a look-alike.)

Pages with fewer than ten lines (ff. 34v, 55r, 64v) are left out of the means: their few
letters leave the best matches to stray look-alikes.

Outputs:
  out/hours_forms.json   per page, the best matches of each letter (score, box)
  out/hours_forms.png    for each letter: the f. 12r examples; the best match on pages spread
                         through the book; and the mean of the best matches per stretch of
                         the book, with its correlation to the f. 12r mean (a second scribe
                         would show as a stretch whose mean letter differs)

Run:  python3 forms.py PDF_PAGE_DIR
      python3 forms.py --replot      (means and figure again from the saved matches)
"""
import json
import multiprocessing
import os
import sys
from pathlib import Path

import cv2
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

import capitals as C
import hands as H
import ink

HERE = Path(__file__).resolve().parent
OUT = HERE / "out"
SURFACE, INK_TEXT, MUTED, DATA = "#fcfcfb", "#0b0b0b", "#52514e", "#2a78d6"
LETTERS = {"g": "g", "d": "round d", "a": "a", "s": "final s", "ꝛ": "r rotunda"}
STRETCHES = 8                   # parts of the book whose mean letters are compared
SCALES = (0.94, 1.0, 1.06)
TOP, BOTTOM = 1.72, 0.78        # template band above and below the baseline (x-heights)
F12R = "p1/pg-026"


def darkness(rgb):
    d = ink.ink_darkness(rgb)
    mask, _ = ink.ink_mask(rgb)
    d[ink.paint_boxes(rgb, mask)] = 0
    d[ink.red_mask(rgb, np.ones_like(mask))] = 0
    return d.astype(np.float32)


def letter_boxes():
    """Box (x0, y0, x1, y1) on f. 12r of every example of the chosen letters, from the
    letters found by align.py (u is the column at the baseline; slanted strokes lean right
    by h·tan(slant) at height h)."""
    found = json.loads((HERE / "data" / "hours_letters_found.json").read_text(encoding="utf-8"))["letters"]
    out = {}
    for f in found:
        if f.get("skipped") or f["char"] not in LETTERS:
            continue
        xh, t = f["xh"], np.tan(np.radians(f["slant"]))
        x0 = f["u0"] - BOTTOM * xh * t - 1
        x1 = f["u1"] + TOP * xh * t + 1
        out.setdefault(f["char"], []).append(
            dict(line=f["line"], box=[int(x0), int(f["yb"] - TOP * xh), int(x1), int(f["yb"] + BOTTOM * xh)]))
    return out


def peaks(score, k, gap):
    """The k best non-overlapping maxima of a correlation map."""
    s = score.copy()
    out = []
    for _ in range(k):
        i = int(np.argmax(s))
        y, x = divmod(i, s.shape[1])
        if not np.isfinite(s[y, x]) or s[y, x] <= 0:
            break
        out.append((float(s[y, x]), x, y))
        s[max(0, y - gap[1]):y + gap[1], max(0, x - gap[0]):x + gap[0]] = -1
    return out


def band_rows(h):
    """Rows of the ascender, x-height and descender bands in a template of height h."""
    xh = h / (TOP + BOTTOM)
    a, b = int(round((TOP - 1) * xh)), int(round(TOP * xh))
    return [(0, a), (a, b), (b, h)]


def band_score(region, T):
    """Correlation map of template T over region, taken band by band: the weakest of the
    bands where T has ink. A band where T is (nearly) empty must be nearly empty in the
    match too, or the place is rejected: the profile of ascenders and descenders, not the
    minim rhythm every textura word shares, decides the match."""
    h, w = T.shape
    H, W = region.shape[0] - h + 1, region.shape[1] - w + 1
    out = np.full((H, W), np.inf, np.float32)
    xband = band_rows(h)[1]
    for r0, r1 in band_rows(h):
        if r1 - r0 < 3:
            continue
        Tb = T[r0:r1]
        Rb = region[r0:r0 + H + (r1 - r0) - 1]
        if Tb.mean() >= 0.2 * T[xband[0]:xband[1]].mean():
            sc = cv2.matchTemplate(Rb, Tb, cv2.TM_CCOEFF_NORMED)
            mean = cv2.boxFilter(Rb, -1, (w, r1 - r0), borderType=cv2.BORDER_CONSTANT)
            sq = cv2.boxFilter(Rb * Rb, -1, (w, r1 - r0), borderType=cv2.BORDER_CONSTANT)
            cy, cx = (r1 - r0) // 2, w // 2
            mean, sq = mean[cy:cy + H, cx:cx + W], sq[cy:cy + H, cx:cx + W]
            std = np.sqrt(np.maximum(sq - mean ** 2, 0))
            # blank patches (margins, blanked paint) correlate as 1 or not at all
            sc[(mean < 0.5 * Tb.mean()) | (std < 0.5 * Tb.std()) | ~np.isfinite(sc)] = -1
        else:
            mean = cv2.boxFilter(Rb, -1, (w, r1 - r0), borderType=cv2.BORDER_CONSTANT)
            cy, cx = (r1 - r0) // 2, w // 2
            extra = mean[cy:cy + H, cx:cx + W] - Tb.mean()
            sc = np.where(extra > 0.35 * T[xband[0]:xband[1]].mean(), -1, np.inf).astype(np.float32)
        out = np.minimum(out, sc)
    out[~np.isfinite(out)] = -1
    return out


def spot(d, block, templates, k=3):
    """Best matches of a word on one page: [(score, x0, y0, x1, y1, template)]."""
    x0, y0, x1, y1 = block
    region = d[max(0, y0 - 40):y1 + 40, max(0, x0 - 20):x1 + 20]
    ox, oy = max(0, x0 - 20), max(0, y0 - 40)
    hits = []
    for ti, T in enumerate(templates):
        for s in SCALES:
            Ts = cv2.resize(T, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
            if Ts.shape[0] >= region.shape[0] or Ts.shape[1] >= region.shape[1]:
                continue
            h, w = Ts.shape
            for v, x, y in peaks(np.minimum(band_score(region, Ts), 1.0), k, (w // 2, h // 3)):
                hits.append((v, ox + x, oy + y, ox + x + w, oy + y + h, ti))
    hits.sort(key=lambda h: -h[0])
    keep = []
    for h in hits:        # one hit per place, whichever template and size found it
        if all(abs(h[1] - g[1]) > (h[3] - h[1]) // 2 or abs(h[2] - g[2]) > (h[4] - h[2]) // 3 for g in keep):
            keep.append(h)
        if len(keep) == k:
            break
    return keep


def main(pdf_dir):
    boxes = letter_boxes()
    if pdf_dir == "--replot":
        rows = json.loads((OUT / "hours_forms.json").read_text(encoding="utf-8"))["pages"]
        ref = next(r for r in rows if r["page"] == F12R)
    else:
        rows, ref = None, next(p for p in H.pages(pdf_dir) if p["page"] == F12R)
    d12 = darkness(ink.load_rgb(ref["path"]))
    templates = typical({c: [d12[b["box"][1]:b["box"][3], b["box"][0]:b["box"][2]].copy() for b in boxes[c]]
                         for c in boxes}, boxes)
    if rows is None:
        rows = match_book(H.pages(pdf_dir), templates, boxes)
    short = short_pages()
    for r in rows:
        r["short"] = r["page"] in short
    res = dict(templates=boxes, short_pages=sorted(short), stretches=stretch_means(rows, templates)[1], pages=rows)
    OUT.mkdir(exist_ok=True)
    (OUT / "hours_forms.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    plot(rows, boxes, templates, d12, OUT / "hours_forms.png")
    return rows


def short_pages(min_lines=10):
    """Pages with too little text to compare (fewer than min_lines lines, or none, in
    hands.py's survey): f. 55r has two lines, f. 64v five, f. 34v six. Their few letters
    leave the best matches to stray look-alikes."""
    path = OUT / "hours_hands.json"
    if not path.exists():
        return set()
    return {r["page"] for r in json.loads(path.read_text(encoding="utf-8"))["pages"]
            if (r.get("lines") or 0) < min_lines}


def match_book(pages, templates, boxes):
    # fresh worker processes ("spawn"): forking after OpenCV has started its threads hangs
    ctx = multiprocessing.get_context("spawn")
    with ctx.Pool(min(4, os.cpu_count() or 1), initializer=_init, initargs=(templates, boxes)) as pool:
        rows = pool.map(page_hits, pages)
    for r in rows:
        print(f"{r['folio']:>5} {r['page']}: " + " ".join(f"{c} {h[0][0]:.2f}" for c, h in r["letters"].items() if h))
    return rows


def typical(templates, boxes, n=8):
    """At most n examples per letter: those closest to the letter's mean (and boxes cut
    to match)."""
    for c, T in templates.items():
        if len(T) <= n:
            continue
        size = (int(np.median([t.shape[1] for t in T])), int(np.median([t.shape[0] for t in T])))
        R = [cv2.resize(t, size) for t in T]
        m = np.mean(R, 0)
        keep = sorted(np.argsort([-ncc(r, m) for r in R])[:n])
        templates[c] = [T[i] for i in keep]
        boxes[c] = [boxes[c][i] for i in keep]
    return templates


_JOB = None


def _init(templates, boxes):
    global _JOB
    _JOB = (templates, boxes)


def page_hits(p, k=4):
    """The best k matches of each letter on one page (run in a worker)."""
    cv2.setNumThreads(1)
    templates, boxes = _JOB
    rgb = ink.load_rgb(p["path"])
    lab = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB).astype(np.float32)
    mask, _ = ink.ink_mask(rgb)
    tb = C.text_block(mask, C.parchment_box(lab))
    if tb is None:
        return dict(p, letters={})
    d = darkness(rgb)
    hits = {}
    for c, T in templates.items():
        hs = spot(d, tb, T, k=k + len(T))
        if p["page"] == F12R:       # on f. 12r a template trivially finds itself
            own = [b["box"] for b in boxes[c]]
            hs = [h for h in hs if not any(abs(h[1] - b[0]) < 6 and abs(h[2] - b[1]) < 6 for b in own)]
        hits[c] = [[float(h[0])] + [int(v) for v in h[1:]] for h in hs[:k]]
    return dict(p, letters=hits)


def ncc(a, b):
    a, b = a - a.mean(), b - b.mean()
    return float((a * b).sum() / np.sqrt((a * a).sum() * (b * b).sum()))


def stretch_means(rows, templates, n=STRETCHES, per_page=2, cache=None):
    """Mean image of each letter per stretch of the book (the best per_page matches of every
    page in it, resized to the f. 12r examples' size), and its correlation with the f. 12r
    mean and with the mean of all the other stretches."""
    cands = [r for r in rows if r["letters"] and not r.get("short")]
    parts = np.array_split(np.arange(len(cands)), n)
    cache = {} if cache is None else cache
    means, stats = {}, []
    for c, T in templates.items():
        size = (int(np.median([t.shape[1] for t in T])), int(np.median([t.shape[0] for t in T])))
        ref = np.mean([cv2.resize(t, size) for t in T], 0)
        M = []
        for part in parts:
            acc = []
            for i in part:
                r = cands[i]
                if r["page"] not in cache:
                    cache[r["page"]] = darkness(ink.load_rgb(r["path"]))
                for v, x0, y0, x1, y1, _ in (r["letters"].get(c) or [])[:per_page]:
                    acc.append(cv2.resize(cache[r["page"]][y0:y1, x0:x1], size))
            M.append(np.mean(acc, 0))
        means[c] = (ref, M)
        for j, (part, m) in enumerate(zip(parts, M)):
            others = np.mean([M[q] for q in range(n) if q != j], 0)
            stats.append(dict(letter=c, stretch=j, folios=f"{cands[part[0]]['folio']}–{cands[part[-1]]['folio']}",
                              vs_f12r=round(ncc(m, ref), 3), vs_rest=round(ncc(m, others), 3),
                              score=round(float(np.mean([h[0] for i in part for h in
                                                         (cands[i]["letters"].get(c) or [])[:per_page]])), 3)))
    return means, stats


def plot(rows, boxes, templates, d12, path, ncol=10):
    """For each letter: the f. 12r examples' mean (blue frame), the best match on pages
    spread through the book, and the mean of the best matches per stretch of the book."""
    letters = [c for c in LETTERS if c in templates]
    cands = [r for r in rows if r["letters"] and not r.get("short")]
    pick = [cands[int(round(i))] for i in np.linspace(0, len(cands) - 1, ncol)]
    cache = {}
    means, stats = stretch_means(rows, templates, cache=cache)
    S = {(s["letter"], s["stretch"]): s for s in stats}
    fig, axes = plt.subplots(2 * len(letters), 1 + max(ncol, STRETCHES), figsize=(1.0 * (1 + ncol), 1.9 * len(letters)),
                             dpi=170, facecolor=SURFACE)
    for i, c in enumerate(letters):
        ref, M = means[c]
        show(axes[2 * i, 0], ref, f"{LETTERS[c]}: f. 12r\nmean of {len(templates[c])}", True)
        for j, r in enumerate(pick):
            ax = axes[2 * i, j + 1]
            hs = r["letters"].get(c) or []
            if not hs:
                ax.axis("off")
                continue
            v, x0, y0, x1, y1, _ = hs[0]
            if r["page"] not in cache:
                cache[r["page"]] = darkness(ink.load_rgb(r["path"]))
            show(ax, cache[r["page"]][y0:y1, x0:x1], f"f. {r['folio']}  {v:.2f}", False)
        axes[2 * i + 1, 0].axis("off")
        axes[2 * i + 1, 0].text(0, 0.5, "mean per\nstretch,\nr with f. 12r", fontsize=5.5, color=MUTED,
                                 transform=axes[2 * i + 1, 0].transAxes, va="center", fontfamily="FreeSerif")
        for j in range(axes.shape[1] - 1):
            ax = axes[2 * i + 1, j + 1]
            if j >= len(M):
                ax.axis("off")
                continue
            s = S[(c, j)]
            show(ax, M[j], f"ff. {s['folios']}\nr = {s['vs_f12r']:.2f}", False)
    fig.suptitle("The same letters through the book: f. 12r's examples (left), the best match on pages from f. 11r "
                 "to f. 64r, and the mean letter of each stretch of the book", fontsize=8, color=INK_TEXT,
                 x=0.01, ha="left")
    fig.tight_layout(rect=(0, 0, 1, 0.97))
    fig.savefig(path, facecolor=SURFACE)
    plt.close(fig)


def show(ax, img, title, ref):
    ax.imshow(np.clip(img / 60.0, 0, 1), cmap="Greys", vmin=0, vmax=1, interpolation="lanczos")
    ax.set_title(title, fontsize=5, color=INK_TEXT if ref else MUTED, loc="left", pad=1,
                 fontweight="bold" if ref else "normal", fontfamily="FreeSerif")
    ax.set_xticks([]); ax.set_yticks([])
    for s in ax.spines.values():
        s.set_color(DATA if ref else "#d6d4cf"); s.set_linewidth(0.8 if ref else 0.4)


if __name__ == "__main__":
    main(sys.argv[1])
