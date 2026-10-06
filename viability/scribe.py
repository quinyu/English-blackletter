"""Writing in the hand of MS 2262: words from the fitted letters, the minim system and
spacing measured on f. 12r — tested on page words held out of every fit, then used to
write a word the page does not contain.

  letters    i, n, m, u from the minim module (minims.py): stems at the measured pitch,
             a hairline from mid-height into the next head inside n and m, from the foot
             into the middle of the next inside u; ſ, f, g, c, a, t and final s from their
             fitted stroke plans (textura.py)
  spacing    every pair of neighbouring letters inside a word on the page (align.py)
             gives the distance from one letter's left edge to the next's; it is modelled
             as an advance for the left letter plus an approach for the right one, so
             that pairs never seen on the page are spaced too. The spread left over
             (0.14 x-height) is mostly the uncertainty of where align.py puts a box edge;
             the scribe's own spacing variation is taken from the stems instead (the
             spread of between-letter stem pitch, minims.py)
  joins      between letters only as the minim rules measured them (minim to minim: a
             head join at the measured rate; into a u: a foot join at its rate)
  ends       a word-final n or m ends in the twist-and-pull tail (twist.py)
  variation  with a random generator: each letter's width and height, the spacing and
             the minim pitch and joins vary by the spreads measured on the page

Held-out test: four page words built only from these letters are written again, each
with its own letters left out of the letter fits and of the spacing model; the word is
placed at its first letter's position and compared with the ink.

Run:  python3 scribe.py   → out/hours_scribe.png, out/hours_scribe.json
"""
import json
import unicodedata
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

import letterforms as LF
import minims as M
import pen
import textura as TX

HERE = Path(__file__).resolve().parent
OUT = HERE / "out"
SURFACE, INK_TEXT, MUTED, DATA, MODEL = "#fcfcfb", "#0b0b0b", "#52514e", "#2a78d6", "#eb6834"
MINIM_LETTERS = M.MINIMS
TEST_WORDS = [(2, "magni"), (4, "infantium"), (5, "ciſti"), (6, "inimicum")]
WORD = "ſignificatis"
RIDGE = 0.5          # pull of rare letters' advance/approach towards the average (x-heights², per pair)


# ---- spacing ---------------------------------------------------------------------------

def pairs(found, exclude=()):
    """Neighbouring letters inside words: (left char, right char, distance in x-heights)."""
    by = {}
    for f in found:
        by.setdefault((f["line"], f["word"]), []).append(f)
    out = []
    for key, F in by.items():
        if key in set(exclude):
            continue
        F = [f for f in sorted(F, key=lambda f: f["index"]) if not f["skipped"] and f["char"] not in ":,."]
        for a, b in zip(F[:-1], F[1:]):
            out.append((a["char"], b["char"], (b["u0"] - a["u0"]) / a["xh"]))
    return out


def fit_spacing(P):
    """distance = advance[left] + approach[right], least squares with a ridge towards
    the average for letters seen in few pairs; returns the model and the residual spread."""
    chars = sorted({p[0] for p in P} | {p[1] for p in P})
    k = {c: i for i, c in enumerate(chars)}
    n = len(chars)
    X = np.zeros((len(P), 2 * n))
    y = np.array([p[2] for p in P])
    for r, (a, b, _) in enumerate(P):
        X[r, k[a]] = 1
        X[r, n + k[b]] = 1
    mu = y.mean()
    A = X.T @ X + RIDGE * np.eye(2 * n)
    coef = np.linalg.solve(A, X.T @ (y - mu))
    resid = y - mu - X @ coef
    adv = {c: float(mu / 2 + coef[k[c]]) for c in chars}
    app = {c: float(mu / 2 + coef[n + k[c]]) for c in chars}
    return dict(advance=adv, approach=app, mean=float(mu), sd=float(np.std(resid)), n=len(P))


def distance(sp, a, b):
    return sp["advance"].get(a, sp["mean"] / 2) + sp["approach"].get(b, sp["mean"] / 2)


