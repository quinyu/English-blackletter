"""The other letters of MS 2262: stroke plans fitted to every example on f. 12r.

The minim letters (i, n, m, u) come from minims.py. Every other lowercase letter on
f. 12r (all but the single x) is a stroke plan:
a few strokes in writing order, each a handful of control points in x-heights (u from
the letter's left edge at the baseline, v above the baseline), drawn with the page's pen
(the nib of corners.py; strokes named "hairline…" with its corner; a stem marked
"terminal" ends in the twist-and-pull terminal of twist.py). The plans were drawn from
gridded close-ups of the sharpest examples; then every control point is fitted to all
the examples align.py found, at once:

  * each example is registered first (shifted up to ±3 px across — ±8 px for letters
    with eight examples or fewer, whose boxes are less reliable — and ±6 px up or down);
  * the letter is drawn in the straightened frame of align.py and compared with the
    ink only inside the letter's own columns (its box, ±3 px, and no further than 4 px
    from the drawn letter) and its height zone, so neighbours do not pull it; drawn ink
    outside those columns costs only where it falls on bare parchment (ſ's head and t's
    hairline overhang the next letter);
  * control points move at most 0.2 x-height from the plan (less where a letter says so),
    and pay a small price for moving at all, so that a few examples cannot drag the shape
    anywhere; points the scribe joined stay joined ("ties").

Examples that fit far worse than the rest (more than 0.25 below the median overlap)
are another form of the letter or a misplaced find; they are set aside, listed, and the
letter is fitted again without them. After the shared fit, each example's width and
height are refitted on their own; their spread is the scribe's variation used when
writing (scribe.py).

Run:  python3 textura.py   → out/hours_textura.png, out/hours_final_s.png, out/hours_textura.json
      (fit(..., exclude=...) refits without some words, for the held-out test in scribe.py)
"""
import json
from pathlib import Path

import cv2
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from scipy.optimize import minimize

import align as A
import minims as M
import pen

HERE = Path(__file__).resolve().parent
OUT = HERE / "out"
SURFACE, INK_TEXT, MUTED, DATA, MODEL = "#fcfcfb", "#0b0b0b", "#52514e", "#2a78d6", "#eb6834"

XH = A.XH
OX = int(round(0.8 * XH))                 # canvas column of u = 0
W = int(round(2.6 * XH))                  # canvas width: u from −0.8 to 1.8 x-heights
HS = np.arange(-A.BOTTOM * XH, A.TOP * XH)[::-1]
ROW0 = float(HS[0])                       # row of the baseline in the straightened frame
H = len(HS)
PAD = 40                                  # padding around straightened lines, px
SS = 2                                    # supersampling of the fast renderer
OWN = 3                                   # px either side of a letter's box that count as its own
NEAR = 4                                  # ... but no further than this from the drawn letter
OTHER_FORM = 0.25                         # overlap this far below the median: another form, set aside
MOVE = 0.2                                # x-heights a control point may move from the plan
PRIOR = 0.5                               # cost of moving, per x-height², relative to the overlap

