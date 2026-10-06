"""Abbreviation signs and punctuation of MS 2262 (f. 12r): stroke plans fitted to every
example, the same way as the letters (textura.py), and the scribe's writer extended to
place them.

What the page shows (gridded close-ups), with the MUFI 4.0 encoding of each sign:

  macron     ◌̄  0304 COMBINING MACRON. A short thick bar, nearly flat, about 1.45 x-heights
                  up, over a vowel for a missing m or n (ī, ā, ē) and over m in qm̄.
  er sign    ◌͛  035B COMBINING ZIGZAG ABOVE, in this hand its curly form (F1C8): a small
                  lozenge with a hairline curl, above the u of vniu[er]ſa.
  et / -m    ꝫ   A76B LATIN SMALL LETTER ET. z-shaped: a top bar, a diagonal down to the
                  left, a small bowl, and a long hairline tail below the line. Only at line
                  ends here (euꝫ, tuaruꝫ).
  pro        ꝓ   A753 LATIN SMALL LETTER P WITH FLOURISH. The p, its base stroke running on
                  under the stem into a long hairline flourish below the line.
  quod       ꝙ   written as q followed by a raised hook at its shoulder, i.e. q + 02BC
                  MODIFIER LETTER APOSTROPHE in MUFI's terms; the reading keeps ꝙ for the
                  word sign. The hook is the same lozenge-and-curl as the er sign.
  colon      :   two lozenges, at about 0.65 x-height and just above the baseline: the
                  mid-verse pause (the chant's mediant), in 5 of the page's 7 full verses.
  comma      ,   a lozenge at mid-height with a long hairline tail below the line: verse
                  end or flex.

Signs with a box from align.py (ꝫ, ꝓ, ꝙ, :, ,) are fitted in their boxes; the marks
(macron, er sign) are fitted above the letter that carries them, compared only in the
band above the x-line. Few examples exist on one page (1–7), so the fits mostly confirm
and adjust plans drawn from the close-ups; the book's other pages hold hundreds more.

The writer (scribe.py) places marks over the letter before them and uses the signs as
letters; out/hours_abbreviated.png writes words in full and abbreviated, as the scribe
could, to fit the space left in a line.

Run:  python3 abbrev.py   → out/hours_signs.json, out/hours_signs.png, out/hours_abbreviated.png
"""
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

import textura as TX

HERE = Path(__file__).resolve().parent
OUT = HERE / "out"
SURFACE, INK_TEXT, MUTED = "#fcfcfb", "#0b0b0b", "#52514e"
MACRON, ER = "̄", "͛"

SIGNS = {
    "ꝫ": dict(zone=(-0.75, 1.3), ties=[((2, 3), (3, 0))], strokes=[
        ("top", [(0.05, 0.95), (0.2, 1.0), (0.42, 0.97)], None),
        ("diagonal", [(0.42, 0.95), (0.08, 0.45)], None),
        ("bowl", [(0.08, 0.45), (0.3, 0.52), (0.42, 0.3), (0.3, 0.02)], None),
        ("hairline tail", [(0.3, 0.02), (0.15, -0.3), (0.22, -0.5), (0.1, -0.72)], None)]),
    "ꝓ": dict(zone=(-0.75, 1.3), strokes=[
        ("stem", [(0.0, 0.97), (0.07, 0.88), (0.08, 0.1)], None),
        ("bowl", [(0.35, 0.93), (0.55, 0.85), (0.58, 0.1)], None),
        ("base and flourish", [(0.6, 0.02), (0.3, 0.0), (0.0, 0.0), (-0.18, -0.2), (-0.38, -0.5)], None)]),
    "ꝙ": dict(zone=(-0.75, 1.3), strokes=[
        ("bowl", [(0.55, 0.98), (0.25, 0.85), (0.1, 0.4), (0.2, 0.0), (0.45, 0.05)], None),
        ("stem", [(0.6, 1.05), (0.62, 0.6), (0.62, -0.2), (0.62, -0.6)], "terminal"),
        ("hook", [(0.85, 0.98), (0.92, 0.88), (0.86, 0.72)], None)]),
    ":": dict(zone=(-0.2, 1.0), move=0.06, strokes=[        # the two points stay apart
        ("upper point", [(0.1, 0.7), (0.17, 0.6)], None),
        ("lower point", [(0.1, 0.2), (0.17, 0.1)], None)]),
    ",": dict(zone=(-0.75, 1.0), ties=[((0, 1), (1, 0))], strokes=[
        ("point", [(0.1, 0.62), (0.17, 0.52)], None),
        ("hairline tail", [(0.17, 0.52), (0.12, 0.15), (0.02, -0.35), (-0.03, -0.72)], None)]),
    MACRON: dict(zone=(1.18, 1.75), strokes=[
        ("bar", [(0.0, 1.43), (0.2, 1.48), (0.42, 1.46)], None)]),
    ER: dict(zone=(1.2, 1.75), move=0.08, ties=[((0, 1), (1, 0))], strokes=[   # keeps its curl, too faint for the ink mask
        ("point", [(0.25, 1.65), (0.31, 1.57)], None),
        ("hairline curl", [(0.31, 1.57), (0.28, 1.45), (0.2, 1.38)], None)]),
}
MUFI = {"ꝫ": ("A76B", "LATIN SMALL LETTER ET"), "ꝓ": ("A753", "LATIN SMALL LETTER P WITH FLOURISH"),
        "ꝙ": ("0071+02BC", "q + MODIFIER LETTER APOSTROPHE (read as ꝙ, A759)"), ":": ("003A", "COLON"),
        ",": ("002C", "COMMA (a medieval punctus with a long tail)"), MACRON: ("0304", "COMBINING MACRON"),
        ER: ("035B", "COMBINING ZIGZAG ABOVE, curly form (MUFI F1C8)")}
