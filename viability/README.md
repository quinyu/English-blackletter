# Viability check: a stroke-and-nib model of one scribe's الله

**Question.** Can a model that *writes* letters, with a pen following stroke paths,
reproduce a real early Qur'anic hand? Can it also vary the way the scribe varied,
instead of repeating one fixed glyph the way a font does?

**Test material.** One page of BnF Arabe 328 (Hijazi script, Sūrat al-Baqarah
2:282–286), the 1024 × 1392 px image from Gallica. Every الله on the page was traced:
9 full instances, plus two لله on line 11. One of those is the second half of a والله
the scribe split across lines 10/11. That gives 11 instances.

**Short answer: viable.** The pen model redraws every instance to within about one scan
pixel. The measurements are reproducible from rough clicks, and the scribe's variation
turns out to be structured, so it can be modelled. Details and limits below.

## How it works

| Step | File | What it does |
|---|---|---|
| Ink | `ink.py` | Separates ink from parchment, water stains and the mirrored show-through from the other side of the leaf. Each pixel is compared with the local parchment brightness. |
| Trace | `data/traces_allah.json`, `../tools/tracer/` | For each word, a rough click at the top and foot of the alif, both lāms, the hā' and the baseline. |
| Measure | `measure.py` | Snaps each rough stroke onto the ink, re-fits it as a straight shaft, finds the baseline and the hā' loop, and outputs 11 features per word. |
| Pen | `nib.py` | Estimates the nib from about 17,000 stroke-width samples across the whole page. |
| Render | `pen.py`, `ductus.py` | Sweeps an elliptical nib along stroke centre-lines and outputs a vector outline (SVG). `ductus.py` is the stroke plan for الله, driven by the measured features. |
| Check | `run.py` | Runs everything and writes figures and numbers to `out/`. |

```sh
pip install -r requirements.txt
python3 run.py          # ~2 minutes; writes out/
```

## Results

### 1. The pen: an almost even-width reed

![Stroke width by direction](out/fig_nib.png)

Stroke width hardly depends on direction. An elliptical nib of **6.6 × 5.6 px held at
47°** fits the page to within 0.19 px, giving a **thick/thin contrast of 1.18**. For
comparison, a broad-edge pen for Naskh or textura is roughly 5–10.

Horizontal strokes come out about 8% heavier than the slanted shafts (6.2 vs 5.7 px).
The reading I gave earlier from the image alone was right. This hand's character lies
in shapes, proportions and spacing, not in thick/thin modulation.

### 2. The model redraws every instance to within about a pixel

![Every instance re-drawn by the model](out/fig_fits.png)

Each word was rebuilt from its own 11 measurements and the page-wide nib, then laid
over its ink:

- **Average outline error: 0.57–1.04 px** against a stroke width of 5.5 px.
- **Overlap: 63–80%.** At this stroke width a one-pixel shift on each side already
  costs about a third of the overlap, so the outline distance is the more telling
  number.

The remaining error is at the scan's resolution limit. Ink from neighbouring letters
that touches the word (shown in grey in the figure) is left out of the score, since
separating it is a segmentation problem, not a pen-model question.

### 3. Measurements are stable; the variation is the scribe's

A real repeatability test was run: every click was moved by random noise (SD 2.5 px)
and each word was re-measured 12 times.

| Feature | n | Mean | Scribe's SD | Range | Measurement noise SD |
|---|---:|---:|---:|---:|---:|
| alif height | 7 | 42.6 px (7.8 sw) | 3.1 px | 36.5–46.8 | 1.4 |
| lām¹ height | 10 | 41.7 px (7.6 sw) | 4.4 px | 35.4–51.3 | 1.0 |
| lām² height | 10 | 40.4 px (7.4 sw) | 5.0 px | 28.9–47.9 | 2.2 |
| alif slant | 7 | 34.4° | 2.5° | 30.8–37.9° | 0.3 |
| lām¹ slant | 10 | 25.3° | 2.0° | 21.5–28.2° | 0.1 |
| lām² slant | 10 | 24.9° | 3.5° | 19.4–30.2° | 0.5 |
| alif → lām¹ gap | 7 | 23.3 px (4.3 sw) | 1.8 px | 20.6–26.1 | 0.2 |
| lām¹ → lām² spacing | 10 | 18.9 px (3.4 sw) | 2.6 px | 14.0–23.1 | 0.2 |
| lām² → end of hā' | 9 | 24.4 px (4.5 sw) | 2.7 px | 22.2–30.5 | 0.6 |
| hā' height | 9 | 12.1 px (2.2 sw) | 1.2 px | 9.5–13.5 | 0.7 |
| hā' width | 9 | 17.6 px (3.2 sw) | 1.9 px | 16.0–22.0 | 0.5 |

