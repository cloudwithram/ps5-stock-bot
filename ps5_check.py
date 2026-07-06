#!/usr/bin/env python3
"""
PS5 STOCK CHECKER — India — v3 (Playwright / real browser)

Renders each page in a REAL headless browser, so it works on
JavaScript-heavy sites (Blinkit, Zepto) exactly like your phone does —
not just server-rendered ones.

Platforms: Blinkit, Zepto, BigBasket, Amazon, Flipkart,
           Vijay Sales, Croma, Reliance Digital
Alerts:    Telegram (instant)
"""

import os, re, random, logging, requests
from datetime import datetime
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

# ── Config from GitHub Secrets ─────────────────────────────────
TELEGRAM_TOKEN   = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
PINCODE          = os.environ.get("PS5_PINCODE", "560043")  # Banaswadi, Bangalore

# ── Products ───────────────────────────────────────────────────
PRODUCTS = [
    # ── Quick Commerce (10-min delivery — location sensitive) ──
    {"name": "PS5 Digital — Blinkit", "site": "blinkit",
     "url": "https://blinkit.com/prn/sony-ps5-digital-edition-slim/prid/547393",
     "price": "₹49,990 • 10-min delivery"},
    {"name": "PS5 Disc — Blinkit", "site": "blinkit",
     "url": "https://blinkit.com/prn/sony-ps5-console-slim/prid/547392",
     "price": "₹54,990 • 10-min delivery"},
    {"name": "PS5 Slim — Zepto", "site": "zepto",
     "url": "https://www.zepto.com/pn/playstation-5-console-slim-playstation-5-console-e-chasis-slim/pvid/ad968d7d-c5d8-415e-b7d4-58f84ff13076",
     "price": "~₹49,990 • 10-min delivery"},
    {"name": "PS5 Digital — BigBasket", "site": "bigbasket",
     "url": "https://www.bigbasket.com/pd/40329964/sony-ps5-slim-digital-edition-console-1-n/",
     "price": "₹44,990 • 10-min delivery"},
    # ── Traditional E-Commerce ──
    {"name": "PS5 Slim Disc — Amazon", "site": "amazon",
     "url": "https://www.amazon.in/dp/B0BCNKKZ91", "price": "₹54,990"},
    {"name": "PS5 Digital — Amazon", "site": "amazon",
     "url": "https://www.amazon.in/dp/B0BCNKVZMK", "price": "₹44,990"},
    {"name": "PS5 Slim — Vijay Sales", "site": "vijaysales",
     "url": "https://www.vijaysales.com/search?q=ps5+slim",
     "price": "₹51,499 (₹3,500 off with HDFC)"},
    {"name": "PS5 — Croma", "site": "croma",
     "url": "https://www.croma.com/searchB?q=playstation+5", "price": "~₹54,990"},
    {"name": "PS5 — Reliance Digital", "site": "reliancedigital",
     "url": "https://www.reliancedigital.in/search?q=ps5", "price": "~₹54,990"},
    {"name": "PS5 Slim — Flipkart", "site": "flipkart",
     "url": "https://www.flipkart.com/search?q=ps5+slim", "price": "~₹54,990"},
]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%d-%b %H:%M:%S",
)
log = logging.getLogger("PS5Bot")


# ── Telegram ───────────────────────────────────────────────────
def send_telegram(message: str) -> bool:
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        log.error("Telegram credentials missing — set GitHub Secrets!")
        return False
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": message,
                  "parse_mode": "HTML", "disable_web_page_preview": False},
            timeout=10)
        if r.status_code == 200:
            log.info("Telegram alert sent!")
            return True
        log.warning(f"Telegram {r.status_code}: {r.text[:200]}")
    except Exception as e:
        log.error(f"Telegram error: {e}")
    return False


def build_alert(product: dict) -> str:
    now = datetime.now().strftime("%d %b %Y, %I:%M %p")
    quick = product["site"] in ("blinkit", "zepto", "bigbasket")
    header = "PS5 IN STOCK — ORDER IN 2 MINS!" if quick else "PS5 IN STOCK — BUY NOW!"
    tail = ("Quick-commerce stock is tiny — open the app and order NOW!"
            if quick else "Stock clears fast — buy immediately!")
    return (f"🚨 <b>{header}</b>\n\n"
            f"📦 <b>{product['name']}</b>\n"
            f"💰 {product.get('price','Check site')}\n"
            f"🕐 Found: {now} IST\n\n"
            f"🔗 <a href=\"{product['url']}\">Open and order → {product['url']}</a>\n\n"
            f"⚡ {tail}")


