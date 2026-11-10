"""Inspect the STEREO/EUVI Level-0 frame behind artifact A1.

Usage: .venv/bin/python -I scripts/euvi_level0.py data/stereo/<file>.fts images/level0

Prints the header keywords relevant to on-board processing, locates the
particle hit as the strongest local outlier near the browse-image position,
and writes a 600x600 log-stretched cutout (nearest-neighbour, 8x).
"""
import sys
from pathlib import Path

import numpy as np
from astropy.io import fits
from PIL import Image

KEYS = ["DATE-OBS", "EXPTIME", "WAVELNTH", "COSMICS", "COMPFACT",
        "IP_PROG0", "IP_PROG1", "IP_PROG2", "IP_PROG3", "BIASMEAN", "CROTA"]
SEARCH = (1900, 1100, 2048, 1300)   # x0, y0, x1, y1 in top-down raw pixels
HALF = 37                           # 75x75 cutout


def main(path, outdir):
    with fits.open(path) as hdul:
        hdr = hdul[0].header
        # Row 0 is the bottom of the image in FITS; flip to top-down.
        img = hdul[0].data.astype(float)[::-1]

    for k in KEYS:
        print(f"{k:9} = {hdr.get(k)!s:<26} / {hdr.comments[k]}")

    x0, y0, x1, y1 = SEARCH
    region = img[y0:y1, x0:x1]
    y, x = np.unravel_index(np.argmax(region), region.shape)
    y, x = y + y0, x + x0
    print(f"\nframe max {img.max():.0f} DN, median {np.median(img):.0f} DN")
    print(f"hit peak at raw top-down (x={x}, y={y}): {img[y, x]:.0f} DN")
    sat = np.argwhere(img >= img.max() - 10)
    print(f"pixels within 10 DN of frame max: {len(sat)} at "
          + ", ".join(f"({c},{r})" for r, c in sat))

    cut = img[y - HALF:y + HALF + 1, x - HALF:x + HALF + 1]
    bias = hdr.get("BIASMEAN", 0)
    v = np.log10(np.clip(cut - bias, 1, None))
    v = (v - v.min()) / (v.max() - v.min()) * 255
    out = Path(outdir)
    out.mkdir(parents=True, exist_ok=True)
    Image.fromarray(v.astype(np.uint8)).resize((600, 600), Image.NEAREST) \
        .save(out / "A1_euvi195_level0.png")
    print(f"cutout origin (top-down raw): ({x - HALF}, {y - HALF})")


if __name__ == "__main__":
    main(*sys.argv[1:3])
