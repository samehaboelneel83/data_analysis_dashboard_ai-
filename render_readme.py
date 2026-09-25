"""Render README.md into a single self-contained README.html.

Images are inlined as data URIs so the file can be emailed, copied to a USB
stick, or opened with no network. Fonts are linked but every stack has a real
local fallback, so the page is correct offline too.
"""
import base64, io, mimetypes, os, re
import markdown

ROOT = r"D:/Omda 2025/projects/data_analysis_dashboard_ai"

# Which document to render. Defaults to README.md so the original call still
# works; pass a filename to render any other markdown in this folder.
import sys
SOURCE = sys.argv[1] if len(sys.argv) > 1 else "README.md"
md_text = io.open(os.path.join(ROOT, SOURCE), encoding="utf-8").read()
#: The page title is the document's own first heading, so a renamed or new
#: markdown file does not silently keep the old page's name.
TITLE = next((l[2:].strip() for l in md_text.splitlines() if l.startswith("# ")),
             SOURCE)

# GitHub renders a list that butts straight up against a paragraph ("**Where.**"
# then "- item"); python-markdown needs a blank line first, or it folds the whole
# list into the paragraph. Insert that blank line rather than editing README.md.
import re as _pre
_out, _prev = [], ""
for _ln in md_text.splitlines():
    _isitem = bool(_pre.match(r"[-*+] |\d+[.)] ", _ln))
    if (_isitem and _prev.strip() and not _prev[:1].isspace()
            and not _pre.match(r"[-*+] |\d+[.)] |\||#|>|```", _prev)):
        _out.append("")
    _out.append(_ln)
    _prev = _ln
md_text = chr(10).join(_out)

md = markdown.Markdown(extensions=["tables", "fenced_code", "toc", "sane_lists"],
                       extension_configs={"toc": {"permalink": False}})
body = md.convert(md_text)

# ---- inline the images -------------------------------------------------------
def inline(m):
    src = m.group(1)
    path = os.path.join(ROOT, src)
    if not os.path.exists(path):
        return m.group(0)
    mime = mimetypes.guess_type(path)[0] or "image/png"
    b64 = base64.b64encode(open(path, "rb").read()).decode()
    return 'src="data:%s;base64,%s"' % (mime, b64)

body = re.sub(r'src="([^"]+\.png)"', inline, body)

# ---- inside part 7, only the numbered headings are topics --------------------
# "The layers, from widest to narrowest" is a sub-heading of topic 10, not a
# thirteenth topic: leaving it an <h3> would split the topic in two.
_KEEP = "Setting up the test environment"
import re as _re
# README links are GitHub-slug style ("#1--auto-profiling"); python-markdown
# mints single-hyphen ids. Repoint them so every in-page link works here too.
body = _re.sub(r'href="#([^"]+)"',
               lambda m: 'href="#' + _re.sub(r'-{2,}', '-', m.group(1)) + '"',
               body)
_m = _re.search(r'<h2 id="([^"]*deep-dive[^"]*)">', body)
PART7 = _m.group(1) if _m else ""
cut = body.find('<h2 id="%s">' % PART7) if PART7 else -1
if cut != -1:
    head, tail = body[:cut], body[cut:]
    def demote(m):
        text = re.sub(r"<[^>]+>", "", m.group(2))
        if re.match(r"^\d+\s*[·.]", text) or text.strip() == _KEEP:
            return m.group(0)
        return '<h4 id="%s">%s</h4>' % (m.group(1), m.group(2))
    tail = re.sub(r'<h3 id="([^"]+)">(.*?)</h3>', demote, tail)
    body = head + tail

# ---- build the sidebar from the h2/h3 tree ----------------------------------
heads = re.findall(r'<h([23]) id="([^"]+)">(.*?)</h[23]>', body)
nav = []
for level, hid, text in heads:
    text = re.sub(r"<[^>]+>", "", text)
    nav.append('<a class="lv%s" href="#%s">%s</a>' % (level, hid, text))
nav_html = "\n".join(nav)

