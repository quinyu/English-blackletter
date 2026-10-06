"""Biting in MS 2262: where two neighbouring letters share a stroke.

In textura, when a letter whose right side is an upright curve or stem (the bowl of o,
b, p) is followed by one whose left side is one too (o, c, e, d, g, q), the two sides are
often written as one stroke: the letters "bite". o + p + p + o can fuse all along; r + a
does not, because r has no right side to share.

For every pair of neighbouring letters inside a word, found by the letter finder
(align.py) on the pages read so far, the ink at the boundary between the two letters is
classed. White there is of two kinds: the counter of a bowl (closed, or open at one
end: this scribe's p often leaves its bowl open at the foot), which always has the
bowl's top or bottom stroke within the x-height, and the space between letters, white
over nearly the whole x-height (0.12–0.88) but for a crossing hairline. Only the second
separates letters. The stroke at the junction is measured in the middle of the band
(0.25–0.75 x-height, where bowls stand upright and heads, feet and joins are absent).

The facing strokes are found where the fitted letters put them: the left letter's last
upright stroke and the right letter's first (the letter finder's boxes overlap by up
to 6 px, so a box alone may hold its neighbour's first stroke):

  separate   two strokes with a column white over the x-height between them
  linked     two strokes, joined only by a hairline
  bitten     one and the same stroke, no wider than 1.5 strokes: it serves both letters
  fused      one run wider than that: the two letters' strokes run together
  touching   (a letter with no upright facing side) its ink meets the neighbour's

Bitten and fused together are biting in the scribe's sense: the two sides are written
on one line. The run's width says how far they overlap (one stroke: 7 px; two side by
side: 14).

The stroke width is measured from the same lines (median dark run, 7 px at f. 12r's
x-height of 29 px).

Run:  python3 biting.py [PDF_PAGE_DIR]   → out/hours_biting.json, out/hours_biting*.png
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

HERE = Path(__file__).resolve().parent
OUT = HERE / "out"
SURFACE, INK_TEXT, MUTED, DATA, MODEL = "#fcfcfb", "#0b0b0b", "#52514e", "#2a78d6", "#eb6834"
CORE = (0.25, 0.75)        # rows of the x-band where the classing looks (x-heights)
SHARED = 1.5               # a dark run up to this many strokes wide is one shared stroke
SEARCH = 0.35              # x-heights either side of the boxes' boundary searched for white
SKIP = set(":,.;") | {"̄", "͛"}


def core_rows():
    hs = np.arange(-A.BOTTOM * A.XH, A.TOP * A.XH)[::-1] / A.XH
    return (hs >= CORE[0]) & (hs <= CORE[1])


def stroke_width(straight):
    """Median width (px) of the dark runs in the middle of the x-band."""
    rows = core_rows()
    W = []
    for img, us in straight.values():
        p = np.r_[img[rows].mean(0) >= 0.7, False]
        run = 0
        for v in p:
            if v:
                run += 1
            elif run:
                W.append(run)
                run = 0
    return float(np.median(W))


GAP_ROWS = (0.12, 0.88)     # a column between letters is white over nearly the whole x-height
HAIRLINE = 2                # px of ink a gap column may hold: a hairline join crossing it


def open_white(img):
    """Per column of a straightened line: whether it is a gap between letters (white over
    0.12–0.88 x-height but for a hairline), and its share of ink in the core rows. A
    counter is never a gap: whether closed (o, b) or open at one end (this scribe's p
    often leaves its bowl open at the foot, e its mouth below the eye), it has the
    bowl's top or bottom stroke within the x-height."""
    hs = np.arange(-A.BOTTOM * A.XH, A.TOP * A.XH)[::-1] / A.XH
    rows = (hs >= GAP_ROWS[0]) & (hs <= GAP_ROWS[1])
    gap = (img[rows] > 0).sum(0) <= HAIRLINE
    return gap.astype(float), img[core_rows()].mean(0)


# The side each letter turns to its neighbour, in the middle of the x-band: the curved
# side of a bowl, a straight stem, or nothing upright (an open side, an arm, a diagonal).
# h's leg is curved like the side of a bowl; f and ſ turn only a crossbar or a head flag
# to the right, t its crossbar.
RIGHT_SIDE = dict({c: "bowl" for c in "obpdgshđꝓ"}, **{c: "stem" for c in "aimnulq"},
                  **{c: "open" for c in "certfſxzꝛyvꝫ"})
