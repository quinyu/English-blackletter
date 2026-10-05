"""Viability check: can a stroke + nib model reproduce, and vary like, this scribe's الله?

Steps
  1. Measure every traced instance (measure.py) and estimate the pen from the page (nib.py).
  2. Re-render each instance from its own measurements with the nib model and compare
     it with the ink (overlap and outline distance).
  3. Describe the variation: spread of each feature, and how much of it is shared by
     the whole word (size, slant) rather than independent per letter.
  4. Generate new instances from that structured variation model, next to a naive
     "independent jitter" baseline, and write vector (SVG) output.

Outputs go to viability/out/.  Run:  python3 run.py
"""
import csv
import json
from pathlib import Path

import cv2
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

import ductus
import measure
import nib
import pen

HERE = Path(__file__).resolve().parent
OUT = HERE / "out"
RNG_SEED = 328
CORRIDOR = 4  # px: ink this close to the model counts as the instance's own

# chart roles (light surface)
SURFACE, INK_TEXT, MUTED = "#fcfcfb", "#0b0b0b", "#52514e"
DATA, MODEL = "#2a78d6", "#eb6834"

FEATURES = ["h_alif", "h_lam1", "h_lam2", "slant_alif", "slant_lam1", "slant_lam2",
            "alif_gap", "lam_spacing", "tail_length", "ha_height", "ha_loop_width"]
HEIGHTS = ["h_alif", "h_lam1", "h_lam2"]
SLANTS = ["slant_alif", "slant_lam1", "slant_lam2"]
LABELS = {
    "h_alif": "alif height", "h_lam1": "lām¹ height", "h_lam2": "lām² height",
    "slant_alif": "alif slant", "slant_lam1": "lām¹ slant", "slant_lam2": "lām² slant",
    "alif_gap": "alif → lām¹ gap", "lam_spacing": "lām¹ → lām² spacing",
    "tail_length": "lām² → end of hā'", "ha_height": "hā' height", "ha_loop_width": "hā' width",
}


# ----------------------------------------------------------------------------- data
def usable(rec, feat):
    """Which measurements enter the statistics (see flags in the traces file)."""
    flags = rec["flags"]
    if "touches_line_above" in flags:
        return False
    if feat in ("h_alif", "slant_alif", "alif_gap") and "alif_joined" in flags:
        return False
    if feat in ("tail_length", "ha_height", "ha_loop_width") and "ha_touches_next" in flags:
        return False
    return feat in rec["features_px"]


def feature_table(recs):
    return {f: np.array([r["features_px"][f] if usable(r, f) else np.nan for r in recs]) for f in FEATURES}


# ----------------------------------------------------------------------------- pen
def estimate_nib(mask):
    m = mask.copy()
    m[:90] = 0; m[1240:] = 0; m[:, :60] = 0; m[:, 1000:] = 0  # text block only
    dirs, widths = nib.width_direction_samples(m)
    fit = nib.fit_nib(dirs, widths)
    fit["n_samples"] = int(len(dirs))
    return fit, dirs, widths