# Stroke plans: (name, control points (u, v) in x-heights, pen): pen "terminal" = the
# twist-and-pull terminal at the end of the stroke. zone = heights the letter may occupy.
PLANS = {
    # final (round) s: B-shaped. A thick back; a roof rising to an apex above the x-line,
    # coming down on the right into a shoulder and cutting back down-left (the spine) to
    # the middle of the back; a belly from there round the right and down to the foot,
    # closing the lower counter; a hairline flag from the shoulder up to the right.
    "s": dict(zone=(-0.25, 1.4), strokes=[
        ("back", [(0.12, 0.78), (0.07, 0.55), (0.08, 0.15), (0.2, -0.02)], None),
        ("roof and spine", [(0.06, 0.72), (0.37, 1.08), (0.6, 0.85), (0.3, 0.56)], None),
        ("belly", [(0.3, 0.56), (0.66, 0.38), (0.5, 0.1), (0.2, 0.0)], None),
        ("hairline flag", [(0.58, 0.88), (0.82, 1.22)], None)]),
    # long ſ: a stem from above the x-line to below the baseline, pulled to a point;
    # a head hooked over to the right.
    "ſ": dict(zone=(-0.8, 1.75), strokes=[
        ("stem", [(0.12, 1.38), (0.12, 0.9), (0.11, 0.2), (0.08, -0.2), (0.07, -0.55)], "terminal"),
        ("head", [(0.1, 1.32), (0.25, 1.5), (0.42, 1.48), (0.52, 1.35)], None)]),
    # f: ſ with a crossbar at the x-line.
    "f": dict(zone=(-0.8, 1.75), strokes=[
        ("stem", [(0.15, 1.4), (0.14, 0.9), (0.13, 0.2), (0.11, -0.2), (0.1, -0.55)], "terminal"),
        ("head", [(0.12, 1.35), (0.28, 1.52), (0.5, 1.5), (0.58, 1.38)], None),
        ("crossbar", [(-0.15, 0.92), (0.15, 0.97), (0.45, 0.98)], None)]),
    # g: a box-like bowl (left side, top, right side) and a tail drawn right to left
    # along the baseline, ending in a hairline down to the left.
    "g": dict(zone=(-0.55, 1.12), strokes=[
        ("left side", [(0.15, 0.95), (0.1, 0.6), (0.12, 0.12), (0.25, 0.05)], None),
        ("top", [(0.12, 0.97), (0.4, 1.0), (0.65, 0.97)], None),
        ("right side", [(0.65, 0.97), (0.68, 0.5), (0.66, 0.0)], None),
        ("tail", [(0.75, -0.02), (0.4, -0.05), (0.05, -0.1), (-0.1, -0.35)], None)]),
    # c: the broken back and a top stroke ending in a small downward tick.
    "c": dict(zone=(-0.25, 1.3), strokes=[
        ("back", [(0.1, 0.95), (0.05, 0.6), (0.06, 0.15), (0.2, 0.0)], None),
        ("top", [(0.06, 0.98), (0.3, 1.02), (0.48, 0.98), (0.5, 0.85)], None)]),
    # a: a stem with a horned head and a foot; a closed bowl drawn from the top of the stem
    # down the left and back to the stem.
    "a": dict(zone=(-0.25, 1.3), strokes=[
        ("stem", [(0.45, 1.05), (0.52, 0.9), (0.53, 0.15), (0.65, 0.02)], None),
        ("bowl", [(0.45, 0.98), (0.2, 0.72), (0.06, 0.35), (0.12, 0.05), (0.35, 0.08), (0.5, 0.3)], None)]),
    # t: a stem with a foot, a long hairline up to the right from its top, a crossbar.
    "t": dict(zone=(-0.25, 1.65), strokes=[
        ("stem", [(0.14, 1.1), (0.13, 0.8), (0.14, 0.15), (0.3, 0.0)], None),
        ("hairline", [(0.14, 1.12), (0.58, 1.55)], None),
        ("crossbar", [(-0.15, 0.85), (0.15, 0.97), (0.5, 0.97)], None)]),
    # o: two broken sides meeting in points at the top and the bottom.
    "o": dict(zone=(-0.25, 1.3), strokes=[
        ("left side", [(0.35, 1.03), (0.17, 0.85), (0.13, 0.2), (0.3, -0.02)], None),
        ("right side", [(0.35, 1.03), (0.52, 0.85), (0.55, 0.2), (0.3, -0.02)], None)]),
    # e: the back (head, stem, foot turning up to the right); a top stroke that climbs thin
    # (along the pen's edge) to a horn well above the x-line (1.17), then comes down thick
    # to 0.8 as the right side of the eye; a hairline from there back down-left to the
    # back, closing a small triangular eye. Drawn from the mean of all 59 e's and the
    # sharpest close-ups (the first plan kept the top at the x-line).
    # The top stroke must keep reaching out to the lozenge (the fit, left free, shrinks it to
    # a nub over the back, which overlaps the ink about as well and is wrong), so e's
    # points move at most 0.1 and the hairline starts where the top stroke ends.
    "e": dict(zone=(-0.25, 1.4), move=0.1, ties=[((1, 3), (2, 0))], strokes=[
        ("back", [(0.12, 0.98), (0.03, 0.8), (0.03, 0.3), (0.12, 0.03), (0.33, 0.1)], None),
        ("top stroke", [(0.06, 0.95), (0.18, 1.08), (0.27, 1.17), (0.38, 0.8)], None),
        ("hairline", [(0.38, 0.8), (0.12, 0.58)], None)]),
    # r: a minim and a shoulder ending in a flag at the x-line.
    "r": dict(zone=(-0.25, 1.3), strokes=[
        ("minim", [(0.0, 0.95), (0.08, 0.88), (0.08, 0.12), (0.18, 0.0)], None),
        ("shoulder", [(0.1, 0.92), (0.3, 1.0), (0.45, 0.92)], None)]),
    # r rotunda (after o), shaped like a 2 leaning on the o: a thick top bar down to the
    # right, a waist cutting back down-left, a lower stroke down to a foot on the baseline.
    # Its left edge stands almost straight, against the o's right side. Drawn from the mean
    # of all 7 (the first plan's top bar was too short and too flat).
    "ꝛ": dict(zone=(-0.25, 1.3), strokes=[
        ("head", [(0.33, 1.02), (0.5, 0.93), (0.7, 0.8)], None),
        ("spine and foot", [(0.68, 0.78), (0.45, 0.5), (0.42, 0.3), (0.52, 0.08), (0.72, 0.06)], None)]),
    # l: a tall stem with a foot; its head curls over to the right.
    "l": dict(zone=(-0.25, 1.85), strokes=[
        ("stem", [(0.15, 1.55), (0.14, 1.0), (0.14, 0.15), (0.28, 0.0)], None),
        ("head", [(0.14, 1.55), (0.3, 1.68), (0.45, 1.6), (0.5, 1.45)], None)]),
    # b: l's ascender and a bowl on the right, closed at the baseline.
    "b": dict(zone=(-0.25, 1.85), strokes=[
        ("stem", [(0.15, 1.55), (0.14, 1.0), (0.15, 0.15), (0.25, 0.0)], None),
        ("head", [(0.14, 1.55), (0.3, 1.66), (0.45, 1.6), (0.5, 1.45)], None),
        ("bowl", [(0.2, 0.9), (0.42, 0.97), (0.55, 0.75), (0.55, 0.15), (0.25, 0.0)], None)]),
    # h: l's ascender, a leg, and a long hairline from the foot of the leg down to the left.
    "h": dict(zone=(-0.75, 1.85), strokes=[
        ("stem", [(0.18, 1.55), (0.15, 1.0), (0.15, 0.15), (0.28, 0.0)], None),
        ("head", [(0.17, 1.55), (0.33, 1.66), (0.47, 1.58), (0.5, 1.45)], None),
        ("leg", [(0.2, 0.88), (0.45, 0.95), (0.6, 0.7), (0.58, 0.15), (0.45, 0.0)], None),
        ("hairline tail", [(0.45, 0.02), (0.0, -0.6)], None)]),
    # d: round-backed. A bowl, and a back leaning up to the left above the x-line.
    "d": dict(zone=(-0.25, 1.75), strokes=[
        ("bowl", [(0.5, 0.82), (0.2, 0.55), (0.18, 0.15), (0.35, -0.02), (0.65, 0.05)], None),
        ("back", [(0.1, 1.5), (0.45, 1.15), (0.68, 0.8), (0.72, 0.3), (0.68, 0.02)], None)]),
    # p: a stem and a right side standing on a base stroke, which runs left and drops
    # below the baseline as a hairline descender.
    "p": dict(zone=(-0.6, 1.3), strokes=[
        ("stem", [(0.0, 0.97), (0.07, 0.88), (0.08, 0.1)], None),
        ("bowl", [(0.35, 0.93), (0.55, 0.85), (0.58, 0.1)], None),
        ("base and descender", [(0.6, 0.02), (0.3, 0.0), (0.02, 0.0), (-0.12, -0.28), (-0.2, -0.45)], None)]),
    # q: a bowl, and a stem from a horned head down below the baseline, pulled to a point.
    "q": dict(zone=(-0.8, 1.3), strokes=[
        ("bowl", [(0.55, 0.98), (0.25, 0.85), (0.1, 0.4), (0.2, 0.0), (0.45, 0.05)], None),
        ("stem", [(0.6, 1.05), (0.62, 0.6), (0.62, -0.2), (0.62, -0.6)], "terminal")]),
    # v (word-initial): a thick left stroke curling in from above the x-line, a right
    # stroke meeting it in a point on the baseline.
    "v": dict(zone=(-0.25, 1.6), strokes=[
        ("left stroke", [(-0.05, 1.32), (0.1, 1.15), (0.3, 0.5), (0.4, 0.02)], None),
        ("right stroke", [(0.62, 0.92), (0.6, 0.5), (0.45, 0.02)], None)]),
}


