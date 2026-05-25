"""
eBay scraper using the official eBay Finding API.
No scraping needed — this is a free, legitimate API.

Sign up for a free App ID at:
https://developer.ebay.com/signin?tab=register
"""

import time
import requests

FINDING_API = "https://svcs.ebay.com/services/search/FindingService/v1"

CONDITION_MAP = {
    "new": "1000",
    "like_new": "1500",
    "used": "3000",
    "any": None,
}


def check_ebay(
    keywords: str,
    max_price_usd: float | None,
    condition: str,
    app_id: str,
    ship_to_country: str = "AE",
) -> list[dict]:
    """
    Search eBay for sealed TCG products.

    Returns a list of listings:
        [{"item_id", "title", "price", "condition", "seller", "url"}, ...]
    """
    if not app_id:
        return []

    params = {
        "OPERATION-NAME": "findItemsAdvanced",
        "SERVICE-VERSION": "1.0.0",
        "SECURITY-APPNAME": app_id,
        "RESPONSE-DATA-FORMAT": "JSON",
        "keywords": keywords,
        "sortOrder": "PricePlusShippingLowest",
        "paginationInput.entriesPerPage": "20",
        # Fixed price only (excludes auctions — better for restocks)
        "itemFilter(0).name": "ListingType",
        "itemFilter(0).value": "FixedPrice",
    }

    filter_idx = 1

    # Condition filter
    condition_code = CONDITION_MAP.get(condition.lower())
    if condition_code:
        params[f"itemFilter({filter_idx}).name"] = "Condition"
        params[f"itemFilter({filter_idx}).value"] = condition_code
        filter_idx += 1

    # Max price filter
    if max_price_usd:
        params[f"itemFilter({filter_idx}).name"] = "MaxPrice"
        params[f"itemFilter({filter_idx}).value"] = str(max_price_usd)
        params[f"itemFilter({filter_idx}).paramName"] = "Currency"
        params[f"itemFilter({filter_idx}).paramValue"] = "USD"
        filter_idx += 1

    # Ships to country filter
    if ship_to_country:
        params[f"itemFilter({filter_idx}).name"] = "AvailableTo"
        params[f"itemFilter({filter_idx}).value"] = ship_to_country
        filter_idx += 1

    try:
        time.sleep(0.5)
        resp = requests.get(FINDING_API, params=params, timeout=20)
        resp.raise_for_status()
        data = resp.json()

        search_result = data.get("findItemsAdvancedResponse", [{}])[0]
        ack = search_result.get("ack", ["Failure"])[0]
        if ack != "Success":
            error = search_result.get("errorMessage", [{}])[0].get("error", [{}])[0].get("message", ["Unknown"])[0]
            print(f"  ⚠️  eBay API error for '{keywords}': {error}")
            return []

        items = (
            search_result.get("searchResult", [{}])[0].get("item", [])
        )

        listings = []
        for item in items:
            try:
                listing = {
                    "item_id": item["itemId"][0],
                    "title": item["title"][0],
                    "price": float(item["sellingStatus"][0]["currentPrice"][0]["__value__"]),
                    "condition": item.get("condition", [{}])[0]
                        .get("conditionDisplayName", ["Unknown"])[0],
                    "seller": item["sellerInfo"][0]["sellerUserName"][0],
                    "url": item["viewItemURL"][0],
                }
                listings.append(listing)
            except (KeyError, IndexError, ValueError, TypeError):
                continue

        return listings

    except requests.exceptions.Timeout:
        print(f"  ⚠️  eBay API timeout for '{keywords}'")
        return []
    except Exception as e:
        print(f"  ⚠️  eBay API error for '{keywords}': {e}")
        return []
