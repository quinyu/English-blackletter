"""Measure and re-draw traced Latin letters (traces in ductus-traces/2 format).

For every traced letter:
  * re-runs the ink-following between its clicks (inkpath.py), so traces made at any
    threshold end up on the same centre-lines,
  * measures it in x-heights of its own line (width, rise above the baseline, drop
    below it, slant of the longest upright stroke),
  * re-draws it with the page's pen (nib.py fit, scaled to the page's stroke width)
    and compares the result with the ink.
It also measures stroke width against the direction the pen was travelling, which a
traced stroke knows and the page-wide estimate does not (upstrokes vs downstrokes).

Run:  python3 measure_letters.py [page]   (page: lucretius, chigi; default both)
      → out/<page>_letters.png, out/<page>_letters.json
"""
import sys
import json
from pathlib import Path

import cv2
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

import ink
import inkpath
import nib
import pen

HERE = Path(__file__).resolve().parent
OUT = HERE / "out"
SURFACE, INK_TEXT, MUTED, DATA, MODEL = "#fcfcfb", "#0b0b0b", "#52514e", "#2a78d6", "#eb6834"
THR = 14.0
CORRIDOR = 3
PAGES = {
    "lucretius": dict(traces="traces_lucretius.json", lines="lucretius_lines.json", out="latin_letters"),
    "chigi": dict(traces="traces_chigi.json", lines="chigi_lines.json", out="chigi_letters"),
    "hours": dict(traces="traces_hours.json", lines="hours_lines.json", out="hours_letters"),
}


def guide(line, x):
    (x0, b0), (x1, b1) = line["baseline"]
    (_, t0), (_, t1) = line["xline"]
    f = (x - x0) / ((x1 - x0) or 1)
    yb, yx = b0 + f * (b1 - b0), t0 + f * (t1 - t0)
    return yb, yb - yx


def letter_features(strokes, line):
    pts = np.array([p for s in strokes for p in s["points"]], float)
    cx = (pts[:, 0].min() + pts[:, 0].max()) / 2
    yb, xh = guide(line, cx)
    # slant: length-weighted mean angle of the near-upright parts of all strokes
    sw = sa = 0.0
    for s in strokes:
        P = np.array(s["points"], float)
        for a, b in zip(P[:-1], P[1:]):
            t, u = (a, b) if a[1] < b[1] else (b, a)
            L = np.hypot(*(u - t))
            if L < 2:
                continue
            ang = np.degrees(np.arctan2(t[0] - u[0], u[1] - t[1]))
            if abs(ang) <= 40:
                sw += L; sa += L * ang
    slant = float(sa / sw) if sw else float("nan")
    return {"width": float(np.ptp(pts[:, 0]) / xh), "rise": float((yb - pts[:, 1].min()) / xh),
            "drop": float((pts[:, 1].max() - yb) / xh), "slant": slant, "x_height_px": float(xh)}


def page_nib(lines_json, mask):
    """Nib with the page's thick/thin contrast and angle (from latin_lines.py), scaled so
    its average stroke width matches the measured width of the ink."""
    p = lines_json["pen"]
    dt = cv2.distanceTransform(mask.astype(np.uint8), cv2.DIST_L2, 5)
    from skimage.morphology import skeletonize
    sk = skeletonize(mask > 0)
    w_ink = float(np.median(2 * dt[sk]))
    k = w_ink / ((p["a"] + p["b"]) / 2)
    return pen.Nib(p["a"] * k, p["b"] * k, p["theta_deg"]), w_ink


