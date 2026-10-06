"""Find every written letter on f. 12r of MS 2262 by aligning each line's reading to its ink.

The reading (data/hours_reading.json) says which letters each line holds, in order; the
ink says where. Each line is straightened by its slant, so that stems stand upright and a
letter occupies a range of columns, and the letters are laid along it by dynamic
programming: every letter is a template (an image of that letter), and the layout chosen
is the one that best explains the line, i.e. leaves the fewest pixels where ink and
templates disagree (ink no template covers, or template where there is no ink).

  * Letters inside a word may touch or overlap a little (textura bites and links), and
    are at most 0.45 x-height apart; words are 0.25–4 x-heights apart (a painted
    initial, masked out of the ink, leaves a wide gap).
  * Each letter may be 15% narrower or wider than its template, or be skipped at a
    fixed cost, so that a place where the ink holds fewer letters than the reading (a
    ligature or an abbreviation the reading spells out) stays local instead of pushing
    the rest of the line along; skipped letters are reported.
  * Textura is a fence of upright strokes, and minim letters differ only in how many
    they hold, so templates alone often slide a letter by one stem. Stems are found in
    the straightened line (columns that are ink over 70% of the middle of the x-band),
    and a letter whose box holds more or fewer stems than it should pays a penalty.
    i, n, m and u hold 1, 2, 3 and 2 by definition; for the other letters the usual
    count is learnt from round 1 (used when at least three quarters of a letter's finds
    agree).
  * Templates: i, n, m and u are drawn by the fitted minim module (minims.py), clean of
    neighbours. Every other letter starts from its boxes in the letterform atlas
    (letterforms.ATLAS); after each round, a letter's templates are replaced by the finds
    that agree best with all its other finds (sharp single examples, where a median of
    slightly misplaced crops blurs), and the lines are aligned again.

Checks: every minim letter (i, n, m, u) must contain exactly the stems that
letterforms.line_stems found for it in minims.RUNS, and the atlas boxes, which round 2
no longer uses, are compared with where round 2 put the same letters.

Run:  python3 align.py   → data/hours_letters_found.json, out/hours_alignment.png
"""
import json
import re
import unicodedata
from pathlib import Path

import cv2
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

import letterforms as LF
import minims as M

HERE = Path(__file__).resolve().parent
OUT = HERE / "out"
SURFACE, INK_TEXT, MUTED, DATA, MODEL = "#fcfcfb", "#0b0b0b", "#52514e", "#2a78d6", "#eb6834"

XH = 29.0           # canonical x-height (px); lines are 28.5–29.4, so nothing is rescaled
TOP, BOTTOM = 1.75, 0.75   # window above and below the baseline, in x-heights
WIDTHS = (0.85, 1.0, 1.15)
GAP_IN = (-0.2, 0.45)      # gap between letters of a word, x-heights
GAP_WORD = (0.25, 4.0)     # gap between words
GAP_SIGN = (0.0, 1.2)      # where a small sign was expanded by the editor, e.g. e[ius]
GAP_RUBRIC = (0.25, 30.0)  # where the reading marks red ink, [R], which the black-ink mask leaves blank
SKIP_COST = 700.0         # weighted pixels: about a minim's worth of disagreement
STEM_PENALTY = 150.0      # per stem too many or too few (≈ the weighted pixels of a third of a stem)
MINIM_STEMS = {"i": 1, "n": 2, "m": 3, "u": 2}
OWN = 3                   # px: overlapping letters must not both count a stem at their shared edge
EXEMPLARS = 4             # finds added per letter per round
ROUNDS = 3
STAND_IN = {"f": "ſ", "x": "c", "ꝫ": "ꝫ -m", "ꝓ": "ꝓ pro", "ꝙ": "ꝙ quod"}


