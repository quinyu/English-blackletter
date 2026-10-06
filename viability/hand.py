"""What the lowercase alphabet of MS 2262 (f. 12r) shows, from the fitted letters.

  * the alphabet: every fitted letter drawn on one sheet (minim letters from minims.py,
    the others from textura.py), with each letter's reach above and below the x-band;
  * shared parts: whether l, b and h carry one ascender head, and how high ascenders
    and how deep descenders go;
  * biting: how often neighbouring letters write their facing sides as one stroke (biting.py)
    in the middle of the x-band, by the shapes that meet;
  * positional rules, counted in the reading: r and ꝛ, ſ and s, v and u, ꝫ and m.

Run:  python3 hand.py   → out/hours_alphabet.png, out/hours_hand.json
"""
import json
import re
import unicodedata
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

import align as A
import minims as M
import pen

HERE = Path(__file__).resolve().parent
OUT = HERE / "out"
SURFACE, INK_TEXT, MUTED, DATA, MODEL = "#fcfcfb", "#0b0b0b", "#52514e", "#2a78d6", "#eb6834"
XH = 29.0
GROUPS = [
    ("minims", "i n m u r"),
    ("round", "o c e a"),
    ("ascenders", "l b h d t"),
    ("descenders", "p q g ſ f"),
    ("other forms", "s ꝛ v"),
]


def letter_strokes(ch, L, minim, t):
    """Strokes (points in x-heights, y up) and pens for one letter."""
    if ch in "inmu":
        p = np.array([minim["module"][k] for k in M.PARAMS])
        R = minim["rules"]
        k = M.MINIMS[ch]
        stems = [0.3 + j * R["pitch"]["inside"] for j in range(k)]
        joins = [(R["foot"]["h0"], R["foot"]["h1"]) if ch == "u" else (R["head"]["h0"], "head")] * (k - 1)
        st = M.module_strokes(stems, 0.0, 1.0, np.degrees(np.arctan(t)), p, joins)
        return [(n, [[x, -y] for x, y in pts], spec) for n, pts, spec in st]
    out = []
    for s in L[ch]["strokes"]:
        out.append((s["name"], [[u + v * t, v] for u, v in s["points"]], "terminal" if s["pen"] == "terminal" else None))
    return out


def draw(ax, strokes, nib, spec):
    geom = pen.render([[[x * XH, -y * XH] for x, y in pts] for _, pts, _ in strokes], nib, step=0.5,
                      names=[n for n, _, _ in strokes], pens=[spec if k == "terminal" else None for _, _, k in strokes])
    for poly in (geom.geoms if hasattr(geom, "geoms") else [geom]):
        ax.fill(*poly.exterior.xy, color="#2a2118", lw=0)
        for hole in poly.interiors:
            ax.fill(*hole.xy, color=SURFACE, lw=0)
    for v, col in ((0, DATA), (-XH, MODEL)):
        ax.axhline(v, color=col, lw=0.5, alpha=0.5)
    x0, y0, x1, y1 = geom.bounds
    ax.set_xlim(-0.35 * XH, 1.75 * XH); ax.set_ylim(0.85 * XH, -1.85 * XH)
    ax.set_aspect("equal"); ax.axis("off")
    return dict(top=float(-y0 / XH), bottom=float(-y1 / XH), width=float((x1 - x0) / XH))


def heads(L):
    """The ascender head of l, b, h, ſ and f: how far it curls right of the stem's top and
    how high it rises (x-heights)."""
    out = {}
    for ch in "lbhſf":
        st = {s["name"]: np.array(s["points"]) for s in L[ch]["strokes"]}
        stem, head = st["stem"], st["head"]
        out[ch] = dict(reach=float(head[:, 0].max() - stem[0, 0]), top=float(head[:, 1].max()),
                       end_drop=float(head[:, 1].max() - head[-1, 1]))
    return out


def biting(found, straight):
    """Biting on this page, measured as biting.py measures it for the whole book: for
    each pair of neighbouring letters, whether the left letter's last upright stroke and
    the right letter's first are one stroke (bitten), two run together (fused), joined by
    a hairline (linked) or apart; by the sides the letters turn to each other, and by
    pair (pairs seen at least three times)."""
    import biting as BT
    P = BT.pairs(found, straight, BT.stroke_width(straight), BT.facing_offsets(found))
    out = {}
    for key, Q in [("sides " + c, [q for q in P if f"{q['right']} → {q['left']}" == c]) for c in BT.SIDE_ORDER] + \
            [("pair " + p, [q for q in P if q["a"] + q["b"] == p]) for p in sorted({q["a"] + q["b"] for q in P})]:
        Q = [q for q in Q if q["kind"] != "unclear"]
        if len(Q) >= 3:
            out[key] = dict(n=len(Q), biting=float(np.mean([q["kind"] in BT.BITING for q in Q])))
    return out


