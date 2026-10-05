"""Line guides, slant and pen for a Latin minuscule page, found from the ink alone.

For every written line this finds:
  * the baseline and the x-height line (straight lines, so a slight slope is kept),
  * how far ascenders rise and descenders drop below, in x-heights,
  * the slant of the upright strokes (degrees from vertical, positive = top to the right).
It also fits the nib (width against direction) over the whole text block.

Run:  python3 latin_lines.py      → data/lucretius_lines.json, out/latin_*.png
"""
import json
from pathlib import Path

import cv2
import numpy as np
from scipy.ndimage import uniform_filter1d
from scipy.signal import find_peaks
from scipy.spatial import cKDTree
from skimage.morphology import skeletonize

import ink
import nib

HERE = Path(__file__).resolve().parent
IMAGE = "lucretius-drn-1r.jpg"
# Text block of the scan (page pixels): excludes the binding, page edges and the ex-libris.
BLOCK = dict(x0=140, x1=900, y0=200, y1=1570)


def line_bands(mask, block, min_gap=28):
    """Rows where text lines sit: peaks of the horizontal ink profile."""
    sub = mask[block["y0"]:block["y1"], block["x0"]:block["x1"]]
    prof = uniform_filter1d(sub.sum(1).astype(float), 5)
    peaks, _ = find_peaks(prof, distance=min_gap, height=0.25 * prof.max())
    return [int(p + block["y0"]) for p in peaks], prof


