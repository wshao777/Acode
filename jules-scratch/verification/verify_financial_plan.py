
from playwright.sync_api import sync_playwright

def run(playwright):
    browser = playwright.chromium.launch(headless=True)
    context = browser.new_context()
    page = context.new_page()

    # Capture console messages
    page.on("console", lambda msg: print(msg.text))

    page.goto("http://localhost:8000")

    # Wait for the app to load
    page.wait_for_selector("body:not(.loading)")

    # Click the menu toggler
    page.click("[attr-action='toggle-menu']")

    # Click the financial plan button
    page.click("[action='financial-plan']")

    # Take a screenshot
    page.screenshot(path="jules-scratch/verification/financial-plan.png")

    browser.close()

with sync_playwright() as playwright:
    run(playwright)
