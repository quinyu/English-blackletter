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

    def coords_at(self, dtheta=0.0, scale=1.0):
        """Nib outline turned by dtheta degrees from its resting angle, with its contact
        shrunk by `scale` (1 = the full edge on the page, towards 0 = only a corner)."""
        if dtheta == 0.0 and scale == 1.0:
            return self.coords
        t = np.radians(-(self.theta + dtheta))
        R = np.array([[np.cos(t), -np.sin(t)], [np.sin(t), np.cos(t)]])
        return (scale * self._base) @ R.T

    @property
    def _base(self):
        n = len(self.coords)
        t = np.linspace(0, 2 * np.pi, n, endpoint=False)
        return np.c_[self.a / 2 * np.cos(t), self.b / 2 * np.sin(t)]


def sweep(points, nib, dthetas=None, scales=None):
    """Outline swept by the nib along a dense centre-line. With per-point dthetas and
    scales the pen twists and lifts as it moves; consecutive stamps are still joined by
    their convex hull, so width changes are continuous."""
    if dthetas is None:
        stamps = [nib.coords] * len(points)
    else:
        stamps = [nib.coords_at(d, k) for d, k in zip(dthetas, scales)]
    hulls = []
    for i in range(len(points) - 1):
        hulls.append(MultiPoint(np.vstack([stamps[i] + points[i], stamps[i + 1] + points[i + 1]])).convex_hull)
    return shapely.union_all(hulls) if hulls else Polygon()


def twist_profile(points, pen_spec):
    """Per-point pen twist and lift from a stroke's "pen" keyframes, given as distance
    before the end of the stroke (px), so the same terminal fits strokes of any length:
    {"from_end_px": [...], "dtheta": [...], "scale": [...]}; before the first keyframe
    the pen rests (0, 1)."""
    seg = np.r_[0, np.cumsum(np.hypot(*np.diff(points, axis=0).T))]
    d_end = seg[-1] - seg
    order = np.argsort(pen_spec["from_end_px"])
    xs = np.asarray(pen_spec["from_end_px"], float)[order]
    dth = np.interp(d_end, xs, np.asarray(pen_spec["dtheta"], float)[order])
    sc = np.interp(d_end, xs, np.asarray(pen_spec["scale"], float)[order])
    return dth, sc


CORNER_FRACTION = 0.5  # corner hairline width as a share of the nib's narrow edge


def is_corner_stroke(name):
    """Separate strokes drawn with the corner of the pen rather than its edge, like the
    hairline that closes a textura e. On MS 2262 these are about half the nib's narrow
    edge. (Tails that grow out of a stroke are not separate strokes: they are drawn by
    twisting the pen along the stroke, see twist_profile.)"""
    return (name or "").lower().startswith("hairline")


def corner_nib(nib):
    c = CORNER_FRACTION * nib.b
    return Nib(c, c, nib.theta)


def render(strokes, nib, step=0.5, names=None, pens=None):
    """Union of all swept strokes. strokes: list of control-point lists. With names,
    hairline strokes are drawn with the pen's corner; with pens (one twist spec or None
    per stroke) the pen, edge or corner, twists and lifts along that stroke."""
    corner = corner_nib(nib)
    names = names or [None] * len(strokes)
    pens = pens or [None] * len(strokes)
    parts = []
    for s_, n, spec in zip(strokes, names, pens):
        P = catmull_rom(s_, step)
        tip = corner if is_corner_stroke(n) else nib
        if spec:
            dth, sc = twist_profile(P, spec)
            parts.append(sweep(P, tip, dth, sc))
        else:
            parts.append(sweep(P, tip))
    return shapely.union_all(parts)


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
