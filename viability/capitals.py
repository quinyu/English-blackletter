"""Capitals in MS 2262, across the whole book (the 137 page images of the PDF).

The scribe writes no capitals inside a verse. Capitals come in two kinds:

  painted initials   gold letters on a ground split into blue and rose, with white
                     tracery, painted after the writing into spaces the scribe left: one
                     line high at verse starts, two to four lines at the starts of psalms,
                     hymns and hours. Found by their blue (b* < −8 in Lab; the gold is too
                     close to the brown ink in colour to find on its own).
  ink capitals       the scribe's own capitals at the starts of responses, antiphons and
                     prayers (Et, Deus, Gloria, Ave …), "touched" with a small stroke of
                     red. Found by those touches: small red marks lying on dark ink, away
                     from other red (so not a rubric).

For every page: the parchment area, the text block, the line pitch (from the period of
the ink's row profile), and each initial's height in lines, place (start of a line or
inside it), share of blue, and position of the blue half; each red touch with a crop.

Run:  python3 capitals.py PDF_PAGE_DIR   (the folders p1, p2, p3 of pg-*.jpg extracted from
      the three parts of the PDF)  → out/hours_capitals.json, out/hours_ink_capitals.png,
      out/hours_initials.png and gallery images in out/
"""
import json
import sys
from pathlib import Path

import cv2
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

import ink

HERE = Path(__file__).resolve().parent
TOUCH_A = 36.0     # a* (Lab) a red mark must reach somewhere to count as the rubricator's red
OUT = HERE / "out"

# page index ranges in the three PDF parts (from their contact sheets)
CALENDAR = {("p1", i) for i in range(4, 24)}
TEXT = ({("p1", i) for i in range(24, 59)} | {("p2", i) for i in range(0, 46)} |
        {("p3", i) for i in range(0, 27)})


