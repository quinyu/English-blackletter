"""Accents for any letter of the hand: anchors on the letters, marks in the scribe's
manner, and the scribe's own placement, as OpenType's mark positioning does it.

Accented letters are the largest group of MUFI characters still missing: about 270 are
one of twenty base letters with one of some thirty marks, singly or stacked two or three
high (Old Norse/Icelandic: á é í ó ú, ǫ, ǿ, ǭ, ǫ́ …; Latin: ę; the vernaculars: â, ü, ŏ …).
A font draws each mark once and puts it on any letter by anchors: a point on the base
(top, bottom …) and a point on the mark (_top, _bottom …) are made to coincide, and a
mark's own top or bottom carries the next mark (mark-to-mark). The same is built here
from the hand itself:

  base anchors  every letter the writer has is drawn alone with the hand's pen, and its
                anchors are read off the ink:
                  top        the middle of the letter's body at its top; on b d h l ſ f,
                             the top of the ascender (t's short one counts as its body)
                  bottom     the middle of the body's foot (hairline tails aside); on
                             g p q ſ f, the descender's end
                  ogonek     the right foot, where a tail hangs (ę, ǫ)
                  middle     the middle of the body (ø, ʉ, ɨ: strokes through the body)
                  bar        through the ascender a little above the x-height, where the
                             scribe crosses his đ
                  cross      across the ascender near its top, where he bars l for -or-
                             (gl̄ia) and h, b for their abbreviations
                  desc       through the descender (ꝑ, ꝗ)
                  top_right  above the right shoulder (comma above right, slashes)
                  high       above the ascender line whatever the letter (MUFI's "high
                             position" and "high macron" marks)
  placement     measured in the book: where the marks the read pages carry (macrons,
                er curls) sit over their letters. They are centred on the body, a little
                to the right (more over r, p, n), their foot a small gap above the
                letter's top; the medians place the marks (a letter's own drift where it
                carries ten or more), the spreads vary them.
  marks         made from what the scribe already does with his pen: the point (his
                colon's), the bar (his macron), the curl (his er sign), short strokes of
                the edge (acute, circumflex, caron) and the hairline (the pen's corner:
                the tilde's link, the er tail, đ's stroke). The fitted marks (macron,
                tilde, er curl) keep their fitted strokes; a bar through a letter is
                đ's fitted hairline.
  stacking      a mark's own top (or bottom) carries the next mark, at a smaller gap.
                MUFI's precomposed characters, Unicode or Private Use Area, are taken
                apart into a base and its marks, from their decomposition or their name.

Run:  python3 anchors.py [PDF_PAGE_DIR]   → out/hours_anchors.json, out/hours_marks.png,
      out/hours_marks_mufi.png, out/hours_marks_words.png
      (given the page images, the placement is measured again: out/hours_mark_placement.json)
"""
import json
import re
import sys
import unicodedata
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

import align as A
import minims as M
import scribe as SC
import textura as TX

HERE = Path(__file__).resolve().parent
OUT = HERE / "out"
XH = A.XH
U0, U1, V0, V1 = -1.0, 2.6, -1.2, 2.8          # the drawing canvas, in x-heights
SURFACE, INK_TEXT, MUTED = "#fcfcfb", "#0b0b0b", "#52514e"
ABOVE = ("top", "top_right", "high", "cross")   # anchors marks sit on (from above)
BELOW = ("bottom",)                              # anchors marks hang from
ASCENDER = 1.45                                  # a letter rising above this has an ascender (t does not)
ASCENDER_LINE = 1.64                             # the hand's ascender height (hours_lines.json: 1.636 x-heights)
MIN_LETTER = 10                                  # a letter's own drift is used from this many measured marks
STACK_GAP = 0.6                                  # gap between stacked marks, as a fraction of the gap above a letter

# ---- the marks ------------------------------------------------------------------------
# Strokes in x-heights, (name, points[, pen]) drawn with the hand's pen. The pen is the
# flat quill unless a stroke says otherwise: {"tilt": t} draws it with the quill tilted
# (pen.tilt_breadth: the contact keeps the quill's thickness and loses breadth), held at
# t or, as keyframes [[f, t], ...] by fraction of the stroke, tilting as it goes. Thin
# strokes are made that way, as the scribe makes his bars (quill_tilt.py), not with a
# corner of the pen. The origin is free: each mark's own anchors are read off its ink.
#   attach   the base anchor it goes to
#   src      "fitted": the fitted strokes of that mark; a mark: its strokes; a letter: its
#            strokes ("đ": its tilted crossbar)
#   cross    over an ascender, cross it as the scribe crosses l, h, b (bar marks only)

POINT = (0.07, -0.103)  # a point: the scribe's colon point (0.117, -0.171: the nib drawn down to the right), at 0.6 size
TILTED = {"tilt": 1.0}  # the quill tilted as far as it goes: as broad as it is thick
BAR = {"tilt": (json.loads((OUT / "hours_tilt.json").read_text(encoding="utf-8"))["summary"]["bar_tilt"]
                if (OUT / "hours_tilt.json").exists() else 1.0)}   # the scribe's bars (quill_tilt.py)
SQUEEZED = {"tilt": [[0.0, 0.0], [0.22, 1.0], [1.0, 1.0]]}   # a tail: begun flat, then suddenly tilted


def point(u, v, k=1.0):
    return ("point", [(u, v), (u + POINT[0] * k, v + POINT[1] * k)])


def thin(*pts, pen=TILTED):
    return ("thin", list(pts), pen)


def acute(u=0.0):
    """A short steep stroke up to the right: with this nib (edge at 33°) the flat quill
    makes a slim wedge, the weight of the letters' thin parts."""
    return [("acute", [(u - 0.03, 0.0), (u + 0.05, 0.14)])]


