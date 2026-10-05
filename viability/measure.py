"""Refine rough hand traces against the ink and measure each instance of الله.

A human (or the tracer tool) only has to click roughly where each stroke starts and ends.
This module snaps those placements to the ink: every shaft is re-fitted as a straight
line through the ink pixels near it, the baseline is found from the lower edge of the
connecting stroke, and the final hā' is measured from the ink blob at the left end.

Measurements are reported in page pixels and in nib widths (the calligrapher's unit).
"""
import json
from pathlib import Path

import cv2
import numpy as np

import ink

HERE = Path(__file__).resolve().parent
SHAFTS = ("alif", "lam1", "lam2")


def _line_frame(p0, p1):
    d = np.asarray(p1, float) - np.asarray(p0, float)
    L = float(np.hypot(*d))
    u = d / L
    n = np.array([-u[1], u[0]])
    return u, n, L


def _sample(img, pts):
    """Bilinear sample of img at float (x, y) points; outside the image reads as 0."""
    x, y = pts[:, 0], pts[:, 1]
    x0, y0 = np.floor(x).astype(int), np.floor(y).astype(int)
    fx, fy = x - x0, y - y0
    h, w = img.shape
    out = np.zeros(len(pts))
    for dx, dy, wt in ((0, 0, (1 - fx) * (1 - fy)), (1, 0, fx * (1 - fy)), (0, 1, (1 - fx) * fy), (1, 1, fx * fy)):
        xi, yi = x0 + dx, y0 + dy
        ok = (xi >= 0) & (xi < w) & (yi >= 0) & (yi < h)
        out[ok] += wt[ok] * img[yi[ok], xi[ok]]
    return out


def snap_segment(mask, top, bottom, baseline, search=10.0, max_turn=12.0):
    """Move a rough shaft placement onto the ink.

    Tries sideways offsets and small rotations of the rough segment (upper part only,
    away from the baseline) and keeps the one that runs through the most ink. This is
    what lets a tracer click approximately instead of precisely.
    """
    soft = cv2.GaussianBlur(mask.astype(np.float32), (0, 0), 1.0)
    p0, p1 = np.asarray(top, float), np.asarray(bottom, float)
    mid = (p0 + 0.6 * (p1 - p0))  # rotate about a point above the baseline
    best = (-1.0, p0, p1)
    ts = np.linspace(0.0, 1.0, 40)
    for turn in np.arange(-max_turn, max_turn + 0.1, 1.5):
        a = np.radians(turn)
        R = np.array([[np.cos(a), -np.sin(a)], [np.sin(a), np.cos(a)]])
        q0, q1 = mid + R @ (p0 - mid), mid + R @ (p1 - mid)
        u, n, _ = _line_frame(q0, q1)
        for off in np.arange(-search, search + 0.1, 0.5):
            a0, a1 = q0 + n * off, q1 + n * off
            line = a0[None] + ts[:, None] * (a1 - a0)[None]
            line = line[line[:, 1] < baseline - 5]
            if len(line) < 10:
                continue
            score = _sample(soft, line).mean()
            if score > best[0]:
                best = (score, a0, a1)
    return best[1], best[2], best[0]


