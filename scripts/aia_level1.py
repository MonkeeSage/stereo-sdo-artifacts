"""Compare the SDO/AIA browse artifacts with Level-1 data and spikes files.

Usage: .venv/bin/python -I scripts/aia_level1.py data/aia images/level1

For each artifact this script:
  * loads the Level-1 image and its spikes file, and "respikes" a copy by
    putting back the original values the ground despiking replaced;
  * finds the hit near its browse-image position;
  * reports how much of the hit despiking removed, the trail asymmetry,
    and whether ordinary isolated spikes are visible in the browse JPEG
    (i.e. whether it was made from despiked data);
  * writes a 1200x600 figure: Level-1 as distributed | respiked.
For A2 it also measures the same region in the frames 12 s before/after.

Spikes files hold a 3xN array: flat pixel index into the Level-1 array
(0-based, FITS row order), the original value, and the despiked value.
"""
import sys
from pathlib import Path

import numpy as np
from astropy.io import fits
from PIL import Image

ORIG = Path("images/originals")

# id, record number, browse file, colour channel, browse head (x, y), crop size
ARTIFACTS = [
    ("A2", 78809622, "20130224_230140_4096_0335.jpg", 2, (3964, 910), 600),
    ("A3", 157692406, "20170620_125617_4096_0193.jpg", 0, (32, 1265), 100),
    ("A4a", 194794212, "20190628_140035_4096_304211171.jpg", 0, (148, 778), 150),
    ("A4b", 194794212, "20190628_140035_4096_304211171.jpg", 0, (58, 3665), 100),
]
A2_NEIGHBOURS = [78809615, 78809629]
SEARCH = 60


def load(data, rec):
    """Return (despiked, respiked, spike mask, header), all top-down."""
    stem = f"{data}/aia.lev1_euv_12s.{rec}"
    with fits.open(f"{stem}.image_lev1.fits") as h:
        img, hdr = h[1].data.astype(float), h[1].header
    sp = fits.getdata(f"{stem}.spikes.fits", 1)
    idx = sp[0].astype(np.int64)
    raw = img.copy().ravel()
    raw[idx] = sp[1]
    mask = np.zeros(img.size, bool)
    mask[idx] = True
    shape = img.shape
    return (img[::-1], raw.reshape(shape)[::-1],
            mask.reshape(shape)[::-1], hdr)


def head(img, x, y):
    win = img[y - SEARCH:y + SEARCH, max(0, x - SEARCH):x + SEARCH]
    dy, dx = np.unravel_index(np.argmax(win), win.shape)
    return max(0, x - SEARCH) + dx, y - SEARCH + dy


def trail(img, x, y, length=50, gap=8):
    """Mean background-subtracted signal above/below the head column."""
    def strip(r0, r1):
        s = img[r0:r1, max(0, x - 4):x + 5].max(axis=1)
        bg = np.median(img[r0:r1, x + 20:x + 40])
        return np.clip(s - bg, 0, None).mean()
    return strip(y - gap - length, y - gap), strip(y + gap, y + gap + length)


def trail_falloff(img, x, y, sign, maxlen=800):
    """Distances (px) from the head, in direction `sign` (+1 down, -1 up),
    at which the trail's column excess (10-px running mean) first falls
    below 50% and 10% of its value just past the head."""
    rows = np.arange(y + sign * 8, y + sign * maxlen, sign)
    rows = rows[(rows >= 0) & (rows < img.shape[0])]
    strip = img[rows]
    # Trail column(s): brightest columns near the head over the first rows.
    lo = max(0, x - 4)
    near = strip[:30, lo:x + 5].mean(axis=0)
    cols = lo + np.argsort(near)[-2:]
    s = strip[:, cols].mean(axis=1)
    # Reference: the mean of two fixed columns 25 px away, so noise and the
    # coronal gradient affect both alike.
    rx = x + 25 if x + 27 < img.shape[1] else x - 27
    ref = strip[:, rx:rx + 2].mean(axis=1)
    run = np.convolve(s - ref, np.ones(10) / 10, "valid")
    start = run[0]

    def first_below(level):
        k = np.nonzero(run < level * start)[0]
        return int(k[0]) + 8 if len(k) else None

    return first_below(0.5), first_below(0.1)


