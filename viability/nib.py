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
