"""Ink extraction: separate the scribe's ink from parchment, stains and show-through.

The page background (parchment colour plus broad water stains) varies slowly, so it is
estimated with a large median filter and subtracted. What remains is local darkening.
Show-through from the verso is much fainter than front-side ink, so a contrast threshold
removes most of it; the remainder leans the wrong way (it is mirrored) and is rejected
later by the per-instance stroke fitting.
"""
import cv2
import numpy as np
from skimage.filters import apply_hysteresis_threshold

def load_rgb(path):
    bgr = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if bgr is None:
        raise FileNotFoundError(path)
    return cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)

def ink_darkness(rgb, bg_kernel=41):
    """Return a float map: how much darker each pixel is than the local parchment (0..~100)."""
    lab = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB).astype(np.float32)
    L = lab[..., 0] * (100.0 / 255.0)
    bg = cv2.medianBlur(L.astype(np.uint8), bg_kernel).astype(np.float32)
    # Parchment is brighter than ink almost everywhere; take the brighter of the two
    # estimates so wide dark strokes do not drag the background down.
    bg = np.maximum(bg, cv2.GaussianBlur(L, (0, 0), 3))
    return np.clip(bg - L, 0, None)

def ink_mask(rgb, threshold=14.0, weak=9.0, min_area=12):
    """Hysteresis threshold: clearly dark pixels seed the mask, and fainter pixels are
    kept only where they connect to them. Thin, faded ends of strokes survive; isolated
    show-through (faint everywhere) does not."""
    d = ink_darkness(rgb)
    m = apply_hysteresis_threshold(d, weak, threshold).astype(np.uint8)
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))
    n, lab, stats, _ = cv2.connectedComponentsWithStats(m, connectivity=8)
    keep = np.zeros(n, bool)
    keep[1:] = stats[1:, cv2.CC_STAT_AREA] >= min_area
    return keep[lab].astype(np.uint8), d


def red_mask(rgb, mask, a_thr=15.0):
    """Ink that is red (rubrics, paragraph marks): high a* in Lab. Brown and black
    text ink sits near a* = 0–8, vermilion rubrication around 20–35."""
    lab = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB).astype(np.float32)
    return ((lab[..., 1] - 128.0) > a_thr) & (mask > 0)
