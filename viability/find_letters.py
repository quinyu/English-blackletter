"""Find the letters on any page of MS 2262 from its reading.

align.py found every letter of f. 12r by laying each line's reading along its ink. This
does the same for any other page whose lines have been read (data/hours_readings.json):

  * Lines: each reading line (with its baseline height at the left, read off the page)
    is matched to the page's line guides (out/hours_book_lines.json, from hands.guides)
    and straightened with its slant removed, rescaled to f. 12r's x-height so that the
    same templates fit.
  * Templates: f. 12r's (atlas boxes, the minim module, and the finds that agree best
    with their fellows, as after align.py's rounds), with the stem counts learnt there;
    for the signs f. 12r lacks, crops of the book's own examples (ꝯ, ꝝ, ꝫ, đ from
    data/hours_book_signs.jsonl); and stand-ins for the rest (lowercase for the scribe's
    ink capitals, p for ꝑ, ꝫ for a semicolon sign, a point for ".").
  * Red ink: the reading marks it [R]; the black-ink mask leaves it blank, so the
    aligner allows a wide gap there.
  * Rounds: after the first, each letter's templates are joined by this page's own finds
    that agree best with each other (align.add_exemplars), and the page is aligned again.

Run:  python3 find_letters.py PDF_PAGE_DIR   → data/hours_pages_found.json
"""
import json
import sys
import unicodedata
from pathlib import Path

import cv2
import numpy as np

import align as A
import hands as H
import letterforms as LF
import minims as M

HERE = Path(__file__).resolve().parent
OUT = HERE / "out"
READINGS = HERE / "data" / "hours_readings.json"
FOUND = HERE / "data" / "hours_pages_found.json"
MATCH_PX = 25              # a reading line and a line guide match if their baselines are this close
STAND = {"ꝑ": "p", "ꝰ": "ꝯ", ";": "ꝫ", "⁊": "ꝫ", "ꝗ": "q", "j": "i", "y": "v", "k": "h", "x": "c", "z": "ꝫ",
         "w": "v", "ꝙ": "q", "ẜ": "ſ"}


def straighten(mask, line):
    """The line's window (align.TOP above the baseline, align.BOTTOM below), slant
    removed, rescaled to f. 12r's x-height: column u is the baseline position u·s on the
    page, s = the line's x-height / align.XH."""
    s = line["x_height"] / A.XH
    (x0, _), (x1, _) = line["baseline"]
    us = np.arange(int(x0 / s - A.XH), int(x1 / s + A.XH))
    t = np.tan(np.radians(line["slant_deg"]))
    hs = np.arange(-A.BOTTOM * A.XH, A.TOP * A.XH)[::-1]
    U, Hh = np.meshgrid(us, hs)
    yb = np.array([LF.guide(line, u * s)[0] for u in us])[None, :] * np.ones_like(Hh)
    X = (U * s + Hh * s * t).astype(np.float32)
    Y = (yb - Hh * s).astype(np.float32)
    img = cv2.remap(mask.astype(np.float32), X, Y, cv2.INTER_LINEAR, borderValue=0)
    return (img > 0.5).astype(np.float32), us


def f12r_templates():
    """f. 12r's straightened lines, found letters, final templates and stem counts."""
    rgb, mask, lines, dark = M.load()
    by = {l["n"]: l for l in lines}
    found = json.loads((HERE / "data" / "hours_letters_found.json").read_text(encoding="utf-8"))["letters"]
    straight = {n: A.straighten(mask, by[n]) for n in {f["line"] for f in found}}
    T = A.atlas_templates(straight)
    T.update(A.minim_templates(next(iter(straight.values()))[0].shape[0]))
    T = A.add_exemplars(found, straight, T)
    counts = A.learn_stem_counts(found, straight)
    return T, counts, found, straight


def sign_templates(pdf_dir, n=4):
    """Crops of the book's own examples of the signs f. 12r lacks."""
    recs = [json.loads(l) for l in (HERE / "data" / "hours_book_signs.jsonl").read_text(encoding="utf-8").splitlines()
            if l.strip()]
    want = {"con": "ꝯ", "rum": "ꝝ", "que": "ꝫ", "semicolon_other": "ꝫ", "d_stroke": "đ"}
    lines = json.loads((OUT / "hours_book_lines.json").read_text(encoding="utf-8"))
    masks, T = {}, {}
    for r in recs:
        ch = want.get(r["sign"])
        if ch is None or r.get("confidence") != "sure" or len(T.get(ch, [])) >= n:
            continue
        if r["page"] not in masks:
            masks[r["page"]] = H.page_ink(Path(pdf_dir) / f"{r['page']}.jpg")[1]
        L = lines[r["page"]]["lines"]
        x0, y0, x1, y1 = r["box"]
        line = min(L, key=lambda l: abs(LF.guide(l, (x0 + x1) / 2)[0] - (y1 if r["sign"] != "con" else y1 - 8)))
        img, us = straighten(masks[r["page"]], line)
        s = line["x_height"] / A.XH
        t = np.tan(np.radians(line["slant_deg"]))
        yb = LF.guide(line, (x0 + x1) / 2)[0]
        hc = yb - (y0 + y1) / 2
        a, b = int((x0 - hc * t) / s - us[0]), int((x1 - hc * t) / s - us[0])
        if 0 <= a < b <= img.shape[1]:
            T.setdefault(ch, []).append(img[:, a:b].copy())
    return T