def browse_spike_test(jpg, raw, lev1, mask, hx, hy, dx, dy, r=300):
    """Fraction of isolated spikes near the hit that are visible in the
    browse JPEG (>20 levels above their 5x5 median), at the best local
    alignment within +-6 px, plus the median over the search grid as a
    chance baseline."""
    y0, x0 = max(0, hy - r), max(0, hx - r)
    ys, xs = np.nonzero(mask[y0:hy + r, x0:hx + r])
    ys, xs = ys + y0, xs + x0
    keep = ((np.hypot(xs - hx, ys - hy) > 60)
            & (raw[ys, xs] - lev1[ys, xs] > 100)
            & (xs - dx > 10) & (xs - dx < 4086)
            & (ys - dy > 10) & (ys - dy < 4086))
    ys, xs = ys[keep], xs[keep]

    def frac(sx, sy):
        on = jpg[ys - sy, xs - sx]
        off = np.array([np.median(jpg[y - sy - 2:y - sy + 3,
                                      x - sx - 2:x - sx + 3])
                        for y, x in zip(ys, xs)])
        return np.mean(on - off > 20)

    grid = [frac(sx, sy) for sy in range(dy - 6, dy + 7)
            for sx in range(dx - 6, dx + 7)]
    return len(ys), max(grid), float(np.median(grid))


def stretch(cut, lo, hi):
    v = np.log10(np.clip(cut - lo, 1, None)) / np.log10(hi - lo)
    return (np.clip(v, 0, 1) * 255).astype(np.uint8)


def main(data, outdir):
    out = Path(outdir)
    out.mkdir(parents=True, exist_ok=True)
    for name, rec, browse, ch, (bx, by), size in ARTIFACTS:
        lev1, raw, mask, hdr = load(data, rec)
        hx, hy = head(raw, bx, by)
        dx, dy = hx - bx, hy - by
        # Same crop box as the browse crop, shifted into Level-1 pixels.
        x0 = min(max(0, bx - size // 2 + dx), 4096 - size)
        y0 = min(max(0, by - size // 4 + dy), 4096 - size)
        box = np.s_[y0:y0 + size, x0:x0 + size]
        bg = np.median(lev1[box])
        hit = raw[box] > bg + 10 * max(1.0, np.std(lev1[box][lev1[box] < bg + 20]))
        excess_raw = np.clip(raw[box] - bg, 0, None)[hit].sum()
        excess_l1 = np.clip(lev1[box] - bg, 0, None)[hit].sum()
        up, down = trail(raw, hx, hy)
        up1, down1 = trail(lev1, hx, hy)

        jpg = np.asarray(Image.open(ORIG / browse).convert("RGB"))[..., ch]
        n_sp, vis, base = browse_spike_test(jpg.astype(float), raw, lev1,
                                            mask, hx, hy, dx, dy)
        my, mx = np.unravel_index(np.argmax(lev1), lev1.shape)

        print(f"== {name}  {hdr['T_OBS']}  {hdr['WAVELNTH']} A  "
              f"exptime {hdr['EXPTIME']:.2f} s  NSPIKES {hdr['NSPIKES']}")
        print(f"  frame maximum after despiking: {lev1.max():.0f} DN at "
              f"top-down ({mx},{my})")
        print(f"  head: browse ({bx},{by}) -> Level-1 top-down ({hx},{hy}), "
              f"offset ({dx},{dy})")
        print(f"  head value: original {raw[hy, hx]:.0f} DN, "
              f"after despike {lev1[hy, hx]:.0f} DN; box median {bg:.1f} DN")
        print(f"  hit pixels: {hit.sum()}, flagged as spikes: "
              f"{(hit & mask[box]).sum()}; excess flux removed by despiking: "
              f"{100 * (1 - excess_l1 / excess_raw):.0f}%")
        print(f"  trail 50 px above/below head: respiked {up:.1f}/{down:.1f}"
              f" DN, despiked {up1:.1f}/{down1:.1f} DN")
        sign = 1 if down > up else -1
        half, tenth = trail_falloff(raw, hx, hy, sign)
        print(f"  trail runs {'down' if sign > 0 else 'up'}; respiked "
              f"brightness falls to 50% by {half} px and 10% by {tenth} px")
        print(f"  browse shows {100 * vis:.0f}% of {n_sp} isolated spikes "
              f"nearby (chance baseline {100 * base:.0f}%)")

        hi = max(raw[hy, hx], bg + 50)
        panels = [stretch(c, bg - 5, hi) for c in (lev1[box], raw[box])]
        tiles = [Image.fromarray(p).resize((600, 600), Image.NEAREST)
                 for p in panels]
        fig = Image.new("L", (1210, 600), 255)
        fig.paste(tiles[0], (0, 0))
        fig.paste(tiles[1], (610, 0))
        fig.save(out / f"{name}_level1_vs_respiked.png")
        print(f"  crop box (Level-1 top-down): ({x0},{y0}) {size}x{size}")

        if name == "A2":
            for nrec in A2_NEIGHBOURS:
                n1, nraw, nmask, nh = load(data, nrec)
                win = nraw[hy - 20:hy + 20, hx - 20:hx + 20]
                print(f"  neighbour {nh['T_OBS']}: max original value in 40x40 "
                      f"around head {win.max():.0f} DN "
                      f"(median {np.median(win):.1f}); DATAMAX {nh['DATAMAX']}")


if __name__ == "__main__":
    main(*sys.argv[1:3])
