# Ductus Tracer

A browser tool for tracing letters on manuscript scans. You click roughly where each
stroke starts and ends, and the tool snaps the stroke onto the ink. The traces are saved
as JSON for `viability/measure.py`.

It currently traces the word الله:

1. top and foot of the alif (press **S** to skip it for words without one)
2. top and foot of the first lām
3. top and foot of the second lām
4. start and left end of the final hā'
5. the baseline (set automatically from the hā' clicks; drag to adjust)

## Run it

```sh
# from the repository root
python3 -m http.server 8000
# open http://localhost:8000/tools/tracer/
```

Served this way, it opens with the BnF Arabe 328 page and the 11 traced instances from
`viability/data/traces_allah.json`.

If you open `index.html` directly as a file instead, the browser blocks pixel access,
so the ink overlay and snapping won't work. In that case:

- use **Open image…** to load the scan, and
- use **Import traces…** to load existing traces.

## Features

- **Ink overlay.** Shows what counts as ink. Parchment, stains and show-through are
  removed by comparing each pixel with the local parchment brightness. The contrast
  slider sets the threshold.
- **Snap to ink.** After you place the second point of a shaft, the tool slides and
  turns the segment slightly so it runs along the stroke. `measure.py` uses the same
  idea.
- **Quick measurements.** Heights, slants and spacings straight from your clicks, for
  the selected word and for all words. The ink-fitted values come from `measure.py`.
- **Export.** Copies the traces as JSON (and downloads them, when the page runs on its
  own). Your work is also kept in the browser's local storage.