# ── Stock detection ────────────────────────────────────────────
OOS_PHRASES = [
    "out of stock", "sold out", "currently unavailable",
    "temporarily unavailable", "notify me when", "notify me",
    "coming soon", "out for stock",
    # Negated forms — MUST be listed so they're caught before the positive
    # "in stock" check below (otherwise "not in stock" matches "in stock").
    "not in stock", "no longer in stock", "currently not in stock",
    "product not available", "item not available",
    # NOTE: bare "unavailable" / "not available" are deliberately NOT here —
    # they also appear in "delivery unavailable" etc. and would cause a
    # FALSE-NEGATIVE (miss a real restock). We only match stock-specific forms.
]
INSTOCK_PHRASES = [
    "add to cart", "buy now", "add to basket", "go to cart",
    # "in stock" handled separately with word-boundary logic in decide_stock
]

# Signals that the page is a CAPTCHA / bot-wall, NOT a real product page.
# These matter because GitHub Actions uses datacenter IPs that Amazon/Flipkart
# sometimes challenge. If we see these, report BLOCKED (not "no stock") so a
# genuine restock isn't silently missed.
BLOCK_PHRASES = [
    "enter the characters you see below", "type the characters you see",
    "are you a robot", "are you a human", "verify you are human",
    "unusual traffic", "automated access", "px-captcha", "captcha",
    "access denied", "request blocked", "to discuss automated access",
    "sorry, we just need to make sure you're not a robot",
]


def scope_main_product(full_text: str) -> str:
    """Trim 'similar products' etc. so their ADD buttons don't false-positive."""
    low = full_text.lower()
    markers = ["similar products", "people also bought", "you may also like",
               "you might also", "related products", "top 10 products",
               "frequently bought", "customers who bought", "more like this",
               "recommended for you"]
    earliest = len(low)
    for m in markers:
        idx = low.find(m)
        if idx != -1:
            earliest = min(earliest, idx)
    return full_text[:earliest]


def decide_stock(page_text: str, add_button_visible: bool) -> tuple:
    """
    Return (status, reason) where status is:
      True    → in stock
      False   → out of stock
      None    → unclear (no signal)
      "BLOCK" → page is a CAPTCHA / bot-wall (site couldn't be read)
    """
    low_all = page_text.lower()

    # 0. Bot-wall / CAPTCHA check FIRST — if the page is a challenge, we can't
    #    trust anything else on it. Report BLOCK so it's visible in logs and
    #    never mistaken for "no stock".
    if not add_button_visible:  # a real product page with a buy button isn't a captcha
        for b in BLOCK_PHRASES:
            if b in low_all:
                return "BLOCK", f"Bot-wall detected: '{b}'"

    main = scope_main_product(page_text).lower()

    # 1. Any OOS / negated phrase wins first (order matters)
    for p in OOS_PHRASES:
        if p in main:
            return False, f"OOS phrase: '{p}'"

    # 2. A visible ADD / Buy button element → in stock
    if add_button_visible:
        return True, "Buy/ADD button visible"

    # 3. Positive buy-path phrases
    for p in INSTOCK_PHRASES:
        if p in main:
            return True, f"In-stock phrase: '{p}'"

    # 4. "in stock" only when NOT preceded by a negator. By step 3 we've already
    #    returned OOS for "not in stock" etc., so a bare "in stock" here is safe —
    #    but double-guard with a regex that requires a word boundary before it.
    if re.search(r"(?<!not )(?<!n't )\bin stock\b", main):
        return True, "In-stock phrase: 'in stock'"

    return None, "No stock signal found"


# ── Browser rendering ──────────────────────────────────────────
BUY_SELECTORS = {
    "blinkit":         ["button:has-text('ADD')", "[data-test-id*='add']"],
    "zepto":           ["button:has-text('Add')", "[data-testid*='add']"],
    "bigbasket":       ["button:has-text('Add')", "[qa='add']"],
    "amazon":          ["#add-to-cart-button", "#buy-now-button"],
    "flipkart":        ["button:has-text('ADD TO CART')", "button:has-text('BUY NOW')"],
    "vijaysales":      ["button:has-text('Add to Cart')", "button:has-text('Buy Now')"],
    "croma":           ["button:has-text('Add to Cart')", "[data-testid*='add-cart']"],
    "reliancedigital": ["button:has-text('Add to Cart')", "button:has-text('Buy Now')"],
}