# ---- the fast renderer (straightened frame, raster only) -------------------------------

class FastPen:
    """Draws strokes straight into the straightened frame: the nib's stamp is sheared
    with the line (u = x − h·tan slant), consecutive stamps are joined by their convex
    hull and filled. Equivalent to pen.render followed by rasterising, but without
    building vector outlines, so a letter can be drawn thousands of times while fitting."""

    def __init__(self, nib, slant_deg):
        self.nib, self.t = nib, np.tan(np.radians(slant_deg))
        self.corner = pen.corner_nib(nib)
        self.spec = json.loads((OUT / "hours_twist.json").read_text(encoding="utf-8"))["terminal"]

    def shear(self, c):
        return np.c_[c[:, 0] + c[:, 1] * self.t, c[:, 1]]

    def stamps(self, P, name, kind):
        if isinstance(kind, dict) and "tilt" in kind:      # the quill tilted (pen.tilt_profile)
            return [self.shear(self.nib.coords_at(0.0, 1.0, t)) for t in pen.tilt_profile(P, kind)]
        tip = self.corner if pen.is_corner_stroke(name) else self.nib
        if kind == "terminal":
            dth, sc = pen.twist_profile(P, self.spec)
            return [self.shear(tip.coords_at(d, k)) for d, k in zip(dth, sc)]
        c = self.shear(tip.coords)
        return [c] * len(P)

    def draw(self, strokes, shape, origin, scale=1.0):
        """strokes: (name, [(u, v)], kind) in x-heights; origin: canvas (column of u = 0,
        row of the baseline). Returns a binary canvas."""
        h, w = shape
        S = SS * 8   # fixed-point: supersampling × 2^3 sub-pixel steps
        canvas = np.zeros((h * SS, w * SS), np.uint8)
        ox, oy = origin
        for name, pts, kind in strokes:
            P = np.array([[ox + u * XH * scale, oy - v * XH * scale] for u, v in pts], float)
            P = pen.catmull_rom(P, step=0.7)
            st = self.stamps(P, name, kind)
            for i in range(len(P) - 1):
                q = np.vstack([st[i] + P[i], st[i + 1] + P[i + 1]])
                q = np.round((q + 0.5) * S - S / SS / 2).astype(np.int32)
                cv2.fillConvexPoly(canvas, cv2.convexHull(q), 1, lineType=cv2.LINE_8, shift=3)
        small = cv2.resize(canvas.astype(np.float32), (w, h), interpolation=cv2.INTER_AREA)
        return (small >= 0.5).astype(np.float32)


