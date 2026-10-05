"""Nib-sweep renderer: stroke centre-lines + a pen → vector outline.

Each stroke is a list of control points (page or local pixel coordinates, y down).
The centre-line is smoothed with a centripetal Catmull–Rom spline and sampled densely.
The nib (an ellipse at a fixed angle, see nib.py) is placed at every sample; consecutive
placements are joined by their convex hull and everything is merged into one outline.
Hulling consecutive stamps is what keeps the edges smooth instead of scalloped.
"""
import cv2
import numpy as np
import shapely
from shapely import affinity
from shapely.geometry import MultiPoint, Polygon


def catmull_rom(ctrl, step=0.5, alpha=0.5):
    """Centripetal Catmull–Rom through the control points, sampled every ~step px."""
    P = np.asarray(ctrl, float)
    if len(P) == 2:
        n = max(2, int(np.hypot(*(P[1] - P[0])) / step) + 1)
        return P[0] + np.linspace(0, 1, n)[:, None] * (P[1] - P[0])
    P = np.vstack([2 * P[0] - P[1], P, 2 * P[-1] - P[-2]])
    out = []
    for i in range(1, len(P) - 2):
        p0, p1, p2, p3 = P[i - 1], P[i], P[i + 1], P[i + 2]
        t0 = 0.0
        t1 = t0 + max(np.hypot(*(p1 - p0)), 1e-6) ** alpha
        t2 = t1 + max(np.hypot(*(p2 - p1)), 1e-6) ** alpha
        t3 = t2 + max(np.hypot(*(p3 - p2)), 1e-6) ** alpha
        n = max(2, int(np.hypot(*(p2 - p1)) / step) + 1)
        for t in np.linspace(t1, t2, n, endpoint=(i == len(P) - 3)):
            a1 = (t1 - t) / (t1 - t0) * p0 + (t - t0) / (t1 - t0) * p1
            a2 = (t2 - t) / (t2 - t1) * p1 + (t - t1) / (t2 - t1) * p2
            a3 = (t3 - t) / (t3 - t2) * p2 + (t - t2) / (t3 - t2) * p3
            b1 = (t2 - t) / (t2 - t0) * a1 + (t - t0) / (t2 - t0) * a2
            b2 = (t3 - t) / (t3 - t1) * a2 + (t - t1) / (t3 - t1) * a3
            out.append((t2 - t) / (t2 - t1) * b1 + (t - t1) / (t2 - t1) * b2)
    return np.array(out)


class Nib:
    """Elliptical nib: broad axis a, narrow axis b, broad-axis angle θ (degrees, y-up)."""

    def __init__(self, a, b, theta_deg, n=24):
        self.a, self.b, self.theta = float(a), float(b), float(theta_deg)
        t = np.linspace(0, 2 * np.pi, n, endpoint=False)
        shape = Polygon(np.c_[a / 2 * np.cos(t), b / 2 * np.sin(t)])
        # page coordinates have y down, so an on-page anticlockwise angle is negative here
        self.shape = affinity.rotate(shape, -self.theta, origin=(0, 0))
        self.coords = np.asarray(self.shape.exterior.coords)[:-1]

    def scaled(self, k):
        return Nib(self.a * k, self.b * k, self.theta)


def sweep(points, nib):
    """Outline swept by the nib along a dense centre-line."""
    hulls = []
    for p, q in zip(points[:-1], points[1:]):
        hulls.append(MultiPoint(np.vstack([nib.coords + p, nib.coords + q])).convex_hull)
    return shapely.union_all(hulls) if hulls else Polygon()


CORNER_FRACTION = 0.5  # corner hairline width as a share of the nib's narrow edge


def is_corner_stroke(name):
    """Strokes drawn with the corner of the pen rather than its edge: hairlines and
    tails. On MS 2262 these are thinner than the nib's own narrow edge (about half)."""
    n = (name or "").lower()
    return n.startswith("hairline") or "tail" in n


def corner_nib(nib):
    c = CORNER_FRACTION * nib.b
    return Nib(c, c, nib.theta)


def render(strokes, nib, step=0.5, names=None):
    """Union of all swept strokes. strokes: list of control-point lists. With names,
    strokes named as hairlines or tails are drawn with the pen's corner."""
    corner = corner_nib(nib)
    names = names or [None] * len(strokes)
    return shapely.union_all([sweep(catmull_rom(s, step), corner if is_corner_stroke(n) else nib)
                              for s, n in zip(strokes, names)])


def _polys(geom):
    if geom.is_empty:
        return []
    return list(geom.geoms) if hasattr(geom, "geoms") else [geom]


def rasterize(geom, shape, origin=(0.0, 0.0), scale=1.0, supersample=4):
    """Binary mask of geom on a pixel grid (pixel centres at integer coordinates)."""
    h, w = shape
    S = supersample
    canvas = np.zeros((h * S, w * S), np.uint8)
    ox, oy = origin

    def to_px(c):
        c = (np.asarray(c)[:, :2] - [ox, oy]) * scale
        return np.round((c + 0.5) * S - 0.5).astype(np.int32)

    for poly in _polys(geom):
        cv2.fillPoly(canvas, [to_px(poly.exterior.coords)], 1)
        for hole in poly.interiors:
            cv2.fillPoly(canvas, [to_px(hole.coords)], 0)
    small = cv2.resize(canvas.astype(np.float32), (w, h), interpolation=cv2.INTER_AREA)
    return (small >= 0.5).astype(np.uint8)


def svg_path(geom, fmt="{:.2f}"):
    d = []
    for poly in _polys(geom):
        for ring in [poly.exterior, *poly.interiors]:
            c = np.asarray(ring.coords)[:-1]
            d.append("M" + " L".join(f"{fmt.format(x)} {fmt.format(y)}" for x, y in c) + " Z")
    return " ".join(d)