LEFT_SIDE = dict({c: "bowl" for c in "ocedgqasꝯđ"}, **{c: "stem" for c in "bhilmnprſftuꝑꝓ"},
                 **{c: "open" for c in "vxzꝛyꝫ"})
NEAR = 10                    # px either side of the boxes' boundary where the junction is looked for


def side(ch, which):
    t = (RIGHT_SIDE if which == "right" else LEFT_SIDE).get(ch.lower())
    return t or "other"


def runs(dark):
    """(start, end) of each run of dark columns."""
    out, start = [], None
    for i, v in enumerate(np.r_[dark, False]):
        if v and start is None:
            start = i
        elif not v and start is not None:
            out.append((start, i - 1))
            start = None
    return out


def facing_offsets(found):
    """Where each letter's first and last upright strokes (dark runs in the middle of the
    x-band) and its outermost ink lie, in px from its box's left edge, for a box of the
    letter's median width on f. 12r. From the fitted letters (textura.py, the sign fits)
    drawn with the page's pen, shifted as their examples were registered; the minim
    letters from the minim module's first-stem offset and stem pitch."""
    import minims as M
    import scribe as SC
    import textura as TX
    M.load()
    L = SC.load_letters()
    fp = TX.FastPen(M.nib_for([1.0]), 0.0)
    hs = TX.HS / TX.XH
    core = (hs >= CORE[0]) & (hs <= CORE[1])
    width = {}
    for f in found:
        if not f.get("skipped"):
            width.setdefault(f["char"], []).append(f["u1"] - f["u0"])
    out = {}
    for ch, v in L.items():
        if "strokes" not in v or len(ch) != 1 or unicodedata.combining(ch):
            continue
        st = [(s_["name"], [tuple(p) for p in s_["points"]], s_["pen"]) for s_ in v["strokes"]]
        m = fp.draw(st, (TX.H, TX.W), (TX.OX, TX.ROW0))
        R = runs(m[core].mean(0) >= 0.5)
        cols = np.nonzero(m.any(0))[0]
        if not R or not len(cols):
            continue
        sh = TX.OX + v.get("shift_px", [0, 0])[0]
        out[ch] = dict(first=(R[0][0] + R[0][1]) / 2 - sh, last=(R[-1][0] + R[-1][1]) / 2 - sh,
                       left_ink=float(cols[0] - sh), right_ink=float(cols[-1] - sh))
    minim = json.loads((OUT / "hours_minims.json").read_text(encoding="utf-8"))
    pitch = minim["rules"]["pitch"]["inside"] * A.XH
    for ch, k in A.MINIM_STEMS.items():
        first = SC.minim_offsets(found).get(ch, 0.4) * A.XH
        out[ch] = dict(first=first, last=first + (k - 1) * pitch, left_ink=first - 4, right_ink=first + (k - 1) * pitch + 4)
    for ch, d in out.items():
        d["width"] = float(np.median(width[ch])) if ch in width else None
    return out


