"""Render ARCHITECTURE_COMPARISON.md into a standalone HTML page.

Usage:  python build_html.py     (run from anywhere; paths resolve from this file)
Requires: pip install markdown

Conversion is done by the `markdown` library so the prose stays byte-faithful to the
source document; everything this script adds is presentational: a design shell, status
classes derived from the status glyphs already in the tables, and scroll containers
around wide tables.
"""
import html
import re
from pathlib import Path

import markdown

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "ARCHITECTURE_COMPARISON.md"
OUT = ROOT / "ARCHITECTURE_COMPARISON.html"

body = markdown.markdown(
    SRC.read_text(encoding="utf-8"),
    extensions=["tables", "fenced_code", "attr_list", "sane_lists", "md_in_html"],
    output_format="html5",
)

# ── Status classes ─────────────────────────────────────────────────────────
# The source encodes status with glyphs. Turn each into a real class so the page can
# render state as form (a chip, a colour) and not only as a character.
STATUS = [
    ("🟢", "ok"), ("✅", "ok"),
    ("🟡", "warn"), ("⚠️", "warn"),
    ("🔴", "bad"), ("❌", "bad"),
    ("⚫", "none"),
]


def tag_cells(m):
    cell = m.group(0)
    for glyph, cls in STATUS:
        if glyph in cell:
            return cell.replace("<td>", f'<td class="s s-{cls}">', 1)
    return cell


body = re.sub(r"<td>.*?</td>", tag_cells, body, flags=re.S)

# Wide tables get their own horizontal scroll container so the page body never
# scrolls sideways.
body = body.replace("<table>", '<div class="tbl"><table>').replace("</table>", "</table></div>")

# ── Layer sections ─────────────────────────────────────────────────────────
# The eight layers are a real ordered sequence in the source architecture, so a
# numbered marker encodes something true rather than decorating.
def layer_heading(m):
    num, rest = m.group(1), m.group(2)
    return (
        f'<h1 class="layer" id="layer-{num}">'
        f'<span class="layer-num">L{num}</span>'
        f'<span class="layer-name">{rest}</span></h1>'
    )


body = re.sub(r"<h1>Layer (\d) — (.*?)</h1>", layer_heading, body)

# python-markdown leaves the MD table-cell pipe escape (\|) literal in the output.
body = body.replace("\\|", "|")

# The hero already carries the title and the same four metadata fields, so drop the
# document's own title and meta block rather than printing them twice.
body = re.sub(r"^\s*<h1>Architecture vs\. Implementation.*?</h1>", "", body, count=1, flags=re.S)
body = re.sub(r"^\s*<p><strong>Target document:.*?</p>", "", body, count=1, flags=re.S)
body = re.sub(r"^\s*<hr\s*/?>", "", body, count=1)

# ── Scorecard data (mirrors the Scorecard by layer table) ──────────────────
SCORE = [
    ("1", "Connectors &amp; Ingestion", 90, "ok", "Built"),
    ("2", "Storage &amp; Query Engine", 45, "warn", "Partial"),
    ("3", "Metadata &amp; Semantic", 30, "bad", "Mostly missing"),
    ("4", "AI Agent Orchestration", 5, "none", "Absent"),
    ("5", "Analysis &amp; Execution", 50, "warn", "Partial"),
    ("6", "Visualization &amp; Dashboards", 85, "ok", "Achieved"),
    ("7", "Publishing &amp; Sharing", 70, "ok", "Largely achieved"),
    ("8", "Platform Core", 65, "warn", "In-house"),
]

cards = "\n".join(
    f'''      <a class="card c-{cls}" href="#layer-{n}">
        <span class="card-n">L{n}</span>
        <span class="card-name">{name}</span>
        <span class="card-pct">{pct}<span class="card-pct-u">%</span></span>
        <span class="bar"><span class="bar-fill" style="width:{pct}%"></span></span>
        <span class="card-state">{state}</span>
      </a>'''
    for n, name, pct, cls, state in SCORE
)

