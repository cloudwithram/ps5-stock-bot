# PS5 Stock Checker Bot — India (v3, Playwright)

Monitors 8 platforms and sends an instant Telegram alert when PS5 comes in stock.
Runs free on GitHub Actions — no server, no laptop.

Uses a REAL headless browser (Playwright), so it works on JavaScript-heavy
sites like Blinkit and Zepto — not just server-rendered ones.

## Platforms covered
Blinkit, Zepto, BigBasket (10-min delivery) + Amazon, Flipkart, Vijay Sales,
Croma, Reliance Digital.

---

## Setup (10 minutes, one-time)

### 1. Create Telegram Bot
- Telegram -> search @BotFather -> send /newbot
- Name it (e.g. PS5 Alert Bot), pick a unique username
- Copy the token (like 7312456789:AAF...)
- Send any message to your new bot
- Open in browser (replace YOUR_TOKEN):
  https://api.telegram.org/botYOUR_TOKEN/getUpdates
- Copy the "id" number inside "chat" -> that's your Chat ID

### 2. Create a GitHub repo
- github.com -> New repository -> name: ps5-stock-bot
- Public (free unlimited Actions)
- Upload all files from this folder, keeping the .github/workflows/ path

### 3. Add GitHub Secrets
Repo -> Settings -> Secrets and variables -> Actions -> New repository secret

| Name              | Value                          |
|-------------------|--------------------------------|
| TELEGRAM_TOKEN    | Token from BotFather           |
| TELEGRAM_CHAT_ID  | Your Chat ID number            |
| PS5_PINCODE       | Your pincode (e.g. 560043)     |

### 4. Enable Actions
Actions tab -> "I understand my workflows, enable them"

### 5. Test
Actions -> PS5 Stock Checker -> Run workflow.
First run takes ~2-3 min (installs browser). You get a Telegram alert if any
platform has stock.

---

## How it works
- Every 5 minutes, GitHub launches a headless Chrome
- Loads each PS5 product page, waits for JavaScript to render stock
- Detects "Out of stock" / "Notify me" vs a live ADD / Buy button
- Ignores "Similar products" ADD buttons (no false alerts)
- Sends Telegram alert only on a genuine in-stock

## Files
- ps5_check.py — main checker (Playwright)
- requirements.txt — playwright + requests
- .github/workflows/ps5_check.yml — 5-minute schedule

## Notes
- Quick-commerce stock is location-based; PS5_PINCODE + the geolocation in the
  script are set to Banaswadi, Bangalore. Change if needed.
- If a site shows a login/pincode wall before stock, that item may read
  "unclear" — the bot simply skips it that cycle and retries next run.

---

## v3.2 improvements
- CAPTCHA / bot-wall detection: if Amazon/Flipkart challenge the datacenter IP,
  the log shows "BLOCKED" instead of silently looking like "no stock".
- Alert de-duplication: you get ONE alert when an item comes in stock, not a
  repeat every 5 minutes. State is cached between runs. If it sells out and
  restocks, you get a fresh alert.
- End-of-run summary: shows how many products were in-stock / OOS / blocked /
  unclear, so you can spot if sites started blocking.

## Known limits (honest)
- GitHub Actions uses datacenter IPs. Amazon/Flipkart sometimes serve a CAPTCHA
  to these — those items will read "BLOCKED" and retry next run. Quick-commerce
  (Blinkit/Zepto/BigBasket) and the others are usually fine.
- No scraper is permanent: if a site changes its layout, its selector may need
  updating. Watch the run logs — repeated "unclear"/"blocked" for one site means
  its selector needs a refresh.