NAMES = {MACRON: "macron", ER: "er sign", "ꝫ": "et / -m", "ꝓ": "pro", "ꝙ": "quod", ":": "colon", ",": "comma"}


def mark_examples(env):
    """Pseudo-finds for the marks: a macron over each letter the reading marks with one;
    the er sign over the u of each vniu[er]ſa."""
    found = env["found"]
    out = []
    for f in found:
        if "macron" in f["flags"]:
            out.append(dict(f, char=MACRON, skipped=False))
    by_line = {}
    for f in found:
        by_line.setdefault(f["line"], []).append(f)
    for n, F in by_line.items():
        F = sorted(F, key=lambda f: f["index"])
        for a, b in zip(F, F[1:]):
            if a["char"] == "u" and b["char"] == "ſ" and a["word"] == b["word"]:
                out.append(dict(a, char=ER, skipped=False))
    return out


def main():
    OUT.mkdir(exist_ok=True)
    TX.PLANS.update(SIGNS)
    env = TX.setup()
    env["found"] = env["found"] + mark_examples(env)
    fits = TX.fit(env, letters=list(SIGNS))
    TX.save(fits, OUT / "hours_signs.json")
    data = json.loads((OUT / "hours_signs.json").read_text(encoding="utf-8"))
    for ch, d in data.items():
        d["mufi"] = dict(zip(("code_point", "name"), MUFI[ch]))
    (OUT / "hours_signs.json").write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")

    n = 8
    keys = list(SIGNS)
    fig, axes = plt.subplots(len(keys), n + 1, figsize=(1.05 * (n + 1), 1.35 * len(keys)), dpi=190,
                             facecolor=SURFACE, gridspec_kw=dict(width_ratios=[1.3] + [1] * n))
    for r, ch in enumerate(keys):
        F = fits[ch]
        TX.draw_letter(axes[r, 0], TX.unpack(TX.PLANS[ch], F["x"]))
        label = NAMES.get(ch, ch)
        axes[r, 0].set_title(f"{label}  {MUFI[ch][0]}\n{len(F['exs'])} fitted, overlap {np.mean(F['score']):.2f}",
                             fontsize=6, color=INK_TEXT, loc="left", pad=1)
        order = np.argsort(F["score"])[::-1]
        TX.show_examples(axes[r, 1:], ch, F["x"], [F["exs"][i] for i in order], env["fp"], n=n)
    fig.suptitle("Abbreviation signs and punctuation of f. 12r: stroke plans fitted to every example "
                 "(marks compared only above the x-line)", fontsize=8, color=INK_TEXT, x=0.01, ha="left")
    fig.tight_layout(rect=(0, 0, 1, 0.97))
    fig.savefig(OUT / "hours_signs.png", facecolor=SURFACE)
    plt.close(fig)
    plot_forms(env, OUT / "hours_abbreviated.png")
    return fits


# the same word, full and abbreviated (the forms on f. 12r, and dn̄s / dōꝫ for dominus)
FORMS = [("dominus", ["dn\u0304s", "do\u0304ꝫ"]), ("quoniam", ["qm\u0304"]), ("eum", ["euꝫ"]),
         ("propter", ["ꝓpter"]), ("quam", ["qua\u0304"]), ("vniuerſa", ["vniu\u035bſa"]),
         ("quod", ["ꝙ"]), ("inimicos", ["i\u0304imicos"])]


def plot_forms(env, path, xh=29.0):
    import scribe as SC
    minim = json.loads((OUT / "hours_minims.json").read_text(encoding="utf-8"))
    found = [f for f in env["found"] if f["char"] not in (MACRON, ER)]
    w = SC.Scribe(SC.load_letters(), minim, SC.fit_spacing(SC.pairs(found)), SC.minim_offsets(found), env["slant"])
    fig, axes = plt.subplots(len(FORMS), 1 + max(len(a) for _, a in FORMS), figsize=(12, 1.15 * len(FORMS)),
                             dpi=180, facecolor=SURFACE)
    for r, (full, abbrs) in enumerate(FORMS):
        for c, word in enumerate([full] + abbrs):
            ax = axes[r, c]
            geom = w.render(w.write(word, 0.0, 0.0, xh))
            SC.fill(ax, geom)
            x0, y0, x1, y1 = geom.bounds
            ax.set_xlim(-0.6 * xh, 7.0 * xh); ax.set_ylim(0.95 * xh, -1.85 * xh)
            ax.set_aspect("equal"); ax.axis("off")
            ax.set_title(("in full" if c == 0 else "abbreviated") + f": {word}", fontsize=7.5, color=MUTED, loc="left",
                         pad=1, fontfamily="FreeSerif")
        for c in range(1 + len(abbrs), axes.shape[1]):
            axes[r, c].axis("off")
    fig.suptitle("Words in full and abbreviated, written from the fitted letters and signs", fontsize=8.5,
                 color=INK_TEXT, x=0.01, ha="left")
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    fig.savefig(path, facecolor=SURFACE)
    plt.close(fig)


if __name__ == "__main__":
    main()
