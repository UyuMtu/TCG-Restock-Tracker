"""
Telegram notifier via Bot API.
Free, instant, and works perfectly in the Gulf region.

How to set up your Telegram bot:
1. Open Telegram and message @BotFather
2. Send /newbot and follow the prompts
3. BotFather gives you a TOKEN — save it as TELEGRAM_BOT_TOKEN in GitHub Secrets

How to get your Chat ID:
1. Start your bot (send it any message)
2. Visit: https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates
3. Find "chat" → "id" in the JSON response
4. Save it as TELEGRAM_CHAT_ID in GitHub Secrets

For a group/channel: add the bot as an admin and use the group's chat ID.
"""

import requests


def send_telegram_alert(bot_token: str, chat_id: str, message: str):
    """
    Send a Markdown-formatted message via Telegram.

    Telegram supports basic Markdown:
    *bold*, _italic_, `code`, [link text](url)
    """
    # Convert plain alerts to Telegram-friendly Markdown
    # Replace Discord ** bold with Telegram * bold
    tg_message = message.replace("**", "*")

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": tg_message,
        "parse_mode": "Markdown",
        "disable_web_page_preview": False,  # Shows a link preview for the product URL
    }

    try:
        resp = requests.post(url, json=payload, timeout=10)
        resp.raise_for_status()
    except requests.exceptions.HTTPError as e:
        print(f"  ⚠️  Telegram alert failed (HTTP {e.response.status_code}): {e.response.text[:200]}")
    except Exception as e:
        print(f"  ⚠️  Telegram alert failed: {e}")
