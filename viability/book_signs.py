"""Abbreviation signs that f. 12r lacks, fitted from the whole of MS 2262.

The book uses signs that f. 12r lacks or has only once or twice: the con sign (ꝯ), the
rum sign (ꝝ), the et sign (ꝫ: one z-shaped sign for several words, read from the letter
before it and the context: qꝫ -que, a vowel + ꝫ a final -m, ſꝫ sed or scilicet, dꝫ
debet, bꝫ -bus), d with a stroke (đ, written by the rubricator in red) and s with a
tilde (s̃; the tilde is a mark, so it can stand over any letter). Their
examples were found by reading every text page (ff. 11r–64v) by eye and recorded in
data/hours_book_signs.jsonl: page, box, word, reading, and a note on anything unusual
in how the sign is written.

Each example's line is found on its page (hands.guides), straightened (slant removed)
and rescaled to f. 12r's x-height, so that examples from any page can be compared with a
stroke plan drawn with f. 12r's pen. The plans are then fitted as the lowercase letters
were (textura.py): one shared plan per sign, examples far below the median set aside as
other forms, and each example's own width and height recorded.

Run:  python3 book_signs.py PDF_PAGE_DIR   → out/hours_book_signs.json, out/hours_book_signs.png,
                                             out/hours_book_signs_all.png (every example),
                                             out/hours_book_abbreviated.png (words written with them)
"""
import json
import sys
import unicodedata
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
import ink
import letterforms as LF

HERE = Path(__file__).resolve().parent
OUT = HERE / "out"
DATA = HERE / "data" / "hours_book_signs.jsonl"
SURFACE, INK_TEXT, MUTED = "#fcfcfb", "#0b0b0b", "#52514e"
CON, RUM, ET, DSTROKE, TILDE = "ꝯ", "ꝝ", "ꝫ", "đ", "\u0303"


def _strokes(path, ch):
    """A fitted letter's strokes from an earlier fit, as plan strokes."""
    F = json.loads((OUT / path).read_text(encoding="utf-8"))[ch]
    return [(s["name"], [tuple(p) for p in s["points"]], s["pen"]) for s in F["strokes"]]


# the scribe's bars are drawn with the quill tilted (quill_tilt.py measures how far)
BAR_TILT = (json.loads((OUT / "hours_tilt.json").read_text(encoding="utf-8"))["summary"]["bar_tilt"]
            if (OUT / "hours_tilt.json").exists() else 1.0)