def junction(img, us, a, b, stroke, offs, cache=None):
    """Class of the junction between letters a and b (found letters on one straightened
    line): (class, white gap px, dark run px). The left letter's facing stroke is the
    dark run (middle of the x-band) at the place its fitted model puts its last upright
    stroke, the right letter's at its first (facing_offsets, scaled to each box's width):
      one and the same run   bitten if no wider than 1.5 strokes (one stroke serves
                             both), fused if wider (their two strokes run together)
      two runs               separate if a column between them is white over the
                             x-height (the gap), linked if only a hairline crosses
    A letter that turns no upright side to its neighbour (c, e, r, t ...) cannot share
    a stroke with it: such a pair is separate if white crosses between the two letters'
    facing ink, touching if not."""
    key = id(img)
    if cache is not None and key in cache:
        gp, dk, rr = cache[key]
    else:
        gp, dk = open_white(img)
        rr = runs(dk >= 0.5)
        if cache is not None:
            cache[key] = (gp, dk, rr)
    oa, ob = offs.get(a["char"]), offs.get(b["char"])
    if oa is None or ob is None:
        return "unclear", 0, 0
    sa = (a["u1"] - a["u0"]) / oa["width"] if oa.get("width") else 1.0
    sb = (b["u1"] - b["u0"]) / ob["width"] if ob.get("width") else 1.0
    x0 = us[0]
    upright = side(a["char"], "right") in ("bowl", "stem") and side(b["char"], "left") in ("bowl", "stem")
    if not upright:
        z0 = int(round(a["u0"] + oa["right_ink"] * sa - x0)) - 3
        z1 = int(round(b["u0"] + ob["left_ink"] * sb - x0)) + 3
        lo, hi = max(0, min(z0, z1)), min(len(gp) - 1, max(z0, z1))
        g = gp[lo:hi + 1] > 0
        return ("separate", int(g.sum()), 0) if g.any() else ("touching", 0, 0)
    ea = a["u0"] + oa["last"] * sa - x0
    eb = b["u0"] + ob["first"] * sb - x0

    def nearest(e):
        best = min(rr, key=lambda r: 0 if r[0] <= e <= r[1] else min(abs(e - r[0]), abs(e - r[1])), default=None)
        if best is None or not (best[0] - 5 <= e <= best[1] + 5):
            return None
        return best
    ra, lb = nearest(ea), nearest(eb)
    if ra is None or lb is None:
        return "unclear", 0, 0
    if ra == lb:
        w = int(ra[1] - ra[0] + 1)
        return ("bitten" if w <= SHARED * stroke else "fused"), 0, w
    if ra[0] > lb[0]:
        ra, lb = lb, ra
    between = gp[ra[1] + 1:lb[0]] > 0
    if between.any():
        return "separate", int(between.sum()), 0
    return "linked", int(lb[0] - ra[1] - 1), 0


def pairs(found, straight, stroke, offs, page="f. 12r", pid="p1/pg-026"):
    """Every pair of neighbouring letters inside a word, classed."""
    by = {}
    for f in found:
        by.setdefault((f["line"], f["word"]), []).append(f)
    out = []
    cache = {}
    for (n, w), F in by.items():
        F = [f for f in sorted(F, key=lambda f: f["index"]) if not f["skipped"] and f["char"] not in SKIP]
        img, us = straight[n]
        for a, b in zip(F[:-1], F[1:]):
            if b["index"] != a["index"] + 1:
                continue                     # a skipped letter between them
            kind, gap, run = junction(img, us, a, b, stroke, offs, cache)
            out.append(dict(page=page, line=n, word=w, a=a["char"], b=b["char"], kind=kind, gap=gap, run=run,
                            right=side(a["char"], "right"), left=side(b["char"], "left"), pid=pid,
                            yb=a.get("yb"), xh=a.get("xh"), scale=a.get("scale", 1.0),
                            u=(a["u1"] + b["u0"]) / 2, ua=a["u0"], a_u1=a["u1"], b_u0=b["u0"], ub=b["u1"]))
    return out


def f12r():
    """f. 12r: its found letters and straightened lines."""
    import minims as M
    rgb, mask, lines, dark = M.load()
    by = {l["n"]: l for l in lines}
    found = json.loads((HERE / "data" / "hours_letters_found.json").read_text(encoding="utf-8"))["letters"]
    straight = {n: A.straighten(mask, by[n]) for n in {f["line"] for f in found}}
    return found, straight


def gallery(P, straight_by_page, path, title, cols=10, z=3):
    """Pairs as straightened ink, the boundary marked, coloured by class."""
    col = {"bitten": (0.92, 0.41, 0.2), "touching": (0.6, 0.3, 0.7), "separate": (0.16, 0.47, 0.84)}
    rows = int(np.ceil(len(P) / cols))
    fig, axes = plt.subplots(rows, cols, figsize=(1.1 * cols, 1.25 * rows), dpi=170, facecolor=SURFACE, squeeze=False)
    for ax in axes.ravel():
        ax.axis("off")
    for ax, q in zip(axes.ravel(), P):
        img, us = straight_by_page[q["page"]][q["line"]]
        c0, c1 = int(q["ua"] - us[0]) - 3, int(q["ub"] - us[0]) + 3
        h = img.shape[0]
        r0, r1 = int(h - (A.BOTTOM + 1.3) * A.XH), int(h - 0.3 * A.XH)
        crop = img[max(0, r0):r1, max(0, c0):c1]
        rgbimg = np.ones(crop.shape + (3,))
        rgbimg[crop > 0] = (0.15, 0.15, 0.15)
        ax.imshow(rgbimg, interpolation="nearest")
        bx = q["u"] - us[0] - max(0, c0)
        ax.axvline(bx, color=col[q["kind"]], lw=1.2)
        ax.set_title(f"{q['a']}{q['b']}  {q['kind']}" + (f" {q['gap']}" if q["kind"] == "separate" else ""),
                     fontsize=5.5, color=col[q["kind"]], loc="left", pad=1)
    fig.suptitle(title, fontsize=8, color=INK_TEXT, x=0.01, ha="left")
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    fig.savefig(path, facecolor=SURFACE)
    plt.close(fig)


