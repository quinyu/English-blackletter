"""The minim system of MS 2262: i, n, m and u built from one stroke and two kinds of join.

In this hand n and m have no arch across the top. Every upright is its own stroke, a
minim with a lozenge head and foot, and neighbouring minims are linked by hairlines:

  head join   inside n and m: leaves the right side of a minim near mid-height and
              rises to the head of the next
  foot join   inside u, and often into a u: leaves the foot of a minim and rises to
              the middle of the next
  no join     between letters, most of the time; i carries no stroke above it

Instead of tracing letters one at a time, everything is measured on the page and the
letters are rebuilt from the measurements (analysis by synthesis):

1. The minim's shape and the pen are fitted to nine n's and m's at once, by drawing them
   with the page's pen and comparing with the ink mask:
     head_dx, head_dy   where the head stroke starts: left of the stem top / below the x-line
     foot_dx, foot_dy   where the foot stroke ends: right of the stem foot / above the baseline
     nib_scale          width of the pen relative to the page estimate
   Each letter is first registered (shifted up to ±2 px across and ±8 px up or down; the
   guides are straight lines fitted to whole lines and can be a few px off locally).
2. The hairlines are too faint for the ink mask, so they are measured on the darkness
   image: across every gap between two minims in fifteen runs of minim letters, the
   straight line with the darkest ink outside the drawn minims is found, and classified
   as a head join, a foot join or no join.
3. Spacing: stem pitch inside letters and between letters, in x-heights.
4. Word-final letters end in the twist-and-pull tail of twist.py.

The module then rebuilds the n, the m and the final n of 'nomen' (line 1) in
data/traces_hours.json, and writes 'minimum' (a word not on the page) with the scribe's
measured variation.

Run:  python3 minims.py   → out/hours_minims.png/json, out/hours_minimum.png, data/traces_hours.json
"""
import json
from pathlib import Path

import cv2
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from scipy.ndimage import map_coordinates
from scipy.optimize import minimize

import ink
import letterforms as LF
import measure_letters as ML
import pen
import twist

HERE = Path(__file__).resolve().parent
OUT = HERE / "out"
SURFACE, INK_TEXT, MUTED = "#fcfcfb", "#0b0b0b", "#52514e"
DATA, MODEL, HEAD_C, FOOT_C = "#2a78d6", "#eb6834", "#d6293e", "#1baf7a"
NIB_P = ML.PAGES["hours"]["nib_p"]   # corner sharpness of the nib (corners.py)
PEN = {}                              # the page's rendering pen, set by load()

# (letter, word, line, stem centres at the baseline) read with letterforms.line_stems
INSTANCES = [
    ("m", "nomen", 1, [320, 335, 350]), ("m", "nomen", 22, [507, 521, 535]),
    ("m", "mine", 21, [251, 265, 278]), ("m", "dominus", 21, [404, 418, 432]),
    ("m", "manuum", 15, [514, 530, 546]), ("m", "manuum", 15, [696, 712, 728]),
    ("n", "nomen", 1, [264, 277]), ("n", "nomen", 22, [450, 465]), ("n", "mine", 21, [307, 322]),
]
# runs of minim letters: (line, word, [(letter, stem centres)])
RUNS = [
    (1, "nomen", [("n", [264, 277.5])]), (1, "nomen", [("m", [320, 335.5, 350.5])]),
    (1, "nomen", [("n", [389.5, 406])]),
    (1, "tuum", [("u", [442.5, 459]), ("u", [475.5, 492.5]), ("m", [508.5, 523, 540])]),
    (1, "in", [("i", [564.5]), ("n", [580.5, 596])]),
    (1, "vniu", [("n", [648, 665]), ("i", [680.5]), ("u", [698, 714])]),
    (21, "mine", [("m", [251.5, 265.5, 278]), ("i", [292]), ("n", [307.5, 322.5])]),
    (21, "dominus", [("m", [404, 418.5, 433]), ("i", [446.5]), ("n", [462.5, 476.5]), ("u", [492, 505])]),
    (22, "nomen", [("n", [451, 465.5])]), (22, "nomen", [("m", [507.5, 521.5, 535.5])]),
    (22, "nomen", [("n", [569.5, 587])]),
    (22, "tuum", [("u", [623, 637.5]), ("u", [652.5, 668.5]), ("m", [685, 699, 716])]),
    (22, "vniu", [("n", [790, 805]), ("i", [819.5]), ("u", [835.5, 851])]),
    (15, "manuum", [("m", [514.5, 530, 546])]),
    (15, "manuum", [("n", [592.5, 608]), ("u", [626, 642]), ("u", [660.5, 677]), ("m", [697, 712.5, 728.5])]),
]
# word-final letters whose tails twist.py measured: twist.py TAILS key → (line, last stem centre)
TAIL_SOURCES = {"nomen, l. 1": (1, 405.5), "tuum, l. 1": (1, 540.0), "tuum, l. 22": (22, 716.0)}
MINIMS = {"i": 1, "n": 2, "u": 2, "m": 3}