SHELL = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="description" content="Layer-by-layer comparison of the specified AI Data Analytics Platform architecture against the Datalytics v2 codebase as built.">
<title>Architecture vs. Implementation</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans:wght@400;500;600;700&family=Source+Serif+4:opsz,wght@8..60,400;8..60,600&display=swap">
<style>
:root {{
  --ground:#f6f7f9; --surface:#ffffff; --surface-2:#eef1f5;
  --ink:#101822; --ink-2:#33404e; --muted:#5c6875;
  --rule:#e1e5ea; --rule-2:#cfd6de;
  --accent:#2d5ba8; --accent-soft:#e8eef8;
  --ok:#16785a; --warn:#a86c15; --bad:#b03a32; --none:#616c7a;
  --ok-bg:#e6f2ed; --warn-bg:#f8efdf; --bad-bg:#f8e9e7; --none-bg:#eceef1;
  --shadow:0 1px 2px rgba(16,24,34,.05), 0 8px 24px -12px rgba(16,24,34,.18);
  --sans:"IBM Plex Sans",-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
  --serif:"Source Serif 4",Georgia,"Times New Roman",serif;
  --mono:"IBM Plex Mono",ui-monospace,"SF Mono",Consolas,monospace;
  --measure:70ch;
}}
@media (prefers-color-scheme: dark) {{
  :root:not([data-theme="light"]) {{
    --ground:#0f141a; --surface:#161c24; --surface-2:#1d242e;
    --ink:#e6ebf1; --ink-2:#c2cbd6; --muted:#8e9aa8;
    --rule:#28313c; --rule-2:#38434f;
    --accent:#84a9e6; --accent-soft:#1b2634;
    --ok:#5cc39c; --warn:#dfae5e; --bad:#e58a80; --none:#8e9aa8;
    --ok-bg:#152720; --warn-bg:#2a2314; --bad-bg:#2b1a18; --none-bg:#1d242e;
    --shadow:0 1px 2px rgba(0,0,0,.4), 0 8px 24px -12px rgba(0,0,0,.6);
  }}
}}
:root[data-theme="dark"] {{
  --ground:#0f141a; --surface:#161c24; --surface-2:#1d242e;
  --ink:#e6ebf1; --ink-2:#c2cbd6; --muted:#8e9aa8;
  --rule:#28313c; --rule-2:#38434f;
  --accent:#84a9e6; --accent-soft:#1b2634;
  --ok:#5cc39c; --warn:#dfae5e; --bad:#e58a80; --none:#8e9aa8;
  --ok-bg:#152720; --warn-bg:#2a2314; --bad-bg:#2b1a18; --none-bg:#1d242e;
  --shadow:0 1px 2px rgba(0,0,0,.4), 0 8px 24px -12px rgba(0,0,0,.6);
}}

*,*::before,*::after {{ box-sizing:border-box; }}
body {{
  margin:0; background:var(--ground); color:var(--ink);
  font-family:var(--serif); font-size:17px; line-height:1.65;
  -webkit-font-smoothing:antialiased;
}}
:focus-visible {{ outline:2px solid var(--accent); outline-offset:3px; border-radius:2px; }}

/* ── Masthead ─────────────────────────────────────────── */
.bar-top {{
  position:sticky; top:0; z-index:20;
  display:flex; align-items:center; gap:.9rem; flex-wrap:wrap;
  padding:.6rem clamp(1rem,5vw,3rem);
  background:var(--surface);
  background:color-mix(in srgb, var(--surface) 88%, transparent);
  backdrop-filter:blur(10px);
  border-bottom:1px solid var(--rule);
  font-family:var(--mono); font-size:.7rem; letter-spacing:.06em;
  text-transform:uppercase; color:var(--muted);
}}
.bar-top b {{ color:var(--ink); font-weight:600; }}
.bar-top .vs {{ color:var(--accent); }}
.bar-top .spacer {{ flex:1 1 2rem; }}