# ---- the minim letters' place in their boxes -------------------------------------------

def minim_offsets(found):
    """Median distance (x-heights) from a minim letter's box edge to its first stem."""
    off = {}
    for n, word, letters in M.RUNS:
        for ch, stems in letters:
            for f in found:
                if f["line"] == n and f["char"] == ch and f["u0"] - 2 <= stems[0] <= f["u1"]:
                    off.setdefault(ch, []).append((stems[0] - f["u0"]) / f["xh"])
                    break
    return {ch: float(np.median(v)) for ch, v in off.items()}


# ---- writing ---------------------------------------------------------------------------

def load_letters():
    """Fitted letters (textura.py) and, when fitted, the abbreviation signs and marks of
    f. 12r (abbrev.py) and of the rest of the book (book_signs.py)."""
    L = json.loads((OUT / "hours_textura.json").read_text(encoding="utf-8"))
    for fn in ("hours_signs.json", "hours_book_signs.json"):
        if (OUT / fn).exists():
            L.update(json.loads((OUT / fn).read_text(encoding="utf-8")))
    return L


def load_biting():
    """The writer's biting parameters (biting.py), or None before the study has run."""
    p = OUT / "hours_biting.json"
    return json.loads(p.read_text(encoding="utf-8"))["summary"].get("writer") if p.exists() else None


def with_book_spacing(sp):
    """The spacing model with the approach and advance of the signs fitted from the whole
    book (book_signs.py), which f. 12r's pairs do not cover."""
    p = OUT / "hours_book_spacing.json"
    if not p.exists():
        return sp
    B = json.loads(p.read_text(encoding="utf-8"))
    return dict(sp, advance=dict(sp["advance"], **B["advance"]), approach=dict(sp["approach"], **B["approach"]))