def grave(u=0.0):
    """Drawn down to the right the flat quill makes a heavy lozenge (a point), and its
    whole breadth would stand across the start of the stroke. The grave is drawn with
    the quill tilted, a little less at its head, so that it is a slim wedge."""
    return [("grave", [(u - 0.11, 0.27), (u - 0.06, 0.2), (u + 0.08, 0.0)], {"tilt": [[0.0, 0.7], [0.35, 1.0], [1.0, 1.0]]})]


def zigzag(v0, h=0.16):
    return [("zigzag", [(-0.22, v0), (-0.02, v0 + h), (0.02, v0), (0.22, v0 + h)])]


RING = [thin((0.0, 0.34), (-0.17, 0.17), (0.0, 0.0), (0.17, 0.17), (0.0, 0.34))]
MARKS = {
    # fitted in the book (abbrev.py, book_signs.py)
    "\u0304": dict(name="macron", attach="top", cross=True, src="fitted"),
    "\u0303": dict(name="tilde", attach="top", src="fitted"),
    "\u035B": dict(name="er curl", attach="top", src="fitted"),
    "\uF1C8": dict(name="zigzag above, curly form (the er curl)", attach="top", src="\u035B"),
    "\u0335": dict(name="stroke (đ's crossbar)", attach="middle", src="đ"),
    # bars: the macron's stroke
    "\u0305": dict(name="overline", attach="top", cross=True, src="\u0304", stretch=1.4),
    "\uF00B": dict(name="medium-high macron, fixed height", attach="top", cross=True, src="\u0304"),
    "\uF00D": dict(name="medium-high overline, fixed height", attach="top", cross=True, src="\u0304", stretch=1.4),
    "\uF00A": dict(name="high macron, fixed height", attach="high", src="\u0304"),
    "\uF00C": dict(name="high overline, fixed height", attach="high", src="\u0304", stretch=1.4),
    "\u033F": dict(name="double overline", attach="top", cross=True, parts=[("\u0305", 0.0, 0.0), ("\u0305", 0.0, 0.3)]),
    "\uF1C0": dict(name="bar above with dot", attach="top", cross=True, parts=[("\u0304", 0.0, 0.0), ("\u0307", 0.0, 0.3)]),
    "\u0331": dict(name="macron below", attach="bottom", src="\u0304"),
    "\u0332": dict(name="low line", attach="bottom", src="\u0304", stretch=1.4),
    "\u0333": dict(name="double low line", attach="bottom", parts=[("\u0332", 0.0, 0.0), ("\u0332", 0.0, -0.3)]),
    # points: the colon's point
    "\u0307": dict(name="dot above", attach="top", strokes=[point(0.0, 0.0)]),
    "\uF1CA": dict(name="dot above, high position", attach="high", strokes=[point(0.0, 0.0)]),
    "\u0308": dict(name="diaeresis", attach="top", strokes=[point(-0.27, 0.0), point(0.2, 0.0)]),
    "diagonal diaeresis": dict(name="diagonal diaeresis", attach="top", strokes=[point(-0.2, 0.0), point(0.12, 0.24)]),
    "\u0323": dict(name="dot below", attach="bottom", strokes=[point(0.0, 0.0)]),
    "\u0324": dict(name="diaeresis below", attach="bottom", strokes=[point(-0.27, 0.0), point(0.2, 0.0)]),
    # strokes of the flat quill
    "\u0301": dict(name="acute", attach="top", strokes=acute()),
    "\u030B": dict(name="double acute", attach="top", strokes=acute(-0.13) + acute(0.13)),
    "\u0302": dict(name="circumflex", attach="top", strokes=[("circumflex", [(-0.2, 0.0), (0.0, 0.18), (0.2, 0.0)])]),
    "\u1DCD": dict(name="double circumflex above", attach="top", strokes=[("circumflex", [(-0.5, 0.0), (0.0, 0.2), (0.5, 0.0)])]),
    "\u030C": dict(name="caron", attach="top", strokes=[("caron", [(-0.2, 0.18), (0.0, 0.0), (0.2, 0.18)])]),
    "\uF1C7": dict(name="zigzag above, angle form", attach="top", strokes=zigzag(0.0)),
    "\u1DCF": dict(name="zigzag below", attach="bottom", strokes=zigzag(0.0)),
    # curls: the er curl
    "\u0309": dict(name="hook above (MUFI: curl)", attach="top", src="\u035B", scale=0.75),
    "\uF1C5": dict(name="curl, high position", attach="high", src="\u035B", scale=0.75),
    "\u0315": dict(name="comma above right", attach="top_right", src=",", scale=0.4),
    # begun flat, then tilted: the grave, and the tails that grow from the letter's foot
    # (the e caudata's: the quill keeps its thickness, its contact is suddenly squeezed)
    "\u0300": dict(name="grave", attach="top", strokes=grave()),
    "\u0328": dict(name="ogonek", attach="ogonek", own="start",
                   strokes=[("tail", [(0.0, 0.02), (-0.08, -0.12), (-0.08, -0.27), (0.02, -0.36), (0.14, -0.33)], SQUEEZED)]),
    "\u0327": dict(name="cedilla", attach="bottom", own="start",
                   strokes=[("tail", [(0.0, 0.02), (0.03, -0.1), (0.15, -0.18), (0.09, -0.31), (-0.09, -0.34)], SQUEEZED)]),
    # the quill tilted throughout: thin strokes of the quill's own thickness
    "\u0306": dict(name="breve", attach="top", strokes=[thin((-0.22, 0.26), (-0.15, 0.06), (0.0, 0.0), (0.15, 0.06), (0.22, 0.26))]),
    "\u030A": dict(name="ring above", attach="top", strokes=RING),
    "\u030D": dict(name="vertical line above", attach="top", strokes=[thin((0.0, 0.0), (0.02, 0.3))]),
    "\u030E": dict(name="double vertical line above", attach="top", strokes=[thin((-0.1, 0.0), (-0.08, 0.3)), thin((0.1, 0.0), (0.12, 0.3))]),
    "\u033E": dict(name="vertical tilde", attach="top", strokes=[thin((0.02, 0.0), (-0.06, 0.11), (0.06, 0.22), (-0.02, 0.34))]),
    "\uF1CC": dict(name="curly bar above", attach="top", strokes=[thin((-0.27, 0.04), (-0.06, 0.14), (0.12, 0.04), (0.3, 0.15))]),
    "\u1DCE": dict(name="ogonek above", attach="top", strokes=[thin((0.0, 0.0), (-0.11, 0.1), (-0.07, 0.25), (0.07, 0.32))]),
    "\u0325": dict(name="ring below", attach="bottom", strokes=RING),
    "\u032F": dict(name="inverted breve below", attach="bottom", strokes=[thin((-0.22, 0.0), (-0.15, 0.2), (0.0, 0.26), (0.15, 0.2), (0.22, 0.0))]),
    "\u035C": dict(name="double breve below", attach="bottom", strokes=[thin((-0.55, 0.22), (-0.36, 0.03), (0.36, 0.03), (0.55, 0.22))]),
    "\u0359": dict(name="asterisk below", attach="bottom", strokes=[thin((0.0, 0.0), (0.0, 0.32)), thin((-0.14, 0.08), (0.14, 0.24)),
                                                                    thin((-0.14, 0.24), (0.14, 0.08))]),
    # bars and slashes: tilted as the scribe tilts for his bars
    "\u0337": dict(name="short slash", attach="middle", strokes=[thin((-0.2, -0.18), (0.2, 0.22), pen=BAR)]),
    "\u0338": dict(name="long slash", attach="middle", strokes=[thin((-0.36, -0.42), (0.38, 0.5), pen=BAR)]),
    "\u0336": dict(name="long stroke", attach="middle", strokes=[thin((-0.42, 0.0), (0.44, 0.03), pen=BAR)]),
    # the scribe's per: his p has a short stem whose foot turns left, and the bar is a
    # slanting stroke from below the line up to the right under the bowl, across the
    # stem's foot (data/hours_book_signs.jsonl, "per"); placed from the letter's middle
    "per stroke": dict(name="per stroke (the scribe's ꝑ)", attach="middle", own="origin",
                       strokes=[thin((-0.68, -0.8), (-0.28, -0.67), (0.14, -0.53), pen=BAR)]),
}