# What follows each red mark, read from gridded close-ups (out/hours_ink_capitals.jpg).
# Keyed by the mark's position on the page, not its order (which moves when detection
# changes). "–" = not a capital: a rubric fragment, a red ornament, or a lone point;
# lowercase letters = the point stands before a lowercase word or a cue.
READ = [   # (page, x, y of the red mark, letter, word as written, yellow wash seen)
    ("p1/pg-024", 695, 296, "E", "Et", True),
    ("p1/pg-024", 780, 420, "D", "Deus (round D)", True),
    ("p1/pg-024", 793, 474, "D", "Dñe", True),
    ("p1/pg-024", 814, 532, "G", "Gla", True),
    ("p1/pg-024", 713, 595, "D", "Do (round D)", False),
    ("p1/pg-025", 997, 1152, "G", "Gla", True),
    ("p1/pg-025", 748, 1155, "A", "Aue", True),
    ("p1/pg-025", 756, 1219, "A", "Aue", False),
    ("p1/pg-028", 287, 1427, "S", "Sca", True),
    ("p1/pg-031", 711, 550, "E", "Et", True),
    ("p1/pg-031", 993, 787, "E", "Et", True),
    ("p1/pg-031", 1118, 786, "I", "Iube", True),
    ("p1/pg-031", 1049, 1425, "q", "quam (lowercase)", False),
    ("p1/pg-046", 650, 1326, "–", "rubric", False),
    ("p1/pg-056", 355, 272, "I", "In", True),
    ("p1/pg-056", 468, 269, "G", "G.", True),
    ("p1/pg-056", 520, 270, "P", "Po", True),
    ("p2/pg-000", 644, 248, "V", "V", True),
    ("p2/pg-000", 1017, 310, "V", "Vi", True),
    ("p2/pg-001", 896, 1229, "–", "red ornament", False),
    ("p2/pg-002", 1160, 219, "–", "red ornament", False),
    ("p2/pg-002", 645, 514, "ſ", "ſancta (lowercase)", False),
    ("p2/pg-002", 524, 575, "ſ", "ſcā (lowercase)", False),
    ("p2/pg-013", 532, 284, "N", "N", True),
    ("p2/pg-015", 725, 1359, "–", "rubric", False),
    ("p2/pg-020", 541, 1432, "G", "Gloria (red stroke through it)", True),
    ("p2/pg-020", 830, 1435, "S", "Sicut (red stroke on it)", True),
    ("p2/pg-026", 958, 874, "–", "rubric", False),
    ("p2/pg-026", 1058, 1198, "E", "Et", True),
    ("p2/pg-030", 495, 988, "–", "painted initial", False),
    ("p2/pg-035", 906, 346, "–", "red ornament", False),
    ("p2/pg-035", 657, 1448, "R", "Requiem", True),
    ("p2/pg-037", 662, 1151, "k", "kyrie (lowercase)", False),
    ("p2/pg-037", 831, 1155, "k", "kyr (lowercase)", False),
    ("p2/pg-037", 908, 1153, "–", "red point alone", False),
    ("p2/pg-045", 619, 251, "T", "Tu", True),
    ("p3/pg-000", 963, 312, "E", "Et", True),
    ("p3/pg-000", 786, 490, "E", "Et", True),
    ("p3/pg-000", 540, 1316, "E", "Et", True),
    ("p3/pg-001", 676, 237, "G", "G", True),
    ("p3/pg-001", 608, 354, "Q", "Qu", True),
    ("p3/pg-001", 608, 406, "D", "Du", True),
    ("p3/pg-001", 362, 471, "S", "Sc", True),
    ("p3/pg-001", 548, 582, "I", "Iu", True),
    ("p3/pg-001", 774, 701, "Q", "Qu", True),
    ("p3/pg-001", 234, 762, "P", "Pl", True),
    ("p3/pg-001", 408, 884, "Q", "Qu", True),
    ("p3/pg-001", 819, 1003, "I", "Iu", True),
    ("p3/pg-001", 585, 1174, "S", "Sc", True),
    ("p3/pg-006", 704, 1026, "k", "kyrie (lowercase)", False),
    ("p3/pg-006", 830, 1026, "x", "xpe (lowercase)", False),
    ("p3/pg-006", 926, 1028, "k", "kyrie (lowercase)", False),
    ("p3/pg-006", 1049, 1030, "D", "Do", True),
    ("p3/pg-009", 587, 1002, "a", "an (cue, lowercase)", False),
    ("p3/pg-010", 886, 741, "a", "ā (cue, lowercase)", False),
    ("p3/pg-010", 755, 1210, "a", "ā (cue, lowercase)", False),
    ("p3/pg-011", 535, 427, "a", "ā (cue, lowercase)", False),
    ("p3/pg-011", 884, 897, "–", "fragment", False),
    ("p3/pg-011", 426, 1435, "–", "rubric", False),
    ("p3/pg-014", 729, 903, "E", "Et", True),
]


def reading(page, centre, tol=12):
    """The reading of the red mark at this place, if one was recorded."""
    best = min((r for r in READ if r[0] == page), key=lambda r: (r[1] - centre[0]) ** 2 + (r[2] - centre[1]) ** 2,
               default=None)
    if best and abs(best[1] - centre[0]) <= tol and abs(best[2] - centre[1]) <= tol:
        return best[3:]
    return None


def capital_height(mask, a, t, first=0.7):
    """Top of the capital's own ink over its first `first` x-heights of width, in
    x-heights above the baseline (a following letter cannot reach into that span)."""
    x, y, w, h = t["capital_box"]
    xh, base = t["xh_px"], y + h
    ink_ = (mask > 0) & (a < 12)
    y0 = int(base - 2.1 * xh)
    win = ink_[y0:int(base + 1), x:int(x + first * xh)].astype(np.uint8)
    n, lab_ = cv2.connectedComponents(win)
    band = lab_[int(win.shape[0] - 0.7 * xh):int(win.shape[0] - 0.3 * xh)]
    own = np.unique(band)
    own = own[own > 0]
    ys = np.nonzero(np.isin(lab_, own).any(1))[0]
    return round(float((base - (y0 + ys[0])) / xh), 2) if len(ys) else None


