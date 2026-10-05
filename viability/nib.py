"""Estimate the pen from the whole page: stroke width as a function of stroke direction.

A nib held at a fixed angle θ draws a line whose width depends on the direction of
travel φ. A cut reed with worn corners is modelled as an ellipse with a broad axis a
and a narrow axis b; the width it leaves is

    width(φ)² = a²·sin²(φ − θ) + b²·cos²(φ − θ)

Moving along the broad axis gives the thinnest line (b); moving across it the thickest
(a). The model is linear in (a², b²) for a fixed θ, so it is fitted by least squares
over a grid of angles. a/b is the thick/thin contrast: a sharp broad-edge pen is 5–10,
a monoline pen is 1. Angles use the maths convention (0° = rightwards, 90° = upwards).
"""
import cv2
import numpy as np
from scipy.spatial import cKDTree
from skimage.morphology import skeletonize


def width_direction_samples(mask, radius=5, min_linearity=6.0, margin=40):
    """(direction_deg in [0,180), width_px) at skeleton points on straight-ish strokes."""
    h, w = mask.shape
    dt = cv2.distanceTransform(mask.astype(np.uint8), cv2.DIST_L2, 5)
    sk = skeletonize(mask > 0)
    ys, xs = np.nonzero(sk)
    keep = (xs > margin) & (xs < w - margin) & (ys > margin) & (ys < h - margin)
    xs, ys = xs[keep], ys[keep]
    pts = np.c_[xs, ys].astype(float)
    tree = cKDTree(pts)
    dirs, widths = [], []
    for i, nb in enumerate(tree.query_ball_point(pts, radius)):
        if len(nb) < 2 * radius - 1:
            continue
        P = pts[nb] - pts[nb].mean(0)
        ev, V = np.linalg.eigh(P.T @ P)
        if ev[0] <= 1e-9 or ev[1] / max(ev[0], 1e-9) < min_linearity:
            continue  # junction or tight curve: width there is not a nib property
        dx, dy = V[:, 1]
        phi = np.degrees(np.arctan2(-dy, dx)) % 180.0  # y-up convention
        dirs.append(phi)
        widths.append(2.0 * dt[ys[i], xs[i]])
    return np.array(dirs), np.array(widths)


def nib_model(phi_deg, a, b, theta_deg):
    d = np.radians(np.asarray(phi_deg) - theta_deg)
    return np.sqrt((a * np.sin(d)) ** 2 + (b * np.cos(d)) ** 2)


def fit_nib(dirs, widths, bin_deg=10):
    """Fit (a, b, θ) to per-direction median widths (robust to outliers)."""
    edges = np.arange(0, 180 + bin_deg, bin_deg)
    centres, med, counts = [], [], []
    for lo, hi in zip(edges[:-1], edges[1:]):
        m = (dirs >= lo) & (dirs < hi)
        if m.sum() >= 15:
            centres.append((lo + hi) / 2)
            med.append(np.median(widths[m]))
            counts.append(int(m.sum()))
    centres, med = np.array(centres), np.array(med)
    best = None
    for theta in np.arange(0, 180, 1.0):
        d = np.radians(centres - theta)
        A = np.c_[np.sin(d) ** 2, np.cos(d) ** 2]
        coef, *_ = np.linalg.lstsq(A, med ** 2, rcond=None)
        a, b = np.sqrt(np.clip(coef, 0.25, None))
        err = np.sum((nib_model(centres, a, b, theta) - med) ** 2)
        if best is None or err < best[0]:
            best = (err, a, b, theta)
    err, a, b, theta = best
    if a < b:  # keep a as the broad edge
        a, b, theta = b, a, (theta + 90) % 180
    rms = float(np.sqrt(err / len(med)))
    return {"a": float(a), "b": float(b), "theta_deg": float(theta), "contrast": float(a / b),
            "rms_px": rms, "bins": {"centre_deg": centres.tolist(), "median_width": med.tolist(), "n": counts}}