def directional_widths(strokes, dark, step=0.5, reach=5.0):
    """(travel direction in degrees 0–360, y-up, ink-mass width) along traced strokes."""
    out = []
    offs = np.arange(-reach, reach + step / 2, step)
    for s in strokes:
        P = np.array(s["points"], float)
        if len(P) < 2:
            continue
        dense = pen.catmull_rom(P, step=1.0) if len(P) > 2 else np.linspace(P[0], P[-1], max(2, int(np.hypot(*(P[-1] - P[0])))))
        for i in range(1, len(dense) - 1):
            d = dense[i + 1] - dense[i - 1]
            L = np.hypot(*d)
            if L < 1e-6:
                continue
            u = d / L
            n = np.array([-u[1], u[0]])
            m = nib.profile_mass(dark, dense[i], n, reach=reach, step=step)
            if m is not None:
                out.append((float(np.degrees(np.arctan2(-u[1], u[0])) % 360), m))
    return out


def main(page):
    P = PAGES[page]
    print(f"== {page}")
    traces = json.loads((HERE / "data" / P["traces"]).read_text(encoding="utf-8"))
    lines_json = json.loads((HERE / "data" / P["lines"]).read_text(encoding="utf-8"))
    lines = {str(l["n"]): l for l in lines_json["lines"]}
    rgb = ink.load_rgb(HERE / "data" / traces["image"])
    mask, dark = ink.ink_mask(rgb)
    the_nib, w_ink = page_nib(lines_json, mask)
    print(f"nib for rendering: {the_nib.a:.2f} x {the_nib.b:.2f} px at {the_nib.theta:.0f} deg (page ink width {w_ink:.2f} px)")

    results, panels, dirw = [], [], []
    for inst in traces["instances"]:
        strokes = []
        for s in inst["strokes"]:
            if s.get("points") == s.get("clicks"):  # drawn without ink-following (faint hairlines)
                clicks, pts = s["clicks"], s["points"]
            else:
                clicks, pts = inkpath.trace_stroke(dark, THR, s["clicks"])
            strokes.append({"name": s["name"], "clicks": clicks, "points": pts})
        line = lines[str(inst["line"])]
        f = letter_features(strokes, line)
        geom = pen.render([s["points"] for s in strokes], the_nib, step=0.25, names=[s["name"] for s in strokes])
        x0, y0, x1, y1 = [int(v) for v in geom.bounds]
        x0 -= 5; y0 -= 5; x1 += 6; y1 += 6
        model = pen.rasterize(geom, (y1 - y0, x1 - x0), origin=(x0, y0))
        ink_win = mask[y0:y1, x0:x1].astype(np.uint8)
        near = cv2.dilate(model, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * CORRIDOR + 1,) * 2))
        own = ink_win & near
        iou = float((own & model).sum() / max(1, (own | model).sum()))

        def edge(m):
            return (m > 0) & (cv2.erode(m, np.ones((3, 3), np.uint8)) == 0)
        eo, em = edge(own), edge(model)
        do = cv2.distanceTransform((~eo).astype(np.uint8), cv2.DIST_L2, 5)
        dm = cv2.distanceTransform((~em).astype(np.uint8), cv2.DIST_L2, 5)
        outline = float(0.5 * (do[em].mean() + dm[eo].mean()))
        f.update(id=inst["id"], char=inst["char"], line=inst["line"], context=inst.get("context", ""),
                 overlap=iou, outline_dist_px=outline, strokes=[s["name"] for s in strokes])
        results.append(f)
        panels.append((inst, strokes, (x0, y0, x1, y1), ink_win, own, model, geom))
        dirw += directional_widths(strokes, dark)
        print(f"  {inst['char']} {inst['id']}: width {f['width']:.2f} rise {f['rise']:.2f} drop {f['drop']:.2f} xh, "
              f"slant {f['slant']:.1f} deg, overlap {iou:.0%}, outline off by {outline:.2f} px")

    # down vs up: pen moving downwards (travel direction 180–360° in y-up degrees) vs upwards
    dirw = np.array(dirw) if dirw else np.zeros((0, 2))
    down = dirw[(dirw[:, 0] > 200) & (dirw[:, 0] < 340), 1] if len(dirw) else []
    up = dirw[(dirw[:, 0] > 20) & (dirw[:, 0] < 160), 1] if len(dirw) else []
    solid = float(np.percentile(dark[mask > 0], 90))
    updown = {"downstroke_width_px": float(np.median(down) / solid) if len(down) else None,
              "upstroke_width_px": float(np.median(up) / solid) if len(up) else None,
              "n_down": int(len(down)), "n_up": int(len(up))}
    print("pen travel:", updown)

    OUT.mkdir(exist_ok=True)
    (OUT / f"{P['out']}.json").write_text(json.dumps({"nib": {"a": the_nib.a, "b": the_nib.b, "theta_deg": the_nib.theta},
                                                        "letters": results, "up_down": updown}, ensure_ascii=False, indent=1),
                                            encoding="utf-8")
    plot(rgb, panels, results, OUT / f"{P['out']}.png")