class Scribe:
    def __init__(self, letters, minim, spacing, offsets, slant, nib=None, terminal=None, biting=None):
        """nib: (a, b, theta, p) of the hand's pen, terminal: its twist-and-pull keyframes;
        both default to MS 2262's as fitted (minims.load, twist.py). biting: the rates
        and stroke offsets with which neighbouring letters share a stroke (biting.py;
        None: letters are only spaced). A hand bundle (bundle.py) carries its own."""
        self.L, self.Mi, self.sp, self.off = letters, minim, spacing, offsets
        self.nib, self.terminal, self.bite = nib, terminal, biting
        self.t = np.tan(np.radians(slant))
        self.p = np.array([minim["module"][k] for k in M.PARAMS])
        self.tail = minim["tail"]

    def write(self, word, x0, yb, xh, rng=None):
        """Strokes (name, page points, pen spec) for a word; x0 is its first letter's left
        edge at the baseline."""
        jit = (lambda mu, sd: mu + sd * rng.standard_normal()) if rng is not None else (lambda mu, sd: mu)
        chance = (lambda r: rng.random() < r) if rng is not None else (lambda r: r >= 0.5)
        R, P = self.Mi["rules"], self.Mi["rules"]["pitch"]
        out = []
        x = x0
        prev_last_stem = None
        # letters with the marks they carry (combining characters: macron, er sign)
        clusters = []
        for ch in unicodedata.normalize("NFD", word):
            if unicodedata.combining(ch) and clusters:
                clusters[-1][1].append(ch)
            else:
                clusters.append((ch, []))
        bases = [c for c, _ in clusters]
        prev_x = x
        for i, (ch, marks) in enumerate(clusters):
            if i > 0:
                d = self.bite_distance(bases[i - 1], ch, chance, jit)
                if d is None:
                    d = jit(distance(self.sp, bases[i - 1], ch), self.Mi["rules"]["pitch"]["between_sd"])
                x = prev_x + xh * d
            prev_x = x
            final = i == len(clusters) - 1
            for mk in marks:          # drawn over this letter's box, from the fitted mark plan
                Lm = self.L[mk]
                Xm = x - Lm["shift_px"][0] * xh / TX.XH
                for s_ in Lm["strokes"]:
                    out.append((s_["name"], [[Xm + u * xh + v * xh * self.t, yb - v * xh] for u, v in s_["points"]], None))
            if ch in MINIM_LETTERS:
                s0 = x + self.off.get(ch, 0.2) * xh
                stems = [s0 + j * xh * jit(P["inside"], P["inside_sd"]) if j else s0 for j in range(MINIM_LETTERS[ch])]
                for j in range(2, len(stems)):
                    stems[j] = stems[j - 1] + xh * jit(P["inside"], P["inside_sd"])
                H, F = R["head"], R["foot"]
                head = (jit(H["h0"], H["h0_sd"]), "head")
                foot = (jit(F["h0"], F["h0_sd"]), jit(F["h1"], F["h1_sd"]))
                joins = [foot if ch == "u" else head for _ in stems[1:]]
                tail = self.tail if (final and ch in "nm") else None
                st = M.module_strokes(stems, yb, xh, np.degrees(np.arctan(self.t)), self.p, joins, tail)
                if tail is not None:
                    st[-1] = (st[-1][0], st[-1][1], self.tail_spec(xh))
                # join from the previous minim letter, at the scribe's rates
                if prev_last_stem is not None:
                    a = prev_last_stem
                    if ch == "u" and chance(R["into_u_rate"]):
                        out.append(("hairline join", M.join_points(a, stems[0], yb, xh, 0.0, *foot), None))
                    elif ch != "u" and chance(R["between_rate"]):
                        m0 = M.minim_points(stems[0], yb, xh, np.degrees(np.arctan(self.t)), self.p)[0]
                        out.append(("hairline join", [M.join_points(a, stems[0], yb, xh, 0.0, head[0], 0)[0], m0], None))
                out += st
                prev_last_stem = stems[-1]
            else:
                Lc = self.L["s" if (ch == "s") else ch]
                su = jit(Lc["width_scale"][0], Lc["width_scale"][1]) if rng is not None else 1.0
                sv = jit(Lc["height_scale"][0], Lc["height_scale"][1]) if rng is not None else 1.0
                X = x - Lc["shift_px"][0] * xh / TX.XH
                for s_ in Lc["strokes"]:
                    pts = [[X + u * su * xh + v * sv * xh * self.t, yb - v * sv * xh] for u, v in s_["points"]]
                    spec = self.tail_spec(xh) if s_["pen"] == "terminal" else None
                    out.append((s_["name"], pts, spec))
                prev_last_stem = None
        return out

    def bite_distance(self, a, b, chance, jit):
        """When a and b bite (at the scribe's rate for the pair, or for its facing sides),
        the distance between their left edges (x-heights) that puts b's first upright
        stroke on a's last one, a little to the right where the two run together; None
        when they do not bite."""
        B = self.bite
        if not B or a not in B["offsets"] or b not in B["offsets"] or a not in B["sides"] or b not in B["sides"]:
            return None
        r = B["pair_rate"].get(a + b)
        if r is None:
            r = B["sides_rate"].get(f"{B['sides'][a][0]} → {B['sides'][b][1]}", 0.0)
        if not r or not chance(r):
            return None
        extra = max(0.0, jit(*B["extra_px"]))
        return (B["offsets"][a]["last"] - B["offsets"][b]["first"] + extra) / TX.XH

    def tail_spec(self, xh, ref_xh=29.4):
        if self.terminal is None:
            return M.tail_spec(xh)
        return dict(self.terminal, from_end_px=[v * xh / ref_xh for v in self.terminal["from_end_px"]])

    def pen(self):
        if self.nib is None:
            return M.nib_for([1.0])
        a, b, theta, p = self.nib
        return pen.Nib(a, b, theta, p=p)

    @classmethod
    def from_bundle(cls, path):
        """The writer for a hand saved by bundle.py."""
        B = json.loads(Path(path).read_text(encoding="utf-8"))
        letters = dict(B["letters"], **B.get("signs", {}))
        n = B["pen"]
        return cls(letters, B["minim"], B["spacing"], B["minim_offsets"], B["slant_deg"],
                   nib=(n["a"], n["b"], n["theta"], n["p"]), terminal=B["terminal"], biting=B.get("biting"))

    def render(self, strokes):
        return pen.render([s for _, s, _ in strokes], self.pen(), step=0.5,
                          names=[n for n, _, _ in strokes], pens=[k for _, _, k in strokes])