# ---- examples --------------------------------------------------------------------------

def load_examples(ch, found, straight, cond=None):
    """Each example of letter ch: its straightened, padded line and box."""
    out = []
    for f in found:
        if f["char"] != ch or f.get("skipped") or (cond and not cond(f)):
            continue
        img, us = straight[f["line"]]
        out.append(dict(f=f, img=img, us=us, dx=0, dy=0))
    return out


def crop(ex, dx, dy):
    """Canvas-sized window of the example's line: column OX at the box's left edge
    shifted by dx, the baseline at ROW0 shifted by dy."""
    img = ex["img"]
    a = ex["f"]["u0"] - ex["us"][0] + PAD - OX - dx
    return img[PAD - dy:PAD - dy + H, a:a + W]


def own_mask(ex, win, dx):
    """Pixels that belong to the letter: its columns (box ± OWN) within its height zone.
    win = (zone, columns of the plan as drawn before fitting): the columns are also cut to
    within NEAR px of the plan, because the letter finder's boxes are a few px off (an e's
    box often runs into the stem of the next letter, an r rotunda's starts inside the o
    it leans on). The cut comes from the plan, not from the letter being fitted: cut to
    the fitted letter, a narrower letter would hide the ink it fails to cover."""
    zone, cols = win
    m = np.zeros((H, W), bool)
    c0 = OX + dx - OWN
    c1 = OX + dx + (ex["f"]["u1"] - ex["f"]["u0"]) + OWN
    if cols is not None:
        c0, c1 = max(c0, cols[0] - NEAR), min(c1, cols[1] + NEAR)
    r0 = int(max(0, ROW0 - zone[1] * XH))
    r1 = int(min(H, ROW0 - zone[0] * XH + 1))
    m[r0:r1, max(0, c0):min(W, c1)] = True
    return m


