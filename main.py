"""
TCG Restock & Price Tracker
Checks Virgin Megastore (.ae/.om/.qa), Amazon, and eBay
for sealed product restocks and price drops.
"""

import json
import os
import yaml
from datetime import datetime
from tracker.scrapers.virgin_megastore import check_virgin_megastore
from tracker.scrapers.ebay import check_ebay
from tracker.scrapers.amazon import check_amazon
from tracker.notifiers.discord import send_discord_alert
from tracker.notifiers.telegram import send_telegram_alert

STATE_FILE = "state.json"
CONFIG_FILE = "config.yaml"

CURRENCY = {"ae": "AED", "om": "OMR", "qa": "QAR"}


def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    return {}


def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def load_config():
    with open(CONFIG_FILE) as f:
        cfg = yaml.safe_load(f)

    # Override secrets with environment variables (set in GitHub Secrets)
    if os.getenv("DISCORD_WEBHOOK_URL"):
        cfg.setdefault("discord", {})["webhook_url"] = os.getenv("DISCORD_WEBHOOK_URL")
    if os.getenv("TELEGRAM_BOT_TOKEN"):
        cfg.setdefault("telegram", {})["bot_token"] = os.getenv("TELEGRAM_BOT_TOKEN")
    if os.getenv("TELEGRAM_CHAT_ID"):
        cfg.setdefault("telegram", {})["chat_id"] = os.getenv("TELEGRAM_CHAT_ID")
    if os.getenv("EBAY_APP_ID"):
        cfg.setdefault("ebay", {})["app_id"] = os.getenv("EBAY_APP_ID")

    return cfg


def send_alert(config, message, embed=None):
    """Send alert to all configured notification channels."""
    sent = False
    if config.get("discord", {}).get("webhook_url"):
        send_discord_alert(config["discord"]["webhook_url"], message, embed)
        sent = True
    if config.get("telegram", {}).get("bot_token") and config.get("telegram", {}).get("chat_id"):
        send_telegram_alert(
            config["telegram"]["bot_token"],
            config["telegram"]["chat_id"],
            message,
        )
        sent = True
    if not sent:
        print("⚠️  No notification channels configured. Check your secrets.")


def check_price_drop(prev_price, new_price, threshold_pct):
    """Returns True and drop % if price dropped by at least threshold_pct."""
    if prev_price and new_price and prev_price > 0:
        drop = (prev_price - new_price) / prev_price * 100
        if drop >= threshold_pct:
            return True, drop
    return False, 0