def tokens(diplomatic):
    """Written letters of a line: (char, word index, flags, gap kind before it)."""
    out, word, gap = [], 0, "start"
    for part in re.split(r"(\[[^\]]*\])", diplomatic):
        if part.startswith("["):
            inner = part[1:-1]
            gap = ("rubric" if inner == "R" else
                   "word" if (inner[:1].isupper() or gap in ("start", "word")) else "sign")
            continue
        for ch in unicodedata.normalize("NFD", part):
            if ch == " ":
                word += 1
                gap = "word" if gap != "start" else "start"
            elif unicodedata.combining(ch):
                out[-1]["flags"].append("macron")
            else:
                out.append(dict(char=ch, word=word, flags=[], gap=gap))
                gap = "in"
    return out


def straighten(mask, line, binary=True):
    """The line's window with the slant removed: column u is the baseline x of a stem.
    A mask comes back binary; with binary=False any image (e.g. darkness) is resampled."""
    (x0, _), (x1, _) = line["baseline"]
    us = np.arange(int(x0 - XH), int(x1 + XH))
    t = np.tan(np.radians(line["slant_deg"] or 0.0))
    hs = np.arange(-BOTTOM * XH, TOP * XH)[::-1]          # height above the baseline, top row first
    U, H = np.meshgrid(us, hs)
    yb = np.array([LF.guide(line, u)[0] for u in us])[None, :] * np.ones_like(H)
    X = (U + H * t).astype(np.float32)
    Y = (yb - H).astype(np.float32)
    img = cv2.remap(mask.astype(np.float32), X, Y, cv2.INTER_LINEAR, borderValue=0)
    return ((img > 0.5).astype(np.float32) if binary else img), us


def stems(img):
    """Stem centres (column indices) of a straightened line."""
    hs = np.arange(-BOTTOM * XH, TOP * XH)[::-1] / XH
    core = (hs >= 0.3) & (hs <= 0.7)
    on = img[core].mean(0) >= 0.7
    out, start = [], None
    for i, v in enumerate(np.r_[on, False]):
        if v and start is None:
            start = i
        if not v and start is not None:
            if i - start >= 2:
                out.append((start + i - 1) / 2)
            start = None
    return np.array(out)


def row_weights():
    """The x-band counts fully; above and below it, neighbouring lines' ascenders and
    descenders reach into the window, so those rows count for less."""
    hs = np.arange(-BOTTOM * XH, TOP * XH)[::-1] / XH
    return np.where((hs >= 0) & (hs <= 1.0), 1.0, 0.35)[:, None].astype(np.float32)