def plan_window(ch, fp):
    """(zone, columns) of letter ch's plan drawn before fitting."""
    m = fp.draw(unpack(PLANS[ch], pack(PLANS[ch])), (H, W), (OX, ROW0))
    cols = np.nonzero(m.any(0))[0]
    return PLANS[ch]["zone"], ((int(cols[0]), int(cols[-1]) + 1) if len(cols) else None)


def score_one(model, ex, win, dx=None, dy=None):
    dx = ex["dx"] if dx is None else dx
    dy = ex["dy"] if dy is None else dy
    I = crop(ex, dx, dy) > 0
    Mo = model > 0
    R = own_mask(ex, win, dx)
    inter = (I & Mo & R).sum()
    union = ((I | Mo) & R).sum()
    stray = (Mo & ~I & ~R).sum() / max(1, Mo.sum())
    return inter / max(1, union) - 0.5 * stray


def register(model, exs, win, xs=None, ys=range(-6, 7)):
    """Best shift of each example; letters with few examples have less reliable boxes
    (their round-1 templates are single atlas crops), so they may shift further."""
    xs = xs or (range(-3, 4) if len(exs) > 8 else range(-8, 9))
    for ex in exs:
        best = max((score_one(model, ex, win, dx, dy), dx, dy) for dy in ys for dx in xs)
        ex["dx"], ex["dy"] = best[1], best[2]


# ---- fitting ---------------------------------------------------------------------------

def unpack(plan, x):
    """Strokes from the packed control points. A plan's "ties" join points that the scribe
    joined: ((stroke, point), (stroke, point)) puts the second on the first."""
    out, k = [], 0
    for name, pts, kind in plan["strokes"]:
        n = len(pts)
        out.append([name, [tuple(x[k + 2 * i:k + 2 * i + 2]) for i in range(n)], kind])
        k += 2 * n
    for (si, pi), (sj, pj) in plan.get("ties", []):
        out[sj][1][pj] = out[si][1][pi]
    return [tuple(o) for o in out]


def pack(plan):
    return np.array([c for _, pts, _ in plan["strokes"] for p in pts for c in p], float)


