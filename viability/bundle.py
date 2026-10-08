"""Save a fitted hand as one file, so the writer can be pointed at any hand.

A codex was often shared among several scribes of one tradition (hands.py looks for them
in MS 2262). A *hand* here is everything the writer needs, fitted from that scribe's
pages: the pen (nib size, angle, corner sharpness), the twist-and-pull terminal, the minim
module with its joins and pitch, the letters and signs with their variation, the spacing
model, the biting rates (which neighbours write their facing sides as one stroke), the
letters' anchors with the marks and the scribe's placement of them, and where it all came
from (pages, numbers of examples). Fitting another scribe means running the same fits on
their pages and saving another bundle; nothing else in the writer changes.

Run:  python3 bundle.py ID [FOLIOS]   → out/hands/ID.json
      e.g.  python3 bundle.py ms2262_A 12r
Use:  scribe.Scribe.from_bundle("out/hands/ms2262_A.json").write("ſignificatis", 0, 0, 29)
"""
import json
import sys
from pathlib import Path

import numpy as np

import minims as M
import scribe as SC
import textura as TX

HERE = Path(__file__).resolve().parent
OUT = HERE / "out"


def build(hand_id, folios, manuscript="Clermont-Ferrand, Bibliothèque du Patrimoine, MS 2262"):
    env = TX.setup()                      # loads the page, the found letters and the pen (M.PEN)
    found = [f for f in env["found"] if not f.get("skipped")]
    minim = json.loads((OUT / "hours_minims.json").read_text(encoding="utf-8"))
    twist = json.loads((OUT / "hours_twist.json").read_text(encoding="utf-8"))
    letters = json.loads((OUT / "hours_textura.json").read_text(encoding="utf-8"))
    if (OUT / "hours_book_letters.json").exists():          # letters f. 12r lacks, from the book (book_letters.py)
        letters.update(json.loads((OUT / "hours_book_letters.json").read_text(encoding="utf-8")))
    signs = {}
    for fn in ("hours_signs.json", "hours_book_signs.json"):     # f. 12r's signs, then the book's
        if (OUT / fn).exists():
            signs.update(json.loads((OUT / fn).read_text(encoding="utf-8")))
    for v in signs.values():       # the book's example lists stay in out/hours_book_signs.json
        v.pop("examples", None)
    B = dict(
        id=hand_id, manuscript=manuscript, folios=folios,
        # the page's pen, as the letters were fitted with it (the minim module's own fit
        # came out 4% narrower: minim.module.nib_scale)
        pen=dict(a=M.PEN["a"], b=M.PEN["b"], theta=M.PEN["theta"], p=M.PEN["p"],
                 note="sizes in px at the page's x-height (x_height_px)"),
        x_height_px=float(np.median([f["xh"] for f in found])),
        slant_deg=env["slant"],
        terminal=twist["terminal"],
        minim=dict(module=minim["module"], rules=minim["rules"], tail=minim["tail"]),
        minim_offsets=SC.minim_offsets(found),
        spacing=SC.load_ink_spacing(SC.with_book_spacing(SC.fit_spacing(SC.pairs(found)))),   # by the white between letters (lines.py)
        word_space=SC.load_word_space(),
        letters=letters, signs=signs,
        biting=SC.load_biting(),          # how often neighbouring letters share a stroke (biting.py)
        anchors=SC.load_anchors(),        # where marks go on each letter, the marks, their placement (anchors.py)
        provenance=dict(letters={ch: v["n"] for ch, v in letters.items()},
                        signs={ch: v["n"] for ch, v in signs.items()},
                        minim_letters_fitted=len(M.INSTANCES), spacing_pairs=len(SC.pairs(found))))
    (OUT / "hands").mkdir(parents=True, exist_ok=True)
    path = OUT / "hands" / f"{hand_id}.json"
    path.write_text(json.dumps(B, ensure_ascii=False, indent=1, default=float), encoding="utf-8")
    return path


if __name__ == "__main__":
    hid = sys.argv[1] if len(sys.argv) > 1 else "ms2262_A"
    folios = sys.argv[2].split(",") if len(sys.argv) > 2 else ["12r"]
    p = build(hid, folios)
    w = SC.Scribe.from_bundle(p)
    g = w.render(w.write("ſignificatis", 0.0, 0.0, 29.0))
    print(f"{p}: {p.stat().st_size // 1024} kB; 'ſignificatis' drawn, area {g.area:.0f} px²")