def plot_nib(fit, dirs, widths, path):
    fig, ax = plt.subplots(figsize=(7.2, 3.6), dpi=150, facecolor=SURFACE)
    ax.set_facecolor(SURFACE)
    c = np.array(fit["bins"]["centre_deg"]); med = np.array(fit["bins"]["median_width"])
    q1, q3 = [], []
    for lo in c - 5:
        m = (dirs >= lo) & (dirs < lo + 10)
        q1.append(np.percentile(widths[m], 25)); q3.append(np.percentile(widths[m], 75))
    ax.fill_between(c, q1, q3, color=DATA, alpha=0.15, linewidth=0, label="page: middle 50% of widths")
    ax.plot(c, med, "o", color=DATA, ms=5, label="page: median width per direction")
    phi = np.linspace(0, 180, 361)
    ax.plot(phi, nib.nib_model(phi, fit["a"], fit["b"], fit["theta_deg"]), color=MODEL, lw=2,
            label=f"elliptical nib fit: {fit['a']:.1f} × {fit['b']:.1f} px at {fit['theta_deg']:.0f}°")
    ax.set_xlim(0, 180); ax.set_ylim(0, 10)
    ax.set_xticks([0, 45, 90, 135, 180])
    ax.set_xticklabels(["0°\n→ / ←", "45°\n↗", "90°\n↑ / ↓", "135°\n↖", "180°"])
    ax.set_ylabel("stroke width (px)", color=MUTED)
    ax.set_xlabel("stroke direction", color=MUTED)
    ax.set_title(f"Pen estimate from the whole page — thick/thin contrast {fit['contrast']:.2f} (≈ monoline)",
                 color=INK_TEXT, fontsize=10, loc="left")
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color("#c9c8c3")
    ax.tick_params(colors=MUTED, labelsize=8)
    ax.grid(axis="y", color="#ecebe8", lw=0.8)
    ax.legend(frameon=False, fontsize=8, loc="lower right", labelcolor=INK_TEXT)
    fig.tight_layout()
    fig.savefig(path, facecolor=SURFACE)
    plt.close(fig)


# ----------------------------------------------------------------------------- re-render check
def instance_geometry(rec, the_nib):
    strokes = ductus.allah_strokes(rec["features_px"], rec["stroke_width"], with_alif="alif" in rec["shafts"])
    origin = (rec["shafts"]["lam2"]["foot"][0], rec["baseline_y"])
    return pen.render(ductus.place(strokes, origin), the_nib)


def compare(mask, inst, geom, pad=4):
    x0, y0, x1, y1 = inst["bbox"]
    x0, y0, x1, y1 = x0 - pad, y0 - pad, x1 + pad, y1 + pad
    ink = mask[y0:y1, x0:x1].astype(np.uint8)
    model = pen.rasterize(geom, ink.shape, origin=(x0, y0))
    # The instance's own ink: ink within a few pixels of the model. Letters of the line
    # above or the next word often touch this word on the page; separating them is a
    # segmentation problem, not a question of whether the pen model fits, so they are
    # left out of the score (and shown in grey in the figure).
    near = cv2.dilate(model, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * CORRIDOR + 1, 2 * CORRIDOR + 1)))
    own = (ink & near).astype(np.uint8)
    inter = (own & model).sum(); union = (own | model).sum()

    def edge(m):
        return (m > 0) & (cv2.erode(m, np.ones((3, 3), np.uint8)) == 0)
    e_own, e_mod = edge(own), edge(model)
    d_own = cv2.distanceTransform((~e_own).astype(np.uint8), cv2.DIST_L2, 5)
    d_mod = cv2.distanceTransform((~e_mod).astype(np.uint8), cv2.DIST_L2, 5)
    boundary = 0.5 * (d_own[e_mod].mean() + d_mod[e_own].mean())
    return {"iou": float(inter / union), "outline_dist_px": float(boundary)}, (x0, y0, x1, y1), ink, own, model


