"""How square are the corners of the pen of MS 2262?

An elliptical nib rounds off the lozenge heads and feet of textura; a broad-edge quill
has a straight edge and corners. The nib is modelled as a superellipse with corner
exponent p (2 = ellipse, inf = sharp rectangle; pen.nib_outline), and p is tested two
ways:

1. Width by direction: the page's per-direction median stroke widths (latin_lines.py,
   from ink mass) are refitted for each p (nib.fit_nib_corners).
2. Letter outlines: the minim module (minims.py) is refitted with each nib, scaled to
   the page's ink width, and its n's and m's are compared with the ink, over the whole
   letter and at the heads and feet only, where the corners show.

Run:  python3 corners.py   → out/hours_nib_corners.png, out/hours_nib_corners.json
"""
import json
from pathlib import Path

import cv2
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

import minims as M
import nib
import pen

HERE = Path(__file__).resolve().parent
OUT = HERE / "out"
SURFACE, INK_TEXT, MUTED, MODEL = "#fcfcfb", "#0b0b0b", "#52514e", "#eb6834"
PS = (2.0, 2.5, 3.0, 4.0, 6.0, np.inf)
SHOW = (2.0, 4.0, np.inf)
HEAD_JOIN = (0.50, "head")   # minims.py's measured head join


def edge(m):
    return (m > 0) & (cv2.erode(m, np.ones((3, 3), np.uint8)) == 0)


def zone_outline(geom, mask, i):
    """Outline distance (px) at the heads and feet only: within 0.15–0.25 x-height of
    the x-line and the baseline."""
    x0, y0, x1, y1 = i["box"]
    ink_ = (mask[y0:y1, x0:x1] > 0).astype(np.uint8)
    mod = pen.rasterize(geom, ink_.shape, origin=(x0, y0))
    h = (i["yb"] - np.arange(y0, y1)[:, None] * np.ones((1, x1 - x0))) / i["xh"]
    zone = ((h > 0.75) & (h < 1.15)) | ((h > -0.15) & (h < 0.25))
    eo, em = edge(ink_), edge(mod)
    do = cv2.distanceTransform((~eo).astype(np.uint8), cv2.DIST_L2, 5)
    dm = cv2.distanceTransform((~em).astype(np.uint8), cv2.DIST_L2, 5)
    return float(0.5 * (do[em & zone].mean() + dm[eo & zone].mean()))


def main():
    OUT.mkdir(exist_ok=True)
    rgb, mask, lines, dark = M.load()
    lines_json = json.loads((HERE / "data" / "hours_lines.json").read_text(encoding="utf-8"))
    w_ink = (M.PEN["a"] + M.PEN["b"]) / 2   # load() scaled the nib to the page's ink width
    rows, shown = [], {}
    for r in nib.fit_nib_corners(lines_json["pen"]["bins"], PS):
        k = w_ink / ((r["a"] + r["b"]) / 2)
        M.PEN.update(a=r["a"] * k, b=r["b"] * k, theta=r["theta_deg"], p=r["p"])
        inst = [M.make_instance(lines, n, stems, ch=ch, word=word) for ch, word, n, stems in M.INSTANCES]
        q, fit = M.fit_minim(inst, mask)
        ov, od, zd = [], [], []
        for i in inst:
            g = M.render_letter(i["stems"], i["yb"], i["xh"], i["slant"], q, [HEAD_JOIN] * (len(i["stems"]) - 1))
            ov.append(M.score(g, mask, i["box"]))
            od.append(M.outline_distance(g, mask, i["box"]))
            zd.append(zone_outline(g, mask, i))
            if r["p"] in SHOW and i["word"] == "nomen" and i["line"] == 22 and i["ch"] == "m":
                shown[r["p"]] = (i, g)
        rows.append(dict(r, nib=dict(M.PEN), module=dict(zip(M.PARAMS, map(float, q))), overlap=float(np.mean(ov)),
                         outline_px=float(np.mean(od)), heads_feet_outline_px=float(np.mean(zd))))
        print(f"p={r['p']:>4}: width-by-direction rms {r['rms_px']:.3f} px | minims: overlap {np.mean(ov):.3f}, "
              f"outline {np.mean(od):.3f} px, at heads and feet {np.mean(zd):.3f} px", flush=True)

    fig, axes = plt.subplots(1, len(SHOW), figsize=(2.6 * len(SHOW), 3.0), dpi=200, facecolor=SURFACE)
    sc = 8
    for ax, p in zip(axes, SHOW):
        i, g = shown[p]
        x0, y0, x1, y1 = i["box"]
        crop = cv2.resize(cv2.cvtColor(rgb[y0:y1, x0:x1], cv2.COLOR_RGB2GRAY), None, fx=sc, fy=sc,
                          interpolation=cv2.INTER_CUBIC)
        ax.imshow(crop, cmap="gray", vmin=0, vmax=255, extent=(x0, x1, y1, y0))
        for poly in (g.geoms if hasattr(g, "geoms") else [g]):
            ax.plot(*poly.exterior.xy, color=MODEL, lw=0.9)
        ax.set_xlim(x0, x1); ax.set_ylim(y1, y0); ax.axis("off")
        r = [r for r in rows if r["p"] == p][0]
        name = "ellipse" if p == 2 else ("sharp rectangle" if np.isinf(p) else f"superellipse p = {p:g}")
        ax.set_title(f"{name}\nheads and feet off by {r['heads_feet_outline_px']:.2f} px", fontsize=7.5,
                     color=INK_TEXT, loc="left")
    fig.suptitle("Nib corners: the fitted minims drawn with three nibs over the m of 'nomen' (line 22)",
                 fontsize=8.5, color=INK_TEXT, x=0.01, ha="left")
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    fig.savefig(OUT / "hours_nib_corners.png", facecolor=SURFACE)
    plt.close(fig)
    (OUT / "hours_nib_corners.json").write_text(json.dumps(rows, indent=1, default=float), encoding="utf-8")


if __name__ == "__main__":
    main()
