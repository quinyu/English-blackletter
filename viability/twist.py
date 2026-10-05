"""Twist-and-pull: how the scribe of MS 2262 finishes a word-final n or m.

The last stroke comes down the stem at full width, then curves away down-left while
the scribe keeps pulling and twists the pen, so the width falls away smoothly into a
long hairline. A pen held at a fixed angle cannot draw this: turning down-left, its
narrowest line is still the nib's narrow edge (about 2.4 px here), while the tail ends
at 0.3–1 px.

Two pen motions can thin a line:
  * turning the pen in the plane of the page (its angle), which changes which part of
    the edge faces the direction of travel, and
  * rolling it about its own axis, which lifts one half of the edge off the page until
    only a corner touches ("scale" below: 1 = full edge, towards 0 = corner only).

For three tails on f. 12r this script measures the width (ink across the stroke) and
the direction of travel along a centre-line pulled onto the ink, then solves at every
point for the smallest turn, and only then the roll, that gives the measured width.
Averaged by distance from the end of the stroke, this gives one reusable terminal for
word-final strokes, stored as keyframes for pen.twist_profile.

Run:  python3 twist.py      → out/hours_twist.json, out/hours_twist.png
"""
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from scipy.ndimage import gaussian_filter, gaussian_filter1d

import ink
import nib
import pen

HERE = Path(__file__).resolve().parent
OUT = HERE / "out"
SURFACE, INK_TEXT, MUTED, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#ecebe8"
COLS = ["#2a78d6", "#eb6834", "#1baf7a"]

# Guide curves along the last stroke of three word-final letters (stem top → tail end)
TAILS = {
    "nomen, l. 1": [[406.5, 229], [405.5, 247], [402, 256], [396, 262], [388, 269]],
    "tuum, l. 1": [[541, 229], [539.5, 248], [535, 256], [529, 261], [522, 266]],
    "tuum, l. 22": [[713, 1442], [712.5, 1463], [708, 1471], [701, 1477], [694, 1481]],
}
KEY_FROM_END = [0, 3, 6, 9, 12, 15, 18, 21, 24, 28]   # px before the end of the stroke


def bilinear(img, x, y):
    x0, y0 = int(np.floor(x)), int(np.floor(y))
    fx, fy = x - x0, y - y0
    return ((1 - fx) * (1 - fy) * img[y0, x0] + fx * (1 - fy) * img[y0, x0 + 1]
            + (1 - fx) * fy * img[y0 + 1, x0] + fx * fy * img[y0 + 1, x0 + 1])


def ridge(dark, guide, reach=3.0, iters=3):
    """Pull a smooth guide curve onto the centre of the ink: every sample moves along
    the normal to the darkness-weighted centre within ±reach px, then is smoothed.
    Unlike ink-following, this stays on faint hairlines."""
    sm = gaussian_filter(dark, 0.8)
    P = pen.catmull_rom(np.array(guide, float), step=0.5)
    offs = np.arange(-reach, reach + 0.01, 0.25)
    for _ in range(iters):
        T = np.gradient(P, axis=0)
        T /= np.linalg.norm(T, axis=1, keepdims=True)
        N = np.c_[-T[:, 1], T[:, 0]]
        Q = P.copy()
        for i in range(len(P)):
            v = np.array([bilinear(sm, *(P[i] + o * N[i])) for o in offs])
            v = np.clip(v - v.min(), 0, None)
            if v.sum() > 0:
                Q[i] = P[i] + (offs * v).sum() / v.sum() * N[i]
        P = np.c_[gaussian_filter1d(Q[:, 0], 3, mode="nearest"), gaussian_filter1d(Q[:, 1], 3, mode="nearest")]
    return P


def profile(dark, solid, P):
    """Width (px, from ink mass) and travel direction (deg, y-up) along a centre-line."""
    T = np.gradient(P, axis=0)
    T /= np.linalg.norm(T, axis=1, keepdims=True)
    w, d = [], []
    for i in range(len(P)):
        m = nib.profile_mass(dark, P[i], np.array([-T[i, 1], T[i, 0]]), reach=6.0, step=0.5)
        w.append(np.nan if m is None else m / solid)
        d.append(np.degrees(np.arctan2(-T[i, 1], T[i, 0])) % 360)
    w = np.array(w)
    ok = ~np.isnan(w)
    w = np.interp(np.arange(len(w)), np.nonzero(ok)[0], w[ok])
    seg = np.r_[0, np.cumsum(np.hypot(*np.diff(P, axis=0).T))]
    return gaussian_filter1d(w, 2), np.array(d), seg