PARAMS = ["head_dx", "head_dy", "foot_dx", "foot_dy", "nib_scale"]
START = [0.085, 0.05, 0.10, 0.02, 1.0]
LO = [0.0, 0.0, 0.0, -0.05, 0.7]
HI = [0.25, 0.2, 0.3, 0.15, 1.3]
FIT_JOIN = (0.45, "head")   # head join used while fitting the minim; the joins are measured in step 2
CONTRAST_MIN = 10.0       # darkness above the gap's background for a hairline to count as present


def minim_points(s, yb, xh, slant, p):
    hx, hy, fx, fy = [v * xh for v in p[:4]]
    t = np.tan(np.radians(slant))
    at = lambda y: s + (yb - y) * t
    yx = yb - xh
    return [[at(yx) - hx, yx + hy], [at(yx + 0.15 * xh), yx + 0.15 * xh],
            [at(yb - 0.15 * xh), yb - 0.15 * xh], [s + fx, yb - fy]]


def join_points(a, b, yb, xh, slant, h0, h1):
    t = np.tan(np.radians(slant))
    return [[a + h0 * xh * t, yb - h0 * xh], [b + h1 * xh * t, yb - h1 * xh]]


def module_strokes(stems, yb, xh, slant, p, joins=None, tail=None):
    """Strokes (name, points, pen spec or None) in writing order. joins: one (h0, h1) or
    None per gap, in x-heights above the baseline at the two stem centres; h1 = "head"
    runs the hairline into the start of the next minim's head stroke. tail: points in
    x-heights relative to the last stem ((x - stem) / xh, height / xh) that replace its
    foot."""
    joins = [FIT_JOIN] * (len(stems) - 1) if joins is None else joins
    out = []
    for i, s in enumerate(stems):
        m = minim_points(s, yb, xh, slant, p)
        if i > 0 and joins[i - 1] is not None:
            h0, h1 = joins[i - 1]
            a = join_points(stems[i - 1], s, yb, xh, slant, h0, 0 if h1 == "head" else h1)
            out.append(("hairline join", [a[0], m[0]] if h1 == "head" else a, None))
        if tail is not None and i == len(stems) - 1:
            m = m[:2] + [[s + u * xh, yb - v * xh] for u, v in tail]
        out.append(("minim", m, None))
    return out


def load():
    """Page, ink mask, line guides and darkness, with PEN set to the page's nib."""
    rgb, mask, lines = LF.load_page("hours")
    the_nib, _ = ML.page_nib(json.loads((HERE / "data" / "hours_lines.json").read_text(encoding="utf-8")), mask, NIB_P)
    PEN.update(a=the_nib.a, b=the_nib.b, theta=the_nib.theta, p=the_nib.p)
    return rgb, mask, lines, ink.ink_darkness(rgb).astype(float)


def nib_for(p):
    return pen.Nib(PEN["a"] * p[-1], PEN["b"] * p[-1], PEN["theta"], p=PEN["p"])


def render_strokes(st, p, tail_spec=None):
    pens = [tail_spec if (tail_spec and k == len(st) - 1) else spec for k, (_, _, spec) in enumerate(st)]
    return pen.render([s for _, s, _ in st], nib_for(p), step=0.5, names=[n for n, _, _ in st], pens=pens)