header.hero {{
  padding:clamp(3rem,9vw,6rem) clamp(1rem,5vw,3rem) 2.5rem;
  border-bottom:1px solid var(--rule);
  background:linear-gradient(180deg, var(--surface) 0%, var(--ground) 100%);
}}
.wrap {{ max-width:var(--measure); margin-inline:auto; }}
.wrap-wide {{ max-width:1180px; margin-inline:auto; }}

.eyebrow {{
  font-family:var(--mono); font-size:.72rem; font-weight:500;
  letter-spacing:.16em; text-transform:uppercase; color:var(--accent);
  margin:0 0 1rem;
}}
h1.title {{
  font-family:var(--sans); font-weight:700; font-size:clamp(2.1rem,5.5vw,3.4rem);
  line-height:1.06; letter-spacing:-.025em; text-wrap:balance;
  margin:0 0 1.2rem; color:var(--ink);
}}
.standfirst {{
  font-size:1.14rem; color:var(--ink-2); margin:0 0 2rem; max-width:62ch;
}}
.meta {{
  display:grid; grid-template-columns:repeat(2,1fr);
  gap:1px; background:var(--rule); border:1px solid var(--rule);
  border-radius:3px; overflow:hidden; margin-top:2rem;
}}
.meta div {{ background:var(--surface); padding:.85rem 1rem; }}
.meta dt {{
  font-family:var(--mono); font-size:.66rem; letter-spacing:.13em;
  text-transform:uppercase; color:var(--muted); margin:0 0 .3rem;
}}
.meta dd {{ margin:0; font-family:var(--sans); font-weight:500; font-size:.92rem; }}

/* ── Scorecard ────────────────────────────────────────── */
.score {{ padding:clamp(2rem,5vw,3.5rem) clamp(1rem,5vw,3rem); border-bottom:1px solid var(--rule); }}
.score h2 {{
  font-family:var(--mono); font-size:.72rem; font-weight:500; letter-spacing:.16em;
  text-transform:uppercase; color:var(--muted); margin:0 0 1.4rem;
}}
.grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(230px,1fr)); gap:.7rem; }}
.card {{
  display:grid; grid-template-columns:auto 1fr auto; grid-template-rows:auto auto auto;
  gap:.15rem .6rem; align-items:center;
  padding:.9rem 1rem; text-decoration:none; color:inherit;
  background:var(--surface); border:1px solid var(--rule);
  border-left:3px solid var(--none); border-radius:3px;
  box-shadow:var(--shadow); transition:transform .14s ease, border-color .14s ease;
}}
.card:hover {{ transform:translateY(-2px); border-color:var(--rule-2); }}
.card-n {{
  font-family:var(--mono); font-size:.72rem; font-weight:600;
  letter-spacing:.06em; color:var(--muted);
}}
.card-name {{ font-family:var(--sans); font-weight:600; font-size:.9rem; line-height:1.25; }}
.card-pct {{
  grid-row:1; grid-column:3; justify-self:end; align-self:center;
  font-family:var(--mono); font-weight:600; font-size:1.5rem;
  font-variant-numeric:tabular-nums; letter-spacing:-.03em;
}}
.card-pct-u {{ font-size:.75rem; opacity:.55; margin-left:1px; }}
.bar {{
  grid-column:1/-1; height:3px; border-radius:2px;
  background:var(--surface-2); overflow:hidden; margin-top:.5rem;
}}
.bar-fill {{ display:block; height:100%; border-radius:2px; }}
.card-state {{
  grid-column:1/-1; font-family:var(--mono); font-size:.66rem;
  letter-spacing:.11em; text-transform:uppercase; margin-top:.35rem;
}}
.c-ok    {{ border-left-color:var(--ok); }}   .c-ok .card-pct,   .c-ok .card-state   {{ color:var(--ok); }}
.c-warn  {{ border-left-color:var(--warn); }} .c-warn .card-pct, .c-warn .card-state {{ color:var(--warn); }}
.c-bad   {{ border-left-color:var(--bad); }}  .c-bad .card-pct,  .c-bad .card-state  {{ color:var(--bad); }}
.c-none  {{ border-left-color:var(--none); }} .c-none .card-pct, .c-none .card-state {{ color:var(--none); }}
.c-ok .bar-fill   {{ background:var(--ok); }}
.c-warn .bar-fill {{ background:var(--warn); }}
.c-bad .bar-fill  {{ background:var(--bad); }}
.c-none .bar-fill {{ background:var(--none); }}