def wrap90(a):
    return (a + 90.0) % 180.0 - 90.0


def solve_pen(w, phi, a, b, theta0):
    """Smallest turn of the pen (dθ), then roll (scale), giving width w at direction phi."""
    w0 = nib.nib_model(phi, a, b, theta0)
    if w >= 0.97 * w0:
        return 0.0, 1.0                      # the resting pen is wide enough already
    if w >= b:                               # turning alone can do it
        delta = np.degrees(np.arcsin(np.sqrt(np.clip((w ** 2 - b ** 2) / (a ** 2 - b ** 2), 0, 1))))
        cands = [wrap90(phi - delta - theta0), wrap90(phi + delta - theta0)]
        return min(cands, key=abs), 1.0
    return wrap90(phi - theta0), max(w / b, 0.05)   # edge-on, and rolled onto the corner


def main():
    OUT.mkdir(exist_ok=True)
    rgb = ink.load_rgb(HERE / "data" / "clermont-ms2262-f012r.jpg")
    mask, dark = ink.ink_mask(rgb)
    solid = float(np.percentile(dark[mask > 0], 90))
    pen_fit = json.loads((HERE / "data" / "hours_lines.json").read_text())["pen"]
    a, b, th0 = pen_fit["a"], pen_fit["b"], pen_fit["theta_deg"]

    tails, grid = {}, np.arange(0, 31, 1.0)
    D, K = [], []
    for name, guide in TAILS.items():
        P = ridge(dark, guide)
        w, d, seg = profile(dark, solid, P)
        sol = np.array([solve_pen(wi, di, a, b, th0) for wi, di in zip(w, d)])
        d_end = seg[-1] - seg
        dth = np.interp(grid, d_end[::-1], gaussian_filter1d(sol[:, 0], 2)[::-1])
        sc = np.interp(grid, d_end[::-1], gaussian_filter1d(sol[:, 1], 2)[::-1])
        D.append(dth); K.append(sc)
        tails[name] = {"points": P.tolist(), "width": w.tolist(), "direction": d.tolist(), "arc": seg.tolist()}
    dth_mean = gaussian_filter1d(np.mean(D, axis=0), 1.0)
    sc_mean = np.clip(gaussian_filter1d(np.mean(K, axis=0), 1.0), 0.05, 1.0)
    spec = {"from_end_px": KEY_FROM_END,
            "dtheta": [round(float(np.interp(x, grid, dth_mean)), 1) for x in KEY_FROM_END],
            "scale": [round(float(np.interp(x, grid, sc_mean)), 3) for x in KEY_FROM_END]}
    spec["dtheta"][-1], spec["scale"][-1] = 0.0, 1.0   # the pen is at rest before the terminal begins
    print("twist-and-pull terminal (px before the end → turn, roll):")
    for x, t, k in zip(spec["from_end_px"], spec["dtheta"], spec["scale"]):
        print(f"  {x:4.0f} px  dθ {t:+6.1f}°  contact {k:.2f}")

    # model widths along each tail: fixed pen, abrupt corner switch, twist-and-pull
    fig = plt.figure(figsize=(11, 6.6), dpi=150, facecolor=SURFACE)
    gs = fig.add_gridspec(2, 4, height_ratios=[1.1, 1], hspace=0.45, wspace=0.25)
    ax = fig.add_subplot(gs[0, :2])
    for (name, t), col in zip(tails.items(), COLS):
        seg = np.array(t["arc"]); d_end = seg[-1] - seg
        ax.plot(d_end, t["width"], color=col, lw=2, label=f"ink: {name}")
    t = tails["nomen, l. 1"]
    seg = np.array(t["arc"]); d_end = seg[-1] - seg; phi = np.array(t["direction"])
    fixed = nib.nib_model(phi, a, b, th0)
    dth, sc = pen.twist_profile(np.array(t["points"]), spec)
    twisted = sc * nib.nib_model(phi, a, b, th0 + dth)
    switch = np.where(d_end < 11, pen.CORNER_FRACTION * b, fixed)
    ax.plot(d_end, fixed, color=MUTED, lw=1.4, ls="--", label="pen held still (nomen)")
    ax.plot(d_end, switch, color="#d55181", lw=1.4, ls=":", label="abrupt switch to the corner (previous)")
    ax.plot(d_end, twisted, color=INK_TEXT, lw=1.8, label="twist-and-pull (fitted)")
    ax.set_xlim(45, 0); ax.set_ylim(0, 7)
    ax.set_xlabel("distance before the end of the stroke (px)", color=MUTED, fontsize=8)
    ax.set_ylabel("stroke width (px)", color=MUTED, fontsize=8)
    ax.set_title("Width along the last stroke of word-final n and m", fontsize=9.5, color=INK_TEXT, loc="left")
    ax.legend(frameon=False, fontsize=7, loc="upper right", labelcolor=INK_TEXT)
    ax2 = fig.add_subplot(gs[0, 2:])
    x = np.array(spec["from_end_px"])
    ax2.plot(x, spec["scale"], "o-", color="#6b5bd2", lw=2, label="contact (1 = full edge, 0 = corner)")
    ax2b = ax2.twinx()
    ax2b.plot(x, spec["dtheta"], "s--", color="#eb6834", lw=1.5, label="turn of the pen (°)")
    ax2.set_xlim(30, 0); ax2.set_ylim(0, 1.1)
    ax2.set_xlabel("distance before the end of the stroke (px)", color=MUTED, fontsize=8)
    ax2.set_ylabel("contact", color="#6b5bd2", fontsize=8); ax2b.set_ylabel("turn (°)", color="#eb6834", fontsize=8)
    ax2.set_title("The fitted terminal: roll onto the corner while pulling", fontsize=9.5, color=INK_TEXT, loc="left")
    h1, l1 = ax2.get_legend_handles_labels(); h2, l2 = ax2b.get_legend_handles_labels()
    ax2.legend(h1 + h2, l1 + l2, frameon=False, fontsize=7, loc="lower left", labelcolor=INK_TEXT)
    for axx in (ax, ax2):
        axx.set_facecolor(SURFACE)
        for s_ in ("top", "right"):
            if axx is ax:
                axx.spines[s_].set_visible(False)
        axx.tick_params(colors=MUTED, labelsize=8)
        axx.grid(axis="y", color=GRID, lw=0.8)
    ax2b.tick_params(colors=MUTED, labelsize=8)

    # renderings of the nomen tail
    P = np.array(tails["nomen, l. 1"]["points"])
    rn = pen.Nib(8.12, 3.08, th0)   # the rendering nib used by measure_letters for this page
    x0, x1, y0, y1 = 378, 418, 222, 276
    variants = [("the scribe", None),
                ("pen held still", pen.sweep(pen.catmull_rom(P, 0.5), rn)),
                ("abrupt corner switch", None),
                ("twist-and-pull", None)]
    split = np.searchsorted(-(np.r_[0, np.cumsum(np.hypot(*np.diff(P, axis=0).T))][-1]
                              - np.r_[0, np.cumsum(np.hypot(*np.diff(P, axis=0).T))]), -11)
    import shapely
    variants[2] = ("abrupt corner switch", shapely.union_all([pen.sweep(pen.catmull_rom(P[:split + 1], 0.5), rn),
                                                              pen.sweep(pen.catmull_rom(P[split:], 0.5), pen.corner_nib(rn))]))
    Pd = pen.catmull_rom(P, 0.5)
    dth, sc = pen.twist_profile(Pd, spec)
    variants[3] = ("twist-and-pull", pen.sweep(Pd, rn, dth, sc))
    for k, (title, geom) in enumerate(variants):
        axk = fig.add_subplot(gs[1, k])
        if geom is None:
            axk.imshow(rgb[y0:y1, x0:x1], extent=(x0, x1, y1, y0), interpolation="lanczos")
        else:
            axk.imshow(np.ones((y1 - y0, x1 - x0, 3)), extent=(x0, x1, y1, y0))
            for poly in (geom.geoms if hasattr(geom, "geoms") else [geom]):
                axk.fill(*poly.exterior.xy, color="#2a2118", lw=0)
        axk.set_xlim(x0, x1); axk.set_ylim(y1, y0); axk.set_aspect("equal"); axk.axis("off")
        axk.set_title(title, fontsize=8.5, color=INK_TEXT, loc="left")
    fig.savefig(OUT / "hours_twist.png", facecolor=SURFACE, bbox_inches="tight")
    plt.close(fig)
    (OUT / "hours_twist.json").write_text(json.dumps({"pen": {"a": a, "b": b, "theta_deg": th0}, "terminal": spec,
                                                      "tails": {k: {kk: vv for kk, vv in v.items() if kk != "points"} for k, v in tails.items()}},
                                                     indent=1), encoding="utf-8")
    return spec, tails


if __name__ == "__main__":
    main()