CSS = """
:root{
  --ground:#f4f6f5; --panel:#fff; --panel-2:#e9edec; --ink:#17211f; --ink-soft:#55635f;
  --ink-faint:#8b9995; --line:#ccd5d2; --accent:#0d6a68; --accent-soft:#d6ebe9;
  --ochre:#9a6209; --ochre-soft:#f5e7cf;
}
@media (prefers-color-scheme: dark){ :root:not([data-theme="light"]){
  --ground:#101614; --panel:#18211f; --panel-2:#202b28; --ink:#e6ecea; --ink-soft:#a3b2ae;
  --ink-faint:#74827e; --line:#2e3c38; --accent:#5bc9c2; --accent-soft:#14322f;
  --ochre:#e0ac5c; --ochre-soft:#33260f;
}}
:root[data-theme="dark"]{
  --ground:#101614; --panel:#18211f; --panel-2:#202b28; --ink:#e6ecea; --ink-soft:#a3b2ae;
  --ink-faint:#74827e; --line:#2e3c38; --accent:#5bc9c2; --accent-soft:#14322f;
  --ochre:#e0ac5c; --ochre-soft:#33260f;
}
*{box-sizing:border-box}
html{scroll-behavior:smooth; scroll-padding-top:20px}
body{margin:0; background:var(--ground); color:var(--ink);
     font-family:"Source Serif 4",Georgia,"Times New Roman",serif; font-size:17px; line-height:1.65}

.shell{display:grid; grid-template-columns:266px minmax(0,1fr); gap:44px;
       max-width:1240px; margin:0 auto; padding:0 24px}

/* ---------- sidebar ---------- */
nav{position:sticky; top:0; align-self:start; max-height:100vh; overflow-y:auto;
    padding:34px 0 60px; display:flex; flex-direction:column; gap:1px}
nav .brand{font-family:"Archivo",system-ui,sans-serif; font-weight:700; font-size:17px;
           letter-spacing:-.01em; margin-bottom:6px}
nav .kicker{font-family:"JetBrains Mono",ui-monospace,monospace; font-size:10px; font-weight:600;
            letter-spacing:.14em; text-transform:uppercase; color:var(--accent); margin-bottom:16px}
nav a{display:block; text-decoration:none; color:var(--ink-soft); font-size:14px;
      padding:5px 10px; border-left:2px solid transparent; border-radius:0 3px 3px 0; line-height:1.35}
nav a:hover{color:var(--ink); background:var(--panel-2)}
nav a.lv2{font-family:"Archivo",sans-serif; font-weight:500; color:var(--ink); margin-top:10px}
nav a.lv3{padding-left:22px; font-size:13.5px}
nav a.active{border-left-color:var(--accent); color:var(--accent); background:var(--accent-soft)}

/* ---------- content ---------- */
main{padding:34px 0 120px; max-width:900px; min-width:0}
h1{font-family:"Archivo",system-ui,sans-serif; font-weight:700; font-size:clamp(28px,4.5vw,42px);
   line-height:1.06; letter-spacing:-.022em; margin:0 0 6px; text-wrap:balance}
h2{font-family:"Archivo",sans-serif; font-weight:700; font-size:25px; letter-spacing:-.012em;
   margin:56px 0 6px; padding-bottom:11px; border-bottom:2px solid var(--ink); text-wrap:balance}
h3{font-family:"Archivo",sans-serif; font-weight:700; font-size:19px; margin:40px 0 4px;
   letter-spacing:-.008em; text-wrap:balance}
h4{font-family:"Archivo",sans-serif; font-weight:500; font-size:15px; margin:26px 0 2px; color:var(--ink-soft)}
p{margin:12px 0}
hr{display:none}
a{color:var(--accent)}
:focus-visible{outline:2px solid var(--accent); outline-offset:2px}

ul,ol{margin:12px 0; padding-left:24px}
li{padding:3px 0}
li>strong:first-child{color:var(--ink)}

blockquote{margin:20px 0; padding:13px 18px; background:var(--ochre-soft);
           border-left:3px solid var(--ochre); border-radius:0 4px 4px 0; color:var(--ink-soft)}
blockquote p{margin:5px 0}
blockquote strong{color:var(--ink)}

.tablewrap{overflow-x:auto; margin:18px 0}
table{border-collapse:collapse; width:100%; font-size:15.5px}
th,td{text-align:left; padding:10px 13px; vertical-align:top; border-bottom:1px solid var(--line)}
th{font-family:"JetBrains Mono",monospace; font-size:10.5px; font-weight:600; letter-spacing:.08em;
   text-transform:uppercase; color:var(--ink-faint); white-space:nowrap}
td strong{font-family:"Archivo",sans-serif; font-weight:500}
tbody tr:hover{background:var(--panel-2)}

code{font-family:"JetBrains Mono",ui-monospace,monospace; font-size:.82em;
     background:var(--panel-2); padding:1.5px 5px; border-radius:3px; color:var(--ink-soft)}
pre{background:var(--panel-2); border:1px solid var(--line); border-radius:6px;
    padding:15px 17px; overflow-x:auto; margin:18px 0; line-height:1.55}
pre code{background:none; padding:0; font-size:12.8px; color:var(--ink)}

img{display:block; width:100%; height:auto; margin:20px 0; border:1px solid var(--line);
    border-radius:6px; background:#f4f6f5}

/* deep-dive topics fold away */
.topic{border:1px solid var(--line); background:var(--panel); border-radius:6px;
       margin:16px 0; padding:0 20px}
.topic>summary{cursor:pointer; list-style:none; display:flex; align-items:center; gap:11px;
               padding:14px 0; font-family:"Archivo",sans-serif; font-weight:700; font-size:18px}
.topic>summary::-webkit-details-marker{display:none}
.topic>summary::before{content:"+"; font-family:"JetBrains Mono",monospace; color:var(--accent);
                       font-weight:600; font-size:16px}
.topic[open]>summary::before{content:"\\2212"}
.topic>summary+*{margin-top:2px}
.topic>*:last-child{margin-bottom:20px}

.toolbar{display:flex; gap:8px; margin:26px 0 0}
.toolbar button{font-family:"JetBrains Mono",monospace; font-size:11px; letter-spacing:.04em;
  text-transform:uppercase; color:var(--ink-soft); background:var(--panel); cursor:pointer;
  border:1px solid var(--line); border-radius:4px; padding:7px 12px}
.toolbar button:hover{color:var(--accent); border-color:var(--accent)}

.printnote{color:var(--ink-faint); font-size:13.5px; font-family:"JetBrains Mono",monospace;
           margin-top:70px; padding-top:16px; border-top:1px solid var(--line)}

@media (max-width:940px){
  .shell{grid-template-columns:1fr; gap:0}
  nav{position:static; max-height:none; padding-bottom:24px; border-bottom:1px solid var(--line)}
  nav a.lv3{display:none}
}
@media print{
  nav,.toolbar{display:none} .shell{display:block} .topic{border:none; padding:0}
  .topic>summary::before{content:""}
}
@media (prefers-reduced-motion:reduce){ html{scroll-behavior:auto} }
"""