def parchment_box(lab):
    """Bounding box of the page (bright, unsaturated), excluding binding and background."""
    L, a = lab[..., 0], lab[..., 1] - 128
    m = ((L > 150) & (np.abs(a) < 12)).astype(np.uint8)
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((15, 15), np.uint8))
    n, lab_, st, _ = cv2.connectedComponentsWithStats(m)
    i = 1 + int(np.argmax(st[1:, cv2.CC_STAT_AREA]))
    x, y, w, h = st[i][:4]
    return int(x), int(y), int(x + w), int(y + h)


def line_pitch(mask, box):
    """Line pitch (px) from the autocorrelation of the ink's row profile in the text block."""
    x0, y0, x1, y1 = box
    prof = mask[y0:y1, x0:x1].sum(1).astype(float)
    prof -= prof.mean()
    ac = np.correlate(prof, prof, "full")[len(prof) - 1:]
    lo, hi = 35, 90
    return float(lo + np.argmax(ac[lo:hi]))


def text_block(mask, pbox):
    """The text column: columns and rows where the ink is dense (the sliver of the
    neighbouring page, the binding and stray marks fall outside)."""
    x0, y0, x1, y1 = pbox
    m = mask[y0:y1, x0:x1] > 0
    if m.sum() < 2000:
        return None
    cols = np.convolve(m.mean(0), np.ones(15) / 15, "same")
    rows = np.convolve(m.mean(1), np.ones(15) / 15, "same")
    c = np.nonzero(cols >= 0.3 * cols.max())[0]
    r = np.nonzero(rows >= 0.15 * rows.max())[0]
    # the longest run of dense columns is the text column
    runs = np.split(c, np.nonzero(np.diff(c) > 25)[0] + 1)
    run = max(runs, key=len)
    return (int(x0 + run[0]), int(y0 + r[0]), int(x0 + run[-1]), int(y0 + r[-1]))


def initials(rgb, lab, mask, pbox, tb, pitch):
    a, b = lab[..., 1] - 128.0, lab[..., 2] - 128.0
    boxes = ink.paint_boxes(rgb, mask, max_side=int(5 * pitch))
    n, lab_, st, _ = cv2.connectedComponentsWithStats(boxes.astype(np.uint8))
    px0, py0, px1, py1 = pbox
    out = []
    for i in range(1, n):
        x, y, w, h = [int(v) for v in st[i][:4]]
        if x < px0 + 10 or y < py0 + 10 or x + w > px1 - 10 or y + h > py1 - 10:
            continue                                  # binding, page edge
        blue = b[y:y + h, x:x + w] < -8
        rose = a[y:y + h, x:x + w] > 13
        fb, fr = float(blue.mean()), float(rose.mean())
        if fb < 0.03:
            continue                                  # red rubric text, not an initial
        if np.median(a[y:y + h, x:x + w][blue]) > 12:
            continue                                  # the library's violet stamp, not azurite
        kind = "line-filler" if w > 2.2 * h else "initial"
        ys, xs = np.nonzero(blue)
        out.append(dict(box=[x, y, w, h], lines=round(h / pitch, 2), kind=kind,
                        blue=round(fb, 3), rose=round(fr, 3),
                        at_line_start=bool(tb is not None and x < tb[0] + 0.6 * pitch),
                        blue_side="left" if xs.mean() < w / 2 - 0.08 * w else
                        ("right" if xs.mean() > w / 2 + 0.08 * w else "both")))
    return out