def fit_letter(ch, exs, fp, iters=2, verbose=True):
    """Shared fit; then examples far below the median are set aside and the fit is redone."""
    x, per = fit_once(ch, exs, fp, iters, verbose)
    off = [i for i, p in enumerate(per) if p < np.median(per) - OTHER_FORM]
    if not off:
        return x, per, exs, []
    keep = [e for i, e in enumerate(exs) if i not in off]
    aside = [exs[i] for i in off]
    if verbose:
        print(f"     set aside: " + ", ".join(f"l.{e['f']['line']} #{e['f']['index']} ({per[i]:.2f})" for i, e in zip(off, aside)))
    x, per = fit_once(ch, keep, fp, iters, verbose)
    return x, per, keep, aside


def fit_once(ch, exs, fp, iters=2, verbose=True):
    plan = PLANS[ch]
    x0 = pack(plan)
    win = plan_window(ch, fp)
    move = plan.get("move", MOVE)
    origin = (OX, ROW0)

    def render(x):
        return fp.draw(unpack(plan, x), (H, W), origin)

    def loss(x):
        m = render(np.clip(x, x0 - move, x0 + move))
        return -np.mean([score_one(m, ex, win) for ex in exs]) + PRIOR * np.mean((x - x0) ** 2)

    x = x0.copy()
    register(render(x), exs, win)
    start = -loss(x)
    for it in range(iters):
        res = minimize(loss, x, method="Powell", bounds=list(zip(x0 - move, x0 + move)),
                       options=dict(maxiter=1, xtol=0.01, ftol=1e-4))
        x = np.clip(res.x, x0 - move, x0 + move)
        register(render(x), exs, win)
    m = render(x)
    per = [score_one(m, ex, win) for ex in exs]
    if verbose:
        print(f"  {ch}: {len(exs)} examples, score {start:.3f} → {np.mean(per):.3f}")
    return x, per


def variation(ch, x, exs, fp, su=np.arange(0.86, 1.15, 0.04), sv=np.arange(0.9, 1.11, 0.04)):
    """Each example's own width and height (scales of the fitted letter about its
    left edge on the baseline), with its registration redone at each scale."""
    plan = PLANS[ch]
    win = plan_window(ch, fp)
    strokes = unpack(plan, x)
    out = []
    models = {}
    for a in su:
        for b in sv:
            st = [(n, [(u * a, v * b) for u, v in pts], k) for n, pts, k in strokes]
            models[(a, b)] = fp.draw(st, (H, W), (OX, ROW0))
    for ex in exs:
        best = max((score_one(m, ex, win, dx, dy), a, b) for (a, b), m in models.items()
                   for dy in range(ex["dy"] - 1, ex["dy"] + 2) for dx in range(ex["dx"] - 1, ex["dx"] + 2))
        out.append((float(best[1]), float(best[2])))
    return np.array(out)


# ---- figures ---------------------------------------------------------------------------

def show_examples(ax_row, ch, x, exs, fp, n=8, f8=6):
    plan = PLANS[ch]
    m = fp.draw(unpack(plan, x), (H, W), (OX, ROW0))
    for ax, ex in zip(ax_row, exs[:n]):
        c = crop(ex, ex["dx"], ex["dy"])
        img = np.ones((H, W, 3))
        img[c > 0] = matplotlib.colors.to_rgb(DATA)
        img[(m > 0) & (c > 0)] = (0.1, 0.1, 0.1)
        img[(m > 0) & (c == 0)] = matplotlib.colors.to_rgb(MODEL)
        R = own_mask(ex, plan_window(ch, fp), ex["dx"])
        img[~R] = 0.55 + 0.45 * img[~R]
        ax.imshow(img, interpolation="nearest")
        ax.set_title(f"l.{ex['f']['line']}", fontsize=6, color=MUTED, loc="left", pad=1)
        ax.axis("off")
    for ax in ax_row[len(exs[:n]):]:
        ax.axis("off")