def render_letter(stems, yb, xh, slant, p, joins=None):
    return render_strokes(module_strokes(stems, yb, xh, slant, p, joins), p)


def instance_box(stems, yb, xh):
    return (int(stems[0] - 0.42 * xh), int(yb - 1.25 * xh), int(stems[-1] + 0.45 * xh), int(yb + 0.25 * xh))


def score(geom, mask, box):
    x0, y0, x1, y1 = box
    ink_ = mask[y0:y1, x0:x1] > 0
    model = pen.rasterize(geom, ink_.shape, origin=(x0, y0)) > 0
    return float((ink_ & model).sum() / max(1, (ink_ | model).sum()))


def outline_distance(geom, mask, box):
    x0, y0, x1, y1 = box
    ink_ = (mask[y0:y1, x0:x1] > 0).astype(np.uint8)
    model = pen.rasterize(geom, ink_.shape, origin=(x0, y0))

    def edge(m):
        return (m > 0) & (cv2.erode(m, np.ones((3, 3), np.uint8)) == 0)
    eo, em = edge(ink_), edge(model)
    do = cv2.distanceTransform((~eo).astype(np.uint8), cv2.DIST_L2, 5)
    dm = cv2.distanceTransform((~em).astype(np.uint8), cv2.DIST_L2, 5)
    return float(0.5 * (do[em].mean() + dm[eo].mean()))


def register(i, p, mask, xs=np.arange(-2, 2.01, 0.5), ys=np.arange(-8, 8.01, 0.5)):
    """Shift letter i (its stems and baseline) to where the module drawn with p overlaps the ink best."""
    g = render_letter(i["stems"], i["yb"], i["xh"], i["slant"], p)
    x0, y0, x1, y1 = i["box"]
    ink_ = mask[y0:y1, x0:x1] > 0
    best = (-1.0, 0.0, 0.0)
    for dy in ys:
        for dx in xs:
            m = pen.rasterize(g, ink_.shape, origin=(x0 - dx, y0 - dy)) > 0
            best = max(best, ((ink_ & m).sum() / max(1, (ink_ | m).sum()), dx, dy))
    _, dx, dy = best
    i["stems"] = [s + dx for s in i["stems"]]
    i["yb"] += dy
    i["shift"] = [i["shift"][0] + dx, i["shift"][1] + dy]


def make_instance(lines, n, stems, **kw):
    l = [l for l in lines if l["n"] == n][0]
    yb, xh = LF.guide(l, float(np.mean(stems)))
    return dict(kw, line=n, stems=list(stems), yb=yb, xh=xh, slant=l["slant_deg"] or 0.0,
                box=instance_box(stems, yb, xh), shift=[0.0, 0.0])


# ---- step 1: the minim's shape and the pen ---------------------------------------------

def fit_minim(inst, mask):
    def loss(x):
        p = np.clip(x, LO, HI)
        return 1.0 - np.mean([score(render_letter(i["stems"], i["yb"], i["xh"], i["slant"], p), mask, i["box"])
                              for i in inst])
    start = 1 - loss(START)
    p, nfev = np.array(START), 0
    for iters in [260, 150]:
        for i in inst:
            register(i, p, mask)
        res = minimize(loss, p, method="Nelder-Mead", options=dict(maxiter=iters, xatol=2e-3, fatol=1e-4))
        p, nfev = np.clip(res.x, LO, HI), nfev + res.nfev
    return p, dict(start=start, fitted=1 - res.fun, renderings=nfev)


# ---- step 2: the hairlines -------------------------------------------------------------

H0 = np.arange(-0.1, 0.91, 0.025)
H1 = np.arange(0.1, 1.11, 0.025)