SIGNS = {
    # ꝯ: a 9: a closed oval bowl at the upper left, a stroke down the right side to the
    # baseline, a hairline running down-left below the line
    CON: dict(zone=(-0.75, 1.3), ties=[((1, 3), (2, 0))], strokes=[
        ("bowl", [(0.55, 0.95), (0.25, 0.9), (0.1, 0.65), (0.2, 0.42), (0.5, 0.45)], None),
        ("stem", [(0.5, 1.0), (0.6, 0.75), (0.58, 0.2), (0.45, 0.02)], None),
        ("hairline tail", [(0.45, 0.02), (0.25, -0.2), (0.1, -0.4)], None)]),
    # ꝝ: the r rotunda written as a z (a short top bar against the o, a diagonal down to
    # the left, a foot along the baseline), crossed by a hairline from its upper right
    # down-left below the line
    RUM: dict(zone=(-0.75, 1.3), ties=[((0, 2), (1, 0)), ((1, 2), (2, 0))], strokes=[
        ("top", [(0.3, 0.95), (0.48, 0.98), (0.66, 0.92)], None),
        ("diagonal", [(0.66, 0.92), (0.46, 0.5), (0.3, 0.1)], None),
        ("foot", [(0.3, 0.1), (0.5, 0.05), (0.7, 0.08)], None),
        ("hairline stroke", [(0.82, 0.72), (0.58, 0.12), (0.36, -0.55)], None)]),
    # ꝫ, the z-shaped sign that stands for -que after q, for a final -m after a vowel, and
    # for sed, -bus, debet ... (SEMI_READINGS): f. 12r's plan (two examples) refitted to
    # every use in the book
    ET: dict(zone=(-0.75, 1.3), ties=[((2, 3), (3, 0))], strokes=_strokes("hours_signs.json", "ꝫ")),
    # đ: the round d (as fitted on f. 12r) with a bar through its ascender, rising a little
    # to the right, drawn with the quill tilted as the scribe draws his bars (quill_tilt.py);
    # the book's examples include the rubricator's red "dd" (David)
    DSTROKE: dict(zone=(-0.25, 1.75), move=0.12, strokes=_strokes("hours_textura.json", "d") + [
        ("crossbar", [(-0.05, 1.16), (0.4, 1.2), (0.85, 1.25)], {"tilt": BAR_TILT})]),
    # the tilde (over s in ut s̃ = ut supra, and in the rubricator's vs̃ = vesperas): two
    # lozenges side by side, each a short down-right stroke of the broad nib (like the
    # points of the colon on f. 12r), joined by a hairline; compared only above the s.
    # Held close to the plan: at this scan the ink mask merges the two lozenges (their
    # waist is a pixel or two), and a free fit collapses them into one
    TILDE: dict(zone=(1.12, 1.85), move=0.05, ties=[((0, 1), (1, 0)), ((1, 1), (2, 0))], strokes=[
        ("left point", [(0.02, 1.47), (0.2, 1.35)], None),
        ("hairline link", [(0.2, 1.35), (0.4, 1.47)], None),
        ("right point", [(0.4, 1.47), (0.6, 1.35)], None)]),
}
MUFI = {CON: ("A76F", "LATIN SMALL LETTER CON"), RUM: ("A75D", "LATIN SMALL LETTER RUM ROTUNDA"),
        ET: ("A76B", "LATIN SMALL LETTER ET (after q: -que; after a vowel: -m)"),
        DSTROKE: ("0111", "LATIN SMALL LETTER D WITH STROKE"), TILDE: ("0303", "COMBINING TILDE (over s: s̃)")}
# One sign, many words: what ꝫ (or its semicolon form) stands for depends on the letter
# before it and on the context. The writer's text step needs the table the other way round
# (word → abbreviated form).
SEMI_READINGS = {"q": ["-que"], "ſ": ["sed", "scilicet"], "d": ["debet"], "b": ["-bus"], "": ["et", "final -m"]}
NAMES = {CON: "con", RUM: "rum", ET: "et sign (-que, -m …)", DSTROKE: "d with stroke", TILDE: "tilde"}
RECORD = {"con": CON, "rum": RUM, "que": ET, "semicolon_other": ET, "d_stroke": DSTROKE, "s_tilde": TILDE}


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
    """(black ink, red ink, lines) of a page, cached. The red is the rubricator's
    (rubrics, and the red d with stroke)."""
    if name not in _PAGES:
        rgb, mask, dark, tb = H.page_ink(Path(pdf_dir) / f"{name}.jpg")
        raw, _ = ink.ink_mask(rgb)
        red = ((raw > 0) & ink.red_mask(rgb, raw)).astype(np.uint8)
        _PAGES[name] = (mask, red, book_lines(pdf_dir)[name]["lines"])
    return _PAGES[name]


def line_of(lines, box):
    """The line whose x-height band [x-line, baseline] the box overlaps most. A line
    written all in red has no guides of its own (they are fitted to the black ink):
    the nearest line is then moved by whole line pitches onto the box."""
    if not lines:
        return None
    x0, y0, x1, y1 = box
    xm = (x0 + x1) / 2

    def overlap(l):
        yb, xh = LF.guide(l, xm)
        return min(y1, yb) - max(y0, yb - xh)
    best = max(lines, key=overlap)
    yb, xh = LF.guide(best, xm)
    if overlap(best) >= 0.4 * xh:
        return best
    bases = sorted(LF.guide(l, xm)[0] for l in lines)
    pitch = float(np.median(np.diff(bases))) if len(bases) > 2 else 2 * xh
    k = round(((y0 + y1) / 2 + 0.3 * xh - yb) / pitch)
    moved = dict(best, baseline=[[x, y + k * pitch] for x, y in best["baseline"]],
                 xline=[[x, y + k * pitch] for x, y in best["xline"]])
    return moved


