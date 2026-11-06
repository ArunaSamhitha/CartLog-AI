"""End-to-end check: a real browser searches through the running UI and API (mock agents).

Expects the API on :8000 and the built frontend served by `vite preview` on :4173.
"""
import sys

from playwright.sync_api import expect, sync_playwright

URL = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:4173"

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(URL)

    page.fill("#query", "used sony headphones under $200")
    page.click("button.go")
    expect(page.locator(".card").first).to_be_visible(timeout=20_000)

    # The query was understood, all three agents answered, and prices respect the budget.
    expect(page.locator(".pill", has_text="under $200.00")).to_be_visible()
    expect(page.locator(".trace-row")).to_have_count(3)
    assert page.locator(".trace-bar.failed").count() == 0, "an agent failed"
    prices = [float(t.replace("$", "").replace(",", "")) for t in page.locator(".meta strong").all_inner_texts()]
    assert prices and max(prices) <= 200, prices

    # A second, related search recalls the first one from memory.
    page.fill("#query", "sony headphones")
    page.click("button.go")
    expect(page.locator(".recall .chip", has_text="used sony headphones under $200")).to_be_visible(timeout=20_000)

    page.screenshot(path="e2e-result.png", full_page=True)
    assert not errors, errors
    print(f"OK: {len(prices)} listings, all under budget; memory recall works")
    browser.close()