def measure_gaps(run, p, dark):
    """For each gap between neighbouring minims: the straight line (h0 at the left stem,
    h1 at the right, in x-heights) with the darkest ink outside the drawn minims."""
    stems, yb, xh, slant = run["stems"], run["yb"], run["xh"], run["slant"]
    st = [s for nm, s, _ in module_strokes(stems, yb, xh, slant, p) if nm == "minim"]
    g = pen.render(st, nib_for(p), step=0.5)
    x0, y0, x1, y1 = run["box"]
    body = cv2.dilate(pen.rasterize(g, (y1 - y0, x1 - x0), origin=(x0, y0)), np.ones((3, 3), np.uint8)) > 0
    inside = lambda xs, ys: body[np.clip(np.round(ys - y0).astype(int), 0, body.shape[0] - 1),
                                 np.clip(np.round(xs - x0).astype(int), 0, body.shape[1] - 1)]
    labels = [(ch, k) for ch, ss in run["letters"] for k in range(len(ss))]
    gaps = []
    for k in range(len(stems) - 1):
        a, b = stems[k], stems[k + 1]
        (c0, _), (c1, k1) = labels[k], labels[k + 1]
        best = (-1e9, None, None)
        for h0 in H0:
            for h1 in H1:
                (xa, ya), (xb, yb_) = join_points(a, b, yb, xh, slant, h0, h1)
                m = int(np.hypot(xb - xa, yb_ - ya) / 0.5) + 1
                xs, ys = np.linspace(xa, xb, m), np.linspace(ya, yb_, m)
                out = ~inside(xs, ys)
                if out.sum() < 8:
                    continue
                v = float(map_coordinates(dark, [ys[out], xs[out]], order=1).mean())
                best = max(best, (v, h0, h1))
        GX, GY = np.meshgrid(np.arange(int(a), int(b) + 1), np.arange(int(yb - xh), int(yb) + 1))
        sel = ~inside(GX.astype(float), GY.astype(float))
        bg = float(np.median(dark[GY[sel], GX[sel]]))
        within = k1 > 0
        context = ("inside " + ("u" if c1 == "u" else "n, m")) if within else ("into u" if c1 == "u" else "between")
        gaps.append(dict(line=run["line"], word=run["word"], pair=c0 if within else f"{c0}{c1}", context=context,
                         pitch_xh=float((b - a) / xh), h0=float(best[1]), h1=float(best[2]),
                         contrast=float(best[0] - bg), a=float(a), b=float(b)))
    return gaps


def classify(g):
    if g["contrast"] < CONTRAST_MIN:
        return "none"
    if 0.25 <= g["h0"] <= 0.75 and g["h1"] >= 0.85:
        return "head"
    if g["h0"] <= 0.2 and 0.35 <= g["h1"] <= 0.8:
        return "foot"
    return "none"


def join_rules(gaps):
    for g in gaps:
        g["join"] = classify(g)
    rq = lambda v: float(np.subtract(*np.percentile(v, [75, 25])) / 1.349)   # robust sd
    rules = {}
    for kind in ("head", "foot"):
        G = [g for g in gaps if g["join"] == kind]
        h0, h1 = np.array([g["h0"] for g in G]), np.array([g["h1"] for g in G])
        rules[kind] = dict(h0=float(np.median(h0)), h1=float(np.median(h1)), n=len(G), h0_sd=rq(h0), h1_sd=rq(h1))
    table = {}
    for ctx in ("inside n, m", "inside u", "into u", "between"):
        G = [g for g in gaps if g["context"] == ctx]
        table[ctx] = {k: sum(g["join"] == k for g in G) for k in ("head", "foot", "none")}
    rules["contexts"] = table
    # between letters: how often the scribe links them
    rules["into_u_rate"] = table["into u"]["foot"] / max(1, sum(table["into u"].values()))
    rules["between_rate"] = table["between"]["head"] / max(1, sum(table["between"].values()))
    intra = np.array([g["pitch_xh"] for g in gaps if g["context"].startswith("inside")])
    inter = np.array([g["pitch_xh"] for g in gaps if not g["context"].startswith("inside")])
    rules["pitch"] = dict(inside=float(np.median(intra)), inside_sd=rq(intra), n_inside=len(intra),
                          between=float(np.median(inter)), between_sd=rq(inter), n_between=len(inter))
    return rules


# ---- step 4: the word-final tail -------------------------------------------------------

