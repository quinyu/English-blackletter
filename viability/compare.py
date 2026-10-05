"""The three hands side by side: pen behaviour, measured the same way on each page.

Stroke width is measured as ink mass across the stroke (nib.mass_width_samples) on
each page's text block and divided by that page's median, so the curves compare the
*shape* of thick/thin against direction, independent of scan resolution.

Run:  python3 compare.py      → out/compare_hands.png, out/compare_hands.json
"""
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

import ink
import nib

HERE = Path(__file__).resolve().parent
OUT = HERE / "out"
SURFACE, INK_TEXT, MUTED, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#ecebe8"
HANDS = [
    # name, image, text block (y0, y1, x0, x1), regions to blank, drop red ink, colour
    ("Hijazi reed — BnF Arabe 328", "bnf-arabe328-baqarah-282-286.jpg", (90, 1240, 60, 1000), [], False, "#2a78d6"),
    ("Humanist cursive — Lucretius", "lucretius-drn-1r.jpg", (200, 1570, 140, 900), [], False, "#eb6834"),
    ("Gothic textualis — Chig. L.VIII.305", "chigi-L-VIII-305-f1r.webp", (96, 711, 0, 836), [(0, 0, 263, 362)], True, "#1baf7a"),
]


def measure(image, block, blank, drop_red):
    rgb = ink.load_rgb(HERE / "data" / image)
    mask, dark = ink.ink_mask(rgb)
    if drop_red:
        mask = (mask > 0) & ~ink.red_mask(rgb, mask)
    m = np.zeros_like(mask, dtype=np.uint8)
    y0, y1, x0, x1 = block
    m[y0:y1, x0:x1] = mask[y0:y1, x0:x1]
    for a, b, c, d in blank:
        m[b:d, a:c] = 0
    dirs, widths = nib.mass_width_samples(m, dark)
    fit = nib.fit_nib(dirs, widths)
    return fit, dirs, widths


def main():
    OUT.mkdir(exist_ok=True)
    fig, ax = plt.subplots(figsize=(8.2, 4.2), dpi=160, facecolor=SURFACE)
    ax.set_facecolor(SURFACE)
    summary = {}
    phi = np.linspace(0, 180, 361)
    for name, image, block, blank, drop_red, col in HANDS:
        fit, dirs, widths = measure(image, block, blank, drop_red)
        c = np.array(fit["bins"]["centre_deg"]); med = np.array(fit["bins"]["median_width"])
        norm = float(np.median(widths))
        ax.plot(c, med / norm, "o", color=col, ms=4.5, mec=SURFACE, mew=1.2)
        curve = nib.nib_model(phi, fit["a"], fit["b"], fit["theta_deg"]) / norm
        ax.plot(phi, curve, color=col, lw=2, label=f"{name}  ·  contrast {fit['contrast']:.2f}")
        summary[name] = {"contrast": fit["contrast"], "thin_direction_deg": fit["theta_deg"],
                         "fit_rms_relative": fit["rms_px"] / norm, "n_samples": int(len(dirs))}
        print(f"{name:40s} contrast {fit['contrast']:.2f}  thinnest at {fit['theta_deg']:.0f} deg  rms {fit['rms_px'] / norm:.3f}")
    ax.legend(frameon=False, fontsize=8, loc="upper left", labelcolor=INK_TEXT)
    ax.set_xlim(0, 180); ax.set_ylim(0, 1.9)
    ax.set_xticks([0, 45, 90, 135, 180])
    ax.set_xticklabels(["0°\n→ / ←", "45°\n↗ / ↙", "90°\n↑ / ↓", "135°\n↖ / ↘", "180°"])
    ax.set_xlabel("stroke direction", color=MUTED, fontsize=8)
    ax.set_ylabel("stroke width ÷ page median", color=MUTED, fontsize=8)
    ax.set_title("Thick and thin by stroke direction, three hands measured the same way",
                 fontsize=10, color=INK_TEXT, loc="left")
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color("#c9c8c3")
    ax.tick_params(colors=MUTED, labelsize=8)
    ax.grid(axis="y", color=GRID, lw=0.8)
    fig.tight_layout()
    fig.savefig(OUT / "compare_hands.png", facecolor=SURFACE)
    plt.close(fig)
    (OUT / "compare_hands.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
