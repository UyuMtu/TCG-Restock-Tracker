"""
Amazon scraper — supports amazon.ae, amazon.com, amazon.co.uk

Amazon actively fights scrapers, so this module uses several techniques:
  1. Realistic browser headers + session cookies
  2. Embedded JSON data in the page (more reliable than parsing HTML)
  3. Multiple CSS selector fallbacks for price + stock
  4. Detects CAPTCHAs and rate-limit pages gracefully (won't crash the run)

Currencies by domain:
  amazon.ae  → AED
  amazon.com → USD
  amazon.co.uk → GBP
"""

import json
import re
import time
import requests
from bs4 import BeautifulSoup

DOMAIN_CURRENCY = {
    "amazon.ae": "AED",
    "amazon.com": "USD",
    "amazon.co.uk": "GBP",
}

# Mimic a real Chrome browser as closely as possible
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;"
        "q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Cache-Control": "max-age=0",
    "Sec-Ch-Ua": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Windows"',
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
}


def _get_domain(url: str) -> str:
    """Extract the Amazon domain from a product URL."""
    for domain in DOMAIN_CURRENCY:
        if domain in url:
            return domain
    return "amazon.com"


def _is_blocked(soup: BeautifulSoup, text: str) -> bool:
    """Detect if Amazon served a CAPTCHA or robot-check page."""
    blocked_signals = [
        "api-services-support@amazon.com",
        "Enter the characters you see below",
        "Sorry, we just need to make sure you're not a robot",
        "Type the characters you see in this image",
        "robot check",
    ]
    return any(s.lower() in text.lower() for s in blocked_signals)


def _extract_price(soup: BeautifulSoup) -> float | None:
    """
    Try multiple strategies to find the price on an Amazon product page.
    Amazon changes their CSS class names frequently, so we try many selectors.
    """
    # Strategy 1: price inside corePriceDisplay_desktop_feature_div
    selectors = [
        {"id": "priceblock_ourprice"},
        {"id": "priceblock_dealprice"},
        {"id": "priceblock_saleprice"},
        {"class": "a-price-whole"},
        {"id": "corePrice_feature_div"},
        {"id": "corePriceDisplay_desktop_feature_div"},
        {"class": "priceToPay"},
    ]
    for attrs in selectors:
        el = soup.find(attrs=attrs)
        if el:
            # Extract digits from strings like "AED 249.00" or "£34.99"
            text = el.get_text(" ", strip=True)
            match = re.search(r"[\d,]+\.?\d{0,2}", text.replace(",", ""))
            if match:
                try:
                    return float(match.group().replace(",", ""))
                except ValueError:
                    continue

    # Strategy 2: JSON data embedded in the page (more reliable)
    for script in soup.find_all("script", type="text/javascript"):
        content = script.string or ""
        # Amazon often embeds price data in a JSON block
        match = re.search(r'"priceAmount"\s*:\s*([\d.]+)', content)
        if match:
            try:
                return float(match.group(1))
            except ValueError:
                pass

    return None


def _extract_stock(soup: BeautifulSoup, page_text: str) -> bool:
    """Determine if the product is in stock."""
    # Strong out-of-stock signals
    oos_signals = [
        "currently unavailable",
        "out of stock",
        "this item is not available",
        "we don't know when or if this item will be back in stock",
        "unavailable",
    ]
    if any(s in page_text.lower() for s in oos_signals):
        return False

    # Strong in-stock signals
    add_to_cart = (
        soup.find("input", {"id": "add-to-cart-button"})
        or soup.find("input", {"name": "submit.add-to-cart"})
        or soup.find("input", {"id": "buy-now-button"})
        or soup.find("span", string=re.compile(r"in stock", re.I))
    )
    return add_to_cart is not None


def check_amazon(url: str, name: str) -> dict:
    """
    Scrape an Amazon product page for stock status and price.

    Returns:
        {
            "name": str,
            "in_stock": bool,
            "price": float | None,
            "currency": str,
            "url": str,
            "error": str | None
        }
    """
    domain = _get_domain(url)
    currency = DOMAIN_CURRENCY.get(domain, "USD")

    # Use a session to carry cookies (helps avoid blocks)
    session = requests.Session()
    session.headers.update(HEADERS)

    try:
        time.sleep(2)  # Amazon needs a slightly longer delay between requests
        resp = session.get(url, timeout=25, allow_redirects=True)
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "lxml")
        page_text = resp.text

        # Check if we got blocked
        if _is_blocked(soup, page_text):
            return {
                "name": name,
                "in_stock": False,
                "price": None,
                "currency": currency,
                "url": url,
                "error": "CAPTCHA detected — Amazon blocked this request. Will retry next run.",
            }

        in_stock = _extract_stock(soup, page_text)
        price = _extract_price(soup)

        return {
            "name": name,
            "in_stock": in_stock,
            "price": price,
            "currency": currency,
            "url": url,
        }

    except requests.exceptions.HTTPError as e:
        return {
            "name": name, "in_stock": False, "price": None,
            "currency": currency, "url": url,
            "error": f"HTTP {e.response.status_code}",
        }
    except requests.exceptions.Timeout:
        return {
            "name": name, "in_stock": False, "price": None,
            "currency": currency, "url": url, "error": "Timeout",
        }
    except Exception as e:
        return {
            "name": name, "in_stock": False, "price": None,
            "currency": currency, "url": url, "error": str(e),
        }