def complete(T, chars):
    """Templates for every character a reading uses: stand-ins where none exists."""
    dot = np.zeros_like(T[":"][0])
    hs = np.arange(-A.BOTTOM * A.XH, A.TOP * A.XH)[::-1] / A.XH
    dot[(hs >= 0.0) & (hs <= 0.2), 1:5] = 1
    T.setdefault(".", [dot])
    for ch in chars:
        if ch in T:
            continue
        lo = ch.lower()
        src = STAND.get(ch) or STAND.get(lo) or (lo if lo in T else None)
        if src is None:
            base = unicodedata.normalize("NFD", ch)[0]
            src = base if base in T else "c"
        T[ch] = [t.copy() for t in T[src if src in T else "c"]]
    return T


def match_lines(reading, guides):
    """{reading line n: line guide}, by baseline height at the reading line's left end."""
    out = {}
    for l in reading:
        if l.get("kind") != "text" or not l["diplomatic"].strip():
            continue
        g = min(guides, key=lambda g: abs(g["baseline"][0][1] - l["y"]))
        if abs(g["baseline"][0][1] - l["y"]) <= MATCH_PX:
            out[l["n"]] = g
    return out


def find_page(pdf_dir, page, reading, T0, counts, rounds=3):
    """Found letters of one page (align.run's format, with page) and its straightened lines."""
    guides = json.loads((OUT / "hours_book_lines.json").read_text(encoding="utf-8"))[page]["lines"]
    rgb, mask, dark, tb = H.page_ink(Path(pdf_dir) / f"{page}.jpg")
    m = match_lines(reading, guides)
    lines = [l for l in reading if l["n"] in m]
    straight = {l["n"]: straighten(mask, m[l["n"]]) for l in lines}
    chars = {tk["char"] for l in lines for tk in A.tokens(l["diplomatic"])}
    T = complete({k: list(v) for k, v in T0.items()}, chars)
    for r in range(rounds):
        found = A.run(None, straight, lines, T, counts)
        if r < rounds - 1:
            T = A.add_exemplars(found, straight, T)
    for f in found:
        g = m[f["line"]]
        s = g["x_height"] / A.XH
        yb, xh = LF.guide(g, (f["u0"] + f["u1"]) / 2 * s)
        f.update(page=page, yb=float(yb), xh=float(xh), slant=float(g["slant_deg"]), scale=float(s))
    return found, straight, dict(lines_read=len(reading), lines_matched=len(lines),
                                 letters=len(found), skipped=sum(f["skipped"] for f in found),
                                 minims_with_their_stems=minim_check(found, straight))


def minim_check(found, straight):
    """[right, checked]: minim letters (i, n, m, u) whose box holds exactly their number
    of stems, the check align.py makes on f. 12r: a misplaced reading or a letter laid
    one stem off fails it."""
    st = {n: A.stems(img) + us[0] for n, (img, us) in straight.items()}
    ok = tot = 0
    for f in found:
        if f["skipped"] or f["char"] not in A.MINIM_STEMS:
            continue
        k = int(((st[f["line"]] >= f["u0"] + A.OWN) & (st[f["line"]] < f["u1"] - A.OWN)).sum())
        ok += k == A.MINIM_STEMS[f["char"]]
        tot += 1
    return [ok, tot]


def load_readings(path=READINGS):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def main(pdf_dir, pages=None):
    T0, counts, _, _ = f12r_templates()
    T0.update({k: v for k, v in sign_templates(pdf_dir).items() if k not in T0 or k in ("ꝫ",)})
    R = load_readings()
    out = json.loads(FOUND.read_text(encoding="utf-8")) if (pages and FOUND.exists()) else {}
    for page, d in R.items():
        if pages and page not in pages:
            continue
        found, straight, stats = find_page(pdf_dir, page, d["lines"], T0, counts)
        out[page] = dict(folio=d["folio"], stats=stats, letters=found)
        print(page, d["folio"], stats, flush=True)
    for d in out.values():
        for f in d["letters"]:
            for k in ("yb", "xh", "slant", "scale"):
                f[k] = round(f[k], 3)
    FOUND.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return out


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2:] or None)
