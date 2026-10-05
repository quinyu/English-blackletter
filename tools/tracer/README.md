# Ductus Tracer

A browser tool for tracing letters on manuscript scans, stroke by stroke. The traces
are saved as JSON for the measurement scripts in `viability/`. The menu at the top
switches between three manuscripts:

| Manuscript | Mode | Output format |
|---|---|---|
| BnF Arabe 328 (Hijazi) | Word template for الله: alif, two lāms, hā', baseline | `viability/data/traces_allah.json` |
| Lucretius, *De rerum natura* I (humanist cursive) | Any letter, any number of strokes, guided by the reading | `ductus-traces/2`, as in `viability/data/traces_lucretius.json` |
| Chig. L.VIII.305, Guinizzelli (Gothic textualis) | Same as Lucretius | `ductus-traces/2`, as in `viability/data/traces_chigi.json` |

## Run it

```sh
# from the repository root
python3 -m http.server 8000
# open http://localhost:8000/tools/tracer/            (add #lucretius or #chigi to open a Latin page)
```

If you open `index.html` directly as a file instead, the browser blocks pixel access,
so the ink overlay and ink-following won't work. In that case:

- use **Open image…** to load the scan, and
- use **Import traces…** to load existing traces.

## Tracing Latin letters

1. **Pick a letter in the Reading panel.** The page zooms to that line, and the line's
   guides (baseline and x-height line, found by `viability/latin_lines.py`) are
   highlighted.
2. **Trace each stroke in writing order.**
   - Click where the pen starts, then where the stroke turns, then where it ends.
   - Between your clicks the path follows the middle of the ink (*Follow ink*), so a
     few clicks are enough even on 14 px letters.
   - Press **Enter** (or double-click) to finish a stroke.
3. **Use the suggested strokes as a guide.** The tool suggests strokes for each letter
   (n = minim, then arch and minim). Use **Skip** when the scribe made two of them in
   one movement, and **Add stroke** when there are more.
4. **Carry on with the next letter.** When a letter is done, the next letter of the
   reading is selected automatically. Traced letters turn green.
5. **Trace abbreviation signs with Other letter…** Use it for signs the reading doesn't
   contain, such as ꝑ or q;. Grey text in [brackets] was added by the editor and isn't
   on the page, so it can't be traced.

Each stroke is stored with its clicks and its centre-line, in the order and direction
the pen moved. That direction is what lets `measure_letters.py` tell upstrokes from
downstrokes.

## Features

- **Ink overlay.** Shows what counts as ink. Parchment, stains and show-through are
  removed by comparing each pixel with the local parchment brightness. The contrast
  slider sets the threshold.
- **Follow ink.**
  - Arabic shafts snap onto the stroke after their second point.
  - Latin strokes follow the ink between clicks.
  - Both use the same ideas as `viability/measure.py` and `viability/inkpath.py`.
- **Quick measurements.**
  - Arabic words: heights, slants and spacings in pixels.
  - Latin letters: width, rise above the baseline and slant, in x-heights, with
    averages per letter.
- **Export.** Copies the traces as JSON (and downloads them, when the page runs on its
  own). Your work is also kept in the browser's local storage, separately for each
  manuscript.
