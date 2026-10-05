"""Stroke plan (ductus) for الله in this Hijazi hand, driven by measured features.

Local coordinates: origin at the foot of the second lām on the baseline centre-line,
x to the right, y down (so letters rise into negative y). Writing order is right to
left: alif, then lām¹ (which carries the baseline connection to lām²), then lām² (which
runs on along the baseline into the final hā' loop).

Feature names match measure.py. Measured heights and widths are ink extents, so half a
stroke width is taken off where a centre-line is needed.
"""
import numpy as np


def _shaft_top(foot_x, height, slant_deg, s):
    h = height - 0.45 * s  # centre-line stops about half a nib short of the ink edge
    return np.array([foot_x + h * np.tan(np.radians(slant_deg)), -h])


def allah_strokes(f, s, with_alif=True):
    """Control points for each stroke. f: feature dict (px), s: stroke width (px)."""
    tan = lambda deg: np.tan(np.radians(deg))
    x2 = 0.0
    x1 = f["lam_spacing"]
    strokes = []

    if with_alif and "h_alif" in f:
        xa = x1 + f["alif_gap"]
        top = _shaft_top(xa, f["h_alif"], f["slant_alif"], s)
        foot = 0.3 * s  # the alif does not join, so it stops short of the baseline centre
        strokes.append([top, [xa + foot * tan(f["slant_alif"]), -foot]])

    # lām¹ comes down and turns left along the baseline to meet lām²
    top1 = _shaft_top(x1, f["h_lam1"], f["slant_lam1"], s)
    k1 = 0.18 * f["h_lam1"]
    strokes.append([top1, [x1 + k1 * tan(f["slant_lam1"]), -k1], [x1 - 0.35 * s, 0.05 * s], [x2, 0.0]])

    # lām² comes down, runs left along the baseline and closes the hā' loop
    top2 = _shaft_top(x2, f["h_lam2"], f["slant_lam2"], s)
    k2 = 0.18 * f["h_lam2"]
    lw = max(f["ha_loop_width"] - s, 0.35 * s)       # loop width (centre-line)
    hh = max(f["ha_height"] - s, 0.35 * s)           # loop height (centre-line)
    xl = -f["tail_length"] + 0.5 * s                 # leftmost centre-line point
    xr = xl + lw
    strokes.append([
        top2, [x2 + k2 * tan(f["slant_lam2"]), -k2], [x2 - 0.35 * s, 0.05 * s],
        [min(xr + 0.25 * s, x2 - 0.6 * s), 0.05 * s],    # connector into the loop
        [xl + 0.45 * lw, 0.15 * s],                      # along the bottom of the loop
        [xl, -0.40 * hh],                                # up the left side
        [xl + 0.40 * lw, -hh],                           # over the top
        [xr, -0.55 * hh],                                # down the right side
        [xl + 0.70 * lw, -0.05 * hh],                    # close onto the baseline
    ])
    return strokes


def place(strokes, origin):
    ox, oy = origin
    return [[(float(p[0]) + ox, float(p[1]) + oy) for p in s] for s in strokes]
