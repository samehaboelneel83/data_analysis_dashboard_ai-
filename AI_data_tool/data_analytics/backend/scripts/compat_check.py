"""The same journey in Chromium, Firefox and WebKit.

Compatibility testing, the level the plan lists and this codebase has never
had. Chromium is the only engine anything here has ever run in — every
frontend test is jsdom, and jsdom is not a browser at all.

The interesting output is not "it worked". It is the DIFFERENCES: a console
error in one engine and not another, a control that renders in Blink and not
in Gecko, a layout that only collapses in WebKit. So each engine runs the same
script and everything is recorded per engine for comparison.

WebKit is Safari's engine, which is what makes it worth the download: it is
the one most likely to disagree, and the one nobody here has ever tried.
"""
import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

OUT = Path(sys.argv[1] if len(sys.argv) > 1 else "compat")
OUT.mkdir(parents=True, exist_ok=True)
APP = "http://localhost:3001"
EMAIL, PASSWORD = "demo-global@example.invalid", "demo-password"

report: dict[str, dict] = {}


def walk(engine, launcher) -> dict:
    result: dict = {"console": [], "http5xx": [], "steps": {}, "widgets": None}
    browser = launcher.launch()
    ctx = browser.new_context(viewport={"width": 1500, "height": 950})
    page = ctx.new_page()
    page.on("pageerror", lambda e: result["console"].append(str(e)[:160]))
    page.on("response", lambda r: result["http5xx"].append(f"{r.status} {r.url[-60:]}")
            if r.status >= 500 else None)

    def step(name, fn):
        try:
            fn()
            page.wait_for_timeout(800)
            page.screenshot(path=str(OUT / f"{engine}_{name}.png"))
            result["steps"][name] = "ok"
        except Exception as e:                              # noqa: BLE001
            result["steps"][name] = f"FAILED: {str(e)[:120]}"

    def login():
        page.goto(APP, wait_until="networkidle")
        page.fill("input[type=email]", EMAIL)
        page.fill("input[type=password]", PASSWORD)
        page.click("button[type=submit]")
        page.wait_for_timeout(2500)
        # Did it actually get in? The login page staying put is the failure.
        result["steps"]["logged_in"] = "no" if page.url.rstrip("/").endswith("login") else "yes"

    step("01_login", login)
    step("02_home", lambda: page.goto(f"{APP}/", wait_until="networkidle"))
    step("03_datasets", lambda: page.goto(f"{APP}/datasets", wait_until="networkidle"))

    def builder():
        page.goto(f"{APP}/reports/166", wait_until="networkidle")
        page.wait_for_timeout(2500)
        # Things added this session, each a chance for an engine to disagree.
        result["widgets"] = {
            "object_picker": page.locator("#object-picker").count(),
            "palette_search": page.locator("input[aria-label='Find a chart']").count(),
            "settings_filter": page.locator("input[aria-label='Filter settings']").count(),
            "svg_charts": page.locator("svg").count(),
        }
    step("04_builder", builder)

    def search_palette():
        box = page.locator("input[aria-label='Find a chart']")
        if box.count():
            box.fill("waterfall")
            page.wait_for_timeout(500)
            result["steps"]["palette_filtered_to"] = page.locator(
                "button:has-text('Waterfall')").count()
    step("05_palette_search", search_palette)

    ctx.close()
    browser.close()
    return result


with sync_playwright() as p:
    for engine, launcher in (("chromium", p.chromium), ("firefox", p.firefox), ("webkit", p.webkit)):
        print(f"== {engine}")
        try:
            report[engine] = walk(engine, launcher)
        except Exception as e:                              # noqa: BLE001
            report[engine] = {"fatal": str(e)[:200]}
        r = report[engine]
        print(f"   logged in: {r.get('steps', {}).get('logged_in')}")
        print(f"   widgets:   {r.get('widgets')}")
        print(f"   console:   {len(r.get('console', []))} errors")
        print(f"   5xx:       {len(r.get('http5xx', []))}")
        bad = {k: v for k, v in r.get("steps", {}).items() if str(v).startswith("FAILED")}
        if bad:
            print(f"   FAILED:    {bad}")

(OUT / "compat.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
print(f"{chr(10)}written to {OUT}")