def red_touches(lab, mask, tb, paint, pitch):
    """Small red marks lying on dark ink inside the text block, away from paint and from
    rubrics. Fragments of one touch (and the red point the rubricator often set before a
    capital) are merged first; a rubric word is a row of more than three red marks."""
    L, a = lab[..., 0], lab[..., 1] - 128.0
    # vermilion: the faint red ruling reaches a* ≈ 20–30, the rubricator's red 40–50
    seed = (a > TOUCH_A) & (L < 185)
    red = ((a > 18) & (L < 185)).astype(np.uint8)
    n0, lab0 = cv2.connectedComponents(red)
    ids = np.unique(lab0[seed])
    red = np.isin(lab0, ids[ids > 0]).astype(np.uint8)                # grown from strong seeds
    red[paint] = 0
    x0, y0, x1, y1 = tb
    m = int(0.3 * pitch)
    keep = np.zeros_like(red)
    keep[y0 + m:y1 - m, x0 - m:x1 + m] = 1
    red &= keep
    merged = cv2.dilate(red, np.ones((5, 5), np.uint8))
    n, lab_, st, cen = cv2.connectedComponentsWithStats(merged)
    dark = (mask > 0) & (a < 12)                  # the page's (brown) ink, not red
    out = []
    centres, areas = cen[1:], st[1:, cv2.CC_STAT_AREA]
    for i in range(1, n):
        x, y, w, h, area = [int(v) for v in st[i]]
        if not (12 <= area <= 400) or w > 0.6 * pitch or h > 0.6 * pitch:
            continue
        cx, cy = cen[i]
        near = (np.abs(centres[:, 1] - cy) < 0.4 * pitch) & (np.abs(centres[:, 0] - cx) < 1.5 * pitch)
        if near.sum() > 3:
            continue                                  # a rubric word
        r = 4
        win = dark[max(0, y - r):y + h + r, max(0, x - r):x + w + r]
        if win.mean() < 0.12:
            continue                                  # not on a letter (e.g. a red point alone)
        cap = capital_right_of(mask, a, cx, cy, pitch)
        if cap is None:
            continue
        out.append(dict(centre=[float(cx), float(cy)], area=int((lab_[y:y + h, x:x + w] == i).sum()), **cap))
    return out


def capital_right_of(mask, a, cx, cy, pitch):
    """The letter just right of a red mark: its columns (up to the first white gap after
    ink starts), its top, and the x-band of the line around it."""
    H, W = mask.shape
    ink_ = (mask > 0) & (a < 12)
    y0, y1 = int(max(0, cy - 1.15 * pitch)), int(min(H, cy + 0.55 * pitch))
    # x-band: rows that are ink-dense across three pitches either side
    wx0, wx1 = int(max(0, cx - 3 * pitch)), int(min(W, cx + 3 * pitch))
    rows = ink_[y0:y1, wx0:wx1].mean(1)
    if rows.max() <= 0:
        return None
    band = np.nonzero(rows >= 0.45 * rows.max())[0]
    # the band closest to the mark, as a run of consecutive rows
    runs = np.split(band, np.nonzero(np.diff(band) > 2)[0] + 1)
    run = min(runs, key=lambda r: abs((y0 + r.mean()) - cy))
    xline, base = y0 + run[0], y0 + run[-1]
    xh = max(base - xline, 0.3 * pitch)
    c0 = int(cx + 2)
    cols = ink_[y0:y1, c0:int(min(W, cx + 1.6 * pitch))].any(0)
    on = np.nonzero(cols)[0]
    if len(on) == 0:
        return None
    start = on[0]
    # the capital ends at the first column, at least 0.45 x-height in, where the middle of
    # the x-band is (nearly) empty: letters inside a word touch only by hairlines
    core = ink_[int(base - 0.7 * xh):int(base - 0.3 * xh) + 1, c0:int(min(W, cx + 1.6 * pitch))].mean(0)
    end = len(core) - 1
    for k in range(start + int(0.45 * xh), len(core)):
        if core[k] <= 0.15:
            end = k
            break
    u0, u1 = c0 + start, c0 + end
    # the capital's own ink: components that reach into this line's x-band in its columns
    win = ink_[y0:y1, u0:u1].astype(np.uint8)
    n, lab_ = cv2.connectedComponents(win)
    own = np.unique(lab_[xline - y0:base - y0 + 1])
    own = own[own > 0]
    ys = np.nonzero(np.isin(lab_, own).any(1))[0]
    if len(ys) == 0:
        return None
    top = y0 + ys[0]
    return dict(capital_box=[int(u0), int(top), int(u1 - u0), int(base - top)],
                height_xh=round(float((base - top) / xh), 2), width_xh=round(float((u1 - u0) / xh), 2),
                xh_px=float(xh))