JS = """
// Fold each deep-dive topic into its own <details>, open by default so the page
// still shows everything at rest.
(function () {
  var main = document.querySelector('main');
  var start = document.getElementById('__PART7__');
  if (!start) return;
  var h3s = [];
  for (var n = start.nextElementSibling; n; n = n.nextElementSibling) {
    if (n.tagName === 'H2') break;
    if (n.tagName === 'H3') h3s.push(n);
  }
  h3s.forEach(function (h3) {
    var d = document.createElement('details');
    d.className = 'topic';
    d.open = true;
    var s = document.createElement('summary');
    s.textContent = h3.textContent;
    d.appendChild(s);
    h3.parentNode.insertBefore(d, h3);
    var n = h3.nextElementSibling;
    h3.remove();
    while (n && n.tagName !== 'H3' && n.tagName !== 'H2') {
      var next = n.nextElementSibling;
      d.appendChild(n);
      n = next;
    }
  });

  var bar = document.querySelector('.toolbar');
  if (bar) {
    bar.querySelector('[data-act="open"]').onclick = function () {
      document.querySelectorAll('.topic').forEach(function (d) { d.open = true; });
    };
    bar.querySelector('[data-act="close"]').onclick = function () {
      document.querySelectorAll('.topic').forEach(function (d) { d.open = false; });
    };
  }
})();

// Highlight the section currently on screen in the sidebar.
(function () {
  var links = {};
  document.querySelectorAll('nav a').forEach(function (a) { links[a.getAttribute('href').slice(1)] = a; });
  var seen = new Set();
  var io = new IntersectionObserver(function (entries) {
    entries.forEach(function (e) { e.isIntersecting ? seen.add(e.target.id) : seen.delete(e.target.id); });
    var ids = Object.keys(links).filter(function (id) { return seen.has(id); });
    document.querySelectorAll('nav a').forEach(function (a) { a.classList.remove('active'); });
    if (ids.length && links[ids[0]]) links[ids[0]].classList.add('active');
  }, { rootMargin: '0px 0px -70% 0px' });
  document.querySelectorAll('h2[id],h3[id],summary').forEach(function (el) {
    if (el.id) io.observe(el);
  });
})();
"""

# tables need a scroll container of their own
body = body.replace("<table>", '<div class="tablewrap"><table>').replace("</table>", "</table></div>")

JS = JS.replace("__PART7__", PART7)

html = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>__TITLE__</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Archivo:wght@500;700&family=JetBrains+Mono:wght@400;600&family=Source+Serif+4:opsz,wght@8..60,400;8..60,600&display=swap">
<style>%s</style>
</head>
<body>
<div class="shell">
  <nav>
    <div class="kicker">Datalytics v2</div>
    <div class="brand">Project map</div>
%s
  </nav>
  <main>
%s
    <p class="printnote">Generated from README.md. Edit the markdown, re-run
    <code>build_html.py</code>, and this page follows.</p>
  </main>
</div>
<script>%s</script>
</body>
</html>
""" % (CSS, nav_html, body, JS)

# the fold/unfold buttons sit right under the part-7 heading
html = re.sub(
    r'(<h2 id="%s">.*?</h2>)' % PART7,
    r'\1<div class="toolbar"><button data-act="open">Open all topics</button>'
    r'<button data-act="close">Close all topics</button></div>',
    html, count=1)

out = os.path.join(ROOT, SOURCE.replace(".md", ".html"))
html = html.replace("__TITLE__", TITLE)
io.open(out, "w", encoding="utf-8").write(html)
print("wrote", out, len(html), "bytes;", len(heads), "headings")