*sw* = stroke widths (5.5 px), the scale-free unit. Slants are measured from vertical,
top leaning right.

- **Measurement noise is small next to the variation.** Slants and spacings are 5–40×
  smaller than the scribe's spread. Heights are the weakest case at 2–4× smaller,
  because the top of a stroke is where a click matters most.
- **A rule a font would not know.** In every one of the 7 words with a free alif, the
  alif leans further than both lāms, by 9° on average (34° vs 25°).
- **Moderate variation.** The scribe's variation is 7–14% of each size and 2–3.5° of
  slant.

### 4. The variation is shared across the word

Each letter was predicted only from the *other* letters of the same word
(leave-one-out), so no letter can explain itself:

- **Size is shared by the whole word.** The alif's height correlates with the average
  lām height of the same word at r = 0.97 (n = 7). Each lām's height correlates with
  the rest of its word at r ≈ 0.63 (n = 10). The whole word's size varies with an SD of
  about 9.5%.
- **Slant is partly shared.** Correlations are 0.38–0.72, and the word's slant varies
  with an SD of 2.3°.

This is the structured variation the earlier discussion predicted. A big part of the
"handmade" look is that a whole word comes out a little larger, or leans a little more,
not that each letter wobbles on its own.

### 5. Generating new instances

![Originals, generated, naive jitter](out/fig_synthesis.png)

- **Top row: the originals.**
- **Middle row: generated words.** Each is sampled from the measured averages, plus a
  shared size and slant per word, plus small per-letter residuals, and drawn with the
  page's nib.
- **Bottom row: the naive alternative.** The same average shape with independent
  random jitter on every point, at the same amount of positional spread (3.3 px). It
  produces kinked shafts no reed would draw.

The middle row stays inside the scribe's range and keeps the straight, confident
shafts. Vector versions are in `out/allah_mean.svg` and `out/allah_variants.svg`.

## Limits of this check

- **Resolution.** At 1024 px a stroke is about 5.5 px wide, so nib shape, stroke ends
  (the reed's cut) and ink pooling can't be measured. The model draws round ends; the
  originals look blunter. The full-resolution Gallica scan (blocked from this
  environment) would fix this. The pipeline doesn't depend on the scale.
- **Sample size.** 7–10 values per feature are enough to show structure, but not to
  pin down correlations precisely. Two hints in the data need more pages before they
  count as findings:
  - The line-end word (K) is the smallest.
  - The word continuing a line-split (F) has the tallest first lām.
- **One word, one template.** The stroke plan for الله was written by hand. The hā'
  loop is a generic teardrop, and the alif-to-lām joins are simplified. Other letters
  need their own plans, and a single connector model is needed for joining.
- **Ink texture is not modelled.** Ink-cycle fading and edge roughness are not part of
  the model. They are a separate rendering layer and were deliberately left out here.

## Exclusions (from the flags in `data/traces_allah.json`)

- **H (line 13):** its lām² and alif run into the line above, so heights can't be
  separated at this resolution. It is shown in the fit figure but left out of all
  statistics.
- **J (بالله):** the alif is joined to the preceding bā', which is a different letter
  form. It is left out of the alif statistics.
- **G (لله ما):** the hā' touches the next letter. It is left out of the hā'
  statistics.
- **F, G:** these have no alif of their own.

## Next steps this supports

1. **More data.** Trace the remaining folios of Arabe 328 with `tools/tracer` to get
   n ≈ 50–100 per letter, ideally at full resolution.
2. **Joining.** Add stroke plans for the other letter forms and one connector model,
   then render a whole line from Unicode text.
3. **Line context.** Add the line-level layer: spacing between connected letter groups,
   stretched joins and line breaks. Then test whether position in the line explains
   the leftover variation.

## Source

The page image is from Gallica: Source gallica.bnf.fr / Bibliothèque nationale de
France, Département des Manuscrits, Arabe 328. Gallica permits free non-commercial
reuse with this attribution. Check the BnF terms before any commercial use.