def page_crop(q, pdf_dir, imgs, pad=(0.35, 0.45)):
    """The pair as it is on the page (RGB), from its straightened coordinates."""
    path = (HERE / "data" / "clermont-ms2262-f012r.jpg") if q["pid"] == "p1/pg-026" else Path(pdf_dir) / f"{q['pid']}.jpg"
    if q["pid"] not in imgs:
        imgs[q["pid"]] = cv2.cvtColor(cv2.imread(str(path)), cv2.COLOR_BGR2RGB)
    im = imgs[q["pid"]]
    s, xh, yb = q["scale"], q["xh"], q["yb"]
    t = np.tan(np.radians(4.8))
    x0, x1 = int(q["ua"] * s - pad[0] * xh), int(q["ub"] * s + pad[1] * xh + 0.6 * xh * t)
    y0, y1 = int(yb - 1.45 * xh), int(yb + 0.55 * xh)
    return im[max(0, y0):y1, max(0, x0):x1]


def gallery_page(P, pdf_dir, path, title, cols=10):
    """Pairs as they are on the page, the class written above each."""
    col = {"bitten": "#c2410c", "fused": "#c2410c", "linked": MUTED, "separate": DATA, "touching": "#7c3aed",
           "unclear": MUTED}
    rows = int(np.ceil(len(P) / cols))
    fig, axes = plt.subplots(rows, cols, figsize=(1.05 * cols, 1.15 * rows), dpi=170, facecolor=SURFACE, squeeze=False)
    imgs = {}
    for ax in axes.ravel():
        ax.axis("off")
    for ax, q in zip(axes.ravel(), P):
        ax.imshow(page_crop(q, pdf_dir, imgs), interpolation="lanczos")
        ax.set_title(f"{q['a']}{q['b']} {q['kind']} · {q['page']}", fontsize=5, color=col[q["kind"]], loc="left", pad=1)
    fig.suptitle(title, fontsize=8, color=INK_TEXT, x=0.01, ha="left")
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    fig.savefig(path, facecolor=SURFACE)
    plt.close(fig)


# ---- the book --------------------------------------------------------------------------

BITING = ("bitten", "fused")


def page_lines(pdf_dir, page, reading):
    """Straightened lines of a page read in data/hours_readings.json (find_letters.py)."""
    import find_letters as FL
    import hands as H
    guides = json.loads((OUT / "hours_book_lines.json").read_text(encoding="utf-8"))[page]["lines"]
    mask = H.page_ink(Path(pdf_dir) / f"{page}.jpg")[1]
    return {n: FL.straighten(mask, g) for n, g in FL.match_lines(reading, guides).items()}


def collect(pdf_dir):
    """Every pair on f. 12r and on the pages whose letters find_letters.py has found."""
    import find_letters as FL
    found12, straight12 = f12r()
    offs = facing_offsets(found12)
    P = pairs(found12, straight12, stroke_width(straight12), offs, page="f. 12r")
    S = {"f. 12r": straight12}
    F = json.loads(FL.FOUND.read_text(encoding="utf-8")) if FL.FOUND.exists() else {}
    R = FL.load_readings()
    for page, d in F.items():
        st = page_lines(pdf_dir, page, R[page]["lines"])
        label = f"f. {d['folio']}"
        P += pairs(d["letters"], st, stroke_width(st), offs, page=label, pid=page)
        S[label] = st
    return P, S, offs


def rate(Q):
    """Share of pairs that bite, among those that could be classed."""
    Q = [q for q in Q if q["kind"] != "unclear"]
    return (sum(q["kind"] in BITING for q in Q) / len(Q)) if Q else None, len(Q)