def tail_template(lines, dark):
    """Mean of the three tails twist.py measured (centre-lines pulled onto the ink by
    twist.ridge), relative to their last stem, from 0.35 x-height above the baseline down."""
    by_n = {l["n"]: l for l in lines}
    res = []
    for key, (n, s) in TAIL_SOURCES.items():
        P = twist.ridge(dark, twist.TAILS[key])
        yb, xh = LF.guide(by_n[n], s)
        U, V = (P[:, 0] - s) / xh, (yb - P[:, 1]) / xh
        keep = V <= 0.35
        U, V = U[keep], V[keep]
        arc = np.r_[0, np.cumsum(np.hypot(np.diff(U), np.diff(V)))]
        q = np.linspace(0, arc[-1], 30)
        res.append(np.c_[np.interp(q, arc, U), np.interp(q, arc, V)])
    return np.mean(res, axis=0)[::2].tolist()


def tail_spec(xh, ref_xh=29.4):
    """The twist-and-pull terminal of twist.py, scaled to x-height xh."""
    spec = json.loads((OUT / "hours_twist.json").read_text(encoding="utf-8"))["terminal"]
    return dict(spec, from_end_px=[v * xh / ref_xh for v in spec["from_end_px"]])


# ---- writing a word --------------------------------------------------------------------

def write_word(word, x0, yb, xh, slant, p, rules, tail, rng=None):
    """Strokes for a word of minim letters (i, n, m, u). With rng, stem pitch, join heights
    and whether letters are linked are drawn from the distributions measured on the page;
    without, the medians are used and letters are linked when the scribe usually links them."""
    P, H, F = rules["pitch"], rules["head"], rules["foot"]
    jit = (lambda mu, sd: mu + sd * rng.standard_normal()) if rng is not None else (lambda mu, sd: mu)
    chance = (lambda rate: rng.random() < rate) if rng is not None else (lambda rate: rate >= 0.5)
    stems, joins, x = [], [], x0
    for ch in word:
        for k in range(MINIMS[ch]):
            if stems:
                inside = k > 0
                x += xh * (jit(P["inside"], P["inside_sd"]) if inside else jit(P["between"], P["between_sd"]))
                head = (jit(H["h0"], H["h0_sd"]), "head")
                foot = (jit(F["h0"], F["h0_sd"]), jit(F["h1"], F["h1_sd"]))
                if ch == "u":
                    joins.append(foot if inside or chance(rules["into_u_rate"]) else None)
                else:
                    joins.append(head if inside or chance(rules["between_rate"]) else None)
            stems.append(x)
    return module_strokes(stems, yb, xh, slant, p, joins, tail)


# ---- traces ----------------------------------------------------------------------------

FINAL_N_STEMS = [388.5, 405.5]   # final n of 'nomen', line 1 (line_stems columns)