def mark_strokes(mk, letters):
    """The mark's strokes (name, points, pen) in x-heights, from its plan, a fitted mark,
    or a fitted letter's stroke ("đ": its crossbar)."""
    m = MARKS[mk]
    src = m.get("src")
    if "parts" in m:              # marks made of other marks: each part's middle set (du, dv) from the first's
        st, c0 = [], None
        for part, du, dv in m["parts"]:
            ps = mark_strokes(part, letters)
            c = np.mean([q for _, pts, _ in ps for q in pts], axis=0)
            c0 = c if c0 is None else c0
            st += [(n, [(u - c[0] + c0[0] + du, v - c[1] + c0[1] + dv) for u, v in pts], k) for n, pts, k in ps]
        return st

    def own(s_):
        return s_["pen"] if isinstance(s_.get("pen"), dict) else None
    if src is None:
        st = [(x[0], [tuple(p) for p in x[1]], x[2] if len(x) > 2 else None) for x in m["strokes"]]
    elif src == "fitted":
        st = [(s_["name"], [tuple(p) for p in s_["points"]], own(s_)) for s_ in letters[mk]["strokes"]]
    elif src == "đ":
        st = [(s_["name"], [tuple(p) for p in s_["points"]], own(s_)) for s_ in letters["đ"]["strokes"][-1:]]
    elif src in MARKS:
        st = mark_strokes(src, letters)
    else:
        st = [(s_["name"], [tuple(p) for p in s_["points"]], own(s_)) for s_ in letters[src]["strokes"]]
    k, f = m.get("scale", 1.0), m.get("stretch", 1.0)
    if k != 1.0 or f != 1.0:
        c = np.mean([p for _, pts, _ in st for p in pts], axis=0)
        st = [(n, [(c[0] + (u - c[0]) * k * f, c[1] + (v - c[1]) * k) for u, v in pts], kd) for n, pts, kd in st]
    return st


# ---- drawing and reading anchors off the ink -------------------------------------------

def writer(slant=0.0, anchors=None):
    """The hand's writer (f. 12r's letters with the book's letters, signs and biting; spaced
    by the white between letters where lines.py has measured it)."""
    found = [f for f in json.loads((HERE / "data" / "hours_letters_found.json").read_text(encoding="utf-8"))["letters"]
             if not f.get("skipped")]
    minim = json.loads((OUT / "hours_minims.json").read_text(encoding="utf-8"))
    return SC.Scribe(SC.load_letters(), minim, SC.load_ink_spacing(SC.with_book_spacing(SC.fit_spacing(SC.pairs(found)))),
                     SC.minim_offsets(found), slant, biting=SC.load_biting(), anchors=anchors)


def draw(strokes, fp):
    """Binary canvas (V1 … V0 top to bottom, U0 … U1 left to right) of strokes in x-heights."""
    shape = (int(round((V1 - V0) * XH)), int(round((U1 - U0) * XH)))
    kinds = [k if isinstance(k, dict) and "tilt" in k else ("terminal" if k is not None else None) for _, _, k in strokes]
    return fp.draw([(n, p, k) for (n, p, _), k in zip(strokes, kinds)], shape, (-U0 * XH, V1 * XH))