def gallery(images, path, tile=(120, 120), cols=12, label=None):
    if not images:
        return
    th, tw = tile
    rows = []
    for k in range(0, len(images), cols):
        row = []
        for im, lab_ in images[k:k + cols]:
            s = min(th / im.shape[0], tw / im.shape[1])
            im = cv2.resize(im, None, fx=s, fy=s, interpolation=cv2.INTER_AREA if s < 1 else cv2.INTER_CUBIC)
            canvas = np.full((th + 14, tw, 3), 255, np.uint8)
            canvas[14:14 + im.shape[0], :im.shape[1]] = im
            cv2.putText(canvas, lab_, (2, 11), cv2.FONT_HERSHEY_SIMPLEX, 0.33, (0, 0, 150), 1)
            row.append(cv2.copyMakeBorder(canvas, 2, 2, 2, 2, cv2.BORDER_CONSTANT, value=(255, 255, 255)))
        while len(row) < cols:
            row.append(np.full_like(row[0], 255))
        rows.append(np.hstack(row))
    cv2.imwrite(str(path), np.vstack(rows))


SURFACE, INK_TEXT, MUTED, DATA, MODEL = "#fcfcfb", "#0b0b0b", "#52514e", "#2a78d6", "#eb6834"
# one clear example of each ink capital (page, mark position), in the order shown
FORMS = [("E", "p1/pg-024", 695, 296), ("D", "p1/pg-024", 793, 474), ("D", "p1/pg-024", 780, 420),
         ("G", "p2/pg-020", 541, 1432), ("A", "p1/pg-025", 748, 1155), ("S", "p2/pg-020", 830, 1435),
         ("I", "p1/pg-031", 1118, 786), ("Q", "p3/pg-001", 774, 701), ("P", "p3/pg-001", 234, 762),
         ("V", "p2/pg-000", 1017, 310), ("R", "p2/pg-035", 657, 1448), ("T", "p2/pg-045", 619, 251)]


def plot_ink_capitals(pages, pdf_dir, path):
    marks = {(p["page"], round(t["centre"][0]), round(t["centre"][1])): (p, t) for p in pages for t in p["touches"]}
    fig, axes = plt.subplots(2, 6, figsize=(12, 4.6), dpi=180, facecolor=SURFACE)
    cache = {}
    for ax, (ch, page, mx, my) in zip(axes.ravel(), FORMS):
        p, t = min(((p, t) for (pg, x, y), (p, t) in marks.items() if pg == page),
                   key=lambda pt: (pt[1]["centre"][0] - mx) ** 2 + (pt[1]["centre"][1] - my) ** 2)
        if page not in cache:
            cache = {page: ink.load_rgb(Path(pdf_dir) / f"{page}.jpg")}
        rgb = cache[page]
        x, y, w, h = t["capital_box"]
        xh, base = t["xh_px"], y + h
        x0, x1 = int(t["centre"][0] - 8), int(t["centre"][0] + 2.3 * xh)
        y0, y1 = int(base - 2.0 * xh), int(base + 0.8 * xh)
        ax.imshow(rgb[y0:y1, x0:x1], extent=(x0, x1, y1, y0), interpolation="lanczos")
        for v, col in ((0, DATA), (1, MODEL)):
            ax.axhline(base - v * xh, color=col, lw=0.6, alpha=0.7)
        ax.axhline(base - 1.5 * xh, color="#1baf7a", lw=0.6, alpha=0.6, ls=(0, (3, 2)))
        ax.set_xlim(x0, x1); ax.set_ylim(y1, y0); ax.axis("off")
        r = t["read"]
        ax.set_title(f"{ch}: {r[1]}", fontsize=7.5, color=INK_TEXT, loc="left", pad=2)
    fig.suptitle("The scribe's ink capitals (red point before, pale yellow wash in the letter): one example of each "
                 "letter found. Lines: baseline, x-line, 1.5 x-heights", fontsize=8.5, color=INK_TEXT, x=0.01, ha="left")
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    fig.savefig(path, facecolor=SURFACE)
    plt.close(fig)