def rebuild_traces(p, inst, lines, rules, tail):
    """Rewrite the n, m and final n of 'nomen' (line 1) in data/traces_hours.json from the module."""
    path = HERE / "data" / "traces_hours.json"
    traces = json.loads(path.read_text(encoding="utf-8"))
    by_id = {t["id"]: t for t in traces["instances"]}
    l1 = [l for l in lines if l["n"] == 1][0]
    slant = l1["slant_deg"] or 0.0
    head = (rules["head"]["h0"], "head")
    r = lambda pts: [[round(float(x), 2), round(float(y), 2)] for x, y in pts]

    def put(tid, stems, yb, xh, tail=None, spec=None):
        st = module_strokes(stems, yb, xh, slant, p, [head] * (len(stems) - 1), tail)
        strokes = [dict(name=n, clicks=r(pts), points=r(pts), fixed=True, **({"pen": sp} if sp else {}))
                   for n, pts, sp in st]
        if spec:
            strokes[-1]["pen"], strokes[-1]["name"] = spec, "minim and tail"
        t = by_id[tid]
        t["strokes"] = strokes
        allp = np.array([q for s_ in strokes for q in s_["points"]])
        pad = 0.5 * PEN["a"] * p[-1]
        t["bbox"] = [int(allp[:, 0].min() - pad), int(allp[:, 1].min() - pad), int(allp[:, 0].max() + pad) + 1,
                     int(allp[:, 1].max() + pad) + 1]

    n1 = [i for i in inst if i["ch"] == "n" and i["line"] == 1][0]
    m1 = [i for i in inst if i["ch"] == "m" and i["line"] == 1][0]
    put("1.0", n1["stems"], n1["yb"], n1["xh"])
    put("1.2", m1["stems"], m1["yb"], m1["xh"])
    yb, xh = LF.guide(l1, float(np.mean(FINAL_N_STEMS)))
    put("1.4", FINAL_N_STEMS, yb, xh, tail=tail, spec=tail_spec(xh))
    traces["note"] = (
        "Seed traces: 'nomen' (line 1), in writing order. o and e were clicked on the ink with ink-following "
        "between clicks. n and m are built from the minim module of minims.py: in this hand they have no arch; "
        "every upright is a separate minim with a lozenge head and foot, and inside n and m a hairline leaves "
        "the right side of one minim near mid-height and rises to the head of the next (the minim's shape is "
        "fitted to nine n's and m's, the hairline measured on the page; 'fixed' = drawn from the module, not "
        "ink-following). Textura e is back (head, stem, foot), a top stroke out to the right, and a hairline "
        "back down-left to the stem. Strokes named 'hairline…' are drawn with the pen's corner "
        "(pen.is_corner_stroke). The final n's last minim ends in a tail drawn by twisting the pen onto its "
        "corner while pulling ('pen' = the twist-and-pull terminal fitted by twist.py; the tail is the mean of "
        "the three tails twist.py measured).")
    path.write_text(json.dumps(traces, ensure_ascii=False, indent=1), encoding="utf-8")


# ---- figures ---------------------------------------------------------------------------

def show_ink_vs_model(ax_img, ax_cmp, rgb, mask, box, geom):
    x0, y0, x1, y1 = box
    ink_ = mask[y0:y1, x0:x1] > 0
    model = pen.rasterize(geom, ink_.shape, origin=(x0, y0)) > 0
    ax_img.imshow(rgb[y0:y1, x0:x1], interpolation="lanczos")
    vis = np.ones(ink_.shape + (3,))
    vis[ink_ & ~model] = matplotlib.colors.to_rgb(DATA)
    vis[model & ~ink_] = matplotlib.colors.to_rgb(MODEL)
    vis[model & ink_] = (0.1, 0.1, 0.1)
    ax_cmp.imshow(vis, interpolation="nearest")
    for a in (ax_img, ax_cmp):
        a.axis("off")


def draw(ax, geom, box, scale=4):
    x0, y0, x1, y1 = box
    m = pen.rasterize(geom, ((y1 - y0) * scale, (x1 - x0) * scale), origin=(x0, y0), scale=scale) > 0
    img = np.ones(m.shape + (3,))
    img[m] = (0.16, 0.13, 0.09)
    ax.imshow(img, interpolation="antialiased")
    ax.axis("off")


def plot_fit(rgb, mask, inst, p, old_geom, path):
    n = len(inst) + 1
    fig, axes = plt.subplots(3, n, figsize=(1.55 * n, 4.9), dpi=170, facecolor=SURFACE)
    cols = [("previous trace", inst[0], old_geom)] + [
        (f"{i['ch']} · {i['word']} l.{i['line']}", i, render_letter(i["stems"], i["yb"], i["xh"], i["slant"], p, i["joins"]))
        for i in inst]
    for k, (title, i, geom) in enumerate(cols):
        show_ink_vs_model(axes[0, k], axes[1, k], rgb, mask, i["box"], geom)
        draw(axes[2, k], geom, i["box"])
        axes[0, k].set_title(title, fontsize=6.5, color=MODEL if k == 0 else INK_TEXT, loc="left")
        axes[1, k].set_title(f"overlap {score(geom, mask, i['box']):.0%}", fontsize=6.5, color=MUTED, loc="left")
    axes[2, 0].set_title("drawn", fontsize=6.5, color=MUTED, loc="left")
    axes[2, 1].set_title("drawn by the module", fontsize=6.5, color=MUTED, loc="left")
    handles = [matplotlib.patches.Patch(color=(0.1, 0.1, 0.1), label="model and ink agree"),
               matplotlib.patches.Patch(color=DATA, label="ink the model misses"),
               matplotlib.patches.Patch(color=MODEL, label="model where there is no ink")]
    fig.legend(handles=handles, loc="lower center", ncol=3, frameon=False, fontsize=7, labelcolor=INK_TEXT)
    fig.suptitle("n and m built from one fitted minim module (minim + hairline join), against the scribe's letters",
                 fontsize=9, color=INK_TEXT, x=0.01, ha="left")
    fig.tight_layout(rect=(0, 0.04, 1, 0.95))
    fig.savefig(path, facecolor=SURFACE)
    plt.close(fig)


