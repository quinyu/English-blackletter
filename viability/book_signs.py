"""Abbreviation signs that f. 12r lacks, fitted from the whole of MS 2262.

The book uses signs that do not occur on f. 12r: the con sign (ꝯ), the rum sign (ꝝ), the
semicolon sign (after q for -que, after ſ for sed), d with a stroke (đ) and s with a
tilde (s̃; the tilde is fitted as a mark, so it can stand over any letter). Their
examples were found by reading every text page (ff. 11r–64v) by eye and recorded in
data/hours_book_signs.jsonl: page, box, word, reading, and a note on anything unusual
in how the sign is written.

Each example's line is found on its page (hands.guides), straightened (slant removed)
and rescaled to f. 12r's x-height, so that examples from any page can be compared with a
stroke plan drawn with f. 12r's pen. The plans are then fitted as the lowercase letters
were (textura.py): one shared plan per sign, examples far below the median set aside as
other forms, and each example's own width and height recorded.

Run:  python3 book_signs.py PDF_PAGE_DIR   → out/hours_book_signs.json, out/hours_book_signs.png,
                                             out/hours_book_signs_all.png (every example)
"""
import json
import sys
from pathlib import Path

import cv2
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

import align as A
A.TOP = 2.05          # marks above the letters (tilde, the bar of đ) reach higher than letters
import textura as TX  # (imported after: its canvas is sized from align.TOP)
import hands as H
import letterforms as LF

HERE = Path(__file__).resolve().parent
OUT = HERE / "out"
DATA = HERE / "data" / "hours_book_signs.jsonl"
SURFACE, INK_TEXT, MUTED = "#fcfcfb", "#0b0b0b", "#52514e"
CON, RUM, SEMI, DSTROKE, TILDE = "ꝯ", "ꝝ", ";", "đ", "\u0303"


def _strokes(path, ch):
    """A fitted letter's strokes from an earlier fit, as plan strokes."""
    F = json.loads((OUT / path).read_text(encoding="utf-8"))[ch]
    return [(s["name"], [tuple(p) for p in s["points"]], s["pen"]) for s in F["strokes"]]


SIGNS = {
    # ꝯ: a 9: a closed oval bowl at the upper left, a stroke down the right side to the
    # baseline, a hairline running down-left below the line
    CON: dict(zone=(-0.75, 1.3), ties=[((1, 3), (2, 0))], strokes=[
        ("bowl", [(0.55, 0.95), (0.25, 0.9), (0.1, 0.65), (0.2, 0.42), (0.5, 0.45)], None),
        ("stem", [(0.5, 1.0), (0.6, 0.75), (0.58, 0.2), (0.45, 0.02)], None),
        ("hairline tail", [(0.45, 0.02), (0.25, -0.2), (0.1, -0.4)], None)]),
    # ꝝ: the r rotunda that leans on the o (strokes as fitted on f. 12r), crossed by a
    # hairline from its upper right down-left below the line
    RUM: dict(zone=(-0.75, 1.3), strokes=_strokes("hours_textura.json", "ꝛ") + [
        ("hairline stroke", [(0.85, 0.7), (0.6, 0.15), (0.38, -0.55)], None)]),
    # the semicolon sign (after q for -que, after ſ for sed): a lozenge point at the
    # x-line, a comma below it with a thick head at mid-height and a hairline tail
    # down-left below the line
    SEMI: dict(zone=(-0.8, 1.15), ties=[((1, 3), (2, 0))], strokes=[
        ("point", [(0.18, 0.95), (0.3, 0.82)], None),
        ("comma", [(0.08, 0.5), (0.22, 0.45), (0.28, 0.22), (0.2, 0.02)], None),
        ("hairline tail", [(0.2, 0.02), (0.08, -0.3), (-0.05, -0.62)], None)]),
}
MUFI = {CON: ("A76F", "LATIN SMALL LETTER CON"), RUM: ("A75D", "LATIN SMALL LETTER RUM ROTUNDA"),
        SEMI: ("F1AC", "LATIN ABBREVIATION SIGN SEMICOLON (q + it for -que, ſ + it for sed)"),
        DSTROKE: ("0111", "LATIN SMALL LETTER D WITH STROKE"), TILDE: ("0303", "COMBINING TILDE (over s: s̃)")}