/* ── Document body ────────────────────────────────────── */
main {{ padding:clamp(2rem,6vw,4.5rem) clamp(1rem,5vw,3rem) 6rem; }}
main > * {{ max-width:var(--measure); margin-inline:auto; }}

h1.layer {{
  display:flex; align-items:baseline; gap:.85rem; flex-wrap:wrap;
  max-width:var(--measure); margin:4.5rem auto 1.6rem; padding-top:2rem;
  border-top:2px solid var(--ink);
  font-family:var(--sans); font-weight:700; font-size:clamp(1.6rem,3.6vw,2.25rem);
  letter-spacing:-.02em; line-height:1.12; text-wrap:balance;
}}
h1.layer:first-of-type {{ margin-top:1rem; }}
.layer-num {{
  font-family:var(--mono); font-size:.8rem; font-weight:600; letter-spacing:.1em;
  color:var(--surface); background:var(--accent);
  padding:.2rem .5rem; border-radius:3px; transform:translateY(-.28em);
}}
main > h1:not(.layer) {{
  font-family:var(--sans); font-weight:700; font-size:clamp(1.6rem,3.6vw,2.25rem);
  letter-spacing:-.02em; line-height:1.14; text-wrap:balance;
  margin:4.5rem auto 1.6rem; padding-top:2rem; border-top:2px solid var(--ink);
}}
main h2 {{
  font-family:var(--sans); font-weight:600; font-size:1.32rem; letter-spacing:-.012em;
  line-height:1.25; text-wrap:balance; margin:2.8rem auto .9rem;
}}
main h3 {{
  font-family:var(--mono); font-weight:600; font-size:.78rem;
  letter-spacing:.13em; text-transform:uppercase; color:var(--muted);
  margin:2.2rem auto .8rem;
}}
main p {{ margin:0 auto 1.15rem; }}
main ul, main ol {{ margin:0 auto 1.3rem; padding-left:1.35rem; }}
main li {{ margin-bottom:.42rem; }}
main li::marker {{ color:var(--muted); }}
strong {{ font-weight:600; color:var(--ink); }}
a {{ color:var(--accent); text-decoration:underline; text-decoration-thickness:1px; text-underline-offset:2px; }}
a:hover {{ text-decoration-thickness:2px; }}
hr {{
  max-width:var(--measure); margin:3rem auto; border:0;
  border-top:1px solid var(--rule);
}}
blockquote {{
  margin:1.6rem auto; padding:1rem 1.2rem;
  background:var(--accent-soft); border-left:3px solid var(--accent);
  border-radius:0 3px 3px 0; color:var(--ink-2);
}}
blockquote p:last-child {{ margin-bottom:0; }}
code {{
  font-family:var(--mono); font-size:.85em;
  background:var(--surface-2); padding:.12em .38em;
  border-radius:3px; color:var(--ink);
}}
pre {{
  max-width:var(--measure); margin:1.5rem auto; padding:1rem 1.15rem;
  background:var(--surface); border:1px solid var(--rule); border-radius:3px;
  overflow-x:auto; font-size:.85rem; line-height:1.55;
}}
pre code {{ background:none; padding:0; }}