def setup():
    """Page, straightened lines, fast pen and the found letters (with word-final marks)."""
    rgb, mask, lines, dark = M.load()
    by = {l["n"]: l for l in lines}
    found = json.loads((HERE / "data" / "hours_letters_found.json").read_text(encoding="utf-8"))["letters"]
    straight = {}
    for n in {f["line"] for f in found}:
        img, us = A.straighten(mask, by[n])
        straight[n] = (np.pad(img, PAD), us)
    slant = float(np.median([l["slant_deg"] or 0.0 for l in lines if l.get("kind") == "text"]))
    fp = FastPen(M.nib_for([1.0]), slant)
    reading = json.loads((HERE / "data" / "hours_reading.json").read_text(encoding="utf-8"))
    words = {l["n"]: l["diplomatic"] for l in reading["lines"] if l.get("kind") == "text"}
    toks = {n: A.tokens(t) for n, t in words.items()}

    def word_final(f):   # last written letter of its word (punctuation after it aside)
        T = toks[f["line"]]
        k = f["index"] + 1
        return k == len(T) or T[k]["word"] != T[f["index"]]["word"] or T[k]["char"] in ":,."

    for f in found:
        f["final"] = word_final(f)
    return dict(rgb=rgb, mask=mask, lines=lines, found=found, straight=straight, fp=fp, toks=toks, slant=slant)


def fit(env, letters=None, exclude=(), verbose=True):
    """Fit the letters' plans; exclude: (line, word index) pairs whose letters are left out."""
    fits = {}
    for ch in letters or PLANS:
        cond = (lambda f: f["final"]) if ch == "s" else None
        exs = [e for e in load_examples(ch, env["found"], env["straight"], cond)
               if (e["f"]["line"], e["f"]["word"]) not in set(exclude)]
        x, per, exs, aside = fit_letter(ch, exs, env["fp"], verbose=verbose)
        var = variation(ch, x, exs, env["fp"])
        fits[ch] = dict(x=x, exs=exs, score=per, var=var, aside=aside)
        if verbose:
            print(f"     width ×{np.median(var[:, 0]):.2f} (spread {np.std(var[:, 0]):.2f}), "
                  f"height ×{np.median(var[:, 1]):.2f} (spread {np.std(var[:, 1]):.2f})")
    return fits


def save(fits, path):
    out = {}
    for ch, F in fits.items():
        out[ch] = dict(strokes=[dict(name=n, points=[[round(u, 4), round(v, 4)] for u, v in p], pen=k)
                                for n, p, k in unpack(PLANS[ch], F["x"])],
                       zone=PLANS[ch]["zone"], n=len(F["exs"]), overlap=float(np.mean(F["score"])),
                       shift_px=[float(np.median([e["dx"] for e in F["exs"]])),
                                 float(np.median([e["dy"] for e in F["exs"]]))],
                       width_scale=[float(np.median(F["var"][:, 0])), float(np.std(F["var"][:, 0]))],
                       height_scale=[float(np.median(F["var"][:, 1])), float(np.std(F["var"][:, 1]))],
                       set_aside=[dict(line=e["f"]["line"], index=e["f"]["index"]) for e in F["aside"]])
    path.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")


def main():
    OUT.mkdir(exist_ok=True)
    env = setup()
    fp = env["fp"]
    fits = fit(env)
    save(fits, OUT / "hours_textura.json")
    plot_fits(fits, fp, OUT / "hours_textura.png")
    plot_final_s(fits["s"], fp, OUT / "hours_final_s.png")
    return fits, fp


def draw_letter(ax, strokes, scale=6):
    """The fitted letter as a clean vector drawing (pen.render), on its x-height guides."""
    pts = [[u * XH, -v * XH] for _, p, _ in strokes for u, v in p]
    geom = pen.render([[[u * XH + v * XH * np.tan(np.radians(4.5)), -v * XH] for u, v in p] for _, p, _ in strokes],
                      M.nib_for([1.0]), step=0.5, names=[n for n, _, _ in strokes],
                      pens=[json.loads((OUT / "hours_twist.json").read_text())["terminal"] if k == "terminal" else None
                            for _, _, k in strokes])
    for poly in (geom.geoms if hasattr(geom, "geoms") else [geom]):
        ax.fill(*poly.exterior.xy, color="#2a2118", lw=0)
        for hole in poly.interiors:   # counters
            ax.fill(*hole.xy, color=SURFACE, lw=0)
    for v, col in ((0, DATA), (-XH, MODEL)):
        ax.axhline(v, color=col, lw=0.5, alpha=0.6)
    ax.set_xlim(-0.6 * XH, 1.4 * XH); ax.set_ylim(0.8 * XH, -1.8 * XH)
    ax.set_aspect("equal"); ax.axis("off")