NAMES = {CON: "con", RUM: "rum", SEMI: "semicolon (que, sed)", DSTROKE: "d with stroke", TILDE: "tilde"}
RECORD = {"con": CON, "rum": RUM, "que": SEMI, "semicolon_other": SEMI, "d_stroke": DSTROKE, "s_tilde": TILDE}


# ---- pages and lines ------------------------------------------------------------------

_PAGES = {}
LINES = OUT / "hours_book_lines.json"


def page_lines(path):
    """Line guides of one page (hands.guides), with a missing slant set to the page's."""
    rgb, mask, dark, tb = H.page_ink(path)
    lines = H.guides(mask, tb) if tb is not None else []
    slants = [l["slant_deg"] for l in lines if l["slant_deg"] is not None and np.isfinite(l["slant_deg"])]
    for l in lines:
        l.pop("g", None)
        if l["slant_deg"] is None or not np.isfinite(l["slant_deg"]):
            l["slant_deg"] = float(np.median(slants)) if slants else 4.6
    return lines


def book_lines(pdf_dir):
    """Line guides of every text page, computed once (4 processes) and kept in
    out/hours_book_lines.json."""
    if LINES.exists():
        return json.loads(LINES.read_text(encoding="utf-8"))
    import multiprocessing
    pages = H.pages(pdf_dir)
    with multiprocessing.get_context("spawn").Pool(4) as pool:
        L = pool.map(page_lines, [p["path"] for p in pages])
    r = lambda v: round(float(v), 2)
    out = {p["page"]: dict(folio=p["folio"], lines=[dict(x0=l["x0"], x1=l["x1"], x_height=r(l["x_height"]),
                                                          slant_deg=r(l["slant_deg"]),
                                                          baseline=[[r(a), r(b)] for a, b in l["baseline"]],
                                                          xline=[[r(a), r(b)] for a, b in l["xline"]]) for l in ls])
           for p, ls in zip(pages, L)}
    LINES.write_text(json.dumps(out, separators=(",", ":")), encoding="utf-8")
    return out


def page(pdf_dir, name):
    """(mask, lines) of a page, cached."""
    if name not in _PAGES:
        rgb, mask, dark, tb = H.page_ink(Path(pdf_dir) / f"{name}.jpg")
        _PAGES[name] = (mask, book_lines(pdf_dir)[name]["lines"])
    return _PAGES[name]


def line_of(lines, box):
    """The line whose x-height band [x-line, baseline] the box overlaps most."""
    x0, y0, x1, y1 = box
    xm = (x0 + x1) / 2

    def overlap(l):
        yb, xh = LF.guide(l, xm)
        return min(y1, yb) - max(y0, yb - xh)
    return max(lines, key=overlap) if lines else None


def straighten(mask, line):
    """The line's window with the slant removed and rescaled to f. 12r's x-height
    (TX.XH): canvas column u is the baseline position u·s on the page, s = this line's
    x-height / TX.XH. Rows as in align.straighten."""
    s = line["x_height"] / TX.XH
    (x0, _), (x1, _) = line["baseline"]
    us = np.arange(int(x0 / s - TX.XH), int(x1 / s + TX.XH))
    t = np.tan(np.radians(line["slant_deg"]))
    U, Hh = np.meshgrid(us, TX.HS)
    yb = np.array([LF.guide(line, u * s)[0] for u in us])[None, :] * np.ones_like(Hh)
    X = (U * s + Hh * s * t).astype(np.float32)
    Y = (yb - Hh * s).astype(np.float32)
    img = cv2.remap(mask.astype(np.float32), X, Y, cv2.INTER_LINEAR, borderValue=0)
    return np.pad((img > 0.5).astype(np.float32), TX.PAD), us, s