def chains(P):
    """Runs of three or more letters, each biting the next (o + p + p + o …)."""
    by = {}
    for q in P:
        by.setdefault((q["page"], q["line"], q["word"]), []).append(q)
    out = []
    for key, Q in by.items():
        Q = sorted(Q, key=lambda q: q["ua"])
        run = []
        for q in Q + [None]:
            if q is not None and q["kind"] in BITING and (not run or run[-1]["b_u0"] == q["ua"]):
                run.append(q)
                continue
            if len(run) >= 2:
                out.append(dict(page=key[0], line=key[1], letters="".join([run[0]["a"]] + [r["b"] for r in run])))
            run = [q] if (q is not None and q["kind"] in BITING) else []
    return out


def summarise(P):
    combos = {}
    for q in P:
        combos.setdefault(f"{q['right']} → {q['left']}", []).append(q)
    by_pair = {}
    for q in P:
        by_pair.setdefault(q["a"] + q["b"], []).append(q)
    kinds = ("bitten", "fused", "linked", "separate", "touching", "unclear")
    S = dict(
        pages=sorted({q["page"] for q in P}, key=lambda p: (int(p[3:-1]), p[-1])), pairs=len(P),
        classes={k: sum(q["kind"] == k for q in P) for k in kinds},
        by_sides={c: dict(n=len(Q), rate=rate(Q)[0], **{k: sum(q["kind"] == k for q in Q) for k in kinds})
                  for c, Q in sorted(combos.items())},
        by_pair={p: dict(n=len(Q), rate=rate(Q)[0], sides=f"{Q[0]['right']} → {Q[0]['left']}",
                         **{k: sum(q["kind"] == k for q in Q) for k in kinds})
                 for p, Q in sorted(by_pair.items(), key=lambda kv: -len(kv[1]))},
        run_px=dict(zip(("p10", "median", "p90"), [float(v) for v in np.percentile(
            [q["run"] for q in P if q["kind"] in BITING] or [0], [10, 50, 90])])),
        chains=chains(P))
    return S


def writer_params(P, summary, offs, stroke=7.0, min_n=5):
    """What the writer needs to bite as the scribe does: the rate for each pair seen at
    least min_n times, the rate for each combination of facing sides, each letter's
    sides and facing-stroke offsets, and how far past one stroke a biting run reaches
    (0 = one shared stroke; up to a stroke = two strokes run together)."""
    extra = np.array([q["run"] - stroke for q in P if q["kind"] in BITING and q["run"] > 0])
    chars = set(offs) | set(RIGHT_SIDE) | set(LEFT_SIDE)
    return dict(
        pair_rate={p: round(v["rate"], 3) for p, v in summary["by_pair"].items()
                   if v["rate"] is not None and v["n"] - v["unclear"] >= min_n},
        sides_rate={c: round(v["rate"], 3) for c, v in summary["by_sides"].items() if v["rate"] is not None},
        sides={c: [side(c, "right"), side(c, "left")] for c in chars},
        offsets={c: dict(first=round(o["first"], 2), last=round(o["last"], 2)) for c, o in offs.items()},
        extra_px=[float(np.mean(np.clip(extra, 0, None))) if len(extra) else 2.0,
                  float(np.std(np.clip(extra, 0, None))) if len(extra) else 1.5],
        stroke_px=stroke)


SIDE_ORDER = ["bowl → bowl", "bowl → stem", "stem → bowl", "stem → stem"]
CLASS_COLOURS = [("biting", ("bitten", "fused"), DATA), ("touching", ("touching",), MODEL),
                 ("linked by a hairline", ("linked",), "#1baf7a"), ("apart", ("separate",), "#d6d4cf")]