def fit_shaft(mask, top, bottom, baseline, band=3.5, snap=True):
    """Fit a straight shaft through the ink near the rough top→bottom placement.

    Pixels in the baseline zone are ignored so the connecting stroke does not pull the
    fit. The top end is found by walking up the axis from the baseline until the ink
    stops, so strokes from the line above are not absorbed. Returns the refined top
    point, the foot (where the shaft axis meets the baseline), slant from vertical
    (positive = top leans right), height and perpendicular stroke width.
    """
    ys, xs = np.nonzero(mask)
    pts = np.c_[xs, ys].astype(float)
    p0, p1 = np.asarray(top, float), np.asarray(bottom, float)
    # The traced top is trusted to within a few pixels: ink above that belongs to the
    # line above when strokes touch (common on this page).
    y_cap = p0[1] - 4.0
    if snap:
        p0, p1, _ = snap_segment(mask, p0, p1, baseline)
    for it in range(2):
        u, n, L = _line_frame(p0, p1)
        rel = pts - p0
        t, s = rel @ u, rel @ n
        sel = (np.abs(s) <= band) & (t >= -6) & (t <= L + 4) & (pts[:, 1] <= baseline - 4) & (pts[:, 1] >= y_cap)
        P, tP = pts[sel], t[sel]
        if len(P) < 10:
            raise ValueError(f"too little ink near shaft {top}->{bottom}")
        # keep only the run of ink contiguous with the lower part of the shaft
        slices = np.unique(np.floor(tP).astype(int))
        lo = int(np.floor(np.percentile(tP, 60)))
        k = lo
        present = set(slices.tolist())
        while any((k - g) in present for g in (1, 2)):
            k -= 1
        P = P[tP >= k]
        c = P.mean(0)
        w, V = np.linalg.eigh(np.cov((P - c).T))
        u = V[:, np.argmax(w)]
        if u[1] < 0:  # point downwards
            u = -u
        tt = (P - c) @ u
        p0 = c + u * tt.min()
        p1 = c + u * ((baseline - c[1]) / u[1])  # foot: axis meets the baseline
        sel_pts = P
    u, n, L = _line_frame(p0, p1)
    s = (sel_pts - p0) @ n
    t = (sel_pts - p0) @ u
    # perpendicular width: per 1px slice along the axis, extent across it
    widths = []
    for k in np.arange(np.floor(t.min()) + 3, np.ceil(t.max()) - 3):
        m = (t >= k) & (t < k + 1)
        if m.sum() >= 2:
            widths.append(s[m].max() - s[m].min() + 1.0)
    slant = float(np.degrees(np.arctan2(p0[0] - p1[0], p1[1] - p0[1])))
    return {
        "top": [float(p0[0]), float(p0[1])],
        "foot": [float(p1[0]), float(p1[1])],
        "slant_deg": slant,
        "height": float(baseline - p0[1]),
        "width": float(np.median(widths)) if widths else float("nan"),
        "n_px": int(len(sel_pts)),
    }


def fit_baseline(mask, x_left, x_right, rough_y, stroke_w):
    """Centre line of the horizontal connecting stroke between x_left and x_right."""
    ys = []
    for x in range(int(round(x_left)), int(round(x_right)) + 1):
        col = mask[int(rough_y - 8): int(rough_y + 7), x]
        idx = np.nonzero(col)[0]
        if len(idx):
            ys.append(rough_y - 8 + idx.max() - (stroke_w - 1) / 2.0)
    return float(np.median(ys)) if ys else float(rough_y)


def measure_ha(mask, x_right, x_left_rough, baseline, stroke_w):
    """Final hā': leftmost extent, loop height above the baseline, loop width."""
    x0 = int(round(x_left_rough - 2))
    x1 = int(round(x_right))
    y0 = int(round(baseline - 18))
    y1 = int(round(baseline + 8))
    win = mask[y0:y1, x0:x1].copy()
    # keep only ink connected to the baseline stroke just left of lām², so letters of
    # the next word and descenders from the line above are not counted
    n, lab = cv2.connectedComponents(win, connectivity=8)
    by = int(round(baseline)) - y0
    seed = lab[max(by - 2, 0): by + 3, max(x1 - x0 - 8, 0): x1 - x0]
    ids = [i for i in np.unique(seed) if i]
    win = np.isin(lab, ids).astype(np.uint8) if ids else win
    ys, xs = np.nonzero(win)
    if len(xs) == 0:
        raise ValueError("no ink for hā'")
    xs = xs + x0
    ys = ys + y0
    left = float(xs.min())
    above = ys < baseline - 0.6 * stroke_w  # the loop rises above the connecting stroke
    loop_xs = xs[above & (xs < left + 0.7 * (x_right - left))]
    loop_ys = ys[above & (xs < left + 0.7 * (x_right - left))]
    top = float(loop_ys.min()) if len(loop_ys) else float(baseline)
    loop_w = float(loop_xs.max() - left + 1) if len(loop_xs) else 0.0
    return {"left": left, "top": top, "height": float(baseline + stroke_w / 2 - top), "loop_width": loop_w}