def grid(shape):
    return V1 - (np.arange(shape[0]) + 0.5) / XH, U0 + (np.arange(shape[1]) + 0.5) / XH


def letter_strokes(w, ch):
    """Letter ch as the writer draws it inside a word (no word-final tail), without
    variation, in x-heights from its box's left edge."""
    st = w.write(ch + "c", 0.0, 0.0, XH)[:-len(w.L["c"]["strokes"])]
    return [(n, [(x / XH, -y / XH) for x, y in pts], k) for n, pts, k in st]


def anchors_of(w, ch, fp):
    st = letter_strokes(w, ch)
    return read_anchors(draw(st, fp), draw([s_ for s_ in st if not s_[0].startswith("hairline")], fp))


def read_anchors(m, bare=None):
    """Anchors of a drawn letter (u, v in x-heights). bare: the letter drawn without its
    hairlines (h's tail, e's closing stroke), for the foot: a dot below goes under the
    letter, not under a flourish."""
    vs, us = grid(m.shape)
    on = m > 0
    foot_on = (bare if bare is not None else m) > 0

    def cols(lo, hi, c0=None, c1=None, ink=on):
        rows = (vs >= lo) & (vs <= hi)
        c = np.nonzero(ink[rows].any(0))[0]
        if c0 is not None:
            c = c[(us[c] >= c0) & (us[c] <= c1)]
        return c

    def mid(c):
        return float((us[c[0]] + us[c[-1]]) / 2)

    def top_of(ink, c0, c1, below=V1):
        r = np.nonzero(ink[:, c0:c1 + 1].any(1) & (vs <= below))[0]
        return float(vs[r[0]])

    def low_of(ink, c0, c1):
        r = np.nonzero(ink[:, c0:c1 + 1].any(1))[0]
        return float(vs[r[-1]])

    body = cols(0.25, 0.95)
    if not len(body):
        body = cols(V0, V1)
    ub, b0, b1 = mid(body), us[body[0]], us[body[-1]]
    xtop = top_of(on, body[0], body[-1], below=1.3)          # the body's top (x-height)
    vtop = top_of(on, 0, on.shape[1] - 1)
    out = dict(middle=[ub, 0.5], xtop=[ub, xtop], body=[float(b0), float(b1)])
    if vtop > ASCENDER:
        out["top"] = [mid(cols(vtop - 0.3, vtop)), vtop]
        for name, v in (("bar", 1.2), ("cross", vtop - 0.28)):
            c = cols(v - 0.04, v + 0.04, b0 - 0.3, b1 + 0.3)
            if len(c):
                out[name] = [mid(c), v]
    else:
        out["top"] = [ub, top_of(on, body[0], body[-1])]
    vlow = low_of(foot_on, 0, on.shape[1] - 1)
    if vlow < -0.25:
        out["bottom"] = [mid(cols(vlow, vlow + 0.25, ink=foot_on)), vlow]
        c = cols(-0.42, -0.34, ink=foot_on)
        if len(c):
            out["desc"] = [mid(c), -0.38]
    else:
        out["bottom"] = [ub, vlow]
    # the ogonek hangs where the letter leaves the baseline on the right: the rightmost
    # column whose lowest ink is on the baseline
    lows = np.array([low_of(foot_on, c, c) if foot_on[:, c].any() else np.inf for c in range(on.shape[1])])
    sit = np.nonzero(np.abs(lows) <= 0.12)[0]
    sit = sit[(us[sit] >= b0) & (us[sit] <= b1)] if len(sit) else sit
    if len(sit):
        out["ogonek"] = [float(us[sit[-1]]) - 0.06, float(lows[sit[-1]])]
    else:
        out["ogonek"] = [b1 - 0.15, 0.0]
    rt = cols(0.7, 1.05)
    out["top_right"] = [float(us[rt[-1]]) if len(rt) else b1, xtop]
    out["high"] = [out["top"][0], max(out["top"][1], ASCENDER_LINE)]
    return {k: [round(float(a), 3), round(float(b), 3)] for k, (a, b) in out.items()}


def mark_anchors(st, attach, own, fp):
    """A mark's own anchors: the point that goes on the base's anchor (_), and the point
    that carries the next mark (next): bottom and top middle of its ink for a mark above,
    top and bottom for one below; the middle for one through the letter; the stroke's
    first point for a tail that grows from the letter (ogonek, cedilla)."""
    m = draw(st, fp)
    vs, us = grid(m.shape)
    r = np.nonzero(m.any(1))[0]
    c = np.nonzero(m.any(0))[0]
    uc, top, low = float((us[c[0]] + us[c[-1]]) / 2), float(vs[r[0]]), float(vs[r[-1]])
    if own == "start":
        p = st[0][1][0]
        a, nxt = [p[0], p[1]], [uc, low]
    elif own == "origin":                 # drawn from the anchor itself
        a, nxt = [0.0, 0.0], [uc, top]
    elif attach in ABOVE:
        a, nxt = [uc, low], [uc, top]
    elif attach in BELOW:
        a, nxt = [uc, top], [uc, low]
    else:
        a, nxt = [uc, (top + low) / 2], [uc, top]
    return dict(_=[round(a[0], 3), round(a[1], 3)], next=[round(nxt[0], 3), round(nxt[1], 3)],
                centre=[round(uc, 3), round((top + low) / 2, 3)],
                width=round(float(us[c[-1]] - us[c[0]]), 3), height=round(top - low, 3))


# ---- where the scribe puts his marks (measured) ----------------------------------------