def example(pdf_dir, rec, k):
    """A textura.py example from a record: the straightened line and the sign's columns
    (u0, u1) in it."""
    mask, lines = page(pdf_dir, rec["page"])
    line = line_of(lines, rec["box"])
    if line is None:
        return None
    img, us, s = straighten(mask, line)
    x0, y0, x1, y1 = rec["box"]
    yb, _ = LF.guide(line, (x0 + x1) / 2)
    hc = yb - (y0 + y1) / 2                     # height of the box's middle above the baseline
    t = np.tan(np.radians(line["slant_deg"]))
    f = dict(char=RECORD[rec["sign"]], line=rec["folio"], index=k, word=rec.get("word", ""),
             u0=int(round((x0 - hc * t) / s)), u1=int(round((x1 - hc * t) / s)),
             page=rec["page"], folio=rec["folio"], box=rec["box"], scale=s, note=rec.get("form_note", ""))
    return dict(f=f, img=img, us=us, dx=0, dy=0)


def records(path=DATA):
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


# ---- fitting ---------------------------------------------------------------------------

def fit(pdf_dir, recs, signs=None, verbose=True):
    TX.PLANS.update(SIGNS)
    env = TX.setup()
    fp = env["fp"]
    fits = {}
    for ch in signs or list(SIGNS):
        rs = [r for r in recs if RECORD.get(r["sign"]) == ch and r.get("confidence", "sure") == "sure"]
        exs = [e for e in (example(pdf_dir, r, k) for k, r in enumerate(rs)) if e is not None]
        if not exs:
            continue
        x, per, keep, aside = TX.fit_letter(ch, exs, fp, verbose=verbose)
        var = TX.variation(ch, x, keep, fp)
        fits[ch] = dict(x=x, exs=keep, score=per, var=var, aside=aside)
    return fits, fp


def save(fits, path):
    TX.save(fits, path)
    data = json.loads(path.read_text(encoding="utf-8"))
    for ch, d in data.items():
        F = fits[ch]
        d["mufi"] = dict(zip(("code_point", "name"), MUFI[ch]))
        d["examples"] = [dict(folio=e["f"]["folio"], page=e["f"]["page"], box=e["f"]["box"], word=e["f"]["word"],
                              overlap=round(float(p), 3), width=round(float(v[0]), 2), height=round(float(v[1]), 2))
                         for e, p, v in zip(F["exs"], F["score"], F["var"])]
        d["set_aside"] = [dict(folio=e["f"]["folio"], page=e["f"]["page"], box=e["f"]["box"], word=e["f"]["word"])
                          for e in F["aside"]]
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


def plot(fits, fp, path, n=10):
    keys = list(fits)
    fig, axes = plt.subplots(len(keys), n + 1, figsize=(1.0 * (n + 1), 1.4 * len(keys)), dpi=190,
                             facecolor=SURFACE, gridspec_kw=dict(width_ratios=[1.3] + [1] * n), squeeze=False)
    for r, ch in enumerate(keys):
        F = fits[ch]
        TX.draw_letter(axes[r, 0], TX.unpack(TX.PLANS[ch], F["x"]))
        axes[r, 0].set_title(f"{NAMES[ch]}  {MUFI[ch][0]}\n{len(F['exs'])} fitted, overlap {np.mean(F['score']):.2f}",
                             fontsize=6, color=INK_TEXT, loc="left", pad=1)
        order = np.argsort(F["score"])[::-1]
        TX.show_examples(axes[r, 1:], ch, F["x"], [F["exs"][i] for i in order], fp, n=n)
        for ax, i in zip(axes[r, 1:], order[:n]):
            ax.set_title(f"f. {F['exs'][i]['f']['folio']}", fontsize=5.5, color=MUTED, loc="left", pad=1)
    fig.suptitle("Signs from the whole book: one stroke plan per sign fitted to its examples from many pages "
                 "(rescaled to f. 12r's x-height)", fontsize=8, color=INK_TEXT, x=0.01, ha="left")
    fig.tight_layout(rect=(0, 0, 1, 0.97))
    fig.savefig(path, facecolor=SURFACE)
    plt.close(fig)


