#!/usr/bin/env python3
"""
Crop full-desktop captures down to the browser viewport.

A full-screen grab of a multi-monitor desktop buries the app in taskbars,
other windows and personal bookmarks. This crops each image to one rectangle
and rewrites it in place.

    python3 crop-captures.py --box 1604,168,2828,866 states/V15_row-cap-3000-rows.png
    python3 crop-captures.py --box 1604,168,2828,866 --all

The box that fitted the 3200x900 dual-1600x900 desktop used on 2026-09-23 was
1604,168,2828,866 -> 1224x698, i.e. the SAS viewport with Chrome's tab strip,
bookmarks bar, Windows taskbar and the second monitor all removed. Re-measure
it for any other display arrangement: open one capture, note the pixel corners
of the app area, pass them as left,top,right,bottom.
"""
import argparse, glob, os, sys

try:
    from PIL import Image
except ImportError:
    sys.exit("Pillow is required:  pip install pillow")

HERE = os.path.dirname(os.path.abspath(__file__))

ap = argparse.ArgumentParser()
ap.add_argument("files", nargs="*")
ap.add_argument("--box", required=True, help="left,top,right,bottom in pixels")
ap.add_argument("--all", action="store_true", help="every V*.png under this tree")
ap.add_argument("--suffix", default="", help="write alongside with this suffix instead of in place")
a = ap.parse_args()

box = tuple(int(v) for v in a.box.split(","))
if len(box) != 4:
    sys.exit("--box needs four numbers: left,top,right,bottom")

targets = a.files or (sorted(glob.glob(os.path.join(HERE, "*", "V*.png"))) if a.all else [])
if not targets:
    sys.exit("Nothing to do — pass file paths or --all")

for p in targets:
    p = p if os.path.isabs(p) else os.path.join(HERE, p)
    im = Image.open(p).convert("RGB")
    if box[2] > im.width or box[3] > im.height:
        print("SKIP %s — %dx%d is smaller than the box" % (os.path.basename(p), im.width, im.height))
        continue
    out = im.crop(box)
    dest = p if not a.suffix else p.replace(".png", a.suffix + ".png")
    out.save(dest, optimize=True)
    print("%-44s %dx%d -> %dx%d  %d bytes"
          % (os.path.relpath(dest, HERE), im.width, im.height, out.width, out.height, os.path.getsize(dest)))