def measure_placement(pdf_dir, letter_anchors):
    """Marks over letters on the pages read for the biting study (data/hours_readings.json,
    with their found letters): each mark is the ink component nearest the letter's middle
    lying wholly in the band above the x-height (below the line above's descenders).
    Returns the offsets of its middle from the letter's top anchor (scaled to the box's
    width) and of its foot from the letter's top."""
    import cv2
    import find_letters as FL
    import hands as H
    found = json.loads((HERE / "data" / "hours_pages_found.json").read_text(encoding="utf-8"))
    R = json.loads((HERE / "data" / "hours_readings.json").read_text(encoding="utf-8"))
    L = json.loads((OUT / "hours_book_lines.json").read_text(encoding="utf-8"))
    width = {}
    for d in found.values():
        for f in d["letters"]:
            width.setdefault(f["char"], []).append(f["u1"] - f["u0"])
    top0 = A.TOP
    A.TOP = 2.3          # room for the marks
    rows = []
    try:
        for page, d in found.items():
            mask = H.page_ink(Path(pdf_dir) / f"{page}.jpg")[1]
            m = FL.match_lines(R[page]["lines"], L[page]["lines"])
            text = {l["n"]: l["diplomatic"] for l in R[page]["lines"]}
            by = {}
            for f in d["letters"]:
                by.setdefault(f["line"], []).append(f)
            for n, F in by.items():
                if not any(f["flags"] for f in F):
                    continue
                toks = clusters_of(text[n])
                img, us = FL.straighten(mask, m[n])
                hs = np.arange(-A.BOTTOM * A.XH, A.TOP * A.XH)[::-1] / A.XH
                k, lab, st, _ = cv2.connectedComponentsWithStats(img.astype(np.uint8), connectivity=8)
                for f in F:
                    if not f["flags"] or f["char"] not in letter_anchors:
                        continue
                    ch, mks = toks[f["index"]]
                    a, b = f["u0"] - us[0], f["u1"] - us[0]
                    best = None
                    for c in range(1, k):
                        x, y, w_, h_, area = st[c]
                        vb, vt = hs[y + h_ - 1], hs[y]
                        if vb < 1.0 or vb > 1.75 or vt > 2.15 or area < 6 or x + w_ < a - 12 or x > b + 12:
                            continue
                        dist = abs(x + w_ / 2 - (a + b) / 2)
                        if best is None or dist < best[0]:
                            best = (dist, x, w_, vb, vt)
                    if best is None:
                        continue
                    _, x, w_, vb, vt = best
                    an = letter_anchors[ch]
                    s = (f["u1"] - f["u0"]) / np.median(width[ch])
                    rows.append(dict(page=page, line=n, index=f["index"], char=ch, mark=mks[0],
                                     du=float((x + w_ / 2 - a) / XH - an["top"][0] * s),
                                     gap=float(vb - an["xtop"][1]), bottom=float(vb), top=float(vt),
                                     width=float(w_ / XH), tall=an["top"][1] > 1.2))
    finally:
        A.TOP = top0
    return rows


def clusters_of(diplomatic):
    """Written letters of a reading line with the marks each carries."""
    out = []
    for part in re.split(r"(\[[^\]]*\])", diplomatic):
        if part.startswith("["):
            continue
        for ch in unicodedata.normalize("NFD", part):
            if ch == " ":
                continue
            if unicodedata.combining(ch) and out:
                out[-1][1].append(ch)
            else:
                out.append((ch, []))
    return out


def robust(v):
    v = np.asarray(v, float)
    med = float(np.median(v))
    return med, float(1.4826 * np.median(np.abs(v - med)))


def placement(rows):
    """The writer's placement from the measured marks over x-height letters (t's tip and
    the ascenders, which the scribe's bars cross, are left out): horizontal drift and gap, median and robust spread. The
    drift's spread is taken over the minim letters (i, n, m, u), whose boxes the finder
    holds to their stems; over other letters it also carries the boxes' uncertainty."""
    xr = [r for r in rows if not r["tall"]]
    mi = [r for r in xr if r["char"] in "inmu"]
    du, du_sd = robust([r["du"] for r in xr])
    _, du_sd_minim = robust([r["du"] for r in mi])
    gap, gap_sd = robust([r["gap"] for r in xr])
    by = {}
    for r in xr:
        by.setdefault(r["char"], []).append(r)
    return dict(n=len(xr), n_minim=len(mi), drift=round(du, 3), drift_sd=round(du_sd_minim, 3),
                drift_sd_all=round(du_sd, 3), gap=round(gap, 3), gap_sd=round(gap_sd, 3),
                stack_gap=round(STACK_GAP * gap, 3),
                bottom=round(robust([r["bottom"] for r in xr])[0], 3),
                by_mark={f"{ord(mk):04X}": dict(n=sum(r["mark"] == mk for r in xr),
                                                drift=round(robust([r["du"] for r in xr if r["mark"] == mk])[0], 3),
                                                gap=round(robust([r["gap"] for r in xr if r["mark"] == mk])[0], 3))
                         for mk in sorted({r["mark"] for r in xr})},
                by_letter={ch: dict(n=len(v), drift=round(robust([r["du"] for r in v])[0], 3),
                                    gap=round(robust([r["gap"] for r in v])[0], 3))
                           for ch, v in sorted(by.items(), key=lambda kv: -len(kv[1])) if len(v) >= 3})


# ---- MUFI: precomposed characters into base + marks ------------------------------------