def outliers(F):
    """Examples that stand out: set aside by the fit (another form); width or height
    more than two spreads from the sign's median; sitting more than 4 px (0.14 x-height)
    off the sign's usual height. Returns {id(example): [reasons]}."""
    out = {}
    exs, var = F["exs"], F["var"]
    if len(exs) >= 4:
        for k, name in ((0, "width"), (1, "height")):
            v = var[:, k]
            med, sd = np.median(v), max(np.std(v), 0.03)
            for e, x in zip(exs, v):
                if abs(x - med) > 2 * sd:
                    out.setdefault(id(e), []).append(f"{'wide' if x > med and k == 0 else 'narrow' if k == 0 else 'tall' if x > med else 'short'} ×{x:.2f}")
        dys = np.array([e["dy"] for e in exs])
        for e, d in zip(exs, dys):
            if abs(d - np.median(dys)) > 4:
                out.setdefault(id(e), []).append("high" if d - np.median(dys) < 0 else "low")
    for e in F["aside"]:
        out.setdefault(id(e), []).append("another form")
    return out


def plot_gallery(fits, pdf_dir, path, cols=12):
    """Every example of each sign as it is on the page (its word), in book order;
    outliers framed and labelled."""
    rows = []
    for ch, F in fits.items():
        odd = outliers(F)
        allx = sorted(F["exs"] + F["aside"], key=lambda e: (e["f"]["page"], e["f"]["box"][1], e["f"]["box"][0]))
        rows.append((ch, allx, odd))
    nrows = sum(int(np.ceil(len(a) / cols)) for _, a, _ in rows)
    fig = plt.figure(figsize=(1.05 * cols, 1.0 * nrows + 0.5 * len(rows)), dpi=170, facecolor=SURFACE)
    gs = fig.add_gridspec(nrows + len(rows), cols, hspace=0.6)
    r = 0
    imgs = {}
    for ch, allx, odd in rows:
        ax = fig.add_subplot(gs[r, :])
        ax.axis("off")
        ax.text(0, 0.1, f"{NAMES[ch]} ({MUFI[ch][0]}): {len(allx)} examples, {len(odd)} outliers framed",
                fontsize=7.5, color=INK_TEXT, transform=ax.transAxes)
        r += 1
        for i, e in enumerate(allx):
            ax = fig.add_subplot(gs[r + i // cols, i % cols])
            p = e["f"]["page"]
            if p not in imgs:
                imgs[p] = cv2.cvtColor(cv2.imread(str(Path(pdf_dir) / f"{p}.jpg")), cv2.COLOR_BGR2RGB)
            x0, y0, x1, y1 = e["f"]["box"]
            s = e["f"]["scale"] * TX.XH
            cx = (x0 + x1) / 2
            crop = imgs[p][int(y0 - 0.45 * s):int(y1 + 0.35 * s), int(cx - 1.1 * s):int(cx + 1.1 * s)]
            ax.imshow(crop, interpolation="lanczos")
            why = odd.get(id(e))
            ax.set_title(f"f. {e['f']['folio']}" + (f"\n{', '.join(why)}" if why else ""), fontsize=4.8,
                         color="#c2410c" if why else MUTED, loc="left", pad=1)
            ax.set_xticks([]); ax.set_yticks([])
            for sp in ax.spines.values():
                sp.set_color("#eb6834" if why else "#d6d4cf"); sp.set_linewidth(1.4 if why else 0.4)
        r += int(np.ceil(len(allx) / cols))
    fig.suptitle("Every example found in the book, as written (in book order); framed: outliers in form, size "
                 "or position", fontsize=8, color=INK_TEXT, x=0.01, ha="left")
    fig.savefig(path, facecolor=SURFACE, bbox_inches="tight")
    plt.close(fig)


def main(pdf_dir):
    recs = records()
    fits, fp = fit(pdf_dir, recs)
    save(fits, OUT / "hours_book_signs.json")
    plot(fits, fp, OUT / "hours_book_signs.png")
    plot_gallery(fits, pdf_dir, OUT / "hours_book_signs_all.png")
    return fits


if __name__ == "__main__":
    main(sys.argv[1])
