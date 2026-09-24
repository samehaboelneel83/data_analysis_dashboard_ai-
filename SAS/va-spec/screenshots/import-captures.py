#!/usr/bin/env python3
"""
Import a timed screenshot run into the va-spec screenshots/ tree.

Your capture program wrote one PNG every ~3 seconds. Claude held each screen
still for ~11 seconds inside a known window (see captures.json). This script
matches each file's timestamp to a window and files it as V<nn>_<slug>.png in
the right subfolder.

    python3 import-captures.py /path/to/your/captures            # dry run
    python3 import-captures.py /path/to/your/captures --apply    # do it

Options
    --apply       actually copy (default is a dry run that changes nothing)
    --move        move instead of copy
    --all         keep every frame in a window as V<nn>_<slug>_1.png, _2.png …
                  (default keeps the single sharpest-looking frame: the middle one)
    --date        capture date, YYYY-MM-DD (default: from captures.json)
    --offset N    shift every window by N seconds if your clock ran ahead/behind
    --use-name    read the time from the FILENAME instead of the file mtime,
                  for programs that stamp names like shot_2026-09-23_11-56-58.png
"""
import argparse, json, os, re, shutil, sys
from datetime import datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))

def parse_hhmmss(s):
    h, m, sec = (int(x) for x in s.split(":"))
    return timedelta(hours=h, minutes=m, seconds=sec)

TIME_IN_NAME = re.compile(r"(\d{4})[-_]?(\d{2})[-_]?(\d{2})[ _T-]+(\d{2})[-_:]?(\d{2})[-_:]?(\d{2})")

def file_time(path, use_name):
    if use_name:
        m = TIME_IN_NAME.search(os.path.basename(path))
        if m:
            y, mo, d, h, mi, s = (int(g) for g in m.groups())
            return datetime(y, mo, d, h, mi, s)
        return None
    return datetime.fromtimestamp(os.path.getmtime(path))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("source", help="folder holding your captured PNGs")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--move", action="store_true")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--date")
    ap.add_argument("--offset", type=int, default=0)
    ap.add_argument("--use-name", action="store_true")
    a = ap.parse_args()

    index = json.load(open(os.path.join(HERE, "captures.json")))
    day = datetime.strptime(a.date or index["date"], "%Y-%m-%d")

    windows = []
    for shot in index["shots"]:
        hold = shot.get("hold")
        if not hold or hold in ("manual", "supplied"):
            continue
        start_s, end_s = hold.split("-")
        start = day + parse_hhmmss(start_s) + timedelta(seconds=a.offset)
        end   = day + parse_hhmmss(end_s)   + timedelta(seconds=a.offset)
        windows.append((start, end, shot))

    files = []
    for name in sorted(os.listdir(a.source)):
        if not name.lower().endswith((".png", ".jpg", ".jpeg")):
            continue
        p = os.path.join(a.source, name)
        t = file_time(p, a.use_name)
        if t:
            files.append((t, p))
    if not files:
        sys.exit("No timestamped images found in %s" % a.source)

    print("%d images, %s -> %s\n" % (len(files), files[0][0], files[-1][0]))

    matched, planned = set(), []
    for start, end, shot in windows:
        hits = [p for t, p in files if start <= t <= end]
        if not hits:
            print("  MISS  %s  %s   (no frame in %s)" % (shot["id"], shot["slug"], shot["hold"]))
            continue
        chosen = hits if a.all else [hits[len(hits) // 2]]
        for i, src in enumerate(chosen, 1):
            suffix = "_%d" % i if a.all and len(chosen) > 1 else ""
            dest = os.path.join(HERE, shot["folder"], "%s_%s%s.png" % (shot["id"], shot["slug"], suffix))
            planned.append((src, dest))
            matched.add(src)
        print("  ok    %s  %s   (%d frame%s)" % (shot["id"], shot["slug"], len(hits), "" if len(hits) == 1 else "s"))

    leftover = [p for _, p in files if p not in matched]
    print("\n%d files to place, %d unmatched (gaps between holds - safe to ignore)"
          % (len(planned), len(leftover)))

    if not a.apply:
        print("\nDry run. Re-run with --apply to write them.")
        return
    for src, dest in planned:
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        (shutil.move if a.move else shutil.copy2)(src, dest)
    print("\nPlaced %d images. Manual shots (V01-V05, V13, V24) and V29 are not "
          "in the windows - drop those in by hand." % len(planned))

if __name__ == "__main__":
    main()