/* ── Tables ───────────────────────────────────────────── */
.tbl {{
  max-width:1180px; margin:1.7rem auto 2.2rem;
  overflow-x:auto; border:1px solid var(--rule); border-radius:3px;
  background:var(--surface); box-shadow:var(--shadow);
}}
table {{ border-collapse:collapse; width:100%; font-family:var(--sans); font-size:.87rem; }}
thead th {{
  background:var(--surface-2); color:var(--ink);
  font-family:var(--mono); font-weight:600; font-size:.68rem;
  letter-spacing:.11em; text-transform:uppercase;
  text-align:left; padding:.7rem .85rem; white-space:nowrap;
  border-bottom:1px solid var(--rule-2);
}}
tbody td {{
  padding:.7rem .85rem; border-bottom:1px solid var(--rule);
  vertical-align:top; line-height:1.5; color:var(--ink-2);
  font-variant-numeric:tabular-nums;
}}
tbody tr:last-child td {{ border-bottom:0; }}
tbody tr:hover td {{ background:var(--surface-2); }}
td:first-child {{ color:var(--ink); }}
td code {{ font-size:.82em; white-space:nowrap; }}
.s {{ font-weight:600; }}
.s-ok   {{ color:var(--ok);   box-shadow:inset 3px 0 0 var(--ok);   background:var(--ok-bg); }}
.s-warn {{ color:var(--warn); box-shadow:inset 3px 0 0 var(--warn); background:var(--warn-bg); }}
.s-bad  {{ color:var(--bad);  box-shadow:inset 3px 0 0 var(--bad);  background:var(--bad-bg); }}
.s-none {{ color:var(--none); box-shadow:inset 3px 0 0 var(--none); background:var(--none-bg); }}
tbody tr:hover .s-ok   {{ background:var(--ok-bg); }}
tbody tr:hover .s-warn {{ background:var(--warn-bg); }}
tbody tr:hover .s-bad  {{ background:var(--bad-bg); }}
tbody tr:hover .s-none {{ background:var(--none-bg); }}

footer {{
  padding:2.5rem clamp(1rem,5vw,3rem) 4rem; border-top:1px solid var(--rule);
  font-family:var(--mono); font-size:.7rem; letter-spacing:.08em;
  text-transform:uppercase; color:var(--muted); text-align:center;
}}

@media (prefers-reduced-motion: reduce) {{
  * {{ animation:none !important; transition:none !important; }}
}}
@media (max-width:640px) {{
  body {{ font-size:16px; }}
  .bar-top {{ font-size:.62rem; gap:.5rem; }}
}}
</style>
</head>
<body>

<div class="bar-top">
  <span><b>ARCHITECTURE.md</b></span>
  <span class="vs">vs</span>
  <span><b>data_analytics</b></span>
  <span class="spacer"></span>
  <span>Alignment <b>~55%</b></span>
  <span>2026-08-24</span>
</div>

<header class="hero">
  <div class="wrap">
    <p class="eyebrow">Architecture audit</p>
    <h1 class="title">Architecture vs. Implementation</h1>
    <p class="standfirst">A layer-by-layer comparison of the specified AI Data Analytics
    Platform against the Datalytics v2 codebase as built — what was achieved, what is
    missing, and what was deliberately done differently. Re-scored after the Layer&nbsp;1
    build.</p>
    <dl class="meta">
      <div><dt>Target document</dt><dd><a href="ARCHITECTURE.md">ARCHITECTURE.md</a> — 8 layers</dd></div>
      <div><dt>Implementation</dt><dd><a href="data_analytics/">data_analytics/</a> — FastAPI · React · PostgreSQL</dd></div>
      <div><dt>Overall alignment</dt><dd>~55% — Layer 1 now built</dd></div>
      <div><dt>Compared on</dt><dd>2026-08-24</dd></div>
    </dl>
  </div>
</header>

<section class="score">
  <div class="wrap-wide">
    <h2>Coverage by layer</h2>
    <div class="grid">
{cards}
    </div>
  </div>
</section>

<main>
{body}
</main>

<footer>Generated from ARCHITECTURE_COMPARISON.md · Datalytics v2 architecture audit</footer>

</body>
</html>
"""

OUT.write_text(SHELL, encoding="utf-8")
print(f"wrote {OUT}  ({OUT.stat().st_size:,} bytes)")