NAMED = [   # MUFI name phrase → (mark, anchor or None for the mark's own); longest first
    ("MEDIUM-HIGH OVERLINE (ACROSS ASCENDER)", "\u0305", "cross"),
    ("HIGH MACRON (ABOVE CHARACTER)", "\u0304", "top"), ("HIGH OVERLINE (ABOVE CHARACTER)", "\u0305", "top"),
    ("MEDIUM-HIGH MACRON (ABOVE CHARACTER)", "\u0304", "top"),
    ("MEDIUM-HIGH OVERLINE (ABOVE CHARACTER)", "\u0305", "top"),
    ("STROKE THROUGH DESCENDER", "\u0335", "desc"), ("HIGH STROKE", "\u0335", "cross"),
    ("CENTRAL SLANTED STROKE", "\u0337", None), ("DIAGONAL STROKE", "\u0338", None),
    ("TWO SHORT SLASHES ABOVE RIGHT", ["\u0315", "\u0315"], "top_right"), ("SHORT SLASH ABOVE RIGHT", "\u0315", "top_right"),
    ("SHORT SLASH", "\u0337", None), ("TWO STROKES", ["\u0335", "\u0335"], None),
    ("DIAGONAL DIAERESIS", "diagonal diaeresis", None), ("CURLY BAR ABOVE", "\uF1CC", None),
    ("INVERTED BREVE BELOW", "\u032F", None), ("VERTICAL LINE ABOVE", "\u030D", None),
    ("DOUBLE ACUTE", "\u030B", None), ("DOT ABOVE", "\u0307", None), ("DOT BELOW", "\u0323", None),
    ("RING ABOVE", "\u030A", None), ("RING BELOW", "\u0325", None), ("HOOK ABOVE", "\u0309", None),
    ("CURL", "\u0309", None), ("ACUTE", "\u0301", None), ("GRAVE", "\u0300", None),
    ("CIRCUMFLEX", "\u0302", None), ("CARON", "\u030C", None), ("BREVE", "\u0306", None),
    ("DIAERESIS", "\u0308", None), ("MACRON", "\u0304", None), ("TILDE", "\u0303", None),
    ("OGONEK", "\u0328", None), ("CEDILLA", "\u0327", None), ("BAR", "\u0335", None), ("STROKE", "\u0335", None),
]
SLASHED = {"o": "\u0338", "l": "\u0337"}        # ø and ł: their "stroke" is a slash
EXTRA = {"ð": ("d", [("\u0335", "bar")]), "ø": ("o", [("\u0338", None)]), "ł": ("l", [("\u0337", None)]),
         "ƀ": ("b", [("\u0335", "bar")]), "ħ": ("h", [("\u0335", "bar")]), "ƚ": ("l", [("\u0335", None)]),
         "ɨ": ("i", [("\u0335", None)]), "ʉ": ("u", [("\u0335", None)]), "ǥ": ("g", [("\u0335", "desc")]),
         "ꝑ": ("p", [("per stroke", None)]), "ꝗ": ("q", [("\u0335", "desc")]), "ꝉ": ("l", [("\u0335", "cross")]),
         "ꝟ": ("v", [("\u0338", None)]), "ı": ("i", [])}


def mufi_names():
    """MUFI's names of its Private Use Area letters with marks (its base characters: the
    "variant letter forms" with a curl are other shapes of the letter, not a mark on it)."""
    p = HERE / "data" / "mufi4.json"
    if not p.exists():
        return {}
    return {r["chars"]: r["name"] for r in json.loads(p.read_text(encoding="utf-8"))
            if r["pua"] and r["group"] != "Variant letter forms"}


def is_capital(ch, mufi_name=""):
    """By Unicode's own name where it has one (the parsed MUFI table swaps a few names)."""
    return "CAPITAL" in (unicodedata.name(ch, "") if len(ch) == 1 else "") or \
        (len(ch) == 1 and not unicodedata.name(ch, "") and "CAPITAL" in mufi_name)


def decompose(ch, names=None):
    """(base, [(mark, anchor or None)]) for a character, or None if it is no letter with
    marks: Unicode's canonical decomposition, the letters with a stroke that Unicode keeps
    whole (ø ł đ ð ħ ƀ ꝑ …), and MUFI's Private Use Area letters by their names (LATIN
    SMALL LETTER O WITH OGONEK AND DOT ABOVE AND ACUTE → o + ogonek, dot above, acute:
    the marks named first sit nearest the letter)."""
    if ch in EXTRA:
        return EXTRA[ch]
    d = unicodedata.normalize("NFD", ch)
    if len(d) > 1 and all(unicodedata.combining(c) for c in d[1:]):
        base, marks = d[0], [(c, None) for c in d[1:]]
        if base in EXTRA:          # ǿ = ø + acute
            b, m = EXTRA[base]
            return b, m + marks
        return base, marks
    name = (names if names is not None else mufi_names()).get(ch, "")
    m = re.match(r"LATIN SMALL LETTER (DOTLESS I|[A-Z]) WITH (.+)$", name)
    if not m:
        return None
    base = "i" if m.group(1) == "DOTLESS I" else m.group(1).lower()     # this scribe's i is dotless
    marks = []
    for part in m.group(2).split(" AND "):
        for phrase, mk, att in NAMED:
            if part == phrase:
                if phrase == "STROKE" and base in SLASHED:
                    mk = SLASHED[base]
                marks += [(c, att) for c in ([mk] if isinstance(mk, str) else mk)]
                break
        else:
            return None
    return base, marks


# ---- building and saving --------------------------------------------------------------

