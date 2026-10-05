"""Ink-following strokes: the path between two clicks runs along the ink's centre-line.

Clicking every few pixels along a 14 px-high cursive letter is slow and imprecise.
Instead the tracer only marks where a stroke starts, where it turns, and where it
ends; between consecutive clicks the cheapest path through a cost map is taken, where
dark ink is cheap and parchment is expensive. Because ink is darkest at the middle of
a stroke (the scan blurs the edges), the path settles on the centre-line.

tools/tracer/index.html uses the same cost function and snapping radius.
"""
import numpy as np
from skimage.graph import route_through_array

SNAP_RADIUS = 1.5


def inkiness(dark, thr):
    return np.clip((dark - 0.5 * thr) / thr, 0.0, 1.0)


def cost_map(dark, thr):
    # ~1.4 per px on solid ink, ~4.6 on parchment, ~3.5 on a faint hairline: cheap
    # enough to keep to the ink, but not so cheap that a long detour through dark
    # neighbouring strokes beats following a hairline directly.
    s = inkiness(dark, thr)
    return 0.6 + 1.0 / (0.25 + s * s)


def snap(dark, p, r=SNAP_RADIUS):
    """Move a click to the darkest pixel within r px (the stroke's centre)."""
    x, y = p
    x0, x1 = int(np.floor(x - r)), int(np.ceil(x + r))
    y0, y1 = int(np.floor(y - r)), int(np.ceil(y + r))
    yy, xx = np.mgrid[y0:y1 + 1, x0:x1 + 1]
    ok = (xx - x) ** 2 + (yy - y) ** 2 <= r * r
    ok &= (xx >= 0) & (yy >= 0) & (xx < dark.shape[1]) & (yy < dark.shape[0])
    if not ok.any():
        return [float(x), float(y)]
    vals = np.where(ok, dark[np.clip(yy, 0, dark.shape[0] - 1), np.clip(xx, 0, dark.shape[1] - 1)], -1)
    k = np.unravel_index(np.argmax(vals), vals.shape)
    return [float(xx[k]), float(yy[k])]


def rdp(points, eps):
    """Ramer–Douglas–Peucker simplification."""
    P = np.asarray(points, float)
    if len(P) < 3:
        return P.tolist()
    a, b = P[0], P[-1]
    ab = b - a
    L = np.hypot(*ab)
    if L < 1e-9:
        d = np.hypot(*(P - a).T)
    else:
        d = np.abs(ab[0] * (P[:, 1] - a[1]) - ab[1] * (P[:, 0] - a[0])) / L
    k = int(np.argmax(d))
    if d[k] > eps:
        return rdp(P[:k + 1], eps)[:-1] + rdp(P[k:], eps)
    return [a.tolist(), b.tolist()]


def follow(dark, thr, a, b, eps=0.5):
    """Centre-line path from a to b (page px), simplified to within eps px."""
    d = np.hypot(b[0] - a[0], b[1] - a[1])
    m = max(6, int(np.ceil(0.35 * d)) + 4)
    x0 = max(0, int(np.floor(min(a[0], b[0]) - m))); x1 = min(dark.shape[1] - 1, int(np.ceil(max(a[0], b[0]) + m)))
    y0 = max(0, int(np.floor(min(a[1], b[1]) - m))); y1 = min(dark.shape[0] - 1, int(np.ceil(max(a[1], b[1]) + m)))
    cost = cost_map(dark[y0:y1 + 1, x0:x1 + 1], thr)
    start = (int(round(a[1])) - y0, int(round(a[0])) - x0)
    end = (int(round(b[1])) - y0, int(round(b[0])) - x0)
    path, _ = route_through_array(cost, start, end, fully_connected=True, geometric=True)
    pts = [[c + x0, r + y0] for r, c in path]
    pts[0], pts[-1] = list(a), list(b)
    return rdp(pts, eps)


def trace_stroke(dark, thr, clicks, snap_clicks=True):
    """Full stroke through all clicks; returns (snapped clicks, dense centre-line)."""
    cl = [snap(dark, c) if snap_clicks else list(c) for c in clicks]
    pts = [cl[0]]
    for a, b in zip(cl[:-1], cl[1:]):
        pts += follow(dark, thr, a, b)[1:]
    return cl, pts