def main():
    config = load_config()
    state = load_state()
    alerts = []
    threshold = config.get("settings", {}).get("price_drop_threshold_percent", 5)

    print(f"\n🔍 TCG Tracker running at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} UTC")
    print("=" * 60)

    # ── Virgin Megastore ─────────────────────────────────────────
    for region in ["ae", "om", "qa"]:
        vm_products = config.get("products", {}).get(f"virgin_megastore_{region}", [])
        if not vm_products:
            continue
        print(f"\n🛍️  Checking Virgin Megastore .{region} ({len(vm_products)} product(s))...")
        currency = CURRENCY[region]
        for product in vm_products:
            result = check_virgin_megastore(product["url"], product["name"])
            key = f"vm_{region}_{product['url']}"
            prev = state.get(key, {})
            max_price = product.get("max_price")

            if result.get("error"):
                print(f"  ⚠️  {product['name']}: {result['error']}")
                continue

            price_str = f"{result['price']:.2f} {currency}" if result["price"] else "N/A"
            status = "✅ IN STOCK" if result["in_stock"] else "❌ Out of stock"
            print(f"  {product['name']}: {status} | {price_str}")

            if result["in_stock"] and not prev.get("in_stock"):
                if not max_price or (result["price"] and result["price"] <= max_price):
                    alerts.append({
                        "type": "restock",
                        "store": f"Virgin Megastore (.{region})",
                        "name": product["name"],
                        "price": price_str,
                        "url": product["url"],
                    })

            if result["in_stock"] and prev.get("in_stock"):
                dropped, pct = check_price_drop(prev.get("price"), result.get("price"), threshold)
                if dropped:
                    alerts.append({
                        "type": "price_drop",
                        "store": f"Virgin Megastore (.{region})",
                        "name": product["name"],
                        "old_price": f"{prev['price']:.2f} {currency}",
                        "new_price": price_str,
                        "pct": round(pct, 1),
                        "url": product["url"],
                    })

            state[key] = result

    # ── Amazon (.ae / .com / .co.uk) ────────────────────────────
    AMAZON_REGIONS = {
        "amazon_ae": ("Amazon.ae", "AED"),
        "amazon_com": ("Amazon.com", "USD"),
        "amazon_co_uk": ("Amazon.co.uk", "GBP"),
    }
    for region_key, (store_label, currency) in AMAZON_REGIONS.items():
        amz_products = config.get("products", {}).get(region_key, [])
        if not amz_products:
            continue
        print(f"\n📦 Checking {store_label} ({len(amz_products)} product(s))...")
        for product in amz_products:
            result = check_amazon(product["url"], product["name"])
            key = f"{region_key}_{product['url']}"
            prev = state.get(key, {})
            max_price = product.get("max_price")

            if result.get("error"):
                print(f"  ⚠️  {product['name']}: {result['error']}")
                # Don't overwrite previous good state on error
                continue

            price_str = f"{result['price']:.2f} {currency}" if result["price"] else "N/A"
            status = "✅ IN STOCK" if result["in_stock"] else "❌ Out of stock"
            print(f"  {product['name']}: {status} | {price_str}")

            # Restock alert
            if result["in_stock"] and not prev.get("in_stock"):
                if not max_price or (result["price"] and result["price"] <= max_price):
                    alerts.append({
                        "type": "restock",
                        "store": store_label,
                        "name": product["name"],
                        "price": price_str,
                        "url": product["url"],
                    })

            # Price drop alert
            if result["in_stock"] and prev.get("in_stock"):
                dropped, pct = check_price_drop(prev.get("price"), result.get("price"), threshold)
                if dropped:
                    alerts.append({
                        "type": "price_drop",
                        "store": store_label,
                        "name": product["name"],
                        "old_price": f"{prev['price']:.2f} {currency}",
                        "new_price": price_str,
                        "pct": round(pct, 1),
                        "url": product["url"],
                    })

            state[key] = result

    # ── eBay ─────────────────────────────────────────────────────
    ebay_products = config.get("products", {}).get("ebay", [])
    if ebay_products:
        ebay_app_id = config.get("ebay", {}).get("app_id")
        if not ebay_app_id:
            print("\n🛒 eBay: Skipped (no App ID configured)")
        else:
            print(f"\n🛒 Checking eBay ({len(ebay_products)} search(es))...")
            for product in ebay_products:
                results = check_ebay(
                    keywords=product["keywords"],
                    max_price_usd=product.get("max_price_usd"),
                    condition=product.get("condition", "new"),
                    app_id=ebay_app_id,
                    ship_to_country=product.get("ship_to_country", "AE"),
                )
                key = f"ebay_{product['keywords']}"
                prev_ids = set(state.get(key, {}).get("item_ids", []))
                new_listings = [r for r in results if r["item_id"] not in prev_ids]

                print(f"  '{product['keywords']}': {len(results)} listing(s), {len(new_listings)} new")

                for listing in new_listings[:3]:  # Cap at 3 alerts per search per run
                    alerts.append({
                        "type": "ebay_listing",
                        "name": product["name"],
                        "title": listing["title"],
                        "price": f"${listing['price']:.2f}",
                        "condition": listing["condition"],
                        "seller": listing["seller"],
                        "url": listing["url"],
                    })

                state[key] = {"item_ids": [r["item_id"] for r in results]}

    # ── Send Alerts ───────────────────────────────────────────────
    print(f"\n{'=' * 60}")
    if not alerts:
        print("✅ No changes detected. No alerts sent.")
    else:
        print(f"🔔 Sending {len(alerts)} alert(s)...")
        for alert in alerts:
            if alert["type"] == "restock":
                msg = (
                    f"🟢 RESTOCK ALERT\n"
                    f"Store: {alert['store']}\n"
                    f"Product: {alert['name']}\n"
                    f"Price: {alert['price']}\n"
                    f"🔗 {alert['url']}"
                )
                embed = {
                    "title": f"🟢 Restock: {alert['name']}",
                    "description": f"**{alert['store']}** has this back in stock!",
                    "color": 0x2ECC71,
                    "fields": [
                        {"name": "Price", "value": alert["price"], "inline": True},
                        {"name": "Store", "value": alert["store"], "inline": True},
                    ],
                    "url": alert["url"],
                }
            elif alert["type"] == "price_drop":
                msg = (
                    f"📉 PRICE DROP\n"
                    f"Store: {alert['store']}\n"
                    f"Product: {alert['name']}\n"
                    f"{alert['old_price']} → {alert['new_price']} ({alert['pct']}% off)\n"
                    f"🔗 {alert['url']}"
                )
                embed = {
                    "title": f"📉 Price Drop: {alert['name']}",
                    "description": f"Price dropped by **{alert['pct']}%** on {alert['store']}",
                    "color": 0xE74C3C,
                    "fields": [
                        {"name": "Was", "value": alert["old_price"], "inline": True},
                        {"name": "Now", "value": alert["new_price"], "inline": True},
                        {"name": "Saving", "value": f"{alert['pct']}%", "inline": True},
                    ],
                    "url": alert["url"],
                }
            else:  # ebay_listing
                msg = (
                    f"🛒 NEW EBAY LISTING\n"
                    f"Search: {alert['name']}\n"
                    f"Title: {alert['title']}\n"
                    f"Price: {alert['price']} ({alert['condition']})\n"
                    f"Seller: {alert['seller']}\n"
                    f"🔗 {alert['url']}"
                )
                embed = {
                    "title": f"🛒 New eBay: {alert['name']}",
                    "description": alert["title"],
                    "color": 0x3498DB,
                    "fields": [
                        {"name": "Price", "value": alert["price"], "inline": True},
                        {"name": "Condition", "value": alert["condition"], "inline": True},
                        {"name": "Seller", "value": alert["seller"], "inline": True},
                    ],
                    "url": alert["url"],
                }
            send_alert(config, msg, embed)
            print(f"  ✉️  Sent: {alert['type']} — {alert.get('name', '')}")

    save_state(state)
    print("\n💾 State saved.")


if __name__ == "__main__":
    main()