def align_line(img, us, toks, templates, stem_counts):
    """Dynamic programming over column positions: returns (u0, u1, template index) per
    letter and the layout's score (minus the number of disagreeing pixels, weighted,
    minus the stem-count penalties)."""
    BEST = []                                   # per letter: best score with it ending at column e
    W = row_weights()
    C = np.r_[0, np.cumsum((img * W).sum(0))]
    L = img.shape[1]
    S = np.zeros(L + 1)
    for c in stems(img):
        S[int(round(c)) + 1] += 1
    CS = np.cumsum(S)                           # stems with centre in [a, b) = CS[b] − CS[a]
    m = OWN                                     # a stem belongs to a letter if it lies m px inside its box
    NEG = -1e12
    cand = []
    for tk in toks:
        opts = []
        for ti, T0 in enumerate(templates[tk["char"]]):
            for f in WIDTHS:
                w = max(3, int(round(T0.shape[1] * f)))
                if w >= L - 1:
                    continue
                T = cv2.resize(T0, (w, T0.shape[0]), interpolation=cv2.INTER_LINEAR) * W
                corr = cv2.matchTemplate(img * W, T, cv2.TM_CCORR)[0]
                win = C[w:w + len(corr)] - C[:len(corr)]
                sc = 2 * corr - win - T.sum()
                want = stem_counts.get(tk["char"])
                if want is not None:
                    n_ = len(corr)
                    have = CS[np.clip(np.arange(n_) + w - m, 0, L)] - CS[np.clip(np.arange(n_) + m, 0, L)]
                    sc = sc - STEM_PENALTY * np.abs(have - want)
                opts.append((w, sc, ti))
        opts.append((0, np.full(L + 1, -SKIP_COST), -1))     # the letter is not in the ink
        cand.append(opts)
    args = []
    for k, (tk, opts) in enumerate(zip(toks, cand)):
        if k == 0:
            pre = -C[:L + 1]
            gaps = None
        else:
            lo, hi = {"in": GAP_IN, "word": GAP_WORD, "sign": GAP_SIGN, "start": GAP_WORD,
                      "rubric": GAP_RUBRIC}[tk["gap"]]
            lo, hi = int(np.floor(lo * XH)), int(np.ceil(hi * XH))
            v = BEST[-1] + C[:L + 1]
            pre = np.full(L + 1, NEG)
            for u in range(L + 1):
                a, b = max(0, u - hi), u - lo
                if b < 0:
                    continue
                b = min(b, L)
                if a > b:
                    continue
                pre[u] = v[a:b + 1].max() - C[u]
            gaps = (lo, hi)
        best = np.full(L + 1, NEG)
        arg = np.zeros((L + 1, 2), int)
        for oi, (w, sc, _) in enumerate(opts):
            starts = np.arange(len(sc))
            ends = starts + w
            val = pre[starts] + sc
            # several starts never share an end for one width, so plain assignment is safe
            better = val > best[ends]
            best[ends[better]] = val[better]
            arg[ends[better]] = np.c_[np.full(better.sum(), oi), starts[better]]
        BEST.append(best)
        args.append((arg, gaps))
    final = BEST[-1] - (C[L] - C[:L + 1])
    e = int(np.argmax(final))
    score = float(final[e])
    out = [None] * len(toks)
    for k in range(len(toks) - 1, -1, -1):
        arg, gaps = args[k]
        oi, u = arg[e]
        w, _, ti = cand[k][oi]
        out[k] = (int(u), int(u + w), int(ti))
        if k == 0:
            break
        lo, hi = gaps
        a, b = max(0, u - hi), min(L, u - lo)
        ps = np.arange(a, b + 1)
        e = int(ps[np.argmax(BEST[k - 1][ps] + C[ps])])
    return [(us[0] + a, us[0] + b, ti) for a, b, ti in out], score


def atlas_templates(straight):
    """Round-1 templates: the letterform atlas boxes, cut from the straightened lines."""
    T = {}
    for _, items in LF.ATLAS:
        for ch, n, x0, x1, word in items:
            img, us = straight[n]
            a, b = int(x0 - us[0]), int(x1 - us[0])
            key = ch.split()[0] if ch not in ("n final",) else "n"
            T.setdefault(key, []).append(img[:, a:b].copy())
    for ch, src in STAND_IN.items():
        if ch not in T:
            T[ch] = [t.copy() for t in T[src.split()[0] if src.split()[0] in T else src]]
    # punctuation: a dot at mid x-band and one on the baseline (:) or one on the baseline (,)
    H = straight[1][0].shape[0]
    hs = np.arange(-BOTTOM * XH, TOP * XH)[::-1] / XH
    for ch, rows in ((":", [(0.55, 0.75), (0.0, 0.2)]), (",", [(0.0, 0.25)])):
        t = np.zeros((H, 6), np.float32)
        for lo, hi in rows:
            t[(hs >= lo) & (hs <= hi), 1:5] = 1
        T[ch] = [t]
    return T


def minim_templates(H):
    """i, n, m, u drawn by the minim module at the canonical x-height, upright (slant 0),
    in a window like the straightened lines; joins inside the letter, faint as they are,
    are left out (the ink mask rarely holds them)."""
    d = json.loads((OUT / "hours_minims.json").read_text(encoding="utf-8"))
    p = np.array([d["module"][k] for k in M.PARAMS])
    P = d["rules"]["pitch"]
    T = {}
    for ch, k in MINIM_STEMS.items():
        stems_ = [0.4 * XH + j * P["inside"] * XH for j in range(k)]
        yb = TOP * XH
        st = [s for s in M.module_strokes(stems_, yb, XH, 0.0, p, [None] * (k - 1))]
        g = M.render_strokes(st, p)
        w = int(round(stems_[-1] + 0.4 * XH))
        T[ch] = [pen_raster(g, (H, w))]
    return T


def pen_raster(g, shape):
    import pen
    return pen.rasterize(g, shape, origin=(0, 0)).astype(np.float32)