def plot_fits(rgb, recs, comps, path):
    n = len(recs)
    cols = 4
    rows = int(np.ceil(n / cols))
    fig, axes = plt.subplots(rows * 2, cols, figsize=(cols * 2.6, rows * 2 * 1.45), dpi=160, facecolor=SURFACE)
    for k in range(rows * cols):
        r, c = divmod(k, cols)
        a_img, a_ovl = axes[2 * r, c], axes[2 * r + 1, c]
        for a in (a_img, a_ovl):
            a.axis("off")
        if k >= n:
            continue
        rec, (m, (x0, y0, x1, y1), ink, own, model) = recs[k], comps[k]
        a_img.imshow(rgb[y0:y1, x0:x1], interpolation="lanczos")
        flag = "  (excluded: touches line above)" if "touches_line_above" in rec["flags"] else ""
        a_img.set_title(f"{rec['id']} · line {rec['line']}{flag}", fontsize=7, color=INK_TEXT, loc="left")
        vis = np.ones(ink.shape + (3,))
        vis[ink > 0] = (0.88, 0.88, 0.86)                                   # other ink nearby
        vis[(own > 0) & (model == 0)] = matplotlib.colors.to_rgb(DATA)     # ink the model misses
        vis[(model > 0) & (own == 0)] = matplotlib.colors.to_rgb(MODEL)    # model where there is no ink
        vis[(model > 0) & (own > 0)] = (0.1, 0.1, 0.1)                     # agreement
        a_ovl.imshow(vis, interpolation="nearest")
        a_ovl.set_title(f"overlap {m['iou']:.0%} · outline off by {m['outline_dist_px']:.1f} px", fontsize=7, color=MUTED, loc="left")
    handles = [matplotlib.patches.Patch(color=(0.1, 0.1, 0.1), label="model and ink agree"),
               matplotlib.patches.Patch(color=DATA, label="ink the model misses"),
               matplotlib.patches.Patch(color=MODEL, label="model where there is no ink"),
               matplotlib.patches.Patch(color=(0.88, 0.88, 0.86), label="other ink (neighbouring letters)")]
    fig.legend(handles=handles, loc="lower center", ncol=4, frameon=False, fontsize=7, labelcolor=INK_TEXT)
    fig.suptitle("Each الله re-drawn by the nib model from its own measurements (scan pixels, 1024 px page)",
                 fontsize=9, color=INK_TEXT, x=0.01, ha="left")
    fig.tight_layout(rect=(0, 0.03, 1, 0.97))
    fig.savefig(path, facecolor=SURFACE)
    plt.close(fig)


# ----------------------------------------------------------------------------- repeatability
def repeatability(mask, instances, trials=12, click_sd=2.5, seed=7):
    """How much do the measurements move if every click is off by a few pixels?

    Each rough point is moved by Gaussian noise (click_sd px) and the instance is
    re-measured. The spread across trials is the measurement noise, which has to be
    small next to the scribe's own variation for the statistics to mean anything.
    """
    rng = np.random.default_rng(seed)
    spread = {f: [] for f in FEATURES}
    for inst in instances:
        if "touches_line_above" in inst.get("flags", []):
            continue
        vals = {f: [] for f in FEATURES}
        for _ in range(trials):
            j = json.loads(json.dumps(inst))
            for k, pts in j["strokes"].items():
                j["strokes"][k] = [[x + rng.normal(0, click_sd), y + rng.normal(0, click_sd)] for x, y in pts]
            j["baseline"] = inst["baseline"] + rng.normal(0, click_sd)
            try:
                r = measure.measure_instance(mask, j)
            except ValueError:
                continue
            for f, v in r["features_px"].items():
                if f in vals:
                    vals[f].append(v)
        for f, v in vals.items():
            if len(v) >= 3:
                spread[f].append(float(np.std(v, ddof=1)))
    return {f: float(np.median(v)) for f, v in spread.items() if v}


