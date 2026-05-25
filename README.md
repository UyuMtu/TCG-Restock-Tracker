# TCG Restock Tracker 🃏

Automatically monitors **Pokémon Center**, **Virgin Megastore** (.ae / .om / .qa), **Amazon** (.ae / .com / .co.uk), and **eBay** for sealed product restocks and price drops — then sends instant alerts to **Discord** and **Telegram**.

Runs every 30 minutes for free on GitHub Actions. No server. No subscription.

---

## What it tracks

| Store | Region | Currency | Method |
|---|---|---|---|
| Pokémon Center | US | USD | Web scraping |
| Virgin Megastore | UAE, Oman, Qatar | AED / OMR / QAR | Web scraping |
| Amazon | UAE, US, UK | AED / USD / GBP | Web scraping |
| eBay | Global → ships to AE | USD | Official API |

## What it does

- 🟢 **Restock alerts** — notifies you the moment an out-of-stock product becomes available
- 📉 **Price drop alerts** — notifies you when a price drops by your chosen threshold (default: 5%)
- 🛒 **New eBay listings** — notifies you when a new listing matches your search
- 💾 **Remembers state** — won't spam you with repeated alerts for the same event

---

## Setup Guide

### Step 1 — Create your GitHub repository

1. Go to [github.com](https://github.com) and sign in
2. Click **+** → **New repository**
3. Name it `tcg-restock-tracker` and set it to **Public**
4. Click **Create repository**
5. Upload all project files (see file structure below)

---

### Step 2 — Get your Discord Webhook URL

1. Open Discord → right-click your alert channel → **Edit Channel**
2. Go to **Integrations** → **Webhooks** → **New Webhook**
3. Copy the webhook URL
4. Save as `DISCORD_WEBHOOK_URL` in GitHub Secrets

---

### Step 3 — Set up your Telegram Bot

1. Message **@BotFather** on Telegram → send `/newbot`
2. Follow the prompts and save your **bot token**
3. Send your bot any message to activate it
4. Get your Chat ID via **@userinfobot** on Telegram
5. Save token as `TELEGRAM_BOT_TOKEN` and Chat ID as `TELEGRAM_CHAT_ID` in GitHub Secrets

---

### Step 4 — Get your eBay App ID

1. Go to [developer.ebay.com](https://developer.ebay.com) and sign in
2. Go to **My Account** → **Application Access Keys**
3. Click **Get a New Key Set** → **Production**
4. Copy the **App ID (Client ID)**
5. Save as `EBAY_APP_ID` in GitHub Secrets

---

### Step 5 — Add all secrets to GitHub

Go to your repo → **Settings** → **Secrets and variables** → **Actions** → **New repository secret**

| Secret Name | Where to get it |
|---|---|
| `DISCORD_WEBHOOK_URL` | Step 2 |
| `TELEGRAM_BOT_TOKEN` | Step 3 |
| `TELEGRAM_CHAT_ID` | Step 3 |
| `EBAY_APP_ID` | Step 4 |

---

### Step 6 — Customise config.yaml

Edit `config.yaml` to add your products. For each product provide a `name` and `url`. Optionally add `max_price` to only alert below a certain price (omit it to alert on any restock).

```yaml
# Alert on any restock, any price:
virgin_megastore_ae:
  - name: "Ascended Heroes ETB"
    url: "https://www.virginmegastore.ae/en/..."

# Alert only if price is at or below max:
amazon_ae:
  - name: "Prismatic Evolutions ETB"
    url: "https://www.amazon.ae/dp/B0DLPL7LC5"
    max_price: 800
```

> **Amazon tip:** Always use the short `/dp/XXXXXXXXXX` URL format.

---

### Step 7 — Run it

1. Go to the **Actions** tab in your repo
2. Click **TCG Restock Tracker** → **Run workflow** to test
3. A green tick ✅ means everything is working
4. The tracker now runs automatically every 30 minutes

---

## Customisation

### Change check frequency
Edit `.github/workflows/tracker.yml`:
```yaml
- cron: "*/30 * * * *"   # Every 30 minutes
- cron: "*/15 * * * *"   # Every 15 minutes
- cron: "0 * * * *"      # Every hour
```

### Change price drop threshold
Edit `config.yaml`:
```yaml
settings:
  price_drop_threshold_percent: 10  # Only alert on 10%+ drops
```

### Add more products
Add entries under the relevant store section in `config.yaml`. No code changes needed — the bot picks them up on the next run.

---

## Troubleshooting

**Green tick but no alerts** → Correct behaviour. Products are out of stock or haven't changed price. The bot will alert you when they do.

**Red X on the run** → Click the run → click "track" → expand "Run TCG tracker" to see the error.

**Amazon CAPTCHA warning** → Amazon occasionally blocks requests. The bot logs a warning and skips that product for that run. It will retry automatically on the next run.

**eBay not working** → Check your `EBAY_APP_ID` secret. Make sure it's from the **Production** environment, not Sandbox.

**Telegram not receiving** → Make sure you sent your bot at least one message before the first run.

**Discord 400 error** → Webhook may have been deleted. Create a new one and update the secret.

---

## File structure

```
tcg-restock-tracker/
├── .github/
│   └── workflows/
│       └── tracker.yml          # Runs every 30 min on GitHub Actions
├── tracker/
│   ├── scrapers/
│   │   ├── __init__.py
│   │   ├── pokemon_center.py    # Pokémon Center scraper
│   │   ├── virgin_megastore.py  # Virgin Megastore (.ae/.om/.qa)
│   │   ├── amazon.py            # Amazon (.ae/.com/.co.uk)
│   │   └── ebay.py              # eBay Finding API
│   ├── notifiers/
│   │   ├── __init__.py
│   │   ├── discord.py           # Discord webhook alerts
│   │   └── telegram.py          # Telegram bot alerts
│   └── __init__.py
├── config.yaml                  # ← Edit this to add products
├── main.py                      # Main script
├── state.json                   # Auto-managed — do not edit
├── requirements.txt             # Python dependencies
└── README.md
```