def fit_shafts(mask, rough, baseline):
    """Fit shafts right to left (the writing order); each fitted shaft claims its ink
    so a neighbouring rough placement cannot snap onto the same stroke."""
    work = mask.copy()
    yy, xx = np.mgrid[0:mask.shape[0], 0:mask.shape[1]]
    out = {}
    for name in SHAFTS:
        if name not in rough:
            continue
        top, bottom = rough[name]
        out[name] = r = fit_shaft(work, top, bottom, baseline)
        u, n, L = _line_frame(r["top"], r["foot"])
        rel_x, rel_y = xx - r["top"][0], yy - r["top"][1]
        s = rel_x * n[0] + rel_y * n[1]
        t = rel_x * u[0] + rel_y * u[1]
        claim = (np.abs(s) <= r["width"] / 2 + 1.0) & (t >= -2) & (yy <= baseline - 4)
        work[claim] = 0
    return out


def measure_instance(mask, inst):
    st = inst["strokes"]
    rb = inst["baseline"]
    out = {"id": inst["id"], "line": inst["line"], "context": inst["context"], "flags": inst.get("flags", [])}
    shafts = fit_shafts(mask, {n: st[n] for n in SHAFTS if n in st}, rb)
    w = float(np.median([s["width"] for s in shafts.values()]))
    lam2_foot_x = shafts["lam2"]["foot"][0]
    base = fit_baseline(mask, st["ha"][1][0] + 2, lam2_foot_x - 1, rb, w)
    # re-fit shafts against the refined baseline so heights and feet are consistent
    shafts = fit_shafts(mask, {n: [[s["top"][0], max(s["top"][1], st[n][0][1])], s["foot"]] for n, s in shafts.items()}, base)
    w = float(np.median([s["width"] for s in shafts.values()]))
    ha = measure_ha(mask, shafts["lam2"]["foot"][0], st["ha"][1][0], base, w)
    out.update({"baseline_y": base, "stroke_width": w, "shafts": shafts, "ha": ha})
    f = {
        "stroke_width": w,
        "h_lam1": shafts["lam1"]["height"],
        "h_lam2": shafts["lam2"]["height"],
        "slant_lam1": shafts["lam1"]["slant_deg"],
        "slant_lam2": shafts["lam2"]["slant_deg"],
        "lam_spacing": shafts["lam1"]["foot"][0] - shafts["lam2"]["foot"][0],
        "tail_length": shafts["lam2"]["foot"][0] - ha["left"],
        "ha_height": ha["height"],
        "ha_loop_width": ha["loop_width"],
    }
    if "alif" in shafts:
        f.update({
            "h_alif": shafts["alif"]["height"],
            "slant_alif": shafts["alif"]["slant_deg"],
            "alif_gap": shafts["alif"]["foot"][0] - shafts["lam1"]["foot"][0],
        })
    out["features_px"] = f
    return out


def load_traces(path=HERE / "data" / "traces_allah.json"):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def page_mask(traces):
    rgb = ink.load_rgb(HERE / "data" / traces["image"])
    mask, dark = ink.ink_mask(rgb)
    return rgb, mask, dark


if __name__ == "__main__":
    traces = load_traces()
    rgb, mask, _ = page_mask(traces)
    res = [measure_instance(mask, i) for i in traces["instances"]]
    for r in res:
        f = r["features_px"]
        print(r["id"], " ".join(f"{k}={v:.1f}" for k, v in f.items()))
