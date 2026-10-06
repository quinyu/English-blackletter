"""The MUFI character recommendation v4.0 (2015) as a table, and how far the hand of
MS 2262 covers it.

MUFI lists 1512 characters for medieval Latin-script texts: base letters with their
precomposed modifications, ligatures, superscript letters and variant forms, then
numbers, combining marks, spacing abbreviation signs, punctuation, symbols, geometrical
and metrical signs. Each has a code point (Unicode, or the Private Use Area where Unicode
has none), an entity name and a descriptive name.

The table is parsed from the text of "MUFI v4.0.pdf" (the repository's master branch),
extracted with pdftotext -layout. Every character is then placed in one of these classes,
by what the writer needs in order to write it (a first pass, from the names and the
Unicode decompositions):

  fitted                    fitted on f. 12r (textura.py, minims.py, abbrev.py)
  composed (fitted marks)   a fitted letter with fitted marks only (e.g. ā, ē, ī, n̄): ready
  composed                  a fitted letter with a modification still to design (an accent,
                            dot, hook, bar or stroke): the letter's strokes are reused
  derived                   built from fitted letters: capitals and small capitals (the
                            scribe's capitals are lowercase-height broken letters), ligatures,
                            superscript letters, enlarged and variant forms
  new                       no fitted base: a letter (thorn, eth, wynn, yogh, k, w, x, y, z …),
                            numeral, punctuation mark or symbol whose strokes must be designed
                            in the hand's manner (the improvisation the end goal allows for)

Run:  python3 mufi.py MUFI_TEXT   → data/mufi4.json, out/mufi_coverage.json
"""
import json
import re
import sys
import unicodedata
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "out"

ROW = re.compile(r"(?P<entity>&[A-Za-z0-9]+;|—)\s+(?P<cp>[0-9A-F]{4,5}(?:\s*\+\s*[0-9A-F]{4,5})*)\s+"
                 r"(?P<chart>[A-Za-z0-9&\-]+(?: & [A-Za-z0-9]+)?)(?:\s+(?P<name>[A-Z][A-Z0-9 \-',./()]+))?$")
NAME = re.compile(r"^\s*([A-Z][A-Z0-9 \-',./()]+)$")
TOP = re.compile(r"^\s*(\d): (.+)$")
LETTER = re.compile(r"^\s*❧(\S+)")
SUB = re.compile(r"^\s*(Base characters|Ligatures|Superscript letters|Variant letter forms|Alphabetical characters|"
                 r"Diacritical marks|Abbreviation marks|[A-Z][a-z]+(?: [a-z]+)*)\s*$")


def parse(text):
    rows, top, letter, sub = [], None, None, None
    started = False
    lines = [l.rstrip() for l in text.splitlines()]
    for k, line in enumerate(lines):
        m = TOP.match(line)
        if m and m.group(2).strip()[0].isupper() and "Alphabetical" in line or (m and started):
            top, letter, sub = f"{m.group(1)}: {m.group(2).strip()}", None, None
            started = True
            continue
        if not started:
            continue
        m = LETTER.match(line)
        if m:
            letter, sub = m.group(1), None
            continue
        if "Glyph" in line and "Entity" in line:
            continue
        m = ROW.search(line)
        if m:
            cps = [int(c, 16) for c in re.split(r"\s*\+\s*", m.group("cp"))]
            name = m.group("name")
            if not name:      # the descriptive name wrapped onto the next line
                nxt = next((l for l in lines[k + 1:k + 4] if l.strip()), "")
                n2 = NAME.match(nxt)
                name = n2.group(1) if n2 else ""
            rows.append(dict(cp="+".join(f"{c:04X}" for c in cps), chars="".join(chr(c) for c in cps),
                             entity=m.group("entity"), chart=m.group("chart"), name=name.strip(),
                             section=top, letter=letter, group=sub,
                             pua=any(0xE000 <= c <= 0xF8FF for c in cps)))
            continue
        m = SUB.match(line)
        if m and len(line.strip()) < 40 and not line.strip().startswith("※"):
            sub = m.group(1)
    return rows