def fit_guides(mask, y_peak, x0, x1, half=26, chunk=90):
    """Baseline and x-height line for one text line.

    The ink profile of a line of minuscule has a dense plateau between the x-height
    line and the baseline (every letter has ink there) and thin tails above and below
    (only ascenders and descenders). The plateau edges are where the profile falls
    below half its height. This is done in horizontal chunks and a straight line is
    fitted through the chunk edges, so a sloping line is followed.
    """
    xs_b, ys_b, xs_x, ys_x = [], [], [], []
    for cx in range(x0, x1 - chunk // 2, chunk // 2):
        sub = mask[y_peak - half: y_peak + half, cx: cx + chunk]
        if sub.sum() < 40:
            continue
        prof = uniform_filter1d(sub.sum(1).astype(float), 3)
        k = int(np.argmax(prof))
        level = 0.5 * prof[k]
        lo = k
        while lo > 0 and prof[lo - 1] >= level:
            lo -= 1
        hi = k
        while hi < len(prof) - 1 and prof[hi + 1] >= level:
            hi += 1
        xs_x.append(cx + chunk / 2); ys_x.append(y_peak - half + lo)
        xs_b.append(cx + chunk / 2); ys_b.append(y_peak - half + hi + 1)
    if len(xs_b) < 2:
        return None

    def robust_line(xs, ys):
        xs, ys = np.array(xs), np.array(ys)
        keep = np.ones(len(xs), bool)
        for _ in range(3):
            a, b = np.polyfit(xs[keep], ys[keep], 1)
            r = ys - (a * xs + b)
            s = max(1.0, 1.4826 * np.median(np.abs(r[keep])))
            keep = np.abs(r) <= 2.5 * s
            if keep.sum() < 2:
                keep[:] = True
                break
        return float(a), float(b)

    ab = robust_line(xs_b, ys_b)
    ax = robust_line(xs_x, ys_x)
    # keep the two guides parallel: share the baseline's slope
    bx = float(np.median(np.array(ys_x) - ab[0] * np.array(xs_x)))
    return {"baseline": ab, "xline": (ab[0], bx)}


def extents(mask, g, x0, x1, xh, prev_base=None, next_xline=None):
    """Ascender and descender reach, in x-heights above the baseline / below it.

    Works on connected strokes, not columns: ascenders of this line and descenders
    of the line above share the same strip of page, so a stroke only counts as an
    ascender if it is attached to this line's x-band, and it is dropped if it runs
    on into the neighbouring line (it can't be measured then).
    """
    yb = lambda x: g["baseline"][0] * x + g["baseline"][1]
    yx = lambda x: g["xline"][0] * x + g["xline"][1]
    top = int(min(yx(x0), yx(x1)) - 2.8 * xh)
    bot = int(max(yb(x0), yb(x1)) + 2.4 * xh)
    sub = mask[max(top, 0):bot, x0:x1].astype(np.uint8)
    n, lab, stats, _ = cv2.connectedComponentsWithStats(sub, connectivity=8)
    ups, downs = [], []
    for i in range(1, n):
        ys, xs = np.nonzero(lab == i)
        X = xs + x0; Y = ys + max(top, 0)
        in_band = (Y >= yx(X) + 1) & (Y <= yb(X) - 1)
        if not in_band.any():
            continue
        k_top, k_bot = np.argmin(Y), np.argmax(Y)
        rise = (yb(X[k_top]) - Y[k_top]) / xh
        drop = (Y[k_bot] - yb(X[k_bot])) / xh
        if prev_base is not None and Y[k_top] <= prev_base(X[k_top]):
            rise = np.nan  # merged with the line above
        if next_xline is not None and Y[k_bot] >= next_xline(X[k_bot]):
            drop = np.nan  # merged with the line below
        if rise > 1.5:
            ups.append(rise)
        if drop > 0.5:
            downs.append(drop)
    q = lambda v: float(np.median(v)) if len(v) >= 2 else float("nan")
    return q(ups), q(downs), len(ups), len(downs)


def line_slant(mask, g, x0, x1, xh, radius=6):
    """Median slant of near-upright strokes on this line, from the skeleton."""
    ytop = int(min(g["xline"][1] + g["xline"][0] * x for x in (x0, x1)) - 1.4 * xh)
    ybot = int(max(g["baseline"][1] + g["baseline"][0] * x for x in (x0, x1)) + 1.4 * xh)
    sub = mask[max(ytop, 0):ybot, x0:x1] > 0
    sk = skeletonize(sub)
    ys, xs = np.nonzero(sk)
    if len(xs) < 50:
        return float("nan"), 0
    pts = np.c_[xs, ys].astype(float)
    tree = cKDTree(pts)
    angles = []
    for i, nb in enumerate(tree.query_ball_point(pts, radius)):
        if len(nb) < 2 * radius - 1:
            continue
        P = pts[nb] - pts[nb].mean(0)
        ev, V = np.linalg.eigh(P.T @ P)
        if ev[1] < 6 * max(ev[0], 1e-9):
            continue
        dx, dy = V[:, 1]
        if dy < 0:
            dx, dy = -dx, -dy
        a = np.degrees(np.arctan2(-dx, dy))  # from vertical; top to the right is positive
        if abs(a) < 35:
            angles.append(a)
    return (float(np.median(angles)) if angles else float("nan")), len(angles)


def analyse(path=HERE / "data" / IMAGE):
    rgb = ink.load_rgb(path)
    mask, _ = ink.ink_mask(rgb)
    peaks, _ = line_bands(mask, BLOCK)
    lines, guides = [], []
    for y in peaks:
        # horizontal extent of this line's ink
        band = mask[y - 10: y + 10, BLOCK["x0"]:BLOCK["x1"]]
        cols = np.nonzero(band.sum(0) > 0)[0]
        if len(cols) < 20:
            continue
        x0, x1 = int(cols.min() + BLOCK["x0"]), int(cols.max() + BLOCK["x0"])
        g = fit_guides(mask, y, x0, x1)
        if g is None:
            continue
        xm = (x0 + x1) / 2
        xh = (g["baseline"][0] * xm + g["baseline"][1]) - (g["xline"][0] * xm + g["xline"][1])
        slant, n_sl = line_slant(mask, g, x0, x1, xh)
        guides.append(g)
        lines.append({
            "x0": x0, "x1": x1,
            "baseline": [[x0, g["baseline"][0] * x0 + g["baseline"][1]], [x1, g["baseline"][0] * x1 + g["baseline"][1]]],
            "xline": [[x0, g["xline"][0] * x0 + g["xline"][1]], [x1, g["xline"][0] * x1 + g["xline"][1]]],
            "x_height": float(xh),
            "slope_deg": float(np.degrees(np.arctan(g["baseline"][0]))),
            "slant_deg": slant, "slant_samples": n_sl,
        })
    for i, (l, g) in enumerate(zip(lines, guides)):
        prev_base = (lambda x, gg=guides[i - 1]: gg["baseline"][0] * x + gg["baseline"][1]) if i > 0 else None
        next_x = (lambda x, gg=guides[i + 1]: gg["xline"][0] * x + gg["xline"][1]) if i + 1 < len(guides) else None
        up, down, nu, nd = extents(mask, g, l["x0"], l["x1"], l["x_height"], prev_base, next_x)
        l.update({"ascender_xh": up, "descender_xh": down, "n_ascenders": nu, "n_descenders": nd})
    return rgb, mask, lines


def attach_reading(lines, reading):
    """Match detected lines to the reading: the last len(text) lines are the text, the
    ones above are title lines, numbered by position so a missed title line keeps the
    others in their right place."""
    text = [r for r in reading["lines"] if r["kind"] == "text"]
    titles = [r for r in reading["lines"] if r["kind"] == "title"]
    body = lines[-len(text):]
    head = lines[:-len(text)]
    for l, r in zip(body, text):
        l.update(n=r["n"], kind="text", edition=r["edition"], diplomatic=r["diplomatic"])
    if head:
        ys = [l["baseline"][0][1] for l in head]
        gaps = [b - a for a, b in zip(ys, ys[1:]) if b - a < 70]
        pitch = float(np.median(gaps)) if gaps else 48.0
        for l, y in zip(head, ys):
            k = int(round((y - ys[0]) / pitch))
            r = titles[min(k, len(titles) - 1)]
            l.update(n=r["n"], kind="title", edition=r["edition"], diplomatic=r["diplomatic"])
    return lines


def plot_lines(rgb, lines, pen, dirs, widths, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    SURFACE, INK_TEXT, MUTED, DATA, MODEL = "#fcfcfb", "#0b0b0b", "#52514e", "#2a78d6", "#eb6834"
    body = [l for l in lines if l["kind"] == "text"]
    n = [l["n"] for l in body]
    fig = plt.figure(figsize=(10, 7.6), dpi=150, facecolor=SURFACE)
    gs = fig.add_gridspec(3, 2, height_ratios=[1.25, 1, 1], hspace=0.55, wspace=0.25)
    ax0 = fig.add_subplot(gs[0, :])
    l1, l3 = body[0], body[2]
    y0 = int(l1["xline"][0][1] - 34); y1 = int(l3["baseline"][0][1] + 26)
    x0, x1 = 300, 890
    ax0.imshow(rgb[y0:y1, x0:x1], extent=(x0, x1, y1, y0))
    for l in body[:3]:
        for key, col in (("baseline", DATA), ("xline", MODEL)):
            (a, b), (c, d) = l[key]
            ax0.plot([a, c], [b, d], color=col, lw=1)
    ax0.set_xlim(x0, x1); ax0.set_ylim(y1, y0); ax0.axis("off")
    ax0.set_title("Guides found from the ink: baseline (blue) and x-height line (orange), lines 1–3",
                  fontsize=9, color=INK_TEXT, loc="left")

    def style(ax, ylabel):
        ax.set_facecolor(SURFACE)
        for s_ in ("top", "right"):
            ax.spines[s_].set_visible(False)
        for s_ in ("left", "bottom"):
            ax.spines[s_].set_color("#c9c8c3")
        ax.tick_params(colors=MUTED, labelsize=8)
        ax.grid(axis="y", color="#ecebe8", lw=0.8)
        ax.set_ylabel(ylabel, color=MUTED, fontsize=8)
        ax.set_xlabel("manuscript line", color=MUTED, fontsize=8)

    panels = [
        (gs[1, 0], [l["x_height"] for l in body], "x-height (px)", "x-height per line"),
        (gs[1, 1], [l["slant_deg"] for l in body], "slant (° from vertical)", "slant of upright strokes per line"),
        (gs[2, 0], [l["ascender_xh"] for l in body], "× x-height above baseline", "ascender reach (median per line)"),
    ]
    for spec, vals, ylab, title in panels:
        ax = fig.add_subplot(spec)
        style(ax, ylab)
        v = np.array(vals, float)
        ax.plot(n, v, "o-", color=DATA, ms=4, lw=1.2)
        m = np.nanmean(v)
        ax.axhline(m, color=MUTED, lw=0.8, ls="--")
        ax.text(n[-1] + 0.3, m, f"mean {m:.1f}", color=MUTED, fontsize=7, va="center")
        ax.set_title(title, fontsize=9, color=INK_TEXT, loc="left")
        ax.set_xlim(0.5, n[-1] + 3)
    ax = fig.add_subplot(gs[2, 1])
    style(ax, "relative stroke width")
    c = np.array(pen["bins"]["centre_deg"]); med = np.array(pen["bins"]["median_width"])
    ax.plot(c, med, "o", color=DATA, ms=4, label="page: median per direction")
    phi = np.linspace(0, 180, 181)
    ax.plot(phi, nib.nib_model(phi, pen["a"], pen["b"], pen["theta_deg"]), color=MODEL, lw=1.8,
            label=f"nib fit: contrast {pen['contrast']:.2f}")
    ax.set_xlim(0, 180); ax.set_xticks([0, 45, 90, 135, 180])
    ax.set_xlabel("stroke direction (°, 0 = horizontal)", color=MUTED, fontsize=8)
    ax.set_ylim(0, max(med) * 1.35)
    ax.legend(frameon=False, fontsize=7, loc="lower right", labelcolor=INK_TEXT)
    ax.set_title("pen: ink across the stroke by direction", fontsize=9, color=INK_TEXT, loc="left")
    fig.savefig(path, facecolor=SURFACE, bbox_inches="tight")
    plt.close(fig)


def main():
    rgb, mask, lines = analyse()
    reading = json.loads((HERE / "data" / "lucretius_reading.json").read_text(encoding="utf-8"))
    lines = attach_reading(lines, reading)
    # pen from ink mass (pixel widths are too coarse at this x-height)
    _, dark = ink.ink_mask(rgb)
    m = mask.copy()
    m[:BLOCK["y0"]] = 0; m[BLOCK["y1"]:] = 0; m[:, :BLOCK["x0"]] = 0; m[:, BLOCK["x1"]:] = 0
    dirs, widths = nib.mass_width_samples(m, dark)
    pen = nib.fit_nib(dirs, widths)
    pen["method"] = "ink mass across the stroke (relative widths)"
    pen["n_samples"] = int(len(dirs))
    body = [l for l in lines if l["kind"] == "text"]
    summary = {k: {"mean": float(np.nanmean([l[k] for l in body])), "sd": float(np.nanstd([l[k] for l in body], ddof=1))}
               for k in ("x_height", "slant_deg", "ascender_xh", "descender_xh", "slope_deg")}
    pitch = np.diff([l["baseline"][0][1] for l in body])
    summary["line_pitch_px"] = {"mean": float(pitch.mean()), "sd": float(pitch.std(ddof=1))}
    out = {"image": IMAGE, "lines": lines, "pen": pen, "summary": summary}

    def clean(v):  # JSON has no NaN: unmeasurable values are written as null
        if isinstance(v, float) and not np.isfinite(v):
            return None
        if isinstance(v, dict):
            return {k: clean(x) for k, x in v.items()}
        if isinstance(v, (list, tuple)):
            return [clean(x) for x in v]
        return v
    (HERE / "data" / "lucretius_lines.json").write_text(json.dumps(clean(out), ensure_ascii=False, indent=1), encoding="utf-8")
    (HERE / "out").mkdir(exist_ok=True)
    plot_lines(rgb, lines, pen, dirs, widths, HERE / "out" / "latin_lines.png")
    for l in lines:
        print(f"{str(l['n']):>3} y={l['baseline'][0][1]:7.1f} xh={l['x_height']:5.1f} asc={l['ascender_xh']:.2f} "
              f"desc={l['descender_xh']:.2f} slant={l['slant_deg']:5.1f}  {l['edition'][:40]}")
    print("summary:", json.dumps(summary, indent=None))
    print("pen:", {k: round(v, 2) for k, v in pen.items() if isinstance(v, float)})


if __name__ == "__main__":
    main()