def straighten(mask, line, span=None):
    """The line's window with the slant removed and rescaled to f. 12r's x-height
    (TX.XH): canvas column u is the baseline position u·s on the page, s = this line's
    x-height / TX.XH. Rows as in align.straighten. span (x0, x1) widens the window to
    take in a box beyond the line's ends (a red line has borrowed guides)."""
    s = line["x_height"] / TX.XH
    (x0, _), (x1, _) = line["baseline"]
    if span is not None:
        x0, x1 = min(x0, span[0]), max(x1, span[1])
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
    mask, red, lines = page(pdf_dir, rec["page"])
    line = line_of(lines, rec["box"])
    if line is None:
        return None
    x0, y0, x1, y1 = rec["box"]
    if RECORD[rec["sign"]] == DSTROKE:           # the first d of the rubricator's "dd" and its stroke
        x1 = min(x1, int(x0 + 1.1 * line["x_height"]))
    in_red = red[y0:y1, x0:x1].sum() > mask[y0:y1, x0:x1].sum()     # written by the rubricator
    img, us, s = straighten(red if in_red else mask, line, span=(x0 - 40, x1 + 40))
    yb, _ = LF.guide(line, (x0 + x1) / 2)
    hc = yb - (y0 + y1) / 2                     # height of the box's middle above the baseline
    t = np.tan(np.radians(line["slant_deg"]))
    f = dict(char=RECORD[rec["sign"]], line=rec["folio"], index=k, word=rec.get("word", ""),
             u0=int(round((x0 - hc * t) / s)), u1=int(round((x1 - hc * t) / s)),
             page=rec["page"], folio=rec["folio"], box=[x0, y0, x1, y1], scale=s, note=rec.get("form_note", ""),
             red=bool(in_red))
    return dict(f=f, img=img, us=us, dx=0, dy=0)


def records(path=DATA):
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


# ---- fitting ---------------------------------------------------------------------------

def fit(pdf_dir, recs, signs=None, verbose=True, env=None):
    TX.PLANS.update(SIGNS)
    env = env or TX.setup()
    fp = env["fp"]
    fits = {}
    for ch in signs or list(SIGNS):
        rs = [r for r in recs if RECORD.get(r["sign"]) == ch and r.get("confidence", "sure") == "sure"]
        exs = [e for e in (example(pdf_dir, r, k) for k, r in enumerate(rs)) if e is not None]
        if not exs:
            continue
        x, per, keep, aside = TX.fit_letter(ch, exs, fp, verbose=verbose)
        # a wider range than f. 12r's letters needed: ꝫ alone runs from 0.75 to 1.4 of its plan
        var = TX.variation(ch, x, keep, fp, su=np.arange(0.62, 1.5, 0.04), sv=np.arange(0.8, 1.21, 0.04))
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
    """Examples that stand out (robust statistics, so a sign with hundreds of examples is
    not judged by its ordinary spread): set aside by the fit (another form); width or
    height more than 2.5 robust spreads (and 0.1) from the sign's median; sitting more
    than 6 px (0.2 x-height) above or below the sign's usual height. Returns
    {id(example): [reasons]}."""
    out = {}
    exs, var = F["exs"], F["var"]
    if len(exs) >= 4:
        for k, name in ((0, "width"), (1, "height")):
            v = var[:, k]
            med = np.median(v)
            lim = max(2.5 * 1.4826 * np.median(np.abs(v - med)), 0.1)
            for e, x in zip(exs, v):
                if abs(x - med) > lim:
                    word = ("wide" if x > med else "narrow") if k == 0 else ("tall" if x > med else "short")
                    out.setdefault(id(e), []).append(f"{word} ×{x:.2f}")
        dys = np.array([e["dy"] for e in exs])
        for e, d in zip(exs, dys):
            if abs(d - np.median(dys)) > 6:
                out.setdefault(id(e), []).append("high" if d - np.median(dys) < 0 else "low")
    for e in F["aside"]:
        out.setdefault(id(e), []).append("another form")
    return out