def rules(reading):
    """Positional rules, counted in the diplomatic reading."""
    words, finals = [], []
    for l in reading:
        raw = l["diplomatic"].split()
        for k, w0 in enumerate(raw):
            if re.match(r"\[[A-Z]\]", w0):
                continue          # its first letter is a painted initial, not the scribe's
            w = unicodedata.normalize("NFC", re.sub(r"\[[^\]]*\]", "", w0).strip(":,."))
            if w:
                words.append(w)
                finals.append(k == len(raw) - 1)
    out = {}
    after_o = sum(w.count("oꝛ") for w in words)
    r_all = sum(w.count("ꝛ") for w in words)
    r_after = sum(1 for w in words for i, c in enumerate(w) if c == "r" and i > 0 and w[i - 1] in "o")
    out["r rotunda"] = dict(after_o=after_o, all=r_all, straight_r_after_o=r_after,
                            straight_r=sum(w.count("r") for w in words))
    out["long and round s"] = dict(
        long_s_word_final=sum(1 for w in words if w.endswith("ſ")),
        long_s=sum(w.count("ſ") for w in words),
        round_s_not_final=sum(1 for w in words if "s" in w[:-1]),
        round_s=sum(w.count("s") for w in words))
    out["v and u"] = dict(v_word_initial=sum(1 for w in words if w.startswith("v")),
                          v=sum(w.count("v") for w in words),
                          u_word_initial=sum(1 for w in words if w.startswith("u")))
    out["final m"] = dict(z_shaped_at_line_end=sum(1 for w, f in zip(words, finals) if w.endswith("ꝫ") and f),
                          z_shaped=sum(1 for w in words if w.endswith("ꝫ")),
                          m_in_full_mid_line=sum(1 for w, f in zip(words, finals) if w.endswith("m") and not f),
                          m_in_full_at_line_end=sum(1 for w, f in zip(words, finals) if w.endswith("m") and f))
    return out


def main():
    OUT.mkdir(exist_ok=True)
    rgb, mask, lines, dark = M.load()
    by = {l["n"]: l for l in lines}
    L = json.loads((OUT / "hours_textura.json").read_text(encoding="utf-8"))
    minim = json.loads((OUT / "hours_minims.json").read_text(encoding="utf-8"))
    found = json.loads((HERE / "data" / "hours_letters_found.json").read_text(encoding="utf-8"))["letters"]
    reading = [l for l in json.loads((HERE / "data" / "hours_reading.json").read_text(encoding="utf-8"))["lines"]
               if l.get("kind") == "text"]
    slant = float(np.median([l["slant_deg"] or 0 for l in lines if l.get("kind") == "text"]))
    t = np.tan(np.radians(slant))
    nib = M.nib_for([1.0])
    spec = M.tail_spec(XH)

    cols = max(len(g.split()) for _, g in GROUPS)
    fig, axes = plt.subplots(len(GROUPS), cols, figsize=(1.7 * cols, 2.0 * len(GROUPS)), dpi=190, facecolor=SURFACE)
    extents = {}
    for r, (title, letters) in enumerate(GROUPS):
        for c in range(cols):
            axes[r, c].axis("off")
        for c, ch in enumerate(letters.split()):
            ext = draw(axes[r, c], letter_strokes(ch, L, minim, t), nib, spec)
            extents[ch] = ext
            n = L[ch]["n"] if ch in L else None
            name = {"ſ": "long s", "s": "final s", "ꝛ": "r rotunda"}.get(ch, ch)
            axes[r, c].set_title(f"{name}" + (f"  ({n})" if n else ""), fontsize=8, color=INK_TEXT, loc="left", pad=1)
        axes[r, 0].text(-0.33 * XH, -1.75 * XH, title, fontsize=7, color=MUTED, va="top")
    fig.suptitle("The lowercase hand of MS 2262, f. 12r, drawn from its fitted strokes\n"
                 "(number of examples fitted in brackets; i, n, m, u from the minim module)", fontsize=8.5,
                 color=INK_TEXT, x=0.01, ha="left")
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    fig.savefig(OUT / "hours_alphabet.png", facecolor=SURFACE)
    plt.close(fig)

    straight = {n: A.straighten(mask, by[n]) for n in {f["line"] for f in found}}
    out = dict(extents_xh=extents, heads=heads(L), biting=biting(found, straight), rules=rules(reading))
    (OUT / "hours_hand.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print("reach above / below the baseline (x-heights):")
    for ch, e in extents.items():
        print(f"  {ch}: top {e['top']:.2f}, bottom {e['bottom']:+.2f}, width {e['width']:.2f}")
    print("ascender heads:", {k: {kk: round(vv, 2) for kk, vv in v.items()} for k, v in out["heads"].items()})
    print("biting:", {k: v for k, v in out["biting"].items()})
    print("rules:", out["rules"])


if __name__ == "__main__":
    main()