def plot_rates(P, summary, path, min_n=8):
    """Left: what happens between two letters, by the sides they turn to each other.
    Right: the biting rate of each pair seen at least min_n times, by side combination;
    the pairs that never bite listed in one line per combination."""
    import textwrap
    groups_r = []
    for r in SIDE_ORDER:
        ps = [(p, v) for p, v in summary["by_pair"].items() if v["sides"] == r and v["rate"] is not None
              and v["n"] - v["unclear"] >= min_n]
        ps.sort(key=lambda kv: (-kv[1]["rate"], -kv[1]["n"]))
        bars = [kv for kv in ps if kv[1]["rate"] > 0]
        never = [kv for kv in ps if kv[1]["rate"] == 0]
        groups_r.append((r, bars, never))
    n_rows = sum(1 + len(b) + (1 + 0.8 * len(textwrap.wrap("never: " + ", ".join(f"{p} {v['n']}" for p, v in nv), 70))
                               if nv else 0) for _, b, nv in groups_r)
    H = max(5.5, 0.2 * n_rows + 1.2)
    fig = plt.figure(figsize=(11.5, H), dpi=170, facecolor=SURFACE)
    left_h = min(1.0, 4.6 / H)
    ax = fig.add_axes([0.13, 1 - left_h * 0.93 - 0.3 / H, 0.3, left_h * 0.8])
    rows = SIDE_ORDER + ["an open side"]
    groups = {r: [q for q in P if q["kind"] != "unclear" and f"{q['right']} → {q['left']}" == r] for r in SIDE_ORDER}
    groups["an open side"] = [q for q in P if q["kind"] != "unclear" and "open" in (q["right"], q["left"])]
    for i, r in enumerate(rows):
        Q = groups[r]
        left = 0.0
        for name, kinds, colour in CLASS_COLOURS:
            share = sum(q["kind"] in kinds for q in Q) / max(1, len(Q))
            if share > 0:
                ax.barh(i, share, left=left, color=colour, height=0.62, edgecolor=SURFACE, linewidth=2)
                if share >= 0.07:
                    ax.text(left + share / 2, i, f"{share:.0%}", ha="center", va="center", fontsize=7,
                            color="white" if colour in (DATA, MODEL, "#1baf7a") else INK_TEXT)
            left += share
        ax.text(1.02, i, f"n = {len(Q)}", va="center", fontsize=7, color=MUTED)
    ax.set_yticks(range(len(rows)))
    ax.set_yticklabels(rows, fontsize=8, color=INK_TEXT)
    ax.invert_yaxis()
    ax.set_xlim(0, 1)
    ax.set_xticks([0, 0.5, 1]); ax.set_xticklabels(["0", "50%", "100%"], fontsize=7, color=MUTED)
    for sp_ in ("top", "right", "left"):
        ax.spines[sp_].set_visible(False)
    ax.spines["bottom"].set_color("#bdbab3")
    ax.tick_params(length=0)
    handles = [matplotlib.patches.Patch(color=c, label=n) for n, _, c in CLASS_COLOURS]
    ax.legend(handles=handles, loc="upper left", bbox_to_anchor=(0, -0.1), ncol=2, frameon=False, fontsize=7,
              labelcolor=INK_TEXT)
    ax.set_title("Between two letters, by the sides they turn to each other\n(the left letter's right side → the "
                 "right letter's left side)", fontsize=8, color=INK_TEXT, loc="left")
    named = []
    for p in ("oc", "po", "pp", "op", "ra"):
        v = summary["by_pair"].get(p)
        if v:
            k = v["n"] - v["unclear"]
            named.append(f"{p[0]} + {p[1]}:  bites {v['bitten'] + v['fused']} of {k}"
                         + (f"  (touching {v['touching']})" if v["touching"] else "")
                         + (f"  (linked {v['linked']})" if v["linked"] else ""))
    if named:
        ax.text(0, -0.42, "The pairs in question\n" + "\n".join(named), transform=ax.transAxes, va="top", fontsize=7.2,
                color=INK_TEXT, linespacing=1.6)
    # right: pairs
    ax2 = fig.add_axes([0.6, 0.03, 0.36, 1 - 0.03 - 0.6 / H])
    y = 0
    labels, ys = [], []
    for name, bars, never in groups_r:
        ax2.text(-0.2, y, name, fontsize=7.5, color=INK_TEXT, ha="left", va="center", fontweight="bold",
                 transform=ax2.get_yaxis_transform())
        y += 1
        for p, v in bars:
            ax2.barh(y, v["rate"], color=DATA, height=0.62)
            ax2.text(v["rate"] + 0.015, y, f"{v['rate']:.0%}  (n = {v['n'] - v['unclear']})", va="center",
                     fontsize=6.3, color=MUTED)
            labels.append(p); ys.append(y)
            y += 1
        if never:
            txt = "never: " + ", ".join(f"{p} {v['n'] - v['unclear']}" for p, v in never)
            lines = textwrap.wrap(txt, 70)
            for k, line in enumerate(lines):
                ax2.text(0.0, y + 0.1 + 0.8 * k, line, fontsize=6.3, color=MUTED, va="center", fontfamily="FreeSerif")
            y += 1 + 0.8 * len(lines)
    ax2.set_yticks(ys); ax2.set_yticklabels(labels, fontsize=7.5, color=INK_TEXT, fontfamily="FreeSerif")
    ax2.set_ylim(y - 0.4, -0.8)
    ax2.set_xlim(0, 1.25); ax2.set_xticks([0, 0.5, 1]); ax2.set_xticklabels(["0", "50%", "100%"], fontsize=7, color=MUTED)
    for sp_ in ("top", "right", "left"):
        ax2.spines[sp_].set_visible(False)
    ax2.spines["bottom"].set_color("#bdbab3")
    ax2.tick_params(length=0, pad=4)
    ax2.set_title(f"How often each pair bites (pairs seen at least {min_n} times)", fontsize=8, color=INK_TEXT, loc="left")
    fig.text(0.01, 1 - 0.25 / H, f"Biting in MS 2262: {summary['pairs']} pairs of neighbouring letters on "
             f"{len(summary['pages'])} pages ({', '.join(summary['pages'])})", fontsize=8.5, color=INK_TEXT)
    fig.savefig(path, facecolor=SURFACE)
    plt.close(fig)