def plot_minimum(rgb, runs, gaps, p, rules, tail, path):
    """Top: two runs from the page with the measured hairlines drawn over them, beside the
    same letters written by the module. Bottom: 'minimum', plain and with variation."""
    fig = plt.figure(figsize=(10, 7.4), dpi=170, facecolor=SURFACE)
    gs = fig.add_gridspec(4, 2, height_ratios=[1, 1, 1.05, 1.05], hspace=0.45, wspace=0.08)
    for row, (word, n) in enumerate([("dominus", 21), ("tuum", 1)]):
        run = [r for r in runs if r["word"] == word and r["line"] == n][0]
        G = [g for g in gaps if g["word"] == word and g["line"] == n]
        xh, yb = run["xh"], run["yb"]
        x0, y0, x1, y1 = int(run["stems"][0] - 0.5 * xh), int(yb - 1.25 * xh), int(run["stems"][-1] + 0.6 * xh), int(yb + 0.5 * xh)
        ax = fig.add_subplot(gs[row, 0])
        ax.imshow(rgb[y0:y1, x0:x1], interpolation="lanczos", extent=(x0, x1, y1, y0))
        for g in G:
            if g["join"] != "none":
                (xa, ya), (xb, yb_) = join_points(g["a"], g["b"], yb, xh, run["slant"], g["h0"], g["h1"])
                ax.plot([xa, xb], [ya, yb_], color=HEAD_C if g["join"] == "head" else FOOT_C, lw=1.4, alpha=0.9)
        ax.set_xlim(x0, x1); ax.set_ylim(y1, y0); ax.axis("off")
        letters = "".join(ch for ch, _ in run["letters"])
        ax.set_title(f"page, line {n}, '{word}': the letters {letters}, with the hairlines found",
                     fontsize=7, color=INK_TEXT, loc="left")
        final = word.endswith(letters)
        st = write_word(letters, run["stems"][0], yb, xh, run["slant"], p, rules, tail if final else None)
        ax2 = fig.add_subplot(gs[row, 1])
        draw(ax2, render_strokes(st, p, tail_spec(xh) if final else None), (x0, y0, x1, y1))
        ax2.set_title(f"written by the module: '{letters}'" + (" (word-final: tail)" if final else ""),
                      fontsize=7, color=INK_TEXT, loc="left")
    xh, yb, slant = 29.0, 0.0, float(np.median([r["slant"] for r in runs]))
    rngs = [None, np.random.default_rng(7), np.random.default_rng(11), np.random.default_rng(23)]
    titles = ["'minimum', medians, no variation", "with the scribe's variation (seed 7)", "seed 11", "seed 23"]
    for k, rng in enumerate(rngs):
        st = write_word("minimum", 0.0, yb, xh, slant, p, rules, tail, rng)
        xs = [q[0] for _, s, _ in st for q in s]
        box = (int(min(xs) - 0.4 * xh), int(yb - 1.3 * xh), int(max(xs) + 0.5 * xh), int(yb + 0.6 * xh))
        ax = fig.add_subplot(gs[2 + k // 2, k % 2])
        draw(ax, render_strokes(st, p, tail_spec(xh)), box)
        ax.set_title(titles[k], fontsize=7, color=INK_TEXT, loc="left")
    fig.text(0.01, 0.015, "Red: head join (mid-height → next head, inside n and m). Green: foot join (foot → middle "
             "of the next, inside u and into u). Between other letters the scribe mostly lifts the pen; i has no "
             "stroke above it on this page.", fontsize=6.5, color=MUTED)
    fig.suptitle("Minim letters from measured rules: the page's own letters, and a word it does not contain",
                 fontsize=9, color=INK_TEXT, x=0.01, ha="left")
    fig.savefig(path, facecolor=SURFACE, bbox_inches="tight")
    plt.close(fig)


def main():
    OUT.mkdir(exist_ok=True)
    rgb, mask, lines, dark = load()

    # 1. the minim and the pen
    inst = [make_instance(lines, n, stems, ch=ch, word=word) for ch, word, n, stems in INSTANCES]
    p, fit = fit_minim(inst, mask)
    print(f"minim fit: mean overlap {fit['start']:.3f} at the start, {fit['fitted']:.3f} fitted "
          f"({fit['renderings']} renderings)")
    for k, v in zip(PARAMS, p):
        print(f"  {k:10s} {v:.3f}")
    print("  shifts (dx, dy px): " + ", ".join(f"{i['word']} l.{i['line']} {i['shift'][0]:+.1f},{i['shift'][1]:+.1f}"
                                              for i in inst))

    # 2–3. the hairlines and the spacing
    runs, gaps = [], []
    for n, word, letters in RUNS:
        r = make_instance(lines, n, [s for _, ss in letters for s in ss], word=word, letters=letters)
        register(r, p, mask)
        runs.append(r)
        gaps += measure_gaps(r, p, dark)
    rules = join_rules(gaps)
    print(f"hairlines across {len(gaps)} gaps (present = darker than the gap by ≥ {CONTRAST_MIN:.0f}):")
    for ctx, c in rules["contexts"].items():
        print(f"  {ctx:12s} head {c['head']:2d}  foot {c['foot']:2d}  none {c['none']:2d}")
    H, F, P = rules["head"], rules["foot"], rules["pitch"]
    for name, J in (("head", H), ("foot", F)):
        print(f"  {name} join {J['h0']:.2f} → {J['h1']:.2f} x-height (±{J['h0_sd']:.2f}, ±{J['h1_sd']:.2f}; n={J['n']})")
    print(f"  pitch inside letters {P['inside']:.3f} ± {P['inside_sd']:.3f} x-height (n={P['n_inside']}), "
          f"between letters {P['between']:.3f} ± {P['between_sd']:.3f} (n={P['n_between']})")

    # the n's and m's with the measured head join
    head = (H["h0"], "head")
    per = []
    for i in inst:
        i["joins"] = [head] * (len(i["stems"]) - 1)
        g = render_letter(i["stems"], i["yb"], i["xh"], i["slant"], p, i["joins"])
        per.append(dict(letter=i["ch"], word=i["word"], line=i["line"], shift_px=i["shift"],
                        overlap=score(g, mask, i["box"]), outline_px=outline_distance(g, mask, i["box"])))
    old_m = json.loads((HERE / "data" / "hours_m_hand_trace.json").read_text(encoding="utf-8"))
    old_geom = pen.render([s["points"] for s in old_m["strokes"]], nib_for([1.0]),
                          step=0.25, names=[s["name"] for s in old_m["strokes"]])
    old = dict(overlap=score(old_geom, mask, inst[0]["box"]), outline_px=outline_distance(old_geom, mask, inst[0]["box"]))
    print(f"m of nomen (l.1): hand trace overlap {old['overlap']:.2f}, outline {old['outline_px']:.2f} px; "
          f"module {per[0]['overlap']:.2f}, {per[0]['outline_px']:.2f} px")

    tail = tail_template(lines, dark)
    plot_fit(rgb, mask, inst, p, old_geom, OUT / "hours_minims.png")
    plot_minimum(rgb, runs, gaps, p, rules, tail, OUT / "hours_minimum.png")
    (OUT / "hours_minims.json").write_text(json.dumps({
        "module": dict(zip(PARAMS, map(float, p))), "pen": PEN, "fit": fit, "letters": per,
        "previous_trace_m_nomen_l1": old, "rules": rules, "tail": tail, "gaps": gaps}, indent=1), encoding="utf-8")
    rebuild_traces(p, inst, lines, rules, tail)


if __name__ == "__main__":
    main()