# ----------------------------------------------------------------------------- variation model
def variation_model(table):
    """Split variation into a word-level part (size, slant) and a per-letter residual.

    size_k  = mean over the word's shafts of height / feature mean   (1.0 = average size)
    slant_k = mean over the word's shafts of slant − feature mean    (degrees)

    How much a letter shares with its word is estimated leave-one-out: each shaft is
    predicted from the *other* shafts of the same word only, so a letter cannot explain
    itself. Everything that is not shared is kept as independent per-feature noise.
    """
    mean = {f: float(np.nanmean(v)) for f, v in table.items()}
    sd = {f: float(np.nanstd(v, ddof=1)) for f, v in table.items()}
    n = len(next(iter(table.values())))

    def factor(group, k, skip=None, ratio=True):
        vals = [(table[g][k] / mean[g]) if ratio else (table[g][k] - mean[g]) for g in group if g != skip]
        vals = [v for v in vals if not np.isnan(v)]
        return np.mean(vals) if vals else np.nan

    size = np.array([factor(HEIGHTS, k) for k in range(n)])
    slant = np.array([factor(SLANTS, k, ratio=False) for k in range(n)])
    resid, share, corr = {}, {}, {}
    for f in FEATURES:
        if f in HEIGHTS:
            pred = np.array([mean[f] * factor(HEIGHTS, k, skip=f) for k in range(n)])
        elif f in SLANTS:
            pred = np.array([mean[f] + factor(SLANTS, k, skip=f, ratio=False) for k in range(n)])
        else:
            resid[f] = sd[f]
            continue
        ok = ~np.isnan(table[f]) & ~np.isnan(pred)
        r = table[f][ok] - pred[ok]
        resid[f] = float(np.sqrt(np.mean(r ** 2)))
        share[f] = float(1 - resid[f] ** 2 / sd[f] ** 2)
        corr[f] = float(np.corrcoef(table[f][ok], pred[ok])[0, 1])
    return {"mean": mean, "sd": sd, "size_sd": float(np.nanstd(size, ddof=1)),
            "slant_sd": float(np.nanstd(slant, ddof=1)), "residual_sd": resid,
            "word_level_share_loo": share, "corr_with_rest_of_word": corr,
            "size": size.tolist(), "slant": slant.tolist()}


def sample_structured(vm, rng):
    f = {}
    z_size = 1 + rng.normal(0, vm["size_sd"])
    z_slant = rng.normal(0, vm["slant_sd"])
    for k in FEATURES:
        # letter-level noise: what the rest of the word does not predict (never more
        # than the feature's total spread)
        r = rng.normal(0, min(vm["residual_sd"][k], vm["sd"][k]))
        if k in HEIGHTS:
            f[k] = vm["mean"][k] * z_size + r
        elif k in SLANTS:
            f[k] = vm["mean"][k] + z_slant + r
        else:
            f[k] = vm["mean"][k] + r
    return f