def add_exemplars(found, straight, old, keep=EXEMPLARS + 1):
    """Templates for the next round. For each letter other than the drawn minim letters,
    with at least three finds: the finds that agree best with all the other finds of that
    letter (mean overlap after resizing to the median width). A crop that was misplaced,
    or an atlas box that took in part of a neighbour, agrees with few others and drops
    out; letters with fewer finds keep their templates."""
    W = row_weights()
    T = {ch: list(v) for ch, v in old.items()}
    by = {}
    for f in found:
        if f["char"] in MINIM_STEMS or f["skipped"]:
            continue
        img, us = straight[f["line"]]
        crop = img[:, f["u0"] - us[0]:f["u1"] - us[0]]
        if crop.shape[1] >= 3:
            by.setdefault(f["char"], []).append(crop)
    for ch, crops in by.items():
        if len(crops) < 3:
            continue
        w = int(np.median([c.shape[1] for c in crops]))
        R = [cv2.resize(c, (w, c.shape[0]), interpolation=cv2.INTER_LINEAR) for c in crops]
        n = len(R)
        agree = np.zeros(n)
        for i in range(n):
            for j in range(n):
                if i != j:
                    inter = (W * np.minimum(R[i], R[j])).sum()
                    union = (W * np.maximum(R[i], R[j])).sum()
                    agree[i] += inter / max(union, 1e-6) / (n - 1)
        T[ch] = [crops[i] for i in np.argsort(-agree)[:keep]]
    return T


def learn_stem_counts(found, straight):
    """Usual number of stems per letter in what a round found (minim letters by definition)."""
    st = {n: (stems(img) + us[0]) for n, (img, us) in straight.items()}
    by = {}
    for f in found:
        if f["skipped"]:
            continue
        k = int(((st[f["line"]] >= f["u0"]) & (st[f["line"]] < f["u1"])).sum())
        by.setdefault(f["char"], []).append(k)
    counts = {}
    for ch, ks in by.items():
        vals, n = np.unique(ks, return_counts=True)
        if len(ks) >= 3 and n.max() / len(ks) >= 0.75:
            counts[ch] = int(vals[np.argmax(n)])
    counts.update(MINIM_STEMS)
    return counts


def run(lines, straight, reading, templates, stem_counts):
    found = []
    for l in reading:
        n = l["n"]
        toks = tokens(l["diplomatic"])
        img, us = straight[n]
        boxes, score = align_line(img, us, toks, templates, stem_counts)
        for k, (tk, (u0, u1, ti)) in enumerate(zip(toks, boxes)):
            found.append(dict(line=n, index=k, char=tk["char"], word=tk["word"], flags=tk["flags"],
                              u0=int(u0), u1=int(u1), skipped=bool(ti < 0)))
    return found


def check_minims(found):
    """Each minim letter of minims.RUNS must hold exactly its stems."""
    ok = tot = 0
    rows = []
    for n, word, letters in M.RUNS:
        for ch, stems in letters:
            tot += 1
            cands = [f for f in found if f["line"] == n and f["char"] == ch]
            hit = [f for f in cands if all(f["u0"] - 1 <= s <= f["u1"] + 1 for s in stems)]
            good = any(sum(f["u0"] - 1 <= s <= f["u1"] + 1 for s in sum((ss for _, ss in letters), [])) == len(stems)
                       for f in hit)
            ok += good
            rows.append(dict(line=n, word=word, letter=ch, stems=stems, ok=bool(good)))
    return ok, tot, rows


def check_atlas(found):
    """Centre of each atlas box against the centre of the same letter found on that line."""
    d = []
    for _, items in LF.ATLAS:
        for ch, n, x0, x1, word in items:
            key = ch.split()[0]
            if key not in ("i", "n", "m", "u", "o", "c", "e", "r", "ꝛ", "ſ", "s", "l", "b", "h", "d", "t",
                           "p", "q", "g", "a", "v"):
                continue
            cands = [f for f in found if f["line"] == n and f["char"] == key]
            if cands:
                c = (x0 + x1) / 2
                d.append(min(abs((f["u0"] + f["u1"]) / 2 - c) for f in cands))
    return np.array(d)