def plot_fits(fits, fp, path, n=8):
    letters = list(fits)
    fig, axes = plt.subplots(len(letters), n + 1, figsize=(1.05 * (n + 1), 1.35 * len(letters)), dpi=190,
                             facecolor=SURFACE, gridspec_kw=dict(width_ratios=[1.3] + [1] * n))
    for r, ch in enumerate(letters):
        F = fits[ch]
        draw_letter(axes[r, 0], unpack(PLANS[ch], F["x"]))
        name = {"ſ": "long s", "s": "final s"}.get(ch, ch)
        axes[r, 0].set_title(f"{name}  ({len(F['exs'])} fitted, overlap {np.mean(F['score']):.2f})",
                             fontsize=6.5, color=INK_TEXT, loc="left", pad=1)
        order = np.argsort(F["score"])[::-1]
        show_examples(axes[r, 1:], ch, F["x"], [F["exs"][i] for i in order], fp, n=n)
    handles = [matplotlib.patches.Patch(color=(0.1, 0.1, 0.1), label="letter and ink agree"),
               matplotlib.patches.Patch(color=DATA, label="ink the letter misses"),
               matplotlib.patches.Patch(color=MODEL, label="letter where there is no ink"),
               matplotlib.patches.Patch(color="#d9d8d5", label="outside the letter's own columns (neighbours)")]
    fig.legend(handles=handles, loc="lower center", ncol=4, frameon=False, fontsize=6.5, labelcolor=INK_TEXT)
    fig.suptitle("The lowercase letters of f. 12r other than the minims: one stroke plan each, fitted to every "
                 "example (left), drawn over the examples (best-fitting first)", fontsize=8, color=INK_TEXT, x=0.01, ha="left")
    fig.tight_layout(rect=(0, 0.03, 1, 0.97))
    fig.savefig(path, facecolor=SURFACE)
    plt.close(fig)


def plot_final_s(F, fp, path):
    """Every word-final s on the page with the fitted s drawn over it."""
    exs = F["exs"]
    n = len(exs)
    cols = 8
    rows = int(np.ceil(n / cols)) + 1
    fig = plt.figure(figsize=(1.1 * cols, 1.45 * rows), dpi=190, facecolor=SURFACE)
    gs = fig.add_gridspec(rows, cols)
    ax = fig.add_subplot(gs[0, :2])
    draw_letter(ax, unpack(PLANS["s"], F["x"]))
    ax.set_title("the fitted final s", fontsize=7, color=INK_TEXT, loc="left")
    ax = fig.add_subplot(gs[0, 2:])
    ax.axis("off")
    ax.text(0, 0.9, "Strokes, in order:\n1  back: down the left side to the foot\n"
            "2  roof and spine: up to the apex above the x-line, down into the shoulder,\n"
            "    then back down-left to the middle (closing the upper counter)\n"
            "3  belly: from the middle round the right and down to the foot (lower counter)\n"
            "4  hairline flag: from the shoulder up to the right (pen corner)",
            fontsize=6.5, color=INK_TEXT, va="top", family="DejaVu Sans")
    axs = [fig.add_subplot(gs[1 + i // cols, i % cols]) for i in range(n)]
    show_examples(axs, "s", F["x"], exs, fp, n=n)
    fig.suptitle(f"Word-final s on f. 12r ({n}), with the fitted letter drawn over each", fontsize=8,
                 color=INK_TEXT, x=0.01, ha="left")
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    fig.savefig(path, facecolor=SURFACE)
    plt.close(fig)


if __name__ == "__main__":
    main()
