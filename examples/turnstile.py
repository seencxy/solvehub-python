"""Solve a Cloudflare Turnstile challenge, then submit the token with Playwright.

    pip install solvehub playwright && playwright install chromium
    export SOLVEHUB_KEY=sh_live_xxx
    python examples/turnstile.py

Point SITE at a page you own or are explicitly authorised to test.
"""

import os

from solvehub import SolveHub, TaskFailed


SITE = "https://example.com/login"
SITE_KEY = "0x4AAAAAAA_SITE_KEY"       # the data-sitekey on the page
FORM_FIELD = "cf-turnstile-response"   # hidden input the site reads

client = SolveHub(os.environ["SOLVEHUB_KEY"])

try:
    task = client.solve(
        "turnstile",
        {"websiteURL": SITE, "websiteKey": SITE_KEY},
        timeout=180,
    )
except TaskFailed as exc:
    raise SystemExit("could not solve: %s" % (exc,))

token = task["solution"]["value"]
print("token %s... (%s)" % (token[:24], task.get("price", "?")))

# The token is bound to the site key and expires in a few minutes: use it now,
# from a real browser session, and do not reuse it across attempts.
from playwright.sync_api import sync_playwright  # noqa: E402

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    page = browser.new_page()
    page.goto(SITE, wait_until="domcontentloaded")
    page.evaluate(
        """([field, value]) => {
            let el = document.querySelector(`[name="${field}"]`);
            if (!el) {
                el = document.createElement('input');
                el.type = 'hidden';
                el.name = field;
                document.forms[0].appendChild(el);
            }
            el.value = value;
        }""",
        [FORM_FIELD, token],
    )
    page.click("button[type=submit]")
    page.wait_for_load_state("networkidle")
    print("after submit ->", page.url)
    browser.close()