def plot(rgb, lines, found, path, show=(1, 7, 15, 21)):
    by = {l["n"]: l for l in lines}
    fig, axes = plt.subplots(len(show), 1, figsize=(12, 1.25 * len(show)), dpi=170, facecolor=SURFACE)
    for ax, n in zip(axes, show):
        l = by[n]
        (x0, _), (x1, _) = l["baseline"]
        yb, xh = LF.guide(l, (x0 + x1) / 2)
        y0, y1 = int(yb - 1.6 * xh), int(yb + 0.95 * xh)
        ax.imshow(rgb[y0:y1, int(x0) - 8:int(x1) + 8], extent=(int(x0) - 8, int(x1) + 8, y1, y0),
                  interpolation="lanczos")
        for k, f in enumerate([f for f in found if f["line"] == n]):
            col = DATA if k % 2 == 0 else MODEL
            yb_, _ = LF.guide(l, (f["u0"] + f["u1"]) / 2)
            ax.plot([f["u0"], f["u1"]], [yb_ + 0.3 * xh] * 2, color=col, lw=2.2, solid_capstyle="butt")
            ax.text((f["u0"] + f["u1"]) / 2, yb_ + 0.6 * xh, f["char"], ha="center", va="center", fontsize=6.5,
                    color=col, fontfamily="FreeSerif")
        ax.set_xlim(int(x0) - 8, int(x1) + 8); ax.set_ylim(y1, y0 + 0.0); ax.axis("off")
        ax.set_title(f"line {n}", fontsize=7, color=MUTED, loc="left", pad=1)
    fig.suptitle("Letters found by aligning the reading to the ink (bars: each letter's columns)",
                 fontsize=9, color=INK_TEXT, x=0.01, ha="left")
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    fig.savefig(path, facecolor=SURFACE)
    plt.close(fig)


def main():
    OUT.mkdir(exist_ok=True)
    rgb, mask, lines, dark = M.load()
    by = {l["n"]: l for l in lines}
    reading = [l for l in json.loads((HERE / "data" / "hours_reading.json").read_text(encoding="utf-8"))["lines"]
               if l.get("kind") == "text"]
    straight = {l["n"]: straighten(mask, by[l["n"]]) for l in reading}
    T = atlas_templates(straight)
    T.update(minim_templates(next(iter(straight.values()))[0].shape[0]))
    counts = dict(MINIM_STEMS)
    for r in range(ROUNDS):
        found = run(lines, straight, reading, T, counts)
        ok, tot, rows = check_minims(found)
        d = check_atlas(found)
        print(f"round {r + 1}: {ok}/{tot} minim letters hold exactly their stems; atlas boxes vs found letters: "
              f"median {np.median(d):.1f} px, {(d <= 3).mean():.0%} within 3 px (n={len(d)})")
        if r == 0:
            counts = learn_stem_counts(found, straight)
            print("  stem counts:", dict(sorted(counts.items())))
        T = add_exemplars(found, straight, T)
    ok2 = ok
    for r in rows:
        if not r["ok"]:
            print("  missed:", r)
    print("  skipped:", [(f["line"], f["char"], f["index"]) for f in found if f["skipped"]])
    for f in found:
        l = by[f["line"]]
        yb, xh = LF.guide(l, (f["u0"] + f["u1"]) / 2)
        f.update(yb=float(yb), xh=float(xh), slant=float(l["slant_deg"] or 0.0))
    (HERE / "data" / "hours_letters_found.json").write_text(json.dumps({
        "note": "Letters of f. 12r found by align.py: u0–u1 are the columns a letter occupies at the "
                "baseline once the line's slant is removed (x at height h is u + h·tan(slant)).",
        "check": {"minim_letters_with_their_stems": [ok2, tot], "atlas_median_px": float(np.median(d)),
                  "atlas_within_3px": float((d <= 3).mean()), "atlas_n": int(len(d))},
        "letters": found}, ensure_ascii=False, indent=1), encoding="utf-8")
    plot(rgb, lines, found, OUT / "hours_alignment.png")
    return found


if __name__ == "__main__":
    main()
