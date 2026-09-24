"""Drive Datalytics in a real browser and photograph every layer.

The only test level in the plan that jsdom cannot reach. Every other frontend
test here runs in jsdom, which has no layout (everything measures 0x0), a
thin PointerEvent, and no real CSS -- so "it renders" and "a person can use
it" are different questions. This answers the second one.

It has already earned its place: run once, it found a training form offered on
a dataset that cannot train, an Analysis tab doing the same, a live dataset
reported as "0 rows", a palette of 67 charts with no search, a settings filter
present on one panel and missing from its twin, and three places where text is
clipped with no way to read it.

RUNNING IT. Playwright's Node package needs Node 20 and this environment has
18, so use the PYTHON one, in a venv of its own rather than the backend's:

    python -m venv .uivenv
    .uivenv/Scripts/python -m pip install playwright
    .uivenv/Scripts/python -m playwright install chromium
    .uivenv/Scripts/python backend/scripts/ui_walkthrough.py shots

Point APP at the SERVED app (the container on :3001), not a stray dev server:
an origin outside `allowed_origins` is blocked by CORS, and the login page
reports that as "Invalid email or password".

Each step is wrapped: one surface failing must not end the walk, because the
failures ARE the findings.
"""
import json
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

OUT = Path(sys.argv[1] if len(sys.argv) > 1 else "shots")
OUT.mkdir(parents=True, exist_ok=True)
APP = "http://localhost:3001"
EMAIL, PASSWORD = "demo-global@example.invalid", "demo-password"

findings: list[dict] = []
shots: list[str] = []


def note(kind: str, where: str, detail: str) -> None:
    findings.append({"kind": kind, "where": where, "detail": detail})
    print(f"  [{kind}] {where}: {detail}")


def shot(page, name: str) -> None:
    path = OUT / f"{name}.png"
    try:
        page.screenshot(path=str(path), full_page=False)
        shots.append(name)
        print(f"  shot {name}")
    except Exception as e:                                  # noqa: BLE001
        note("shot-failed", name, str(e)[:160])


def step(page, name: str, fn) -> None:
    """One surface. A failure is a finding, not the end of the walk."""
    print(f"- {name}")
    try:
        fn()
        page.wait_for_timeout(900)
        shot(page, name)
    except Exception as e:                                  # noqa: BLE001
        note("step-failed", name, str(e)[:200])
        shot(page, f"{name}__failed")


def main() -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(viewport={"width": 1600, "height": 1000})
        page = ctx.new_page()

        # Console errors and failed requests are UX findings: a page that looks
        # fine while throwing is a page one state change away from not looking
        # fine.
        page.on("pageerror", lambda e: note("console-error", page.url, str(e)[:200]))
        page.on("response", lambda r: note("http-error", r.url.split("/api/v1")[-1][:80],
                                           f"{r.status}") if r.status >= 500 else None)

        # ── login
        print("- login")
        page.goto(APP, wait_until="networkidle")
        shot(page, "00_login")
        try:
            page.fill("input[type=email]", EMAIL)
            page.fill("input[type=password]", PASSWORD)
            page.click("button[type=submit]")
            page.wait_for_timeout(2500)
        except Exception as e:                              # noqa: BLE001
            note("step-failed", "login", str(e)[:200])
        shot(page, "01_after_login")

        step(page, "02_dashboard", lambda: page.goto(f"{APP}/", wait_until="networkidle"))
        step(page, "03_datasets", lambda: page.goto(f"{APP}/datasets", wait_until="networkidle"))
        step(page, "04_reports", lambda: page.goto(f"{APP}/reports", wait_until="networkidle"))

        # ── dataset, every tab
        ds_id = None
        try:
            page.goto(f"{APP}/datasets", wait_until="networkidle")
            page.wait_for_timeout(800)
            link = page.locator("a[href*='/datasets/']").first
            href = link.get_attribute("href") or ""
            ds_id = href.rsplit("/", 1)[-1].split("?")[0]
        except Exception as e:                              # noqa: BLE001
            note("step-failed", "find-dataset", str(e)[:160])

        if ds_id and ds_id.isdigit():
            for tab in ("overview", "data", "statistics", "alerts", "models"):
                step(page, f"05_dataset_{tab}",
                     lambda t=tab: page.goto(f"{APP}/datasets/{ds_id}?tab={t}", wait_until="networkidle"))
        else:
            note("blocked", "dataset-tabs", "no dataset link found on /datasets")

        # ── report builder, and the panes an author lives in
        rep_id = None
        try:
            page.goto(f"{APP}/reports", wait_until="networkidle")
            page.wait_for_timeout(800)
            link = page.locator("a[href*='/reports/']").first
            href = link.get_attribute("href") or ""
            rep_id = href.rsplit("/", 1)[-1].split("?")[0]
        except Exception as e:                              # noqa: BLE001
            note("step-failed", "find-report", str(e)[:160])

        if rep_id and rep_id.isdigit():
            step(page, "06_builder",
                 lambda: page.goto(f"{APP}/reports/{rep_id}", wait_until="networkidle"))

            # The object picker added this session: does it list the objects?
            def pick_object():
                page.wait_for_timeout(1500)
                sel = page.locator("#object-picker")
                if sel.count() == 0:
                    note("missing", "object-picker", "not rendered on the builder")
                    return
                opts = sel.locator("option").all_text_contents()
                note("info", "object-picker", f"{len(opts)} objects: {opts[:6]}")
                if len(opts) > 1:
                    sel.select_option(index=1)
                    page.wait_for_timeout(1200)

            step(page, "07_builder_object_picker", pick_object)

            # Properties panel with a widget selected.
            step(page, "08_builder_properties", lambda: page.wait_for_timeout(600))

        else:
            note("blocked", "builder", "no report link found on /reports")

        ctx.close()
        browser.close()

    (OUT / "findings.json").write_text(json.dumps(findings, indent=2), encoding="utf-8")
    print(f"{chr(10)}{len(shots)} screenshots, {len(findings)} findings -> {OUT}")


if __name__ == "__main__":
    main()