def render_and_check(page, product: dict) -> tuple:
    site, url = product["site"], product["url"]
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=20000)
    except PWTimeout:
        return None, "Page load timeout"
    except Exception as e:
        return None, f"Navigation error: {e}"

    page.wait_for_timeout(4000)  # let JS hydrate stock status

    add_visible = False
    for sel in BUY_SELECTORS.get(site, []):
        try:
            el = page.locator(sel).first
            if el.count() > 0 and el.is_visible(timeout=1500):
                add_visible = True
                break
        except Exception:
            continue

    try:
        page_text = page.inner_text("body", timeout=5000)
    except Exception:
        page_text = ""

    if not page_text:
        return None, "Empty page (blocked or not rendered)"
    return decide_stock(page_text, add_visible)


# ── De-dupe state (cached between GitHub Actions runs) ─────────
# GitHub Actions runs are stateless, but the workflow caches this file so we
# remember which products we've already alerted on. We only re-alert if a
# product goes OOS and then comes back (edge → re-trigger).
STATE_FILE = os.environ.get("PS5_STATE_FILE", "ps5_state.json")


def load_state() -> dict:
    try:
        import json
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return {}


def save_state(state: dict) -> None:
    try:
        import json
        with open(STATE_FILE, "w") as f:
            json.dump(state, f)
    except Exception as e:
        log.warning(f"Could not save state: {e}")


# ── Main ───────────────────────────────────────────────────────
def main():
    log.info(f"PS5 Bot v3.2 (Playwright) — {datetime.now().strftime('%d %b %Y %H:%M IST')}")
    log.info(f"Pincode: {PINCODE} | Checking {len(PRODUCTS)} products across 8 platforms")

    state = load_state()          # {product_name: "in_stock"|"out"} from last run
    new_state = {}
    counts = {"in_stock": 0, "oos": 0, "blocked": 0, "unclear": 0, "error": 0}
    alerted = []

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-blink-features=AutomationControlled",
                  "--disable-dev-shm-usage"])
        context = browser.new_context(
            user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"),
            locale="en-IN",
            viewport={"width": 1366, "height": 900},
            geolocation={"latitude": 12.9784, "longitude": 77.6408},  # Banaswadi
            permissions=["geolocation"])
        page = context.new_page()

        for product in PRODUCTS:
            name = product["name"]
            log.info(f"Checking: {name}")
            try:
                status, reason = render_and_check(page, product)
            except Exception as e:
                log.error(f"Error — {name}: {e}")
                counts["error"] += 1
                # keep previous known state so a transient error doesn't reset dedupe
                if name in state:
                    new_state[name] = state[name]
                page.wait_for_timeout(random.randint(1500, 3500))
                continue

            if status is True:
                counts["in_stock"] += 1
                new_state[name] = "in_stock"
                # Only alert if it wasn't already in stock last run (de-dupe)
                if state.get(name) != "in_stock":
                    log.info(f"IN STOCK (NEW) -> {name} ({reason}) — sending alert")
                    send_telegram(build_alert(product))
                    alerted.append(name)
                else:
                    log.info(f"IN STOCK (already alerted) -> {name} — skipping repeat")
            elif status is False:
                counts["oos"] += 1
                new_state[name] = "out"
                log.info(f"Out of stock -> {name} ({reason})")
            elif status == "BLOCK":
                counts["blocked"] += 1
                # don't overwrite a known-good state with a block
                if name in state:
                    new_state[name] = state[name]
                log.warning(f"BLOCKED (bot-wall) -> {name} ({reason})")
            else:  # None / unclear
                counts["unclear"] += 1
                if name in state:
                    new_state[name] = state[name]
                log.warning(f"Unclear -> {name} ({reason})")

            page.wait_for_timeout(random.randint(1500, 3500))

        browser.close()

    save_state(new_state)

    # ── Clear end-of-run summary ──
    log.info("-" * 46)
    log.info(f"SUMMARY: {counts['in_stock']} in-stock, {counts['oos']} OOS, "
             f"{counts['blocked']} blocked, {counts['unclear']} unclear, "
             f"{counts['error']} errors")
    if alerted:
        log.info(f"Alerts sent for: {', '.join(alerted)}")
    if counts["blocked"] or counts["unclear"]:
        readable = len(PRODUCTS) - counts["blocked"] - counts["unclear"] - counts["error"]
        log.warning(f"Only {readable}/{len(PRODUCTS)} products were reliably read this run. "
                    f"Blocked/unclear sites are retried next cycle.")
    if not alerted:
        log.info("No new in-stock alerts this run.")
    log.info("Run complete.")


if __name__ == "__main__":
    main()