def jitter_strokes(strokes, sigma, rng, densify=4):
    """Naive baseline: same mean template, independent noise on every point.

    Strokes are first resampled to evenly spaced points (as a vectorised outline font or a
    simple 'roughen' filter would have them), then each point is moved on its own.
    """
    out = []
    for s in strokes:
        dense = pen.catmull_rom(s, step=3.0)
        dense = dense[:: max(1, len(dense) // max(densify, len(s)))] if len(dense) > 2 else dense
        out.append([p + rng.normal(0, sigma, 2) for p in dense])
    return out


def render_row(feature_sets, s, the_nib, spacing=78, jitter=None, rng=None):
    geoms, x = [], 0.0
    for f in feature_sets:
        st = ductus.allah_strokes(f, s)
        if jitter is not None:
            st = jitter_strokes(st, jitter, rng)
        geoms.append(pen.render(ductus.place(st, (x, 0.0)), the_nib))
        x -= spacing  # right to left
    return geoms


def row_canvas(n, spacing=78, top=62, bottom=14, left=52, right=72):
    """Blank row; returns it with the position of the first word's lām² foot."""
    W = int(spacing * (n - 1) + left + right)
    return np.zeros((top + bottom, W), np.uint8), (W - right, top)


def plot_synthesis(orig_tiles, struct_geoms, jitter_geoms, path, spacing=78):
    """Three rows at scan resolution: original ink, structured samples, naive jitter."""
    n = len(orig_tiles)
    rows = []
    canvas, (ox, oy) = row_canvas(n, spacing)
    for k, (page_xy, own, foot) in enumerate(orig_tiles):
        ys, xs = np.nonzero(own)
        X = xs + page_xy[0] - foot[0] - k * spacing + ox
        Y = ys + page_xy[1] - foot[1] + oy
        ok = (X >= 0) & (X < canvas.shape[1]) & (Y >= 0) & (Y < canvas.shape[0])
        canvas[Y[ok].astype(int), X[ok].astype(int)] = 1
    rows.append(canvas)
    for geoms in (struct_geoms, jitter_geoms):
        canvas, (ox, oy) = row_canvas(n, spacing)
        for g in geoms:
            canvas |= pen.rasterize(g, canvas.shape, origin=(-ox, -oy))
        rows.append(canvas)
    titles = ["Originals from the page — each word's own ink, aligned on the baseline",
              "Generated: measured averages + shared word-level size and slant + small per-letter residuals",
              f"Naive alternative: same average shape, independent random jitter on every point"]
    fig, axes = plt.subplots(3, 1, figsize=(10, 4.6), dpi=170, facecolor=SURFACE)
    ink_rgb = np.array([0.10, 0.09, 0.08]); bg = np.array(matplotlib.colors.to_rgb(SURFACE))
    for ax, title, c in zip(axes, titles, rows):
        img = np.where(c[..., None] > 0, ink_rgb, bg)
        ax.imshow(img, interpolation="nearest")
        ax.axhline(oy, color="#e2e1dc", lw=0.5)
        ax.set_title(title, fontsize=8, color=INK_TEXT, loc="left")
        ax.axis("off")
    fig.tight_layout()
    fig.savefig(path, facecolor=SURFACE)
    plt.close(fig)


def write_svg(geoms, path, spacing=78, title=""):
    xs = [c for g in geoms for poly in pen._polys(g) for c in np.asarray(poly.exterior.coords)[:, 0]]
    ys = [c for g in geoms for poly in pen._polys(g) for c in np.asarray(poly.exterior.coords)[:, 1]]
    x0, x1, y0, y1 = min(xs) - 6, max(xs) + 6, min(ys) - 6, max(ys) + 6
    paths = "\n".join(f'  <path d="{pen.svg_path(g)}"/>' for g in geoms)
    path.write_text(
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{x0:.1f} {y0:.1f} {x1 - x0:.1f} {y1 - y0:.1f}" '
        f'width="{(x1 - x0) * 4:.0f}" height="{(y1 - y0) * 4:.0f}">\n'
        f"  <title>{title}</title>\n"
        f'  <rect x="{x0:.1f}" y="{y0:.1f}" width="{x1 - x0:.1f}" height="{y1 - y0:.1f}" fill="#fcfcfb"/>\n'
        f'  <g fill="#1a1714" fill-rule="evenodd">\n{paths}\n  </g>\n</svg>\n', encoding="utf-8")


# ----------------------------------------------------------------------------- main
def main():
    OUT.mkdir(exist_ok=True)
    traces = measure.load_traces()
    rgb, mask, _ = measure.page_mask(traces)
    recs = [measure.measure_instance(mask, i) for i in traces["instances"]]

    fit, dirs, widths = estimate_nib(mask)
    plot_nib(fit, dirs, widths, OUT / "fig_nib.png")
    the_nib = pen.Nib(fit["a"], fit["b"], fit["theta_deg"])

    comps, fits = [], {}
    for inst, rec in zip(traces["instances"], recs):
        geom = instance_geometry(rec, the_nib)
        m, box_, ink, own, model = compare(mask, inst, geom)
        comps.append((m, box_, ink, own, model))
        fits[rec["id"]] = m
        rec["model_fit"] = m
    plot_fits(rgb, recs, comps, OUT / "fig_fits.png")

    table = feature_table(recs)
    s_mean = float(np.median([r["stroke_width"] for r in recs]))
    stats = {}
    for f, v in table.items():
        v = v[~np.isnan(v)]
        unit = "deg" if f.startswith("slant") else "px"
        stats[f] = {"label": LABELS[f], "unit": unit, "n": int(len(v)), "mean": float(v.mean()),
                    "sd": float(v.std(ddof=1)), "min": float(v.min()), "max": float(v.max())}
        if unit == "px":
            stats[f]["mean_sw"] = float(v.mean() / s_mean)
            stats[f]["sd_sw"] = float(v.std(ddof=1) / s_mean)
            stats[f]["cv"] = float(v.std(ddof=1) / v.mean())
    vm = variation_model(table)
    noise = repeatability(mask, traces["instances"])
    for f in stats:
        if f in noise:
            stats[f]["measurement_noise_sd"] = noise[f]

    rng = np.random.default_rng(RNG_SEED)
    n_show = sum("touches_line_above" not in r["flags"] for r in recs)
    struct_feats = [sample_structured(vm, rng) for _ in range(n_show)]
    mean_feats = {f: vm["mean"][f] for f in FEATURES}
    # jitter size chosen to match the typical positional spread of the shaft tops
    top_sd = float(np.sqrt(np.mean([
        (vm["sd"][h] ** 2 + (vm["mean"][h] * np.radians(vm["sd"][sl])) ** 2) / 2
        for h, sl in zip(HEIGHTS, SLANTS)])))
    struct_geoms = render_row(struct_feats, s_mean, the_nib)
    jitter_geoms = render_row([mean_feats] * n_show, s_mean, the_nib, jitter=top_sd, rng=rng)
    orig_tiles = []
    for r, (m, (x0, y0, x1, y1), ink, own, model) in zip(recs, comps):
        if "touches_line_above" in r["flags"]:
            continue
        orig_tiles.append(((x0, y0), own, (r["shafts"]["lam2"]["foot"][0], r["baseline_y"])))
    plot_synthesis(orig_tiles, struct_geoms, jitter_geoms, OUT / "fig_synthesis.png")

    write_svg([pen.render(ductus.place(ductus.allah_strokes(mean_feats, s_mean), (0, 0)), the_nib)],
              OUT / "allah_mean.svg", title="الله — mean of the measured instances, nib-rendered")
    write_svg(struct_geoms, OUT / "allah_variants.svg", title="الله — generated variants (structured variation)")

    (OUT / "measurements.json").write_text(json.dumps(recs, ensure_ascii=False, indent=1), encoding="utf-8")
    with open(OUT / "features.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["id", "line", "context", "flags", "stroke_width"] + FEATURES + ["model_overlap", "model_outline_dist_px"])
        for r in recs:
            f = r["features_px"]
            w.writerow([r["id"], r["line"], r["context"], ";".join(r["flags"]), f"{r['stroke_width']:.2f}"]
                       + [f"{f[k]:.2f}" if k in f else "" for k in FEATURES]
                       + [f"{r['model_fit']['iou']:.3f}", f"{r['model_fit']['outline_dist_px']:.2f}"])
    summary = {"nib": {k: v for k, v in fit.items()}, "stroke_width_px": s_mean, "features": stats,
               "variation_model": vm, "jitter_sigma_px": top_sd, "model_fit": fits,
               "excluded": {r["id"]: r["flags"] for r in recs if r["flags"]}}
    (OUT / "stats.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")

    # console summary
    print(f"nib: {fit['a']:.2f} x {fit['b']:.2f} px at {fit['theta_deg']:.0f} deg, contrast {fit['contrast']:.2f}, rms {fit['rms_px']:.2f} px, n={fit['n_samples']}")
    print("model fit (overlap, outline distance):")
    for k, m in fits.items():
        print(f"  {k}: {m['iou']:.2f}  {m['outline_dist_px']:.2f}px")
    print("features:")
    for f, st in stats.items():
        extra = f"  ({st['mean_sw']:.2f} sw, CV {st['cv']:.0%})" if st["unit"] == "px" else ""
        print(f"  {f:14s} n={st['n']:2d} mean={st['mean']:6.1f} sd={st['sd']:5.2f} [{st['min']:.1f}, {st['max']:.1f}]{extra}  noise sd={st.get('measurement_noise_sd', float('nan')):.2f}")
    print(f"word size factor sd={vm['size_sd']:.3f}, word slant sd={vm['slant_sd']:.2f} deg")
    print("leave-one-out: corr with rest of word:", {k: round(v, 2) for k, v in vm["corr_with_rest_of_word"].items()})
    print("leave-one-out: share of variance predicted by rest of word:", {k: round(v, 2) for k, v in vm["word_level_share_loo"].items()})
    print(f"jitter sigma={top_sd:.2f}px")


if __name__ == "__main__":
    main()
