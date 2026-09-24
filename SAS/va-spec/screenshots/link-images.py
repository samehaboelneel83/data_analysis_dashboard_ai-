#!/usr/bin/env python3
"""
Rewrite each MANIFEST.md's Images section from what is actually on disk, and
embed every image that is present so the markdown renders it.

    python3 link-images.py

Safe to re-run after every import: it regenerates the section from scratch.
"""
import json, os, re

HERE = os.path.dirname(os.path.abspath(__file__))
idx = json.load(open(os.path.join(HERE, "captures.json")))

by_folder = {}
for s in idx["shots"]:
    by_folder.setdefault(s["folder"], []).append(s)

total_present = 0
for folder, shots in sorted(by_folder.items()):
    path = os.path.join(HERE, folder, "MANIFEST.md")
    if not os.path.exists(path):
        continue
    text = open(path, encoding="utf-8").read()

    rows, embeds, present_n = [], [], 0
    for sh in sorted(shots, key=lambda x: x["id"]):
        fn = "%s_%s.png" % (sh["id"], sh["slug"])
        on_disk = os.path.exists(os.path.join(HERE, folder, fn))
        if on_disk:
            present_n += 1
            state = "yes"
            embeds.append("### %s — %s\n\n![%s %s](%s)\n"
                          % (sh["id"], sh["screen"], sh["id"], sh["screen"], fn))
        elif sh["status"] == "BLOCKED":
            state = "n/a — **BLOCKED**"
        else:
            state = "pending"
        rows.append("| %s | `%s` | %s | %s |" % (sh["id"], fn, state, sh["hold"] or "—"))

    total_present += present_n
    section = ["", "## Images", "",
               "**%d of %d present.**" % (present_n, len(shots)), "",
               "| ID | File | Present | Hold window (2026-09-23, EEST) |",
               "|---|---|---|---|"] + rows
    if embeds:
        section += ["", "## Captures", ""] + embeds
    block = "\n".join(section).rstrip() + "\n"

    text = re.sub(r"\n## Images\n.*$", "", text, flags=re.S)
    open(path, "w", encoding="utf-8").write(text.rstrip() + "\n" + block)
    print("%-14s %d/%d present" % (folder, present_n, len(shots)))

print("\ntotal images linked: %d" % total_present)