def plot_gallery(fits, pdf_dir, path, cols=12, cap=48):
    """The examples of each sign as they are on the page (in book order): all of them, or,
    for a sign with more than cap, every outlier and an even sample of the rest; outliers
    framed and labelled."""
    rows = []
    for ch, F in fits.items():
        odd = outliers(F)
        allx = sorted(F["exs"] + F["aside"], key=lambda e: (e["f"]["page"], e["f"]["box"][1], e["f"]["box"][0]))
        if len(allx) > cap:     # every outlier, and the rest sampled evenly through the book
            rest = [e for e in allx if id(e) not in odd]
            keep = {id(e) for e in allx if id(e) in odd}
            keep |= {id(rest[int(i)]) for i in np.linspace(0, len(rest) - 1, max(0, cap - len(keep)))}
            allx = [e for e in allx if id(e) in keep]
        rows.append((ch, allx, odd))
    nrows = sum(int(np.ceil(len(a) / cols)) for _, a, _ in rows)
    fig = plt.figure(figsize=(1.05 * cols, 1.0 * nrows + 0.5 * len(rows)), dpi=150, facecolor=SURFACE)
    gs = fig.add_gridspec(nrows + len(rows), cols, hspace=0.6, top=0.985, bottom=0.01)
    r = 0
    imgs = {}
    for ch, allx, odd in rows:
        ax = fig.add_subplot(gs[r, :])
        ax.axis("off")
        n_all = len(fits[ch]["exs"]) + len(fits[ch]["aside"])
        ax.text(0, 0.1, f"{NAMES[ch]} ({MUFI[ch][0]}): {n_all} examples" + (f" ({len(allx)} shown)" if len(allx) < n_all else "")
                + f", {len(odd)} outliers framed",
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


# ---- spacing next to the signs ---------------------------------------------------------

SPACING = OUT / "hours_book_spacing.json"
SIGN_CHARS = {ET: ";ꝫz3", CON: "ꝯ9", RUM: "ꝝ", DSTROKE: "đ"}


def neighbours(rec, ch):
    """The letters before and after the sign in the reader's spelling of the word ('' at
    the word's edges)."""
    w = [c for c in unicodedata.normalize("NFD", rec.get("word") or "") if not unicodedata.combining(c)]
    idx = [i for i, c in enumerate(w) if c in SIGN_CHARS.get(ch, "")]
    if not idx:
        return "", ""
    i = idx[-1] if ch == ET else idx[0]
    return (w[i - 1] if i > 0 else ""), (w[i + 1] if i + 1 < len(w) else "")


def page_gaps(ch, F, fp):
    """For each example: the white gap (canonical px) between the sign and the ink to its
    left and to its right, in the middle of the x-height band; None where no neighbour
    is found within an x-height, 0 where the sign touches it."""
    m = fp.draw(TX.unpack(TX.PLANS[ch], F["x"]), (TX.H, TX.W), (TX.OX, TX.ROW0)) > 0
    r0, r1 = int(TX.ROW0 - 0.8 * TX.XH), int(TX.ROW0 - 0.2 * TX.XH)
    cols = np.nonzero(m[r0:r1].any(0))[0]
    if not len(cols):
        return []
    L, R = int(cols[0]), int(cols[-1])
    out = []
    for e in F["exs"]:
        p = (TX.crop(e, e["dx"], e["dy"])[r0:r1] > 0).any(0)

        def walk(start, step):
            c, own = start, 0
            while 0 <= c < len(p) and p[c] and own < 0.3 * TX.XH:      # the sign's own ink
                c += step; own += 1
            if own >= 0.3 * TX.XH:
                return 0                                                # joined to its neighbour
            g = 0
            while 0 <= c < len(p) and not p[c] and g <= TX.XH:
                c += step; g += 1
            return g if (0 <= c < len(p) and g <= TX.XH) else None
        out.append((walk(L, -1), walk(R, +1)))
    return out


def writer_edges(w, ch):
    """Left and right edge of a letter or sign as the writer draws it alone at x = 0, in the
    middle of the x-height band (px at TX.XH)."""
    from shapely.geometry import box
    g = w.render(w.write(ch, 0.0, 0.0, TX.XH)).intersection(box(-5 * TX.XH, -0.8 * TX.XH, 5 * TX.XH, -0.2 * TX.XH))
    return (g.bounds[0], g.bounds[2]) if not g.is_empty else None


def spacing(fits, recs, fp, w):
    """Approach (from the letter before) and advance (to the letter after) of each sign, so
    that the writer leaves the gaps measured on the page: with distance = advance[a] +
    approach[b] between left edges, the gap the writer draws is
    xh·(advance[a] + approach[b]) + left edge of b − right edge of a. Medians over the
    examples whose neighbour is a letter the writer knows."""
    sp = w.sp
    out = dict(approach={}, advance={}, n={})
    for ch, F in fits.items():
        if ch == TILDE:
            continue
        app, adv = [], []
        eb = writer_edges(w, ch)
        for e, (gl, gr) in zip(F["exs"], page_gaps(ch, F, fp)):
            prev, nxt = neighbours(dict(word=e["f"]["word"]), ch)
            if gl is not None and prev in sp["advance"] and eb:
                ea = writer_edges(w, prev)
                if ea:
                    app.append((gl + ea[1] - eb[0]) / TX.XH - sp["advance"][prev])
            if gr is not None and nxt in sp["approach"] and eb:
                en = writer_edges(w, nxt)
                if en:
                    adv.append((gr + eb[1] - en[0]) / TX.XH - sp["approach"][nxt])
        if app:
            out["approach"][ch] = round(float(np.median(app)), 3)
        if adv:
            out["advance"][ch] = round(float(np.median(adv)), 3)
        out["n"][ch] = dict(approach=len(app), advance=len(adv))
    SPACING.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    return out


# words written in full and abbreviated with the new signs: the user's examples first
# (from another manuscript: p͛đoꝝ, qqꝫ, ꝯu͛s̃, qꝝ), then forms found in this book
FORMS = [("predicatorum", ["p\u035bđoꝝ"]), ("quoque", ["qqꝫ"]), ("conuersis", ["ꝯu\u035bs\u0303"]),
         ("quorum", ["qꝝ"]), ("noſtrorum", ["noſtroꝝ"]), ("neque", ["neqꝫ"]),
         ("comprehenderunt", ["ꝯpꝛehenderunt"]), ("supra", ["s\u0303"]), ("sed", ["ſꝫ"]), ("debet", ["dꝫ"]),
         ("dei", ["đ"])]


def main(pdf_dir):
    import abbrev
    recs = records()
    env = TX.setup()
    fits, fp = fit(pdf_dir, recs, env=env)
    save(fits, OUT / "hours_book_signs.json")
    import scribe as SC
    found = [f for f in env["found"] if f["char"] not in ("\u0304", "\u035b")]
    minim = json.loads((OUT / "hours_minims.json").read_text(encoding="utf-8"))
    w = SC.Scribe(SC.load_letters(), minim, SC.fit_spacing(SC.pairs(found)), SC.minim_offsets(found), env["slant"])
    print("spacing:", spacing(fits, recs, fp, w))
    plot(fits, fp, OUT / "hours_book_signs.png")
    plot_gallery(fits, pdf_dir, OUT / "hours_book_signs_all.png")
    abbrev.plot_forms(env, OUT / "hours_book_abbreviated.png", forms=FORMS,
                      title="Words in full and abbreviated with the signs fitted from the whole book")
    return fits


if __name__ == "__main__":
    main(sys.argv[1])