def mass_width_samples(mask, dark, radius=5, min_linearity=6.0, margin=40, reach=7.0, step=0.5):
    """Stroke width from the amount of ink across the stroke, for thin strokes.

    When strokes are only 2–4 px wide, counting pixels cannot tell a 2.4 px hairline
    from a 3.4 px stem. Blur spreads ink sideways but does not change how much ink
    lies across the stroke, so the darkness summed along the stroke's normal is
    proportional to its true width. Dividing by the darkness of solid ink (taken from
    the centres of the heaviest strokes) turns it back into pixels.
    """
    h, w = mask.shape
    sk = skeletonize(mask > 0)
    ys, xs = np.nonzero(sk)
    keep = (xs > margin) & (xs < w - margin) & (ys > margin) & (ys < h - margin)
    xs, ys = xs[keep], ys[keep]
    pts = np.c_[xs, ys].astype(float)
    tree = cKDTree(pts)
    offs = np.arange(-reach, reach + step / 2, step)
    dirs, masses, peaks = [], [], []

    def bilinear(px, py):
        x0, y0 = np.floor(px).astype(int), np.floor(py).astype(int)
        fx, fy = px - x0, py - y0
        x0 = np.clip(x0, 0, w - 2); y0 = np.clip(y0, 0, h - 2)
        return ((1 - fx) * (1 - fy) * dark[y0, x0] + fx * (1 - fy) * dark[y0, x0 + 1]
                + (1 - fx) * fy * dark[y0 + 1, x0] + fx * fy * dark[y0 + 1, x0 + 1])

    for i, nb in enumerate(tree.query_ball_point(pts, radius)):
        if len(nb) < 2 * radius - 1:
            continue
        P = pts[nb] - pts[nb].mean(0)
        ev, V = np.linalg.eigh(P.T @ P)
        if ev[0] <= 1e-9 or ev[1] / max(ev[0], 1e-9) < min_linearity:
            continue
        dx, dy = V[:, 1]
        nx, ny = -dy, dx
        prof = bilinear(pts[i, 0] + offs * nx, pts[i, 1] + offs * ny)
        c = len(offs) // 2
        k = c + int(np.argmax(prof[c - 2:c + 3])) - 2
        pk = prof[k]
        if pk <= 0:
            continue
        lo, hi = k, k
        while lo > 0 and prof[lo - 1] > 0.15 * pk and prof[lo - 1] <= prof[lo] * 1.15:
            lo -= 1
        while hi < len(prof) - 1 and prof[hi + 1] > 0.15 * pk and prof[hi + 1] <= prof[hi] * 1.15:
            hi += 1
        if lo == 0 or hi == len(prof) - 1:
            continue  # ran into a neighbouring stroke
        dirs.append(np.degrees(np.arctan2(-dy, dx)) % 180.0)
        masses.append(prof[lo:hi + 1].sum() * step)
        peaks.append(pk)
    dirs, masses, peaks = map(np.array, (dirs, masses, peaks))
    solid = np.percentile(peaks, 90)  # darkness of solid ink
    return dirs, masses / solid


def profile_mass(dark, point, normal, reach=7.0, step=0.5):
    """Ink summed across one stroke at `point` along `normal`, stopping where the
    profile turns up again (the gap before a neighbouring stroke). None if the stroke
    runs into the edge of the window."""
    h, w = dark.shape
    offs = np.arange(-reach, reach + step / 2, step)
    px, py = point[0] + offs * normal[0], point[1] + offs * normal[1]
    x0, y0 = np.floor(px).astype(int), np.floor(py).astype(int)
    fx, fy = px - x0, py - y0
    x0 = np.clip(x0, 0, w - 2); y0 = np.clip(y0, 0, h - 2)
    prof = ((1 - fx) * (1 - fy) * dark[y0, x0] + fx * (1 - fy) * dark[y0, x0 + 1]
            + (1 - fx) * fy * dark[y0 + 1, x0] + fx * fy * dark[y0 + 1, x0 + 1])
    c = len(offs) // 2
    k = c + int(np.argmax(prof[c - 2:c + 3])) - 2
    pk = prof[k]
    if pk <= 0:
        return None
    lo = hi = k
    while lo > 0 and prof[lo - 1] > 0.15 * pk and prof[lo - 1] <= prof[lo] * 1.15:
        lo -= 1
    while hi < len(prof) - 1 and prof[hi + 1] > 0.15 * pk and prof[hi + 1] <= prof[hi] * 1.15:
        hi += 1
    if lo == 0 or hi == len(prof) - 1:
        return None
    return float(prof[lo:hi + 1].sum() * step)