def plot_initials(pages, pdf_dir, path):
    """Size counts of the painted initials, and one example of each size."""
    text = [p for p in pages if not p["calendar"]]
    ins = [(p, i) for p in text for i in p["initials"] if i["kind"] == "initial" and 0.6 <= i["lines"] <= 6]
    fil = [(p, i) for p in text for i in p["initials"] if i["kind"] == "line-filler"]
    sizes = [("1 line", 0.6, 1.75), ("2 lines", 1.75, 2.75), ("3 lines", 2.75, 3.75), ("4 lines", 3.75, 6)]
    fig = plt.figure(figsize=(12, 4.2), dpi=180, facecolor=SURFACE)
    gs = fig.add_gridspec(1, 7, width_ratios=[1.6, 1, 1, 1, 1, 1.2, 0.2], wspace=0.25)
    ax = fig.add_subplot(gs[0, 0])
    counts = [sum(lo <= i["lines"] < hi for _, i in ins) for _, lo, hi in sizes]
    starts = [sum(lo <= i["lines"] < hi and i["at_line_start"] for _, i in ins) for _, lo, hi in sizes]
    ys = np.arange(len(sizes))[::-1]
    ax.barh(ys, counts, color=DATA, height=0.6, label="inside a line")
    ax.barh(ys, starts, color=MODEL, height=0.6, label="at the start of a line")
    for yv, c in zip(ys, counts):
        ax.text(c + 8, yv, str(c), va="center", fontsize=7.5, color=INK_TEXT)
    ax.set_yticks(ys, [n for n, _, _ in sizes], fontsize=7.5)
    ax.tick_params(axis="x", labelsize=7)
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)
    ax.set_xlim(0, max(counts) * 1.2)
    ax.legend(frameon=False, fontsize=7, loc="lower right", labelcolor=INK_TEXT)
    ax.set_title(f"painted initials on {len(text)} text pages ({len(fil)} line-fillers besides)", fontsize=7.5,
                 color=INK_TEXT, loc="left")
    examples = []
    for name, lo, hi in sizes:
        cand = [(p, i) for p, i in ins if lo <= i["lines"] < hi and i["blue"] > 0.06
                and 0.9 <= i["box"][2] / i["box"][3] <= 1.6]
        cand.sort(key=lambda pi: -pi[1]["blue"])
        examples.append((name, cand[min(3, len(cand) - 1)]))
    examples.append(("line-filler", max(fil, key=lambda pi: pi[1]["box"][2])))
    cache = {}
    for k, (name, (p, i)) in enumerate(examples):
        axk = fig.add_subplot(gs[0, 1 + k])
        if p["page"] not in cache:
            cache = {p["page"]: ink.load_rgb(Path(pdf_dir) / f"{p['page']}.jpg")}
        rgb = cache[p["page"]]
        x, y, w, h = i["box"]
        m = int(0.25 * p["pitch"])
        axk.imshow(rgb[max(0, y - m):y + h + m, max(0, x - m):x + w + m], interpolation="lanczos")
        axk.axis("off")
        axk.set_title(f"{name}\n{p['page']}", fontsize=7, color=MUTED, loc="left")
    fig.suptitle("Painted initials of MS 2262: gold letters on a blue-and-rose ground with white tracery",
                 fontsize=8.5, color=INK_TEXT, x=0.01, ha="left")
    fig.savefig(path, facecolor=SURFACE, bbox_inches="tight")
    plt.close(fig)