def build(rows=None):
    M.load()
    w = writer()
    fp = TX.FastPen(M.nib_for([1.0]), 0.0)
    letters = {}
    for ch in sorted({c for c in w.L if len(c) == 1 and not unicodedata.combining(c)} | set(SC.MINIM_LETTERS)):
        letters[ch] = anchors_of(w, ch, fp)
    letters["ı"] = letters["i"]
    marks = {}
    for mk, m in MARKS.items():
        st = mark_strokes(mk, w.L)
        marks[mk] = dict(name=m["name"], attach=m["attach"], cross=bool(m.get("cross")), own=m.get("own"),
                         strokes=[dict(name=n, points=[[round(u, 4), round(v, 4)] for u, v in pts], pen=k) for n, pts, k in st],
                         **mark_anchors(st, m["attach"], m.get("own"), fp))
    p = OUT / "hours_mark_placement.json"
    if rows is not None:
        p.write_text(json.dumps(dict(summary=placement(rows), marks=rows), ensure_ascii=False, separators=(",", ":")),
                     encoding="utf-8")
    place = json.loads(p.read_text(encoding="utf-8"))["summary"]
    use = {k: place[k] for k in ("drift", "drift_sd", "gap", "gap_sd", "stack_gap")}
    use["drift_by_letter"] = {ch: v["drift"] for ch, v in place["by_letter"].items() if v["n"] >= MIN_LETTER}
    if (OUT / "hours_tilt.json").exists():          # how much the scribe's tilt varies (quill_tilt.py)
        use["tilt_sd"] = json.loads((OUT / "hours_tilt.json").read_text(encoding="utf-8"))["summary"]["bar_tilt_sd"]
    return dict(letters=letters, marks=marks, placement=use)


# ---- figures --------------------------------------------------------------------------

SHOW_BASES = "aeiounmlbdhpqgt"


def fill_word(ax, w, text, x0=0.0, xh=XH, rng=None):
    geom = w.render(w.write(text, x0, 0.0, xh, rng))
    SC.fill(ax, geom)
    return geom


def plot_marks(an, path, bases=SHOW_BASES):
    """Every mark on a row of letters, placed by the anchors (no variation)."""
    M.load()
    w = writer(slant=_slant(), anchors=an)
    rows = [mk for mk in an["marks"] if mk != "per stroke"]          # that one is p's alone
    fig, axes = plt.subplots(len(rows), 1, figsize=(len(bases) * 0.62 + 1.6, len(rows) * 0.62), dpi=140,
                             facecolor=SURFACE)
    for ax, mk in zip(axes, rows):
        x = 0.0
        for b in bases:
            fill_word(ax, w, [b, mk], x)
            x += (2.3 if b == "m" else 1.7) * XH
        ax.set_xlim(-0.6 * XH, x); ax.set_ylim(1.45 * XH, -2.3 * XH)
        ax.set_aspect("equal"); ax.axis("off")
        ax.text(-0.8 * XH, -0.4 * XH, f"{code(mk)} {an['marks'][mk]['name']}", ha="right", va="center", fontsize=6,
                color=MUTED, fontfamily="FreeSerif")
    fig.subplots_adjust(left=0.2, right=0.99, top=0.99, bottom=0.01, hspace=0.05)
    fig.savefig(path, facecolor=SURFACE)
    plt.close(fig)


def writable(w, ch, names):
    """(base, marks) if the writer can write ch: a letter it has with marks it has."""
    d = decompose(ch, names)
    if d is None:
        return None
    base, marks = d
    if (base in w.L or base in SC.MINIM_LETTERS) and all(m in w.anchors["marks"] for m, _ in marks) and marks:
        return d
    return None


def mufi_composed(w):
    """MUFI's letters with marks (and its combining marks) that the writer can write."""
    rows = json.loads((HERE / "data" / "mufi4.json").read_text(encoding="utf-8"))
    names = mufi_names()
    out = []
    for r in rows:
        ch = r["chars"]
        if r["name"].startswith("COMBINING") and ch in w.anchors["marks"]:
            out.append((r, ["o", ch] if ch not in "\u0328\u0327" else ["e", ch]))
        elif not is_capital(ch, r["name"]) and ch not in w.L and len(ch) == 1 and writable(w, ch, names):
            out.append((r, ch))
    return out


def plot_mufi(an, path, ncol=14):
    """MUFI's letters with marks as the writer writes them now: each from its base letter
    and its marks, placed by the anchors (no variation)."""
    M.load()
    w = writer(slant=_slant(), anchors=an)
    items = mufi_composed(w)
    nrow = (len(items) + ncol - 1) // ncol
    fig, axes = plt.subplots(nrow, ncol, figsize=(ncol * 0.95, nrow * 1.3), dpi=150, facecolor=SURFACE)
    for ax in axes.flat:
        ax.axis("off")
    for ax, (r, text) in zip(axes.flat, items):
        geom = w.render(w.write(text, 0.0, 0.0, XH))
        SC.fill(ax, geom)
        x0, _, x1, _ = geom.bounds
        c = (x0 + x1) / 2
        ax.set_xlim(c - 1.0 * XH, c + 1.0 * XH); ax.set_ylim(1.35 * XH, -2.35 * XH); ax.set_aspect("equal")
        ax.set_title(r["cp"].replace("+", " "), fontsize=6.5, color=MUTED, pad=0, fontfamily="DejaVu Sans")
    fig.suptitle(f"MUFI 4.0 letters with marks, written from the hand's letters and marks placed by anchors ({len(items)})",
                 fontsize=9, color=INK_TEXT, x=0.01, ha="left")
    fig.subplots_adjust(left=0.01, right=0.99, top=0.97, bottom=0.01, hspace=0.25, wspace=0.05)
    fig.savefig(path, facecolor=SURFACE)
    plt.close(fig)
    return items


WORDS = [   # (language, text) in the scribe's letter forms (ſ inside words, s at the end)
    ("Old Icelandic", ["ſá maðr hét hǫrðr", "góðr dóttir ór ſǫgu", "fǫður ſinn á lǫg", "ǫ́l, ǭ, ǿ, mál, hón"]),
    ("Latin, e caudata", ["eccleſię", "pręſul", "ſanctę dei"]),
    ("Middle High German", ["mîn hêre", "ûf dem ſê", "hôhe"]),
    ("Old French", ["été", "çà", "là où"]),
]