EXAMPLE_PAIRS = ["pe", "de", "do", "os", "bo", "ho", "po", "oc", "oe", "op", "pp", "le", "ne", "ar", "at", "ra", "oꝛ", "um"]


def plot_examples(P, pdf_dir, path, per=8):
    """Each pair as written on the page: biting examples first, then the others."""
    rows = [p for p in EXAMPLE_PAIRS if any(q["a"] + q["b"] == p for q in P)]
    fig, axes = plt.subplots(len(rows), per, figsize=(1.0 * per + 0.6, 0.95 * len(rows)), dpi=120, facecolor=SURFACE,
                             squeeze=False)
    imgs = {}
    order = {"bitten": 0, "fused": 1, "touching": 2, "linked": 3, "separate": 4, "unclear": 5}
    for r, p in enumerate(rows):
        Q = [q for q in P if q["a"] + q["b"] == p and q["kind"] != "unclear"]
        bite = [q for q in Q if q["kind"] in BITING]
        rest = [q for q in Q if q["kind"] not in BITING]
        show = (bite[:per // 2] + rest[:per - min(len(bite), per // 2)])[:per]
        if len(show) < per:
            show = (bite + rest)[:per]
        show.sort(key=lambda q: order[q["kind"]])
        for c in range(per):
            ax = axes[r, c]
            ax.axis("off")
            if c >= len(show):
                continue
            q = show[c]
            ax.imshow(page_crop(q, pdf_dir, imgs), interpolation="lanczos")
            col = "#c2410c" if q["kind"] in BITING else MUTED
            ax.set_title(f"{q['kind']} · {q['page']}", fontsize=4.6, color=col, loc="left", pad=1)
        n_b = len(bite)
        axes[r, 0].text(-0.15, 0.5, f"{p}\n{n_b}/{len(Q)}", transform=axes[r, 0].transAxes, ha="right", va="center",
                        fontsize=8, color=INK_TEXT, fontfamily="FreeSerif")
    fig.suptitle("Pairs as the scribe wrote them: biting (bitten: one shared stroke; fused: two strokes run "
                 "together) and not (touching, linked, separate)", fontsize=7.5, color=INK_TEXT, x=0.01, ha="left")
    fig.tight_layout(rect=(0.03, 0, 1, 0.97))
    fig.savefig(path, facecolor=SURFACE)
    plt.close(fig)


def word_text(letters):
    """A found word's letters as the writer spells them (marks after their letter)."""
    out = ""
    for f in letters:
        out += f["char"] + ("\u0304" if "macron" in f["flags"] else "")
    return out


def plot_words(P, pdf_dir, path, n=12):
    """Words with two or more biting pairs, as the scribe wrote them (left) and as the
    writer writes them, biting at the scribe's rates (right)."""
    import find_letters as FL
    import scribe as SC
    import textura as TX
    env = TX.setup()
    found12 = [f for f in env["found"] if f["char"] not in ("\u0304", "\u035b")]
    minim = json.loads((OUT / "hours_minims.json").read_text(encoding="utf-8"))
    w = SC.Scribe(SC.load_letters(), minim, SC.with_book_spacing(SC.fit_spacing(SC.pairs(found12))),
                  SC.minim_offsets(found12), env["slant"], biting=SC.load_biting())
    # words: (page label, line, word) -> its letters, from f. 12r and the read pages
    words = {}
    for f in found12:
        words.setdefault(("f. 12r", "p1/pg-026", f["line"], f["word"]), []).append(dict(f, scale=1.0))
    F = json.loads(FL.FOUND.read_text(encoding="utf-8")) if FL.FOUND.exists() else {}
    for page, d in F.items():
        for f in d["letters"]:
            words.setdefault((f"f. {d['folio']}", page, f["line"], f["word"]), []).append(f)
    bites = {}
    for q in P:
        if q["kind"] in BITING:
            bites[(q["page"], q["line"], q["word"])] = bites.get((q["page"], q["line"], q["word"]), 0) + 1
    cand = []
    for key, L in words.items():
        L = sorted(L, key=lambda f: f["index"])
        if bites.get((key[0], key[2], key[3]), 0) < 2 or any(f["skipped"] for f in L) or not 4 <= len(L) <= 10 \
                or any(not f["char"].isalpha() for f in L):
            continue
        cand.append((key, L))
    # spread over the pages
    by_page = {}
    for key, L in cand:
        by_page.setdefault(key[0], []).append((key, L))
    pick = []
    while len(pick) < n and any(by_page.values()):
        for k in list(by_page):
            if by_page[k] and len(pick) < n:
                pick.append(by_page[k].pop(0))
    fig, axes = plt.subplots(len(pick), 2, figsize=(7.5, 0.95 * len(pick)), dpi=130, facecolor=SURFACE, squeeze=False)
    imgs = {}
    for r, (key, L) in enumerate(pick):
        q = dict(pid=key[1], scale=L[0].get("scale", 1.0), xh=L[0]["xh"], yb=L[0]["yb"], ua=L[0]["u0"], ub=L[-1]["u1"])
        ax = axes[r, 0]
        ax.imshow(page_crop(q, pdf_dir, imgs, pad=(0.3, 0.3)), interpolation="lanczos")
        ax.axis("off")
        ax.set_title(f"{key[0]}, line {key[2]}", fontsize=5.5, color=MUTED, loc="left", pad=1)
        ax = axes[r, 1]
        text = word_text(L)
        g = w.render(w.write(text, 0.0, 0.0, 29.0))
        SC.fill(ax, g)
        ax.set_xlim(-0.4 * 29, max(g.bounds[2] + 0.4 * 29, 6 * 29)); ax.set_ylim(0.75 * 29, -1.85 * 29)
        ax.set_aspect("equal"); ax.axis("off")
        ax.set_title(text, fontsize=6.5, color=MUTED, loc="left", pad=1, fontfamily="FreeSerif")
    fig.suptitle("Words with biting pairs: as the scribe wrote them (left) and as the writer writes them (right)",
                 fontsize=7.5, color=INK_TEXT, x=0.01, ha="left")
    fig.tight_layout(rect=(0, 0, 1, 0.97))
    fig.savefig(path, facecolor=SURFACE)
    plt.close(fig)


def main(pdf_dir):
    P, S, offs = collect(pdf_dir)
    summary = summarise(P)
    summary["writer"] = writer_params(P, summary, offs)
    OUT.mkdir(exist_ok=True)
    keep = ("page", "line", "word", "a", "b", "kind", "gap", "run", "right", "left")
    (OUT / "hours_biting.json").write_text(json.dumps(dict(summary=summary, pairs=[{k: q[k] for k in keep} for q in P]),
                                                      ensure_ascii=False, separators=(",", ":"), default=float),
                                           encoding="utf-8")
    plot_rates(P, summary, OUT / "hours_biting.png")
    plot_examples(P, pdf_dir, OUT / "hours_biting_examples.png")
    plot_words(P, pdf_dir, OUT / "hours_biting_words.png")
    return P, S, summary


if __name__ == "__main__":
    P, S, summary = main(sys.argv[1])
    print(json.dumps({k: summary[k] for k in ("pages", "pairs", "classes", "by_sides")}, indent=1, default=float))