# --- coverage --------------------------------------------------------------------------

def fitted_set():
    """Characters and marks with fitted strokes: textura.py letters, the minim letters,
    abbrev.py signs and marks (ꝙ is not counted: the page writes quod as q + a hook)."""
    F = set("inmu") | {"ı"}     # the scribe's i carries no dot: it is the dotless i (0131)
    for fn in ("hours_textura.json", "hours_signs.json"):
        p = OUT / fn
        if p.exists():
            F |= set(json.loads(p.read_text(encoding="utf-8")))
    F.discard("ꝙ")
    return F


def letters_in(name):
    """Letters named in a MUFI descriptive name: X in "LETTER X ...", A and E in "LETTER AE",
    the letters of "LIGATURE LONG S T" (ſ, t). Words that qualify a letter (ROTUNDA,
    INSULAR, SMALL, CAPITAL …) are skipped."""
    m = re.search(r"(?:LIGATURE|LETTER) ((?:SMALL CAPITAL |SMALL |CAPITAL )?[A-Z ]+?)(?: WITH .*)?$", name)
    if not m:
        return []
    words = m.group(1).split()
    out, k = [], 0
    while k < len(words):
        w = words[k]
        if w == "LONG" and k + 1 < len(words) and words[k + 1] == "S":
            out.append("ſ"); k += 2; continue
        if len(w) <= 2 and w.isalpha():
            out += [c.lower() for c in w]
        k += 1
    return out


def classify(r, F):
    """fitted | composed (fitted marks) | composed | derived | new: what writing it needs."""
    name, ch = r["name"], r["chars"]
    if ch in F:
        return "fitted"
    sec = r["section"] or ""
    d = unicodedata.normalize("NFD", ch) if not r["pua"] else ch
    if len(d) > 1 and d[0] in F and all(unicodedata.combining(c) for c in d[1:]):
        return "composed (fitted marks)" if all(c in F for c in d[1:]) else "composed"
    if sec.startswith("3"):
        return "composed" if r["group"] != "Alphabetical characters" else "derived"
    if sec.startswith("1"):
        ls = letters_in(name)
        if ls and all(l in F or l == "ſ" for l in ls):
            small = " SMALL " in f" {name} " and not any(w in name for w in ("CAPITAL", "ENLARGED"))
            plain = re.search(r"LETTER (SMALL )?[A-Z]$", name) and r["group"] == "Base characters"
            if small and r["group"] == "Base characters" and not plain:
                return "composed"          # a fitted small letter with a modification
            return "derived"              # capital, small capital, ligature, superscript, variant
        return "new"
    if r["chars"] in "0123456789":
        return "new"
    return "new"


ORDER = ["fitted", "composed (fitted marks)", "composed", "derived", "new"]


def main(path):
    text = Path(path).read_text(encoding="utf-8")
    rows = parse(text)
    F = fitted_set()
    for r in rows:
        r["class"] = classify(r, F)
    (HERE / "data" / "mufi4.json").write_text(json.dumps(rows, ensure_ascii=False, indent=0), encoding="utf-8")
    by_sec = {}
    for r in rows:
        by_sec.setdefault(r["section"], Counter())[r["class"]] += 1
    total = Counter(r["class"] for r in rows)
    cov = dict(characters=len(rows), unique_code_points=len({r["cp"] for r in rows}),
               pua=sum(r["pua"] for r in rows), fitted=sorted(F),
               classes={k: total[k] for k in ORDER},
               by_section={k: dict(v) for k, v in by_sec.items()})
    OUT.mkdir(exist_ok=True)
    (OUT / "mufi_coverage.json").write_text(json.dumps(cov, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(cov, ensure_ascii=False, indent=1))
    return rows


if __name__ == "__main__":
    main(sys.argv[1])