def plot_words(an, path, seeds=(None, 5)):
    """Words in languages full of marks, plain and with the scribe's variation."""
    M.load()
    w = writer(slant=_slant(), anchors=an)
    lines = [(lang, t) for lang, ts in WORDS for t in ts]
    fig, axes = plt.subplots(len(lines), len(seeds), figsize=(6.2 * len(seeds), 0.8 * len(lines)), dpi=170,
                             facecolor=SURFACE, squeeze=False)
    for r, (lang, text) in enumerate(lines):
        for c, seed in enumerate(seeds):
            ax = axes[r, c]
            rng = None if seed is None else np.random.default_rng(seed + r)
            x = 0.0
            for word in text.split(" "):
                geom = w.render(w.write(word, x, 0.0, XH, rng))
                SC.fill(ax, geom)
                x = geom.bounds[2] + 0.75 * XH
            ax.set_xlim(-0.4 * XH, 16.5 * XH); ax.set_ylim(1.1 * XH, -2.1 * XH); ax.set_aspect("equal"); ax.axis("off")
            if c == 0:
                ax.set_title(f"{lang}: {text}", fontsize=7, color=MUTED, loc="left", pad=1, fontfamily="DejaVu Serif")
            elif r == 0:
                ax.set_title("with the scribe's variation", fontsize=7, color=MUTED, loc="right", pad=1)
    fig.subplots_adjust(left=0.01, right=0.99, top=0.97, bottom=0.01, hspace=0.35, wspace=0.03)
    fig.savefig(path, facecolor=SURFACE)
    plt.close(fig)


TILT_SHOW = ["ð", "ƀ", "ħ", "ł", "ø", "ʉ", "ꝑ", "ę", "ǫ", "ç", "ò", "ŭ", "ů", "ǫ́", "ǭ"]
TILT_WORDS = ["hǫrðr", "eccleſię", "fǫður", "oꝑa", "là"]


def cornered(an, letters):
    """The same marks, and đ, with every tilted stroke drawn by the corner of the pen
    instead, as the writer drew its thin strokes before (for comparison)."""
    import copy
    an, letters = copy.deepcopy(an), copy.deepcopy(letters)
    for m in an["marks"].values():
        for s_ in m["strokes"]:
            if isinstance(s_.get("pen"), dict):
                s_["name"], s_["pen"] = "hairline", None
    for s_ in letters["đ"]["strokes"]:
        if isinstance(s_.get("pen"), dict):
            s_["name"], s_["pen"] = "hairline", None
    return an, letters


def plot_tilt(an, path):
    """Thin strokes drawn with the corner of the pen (before) and with the quill tilted
    (now), on the same strokes."""
    M.load()
    slant = _slant()
    w = writer(slant=slant, anchors=an)
    an0, L0 = cornered(an, w.L)
    w0 = writer(slant=slant, anchors=an0)
    w0.L = L0
    fig, axes = plt.subplots(4, 1, figsize=(len(TILT_SHOW) * 0.85, 4 * 1.25), dpi=170, facecolor=SURFACE)
    rows = [(w0, TILT_SHOW, "with the corner of the pen (before)"), (w, TILT_SHOW, "with the quill tilted (now)"),
            (w0, TILT_WORDS, "with the corner of the pen (before)"), (w, TILT_WORDS, "with the quill tilted (now)")]
    for ax, (W, items, title) in zip(axes, rows):
        x = 0.0
        for it in items:
            for word in it.split(" "):
                geom = W.render(W.write(word, x, 0.0, XH))
                SC.fill(ax, geom)
                x = geom.bounds[2] + (0.5 if items is TILT_WORDS else 0.75) * XH
            x += (0.6 if items is TILT_WORDS else 0.0) * XH
        ax.set_xlim(-0.5 * XH, max(x, 18 * XH)); ax.set_ylim(1.15 * XH, -2.0 * XH); ax.set_aspect("equal"); ax.axis("off")
        ax.set_title(title, fontsize=7.5, color=MUTED, loc="left", pad=1)
    fig.subplots_adjust(left=0.01, right=0.99, top=0.95, bottom=0.01, hspace=0.25)
    fig.savefig(path, facecolor=SURFACE)
    plt.close(fig)


def code(mk):
    return f"{ord(mk):04X}" if len(mk) == 1 else "—"


def _slant():
    lines = json.loads((HERE / "data" / "hours_lines.json").read_text(encoding="utf-8"))
    L = lines["lines"] if isinstance(lines, dict) else lines
    return float(np.median([l.get("slant_deg") or 0.0 for l in L if l.get("kind", "text") == "text"]))


def main(pdf_dir=None):
    OUT.mkdir(exist_ok=True)
    rows = None
    if pdf_dir:
        M.load()
        w = writer()
        fp = TX.FastPen(M.nib_for([1.0]), 0.0)
        la = {ch: anchors_of(w, ch, fp)
              for ch in sorted({c for c in w.L if len(c) == 1 and not unicodedata.combining(c)} | set(SC.MINIM_LETTERS))}
        rows = measure_placement(pdf_dir, la)
    an = build(rows)
    (OUT / "hours_anchors.json").write_text(json.dumps(an, ensure_ascii=False, indent=0), encoding="utf-8")
    print(json.dumps(an["placement"]))
    plot_marks(an, OUT / "hours_marks.png")
    items = plot_mufi(an, OUT / "hours_marks_mufi.png")
    print(f"MUFI letters and marks written with anchored marks: {len(items)}")
    plot_words(an, OUT / "hours_marks_words.png")
    plot_tilt(an, OUT / "hours_marks_tilt.png")
    return an


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else None)
