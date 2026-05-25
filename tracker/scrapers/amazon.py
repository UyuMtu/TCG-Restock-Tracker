"""
Amazon scraper — supports amazon.ae, amazon.com, amazon.co.uk

Uses multiple strategies to avoid CAPTCHA blocks:
  1. Realistic browser headers + session cookies
  2. Homepage visit first to establish a valid session
  3. Tries the mobile site as fallback (less protected)
  4. Extracts data from embedded JSON (more reliable than HTML parsing)
  5. Graceful CAPTCHA detection — won't crash the run
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

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
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

# Mobile user agent — Amazon's mobile site is less aggressively protected
MOBILE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) "
        "Version/17.0 Mobile/15E148 Safari/604.1"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
}


def _get_domain(url: str) -> str:
    for domain in DOMAIN_CURRENCY:
        if domain in url:
            return domain
    return "amazon.com"


def _get_base_url(url: str) -> str:
    domain = _get_domain(url)
    return f"https://www.{domain}"


def _is_blocked(text: str) -> bool:
    blocked_signals = [
        "api-services-support@amazon.com",
        "Enter the characters you see below",
        "Sorry, we just need to make sure you're not a robot",
        "Type the characters you see in this image",
        "robot check",
        "captcha",
    ]
    return any(s.lower() in text.lower() for s in blocked_signals)


def _extract_price(soup: BeautifulSoup) -> float | None:
    # Strategy 1: Common price element IDs and classes
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
            text = el.get_text(" ", strip=True)
            match = re.search(r"[\d,]+\.?\d{0,2}", text.replace(",", ""))
            if match:
                try:
                    return float(match.group().replace(",", ""))
                except ValueError:
                    continue

    # Strategy 2: JSON embedded in page scripts
    for script in soup.find_all("script", type="text/javascript"):
        content = script.string or ""
        match = re.search(r'"priceAmount"\s*:\s*([\d.]+)', content)
        if match:
            try:
                return float(match.group(1))
            except ValueError:
                pass

    # Strategy 3: Any span with a currency symbol
    for span in soup.find_all("span", class_=re.compile(r"price", re.I)):
        text = span.get_text(strip=True)
        match = re.search(r"[\d,]+\.?\d{0,2}", text.replace(",", ""))
        if match:
            try:
                val = float(match.group().replace(",", ""))
                if val > 0:
                    return val
            except ValueError:
                continue

    return None


def _extract_stock(soup: BeautifulSoup, page_text: str) -> bool:
    oos_signals = [
        "currently unavailable",
        "out of stock",
        "this item is not available",
        "we don't know when or if this item will be back in stock",
    ]
    if any(s in page_text.lower() for s in oos_signals):
        return False

    add_to_cart = (
        soup.find("input", {"id": "add-to-cart-button"})
        or soup.find("input", {"name": "submit.add-to-cart"})
        or soup.find("input", {"id": "buy-now-button"})
        or soup.find("span", string=re.compile(r"in stock", re.I))
    )
    return add_to_cart is not None


def _try_fetch(url: str, headers: dict) -> requests.Response | None:
    """Attempt to fetch a URL with given headers, returns None on failure."""
    try:
        session = requests.Session()
        session.headers.update(headers)

        # Visit homepage first to get cookies
        base_url = _get_base_url(url)
        try:
            session.get(base_url, timeout=10)
            time.sleep(1)
        except Exception:
            pass

        resp = session.get(url, timeout=25, allow_redirects=True)
        resp.raise_for_status()
        return resp
    except Exception:
        return None


def check_amazon(url: str, name: str) -> dict:
    domain = _get_domain(url)
    currency = DOMAIN_CURRENCY.get(domain, "USD")

    time.sleep(2)

    # Attempt 1: Desktop browser headers
    resp = _try_fetch(url, HEADERS)

    # Attempt 2: Mobile browser headers if desktop was blocked
    if resp is None or _is_blocked(resp.text):
        time.sleep(3)
        resp = _try_fetch(url, MOBILE_HEADERS)

    if resp is None:
        return {
            "name": name, "in_stock": False, "price": None,
            "currency": currency, "url": url,
            "error": "Failed to fetch page after 2 attempts",
        }

    if _is_blocked(resp.text):
        return {
            "name": name, "in_stock": False, "price": None,
            "currency": currency, "url": url,
            "error": "CAPTCHA detected — Amazon blocked this request. Will retry next run.",
        }

    soup = BeautifulSoup(resp.text, "lxml")
    in_stock = _extract_stock(soup, resp.text)
    price = _extract_price(soup)

    return {
        "name": name,
        "in_stock": in_stock,
        "price": price,
        "currency": currency,
        "url": url,
    }