def plot(rgb, panels, results, path, per_row=4):
    n = len(panels)
    cols = min(n, per_row)
    groups = int(np.ceil(n / cols))
    fig, axes = plt.subplots(3 * groups, cols, figsize=(2.3 * cols, 5.6 * groups), dpi=170,
                             facecolor=SURFACE, squeeze=False)
    for a in axes.flat:
        a.axis("off"); a.set_facecolor(SURFACE)
    colors = ["#2a78d6", "#eb6834", "#129b6b", "#d55181", "#6b5bd2"]
    for k, ((inst, strokes, (x0, y0, x1, y1), ink_win, own, model, geom), r) in enumerate(zip(panels, results)):
        g, c = divmod(k, cols)
        a0, a1, a2 = axes[3 * g, c], axes[3 * g + 1, c], axes[3 * g + 2, c]
        a0.imshow(rgb[y0:y1, x0:x1], extent=(x0, x1, y1, y0), interpolation="lanczos")
        a0.set_title(f"“{inst['char']}” · {inst.get('context', '')} · line {inst['line']}", fontsize=8, color=INK_TEXT, loc="left")
        a1.imshow(rgb[y0:y1, x0:x1], extent=(x0, x1, y1, y0), interpolation="lanczos", alpha=0.45)
        for i, s in enumerate(strokes):
            P = np.array(s["points"])
            a1.plot(P[:, 0], P[:, 1], color=colors[i % len(colors)], lw=1.6)
            a1.annotate("", xy=P[-1], xytext=P[-2] if len(P) > 1 else P[-1],
                        arrowprops=dict(arrowstyle="-|>", color=colors[i % len(colors)], lw=1.2))
            a1.text(P[0][0], P[0][1] - 0.6, str(i + 1), color=colors[i % len(colors)], fontsize=7, ha="center", va="bottom")
        a1.set_xlim(x0, x1); a1.set_ylim(y1, y0)
        a1.set_title("strokes, in order", fontsize=7.5, color=MUTED, loc="left")
        vis = np.ones(ink_win.shape + (3,))
        vis[ink_win > 0] = (0.88, 0.88, 0.86)
        vis[(own > 0) & (model == 0)] = matplotlib.colors.to_rgb(DATA)
        vis[(model > 0) & (own == 0)] = matplotlib.colors.to_rgb(MODEL)
        vis[(model > 0) & (own > 0)] = (0.1, 0.1, 0.1)
        a2.imshow(vis, extent=(x0, x1, y1, y0), interpolation="nearest")
        a2.set_title(f"page's pen · off by {r['outline_dist_px']:.1f} px", fontsize=7.5, color=MUTED, loc="left")
    handles = [matplotlib.patches.Patch(color=(0.1, 0.1, 0.1), label="model and ink agree"),
               matplotlib.patches.Patch(color=DATA, label="ink the model misses"),
               matplotlib.patches.Patch(color=MODEL, label="model where there is no ink")]
    fig.legend(handles=handles, loc="lower center", ncol=3, frameon=False, fontsize=7, labelcolor=INK_TEXT)
    fig.tight_layout(rect=(0, 0.05 / groups, 1, 1))
    fig.savefig(path, facecolor=SURFACE)
    plt.close(fig)


if __name__ == "__main__":
    for page in (sys.argv[1:] or list(PAGES)):
        main(page)