def main(pdf_dir):
    OUT.mkdir(exist_ok=True)
    pdf_dir = Path(pdf_dir)
    pages, gal_init, gal_big, gal_touch = [], [], [], []
    for part in ("p1", "p2", "p3"):
        for f in sorted((pdf_dir / part).glob("pg-*.jpg")):
            idx = int(f.stem.split("-")[1])
            key = (part, idx)
            if key not in TEXT and key not in CALENDAR:
                continue
            rgb = ink.load_rgb(f)
            lab = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB).astype(np.float32)
            mask, dark = ink.ink_mask(rgb)
            pbox = parchment_box(lab)
            tb = text_block(mask, pbox)
            pitch = line_pitch(mask, tb) if tb else 58.0
            ins = initials(rgb, lab, mask, pbox, tb, pitch)
            paint = np.zeros(mask.shape, bool)
            g = int(0.35 * pitch)
            for it in ins:
                x, y, w, h = it["box"]
                paint[max(0, y - g):y + h + g, max(0, x - g):x + w + g] = True
            touches = red_touches(lab, mask, tb, paint, pitch) if (key in TEXT and tb) else []
            for k, tch in enumerate(touches):
                tch["id"] = f"{part}/{f.stem}#{k}"
                tch["read"] = reading(f"{part}/{f.stem}", tch["centre"])
                tch["height_xh"] = capital_height(mask, lab[..., 1] - 128.0, tch)
            name = f"{part}/{f.stem}"
            pages.append(dict(page=name, calendar=key in CALENDAR, pitch=pitch, text_block=tb,
                              initials=ins, touches=touches))
            bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
            for it in ins:
                x, y, w, h = it["box"]
                im = bgr[y:y + h, x:x + w]
                lab_ = f"{name[-6:]} {it['lines']:.1f}"
                if it["kind"] == "initial":
                    (gal_big if it["lines"] >= 1.75 else gal_init).append((im, lab_))
            for k, tch in enumerate(touches):
                cx, cy = tch["centre"]
                x, y, w, h = tch["capital_box"]
                im = bgr[max(0, y - 4):int(y + h + 0.3 * pitch), max(0, int(cx) - 5):x + w + int(0.5 * pitch)]
                r = tch["read"]
                hh = "" if tch["height_xh"] is None else f" {tch['height_xh']:.1f}"
                gal_touch.append((im, f"{name[:2]}{name[-3:]}#{k} {r[1] if r else '?'}{hh}"))
            print(f"{name}: pitch {pitch:.0f}px, {sum(i['kind'] == 'initial' for i in ins)} initials, "
                  f"{sum(i['kind'] == 'line-filler' for i in ins)} line-fillers, {len(touches)} red touches", flush=True)
    gallery(gal_big, OUT / "hours_initials_large.jpg", tile=(150, 150), cols=10)
    gallery(gal_init[::3], OUT / "hours_initials_one_line.jpg", tile=(90, 110), cols=14)
    gallery(gal_touch, OUT / "hours_ink_capitals.jpg", tile=(130, 110), cols=10)
    (OUT / "hours_capitals.json").write_text(json.dumps(pages, indent=1), encoding="utf-8")
    plot_ink_capitals(pages, pdf_dir, OUT / "hours_ink_capitals.png")
    plot_initials(pages, pdf_dir, OUT / "hours_initials.png")
    return pages


if __name__ == "__main__":
    main(sys.argv[1])