# ---- the held-out test -----------------------------------------------------------------

def word_letters(env, line, word):
    T = env["toks"][line]
    words = sorted({t["word"] for t in T})
    for w in words:
        letters = [t for t in T if t["word"] == w and t["char"] not in ":,."]
        if "".join(t["char"] for t in letters) == word:
            idx = [k for k, t in enumerate(T) if t["word"] == w and t["char"] not in ":,."]
            F = [f for f in env["found"] if f["line"] == line and f["index"] in idx]
            return w, sorted(F, key=lambda f: f["index"])
    raise ValueError(f"{word} not on line {line}")


def word_box(F, yb, xh):
    return (int(F[0]["u0"] - 0.35 * xh), int(yb - 1.75 * xh), int(F[-1]["u1"] + 0.35 * xh), int(yb + 0.85 * xh))


def compare(geom, mask, box):
    """Overlap of the written word with the ink in its box, after the best shift
    (±3 px across, ±6 px up or down: the line guides are straight lines)."""
    x0, y0, x1, y1 = box
    best = (-1, 0, 0)
    for dy in range(-6, 7):
        for dx in range(-3, 4):
            ink_ = mask[y0 + dy:y1 + dy, x0 + dx:x1 + dx] > 0
            m = pen.rasterize(geom, ink_.shape, origin=(x0, y0)) > 0
            best = max(best, ((ink_ & m).sum() / max(1, (ink_ | m).sum()), dx, dy))
    return best


def main():
    OUT.mkdir(exist_ok=True)
    env = TX.setup()
    mask, lines, rgb = env["mask"], env["lines"], env["rgb"]
    by = {l["n"]: l for l in lines}
    minim = json.loads((OUT / "hours_minims.json").read_text(encoding="utf-8"))
    letters_all = load_letters()
    offsets = minim_offsets(env["found"])
    sp_all = fit_spacing(pairs(env["found"]))
    print(f"spacing: {sp_all['n']} letter pairs, mean {sp_all['mean']:.3f} x-height, residual spread {sp_all['sd']:.3f}")

    tests = []
    for line, word in TEST_WORDS:
        w, F = word_letters(env, line, word)
        own = sorted({c for c in word if c not in MINIM_LETTERS})
        held = TX.fit(env, letters=own, exclude=[(line, w)], verbose=False)
        tmp = OUT / "_heldout.json"
        TX.save(held, tmp)
        L = dict(letters_all, **json.loads(tmp.read_text(encoding="utf-8")))
        tmp.unlink()
        sp = fit_spacing(pairs(env["found"], exclude=[(line, w)]))
        scribe = Scribe(L, minim, sp, offsets, env["slant"])
        yb, xh = LF.guide(by[line], F[0]["u0"])
        st = scribe.write(word, F[0]["u0"], yb, xh)
        geom = scribe.render(st)
        box = word_box(F, yb, xh)
        ov, dx, dy = compare(geom, mask, box)
        # the same word with nothing held out, for comparison
        full = Scribe(letters_all, minim, sp_all, offsets, env["slant"])
        ov_in, _, _ = compare(full.render(full.write(word, F[0]["u0"], yb, xh)), mask, box)
        # where the page's letters really start, against where the spacing model put them
        starts = np.array([f["u0"] for f in F], float)
        model_starts = [F[0]["u0"]]
        for a, b in zip(word[:-1], word[1:]):
            model_starts.append(model_starts[-1] + xh * distance(sp, a, b))
        drift = float(np.max(np.abs(np.array(model_starts) - starts)))
        tests.append(dict(word=word, line=line, overlap_held_out=float(ov), overlap_in_sample=float(ov_in),
                          shift_px=[dx, dy], spacing_max_error_px=drift, box=box, geom=geom))
        print(f"{word:10s} l.{line}: overlap {ov:.2f} held out ({ov_in:.2f} with nothing held out); "
              f"letter positions from the spacing model within {drift:.1f} px")

    scribe = Scribe(letters_all, minim, sp_all, offsets, env["slant"])
    plot(rgb, tests, scribe, OUT / "hours_scribe.png")
    (OUT / "hours_scribe.json").write_text(json.dumps({
        "spacing": sp_all, "minim_offsets": offsets,
        "tests": [{k: v for k, v in t.items() if k != "geom"} for t in tests]}, ensure_ascii=False, indent=1),
        encoding="utf-8")


def fill(ax, geom, color="#2a2118"):
    for poly in (geom.geoms if hasattr(geom, "geoms") else [geom]):
        ax.fill(*poly.exterior.xy, color=color, lw=0)
        for hole in poly.interiors:
            ax.fill(*hole.xy, color=SURFACE, lw=0)


def plot(rgb, tests, scribe, path):
    fig = plt.figure(figsize=(10.5, 2.0 * len(tests) / 2 + 4.6), dpi=180, facecolor=SURFACE)
    nt = len(tests)
    gs = fig.add_gridspec(nt + 4, 2, height_ratios=[1] * nt + [0.25, 1.15, 1.15, 0.1], hspace=0.55, wspace=0.05)
    for r, t in enumerate(tests):
        x0, y0, x1, y1 = t["box"]
        ax = fig.add_subplot(gs[r, 0])
        dx, dy = t["shift_px"]
        ax.imshow(rgb[y0 + dy:y1 + dy, x0 + dx:x1 + dx], extent=(x0, x1, y1, y0), interpolation="lanczos")
        ax.set_xlim(x0, x1); ax.set_ylim(y1, y0); ax.axis("off")
        ax.set_title(f"page, line {t['line']}: '{t['word']}'", fontsize=7, color=INK_TEXT, loc="left", pad=2)
        ax = fig.add_subplot(gs[r, 1])
        fill(ax, t["geom"])
        ax.set_xlim(x0, x1); ax.set_ylim(y1, y0); ax.set_aspect("equal"); ax.axis("off")
        ax.set_title(f"written with its own letters held out: overlap {t['overlap_held_out']:.0%}",
                     fontsize=7, color=INK_TEXT, loc="left", pad=2)
    ax = fig.add_subplot(gs[nt, :]); ax.axis("off")
    ax.text(0, 0.0, f"'{WORD}' (not on the page): first plain, then with the scribe's variation", fontsize=8,
            color=INK_TEXT, va="bottom")
    xh, yb = 29.0, 0.0
    for k, seed in enumerate([None, 3, 8, 21]):
        rng = None if seed is None else np.random.default_rng(seed)
        geom = scribe.render(scribe.write(WORD, 0.0, yb, xh, rng))
        ax = fig.add_subplot(gs[nt + 1 + k // 2, k % 2])
        fill(ax, geom)
        x0, y0, x1, y1 = geom.bounds
        ax.set_xlim(x0 - 6, x1 + 6); ax.set_ylim(yb + 0.9 * xh, yb - 1.8 * xh); ax.set_aspect("equal"); ax.axis("off")
        ax.set_title("medians, no variation" if seed is None else f"variation, seed {seed}", fontsize=7,
                     color=MUTED, loc="left", pad=2)
    fig.suptitle("Writing in the hand of MS 2262 from fitted letters and measured spacing", fontsize=9,
                 color=INK_TEXT, x=0.01, ha="left")
    fig.savefig(path, facecolor=SURFACE, bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    main()
