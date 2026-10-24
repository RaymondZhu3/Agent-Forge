"""Clearly labeled local demo fixtures.

Used ONLY when credentials are missing or *_MOCK=1. Every result built from these
is returned with fixture=True so the UI can label it "Demo data" and never
present it as a live API call. Shapes mirror the real API responses so the same
normalizers run on both.
"""

from __future__ import annotations

from typing import Any

# ---------------- SerpApi raw responses (same shape as serpapi.com/search.json) ----------------

_SHOPPING: dict[str, list[dict[str, Any]]] = {
    "airpods": [
        {"title": "Apple AirPods Pro 2 (USB-C)", "source": "Best Buy", "extracted_price": 199.99, "product_link": "https://www.bestbuy.com/"},
        {"title": "Apple AirPods Pro 2 (USB-C)", "source": "Amazon.com", "extracted_price": 189.99, "product_link": "https://www.amazon.com/"},
        {"title": "Apple AirPods Pro 2 (USB-C)", "source": "Target", "extracted_price": 249.00, "product_link": "https://www.target.com/"},
        {"title": "Apple AirPods Pro 2 (USB-C)", "source": "Walmart", "extracted_price": 194.00, "product_link": "https://www.walmart.com/"},
    ],
    "stanley": [
        {"title": "Stanley Quencher H2.0 FlowState Tumbler 40 oz", "source": "Amazon.com", "extracted_price": 35.00, "product_link": "https://www.amazon.com/"},
        {"title": "Stanley Quencher H2.0 FlowState Tumbler 40 oz", "source": "Dick's Sporting Goods", "extracted_price": 45.00, "product_link": "https://www.dickssportinggoods.com/"},
        {"title": "Simple Modern 40 oz Tumbler with Handle", "source": "Target", "extracted_price": 24.99, "product_link": "https://www.target.com/"},
    ],
    "mx master": [
        {"title": "Logitech MX Master 3S Wireless Mouse", "source": "Best Buy", "extracted_price": 89.99, "product_link": "https://www.bestbuy.com/"},
        {"title": "Logitech MX Master 3S Wireless Mouse", "source": "Amazon.com", "extracted_price": 84.99, "product_link": "https://www.amazon.com/"},
        {"title": "Logitech MX Master 3S Wireless Mouse", "source": "Logitech", "extracted_price": 109.99, "product_link": "https://www.logitech.com/"},
    ],
}

_NEWS = [
    {"title": "Chipmakers race to expand advanced packaging capacity", "source": {"name": "Demo Wire"}, "date": "10/23/2026", "link": "https://example.com/news/packaging", "snippet": "Demo fixture article."},
    {"title": "Cloud providers announce new AI data center sites", "source": {"name": "Demo Times"}, "date": "10/22/2026", "link": "https://example.com/news/datacenters", "snippet": "Demo fixture article."},
    {"title": "Memory prices climb as AI demand grows", "source": {"name": "Demo Journal"}, "date": "10/21/2026", "link": "https://example.com/news/memory", "snippet": "Demo fixture article."},
]

_WEB = [
    {"title": "Demo search result", "link": "https://example.com/", "snippet": "This is a labeled demo fixture, not a live search result."},
]

_LOCAL = [
    {"title": "Best Buy (demo)", "address": "Austin, TX", "rating": 4.3, "reviews": 1200, "type": "Electronics store", "hours": "Open ⋅ Closes 9 PM"},
    {"title": "Target (demo)", "address": "Austin, TX", "rating": 4.2, "reviews": 900, "type": "Department store", "hours": "Open ⋅ Closes 10 PM"},
]


def serp_fixture(engine: str, query: str) -> dict[str, Any]:
    q = query.lower()
    if engine == "google_shopping":
        for key, rows in _SHOPPING.items():
            if key in q:
                return {"shopping_results": rows}
        return {"shopping_results": []}
    if engine == "google_news":
        return {"news_results": _NEWS}
    if engine == "google":
        return {"organic_results": _WEB}
    if engine == "google_local":
        return {"local_results": _LOCAL}
    return {}


# ---------------- Nessie (same shapes as the Nessie REST API) ----------------

DEMO_CUSTOMER = {"_id": "demo_customer_maria", "first_name": "Maria", "last_name": "Lopez"}

DEMO_ACCOUNTS = [
    {"_id": "demo_acct_checking", "type": "Checking", "nickname": "Everyday Checking", "balance": 2140.55, "customer_id": "demo_customer_maria"},
    {"_id": "demo_acct_credit", "type": "Credit Card", "nickname": "Quicksilver", "balance": 612.30, "customer_id": "demo_customer_maria"},
]

DEMO_MERCHANTS = {
    "m_target": "Target",
    "m_starbucks": "Starbucks",
    "m_ubereats": "Uber Eats",
    "m_amazon": "Amazon",
    "m_heb": "H-E-B",
}

DEMO_PURCHASES = {
    "demo_acct_credit": [
        {"description": "AirPods Pro 2", "amount": 249.00, "merchant_id": "m_target", "purchase_date": "2026-10-02"},
        {"description": "Stanley Quencher Tumbler 40 oz", "amount": 45.00, "merchant_id": "m_target", "purchase_date": "2026-10-05"},
        {"description": "Logitech MX Master 3S", "amount": 109.99, "merchant_id": "m_amazon", "purchase_date": "2026-09-28"},
        {"description": "Uber Eats order", "amount": 32.40, "merchant_id": "m_ubereats", "purchase_date": "2026-10-10"},
        {"description": "Uber Eats order", "amount": 28.15, "merchant_id": "m_ubereats", "purchase_date": "2026-10-14"},
        {"description": "Uber Eats order", "amount": 36.80, "merchant_id": "m_ubereats", "purchase_date": "2026-10-19"},
    ],
    "demo_acct_checking": [
        {"description": "Coffee", "amount": 6.45, "merchant_id": "m_starbucks", "purchase_date": "2026-10-07"},
        {"description": "Coffee", "amount": 7.10, "merchant_id": "m_starbucks", "purchase_date": "2026-10-09"},
        {"description": "Coffee", "amount": 5.95, "merchant_id": "m_starbucks", "purchase_date": "2026-10-13"},
        {"description": "Coffee", "amount": 6.45, "merchant_id": "m_starbucks", "purchase_date": "2026-10-16"},
        {"description": "Groceries", "amount": 84.22, "merchant_id": "m_heb", "purchase_date": "2026-10-12"},
    ],
}

DEMO_BILLS = {
    "demo_acct_checking": [
        {"payee": "Netflix", "nickname": "Netflix Premium", "payment_amount": 24.99, "recurring_date": 3, "status": "recurring"},
        {"payee": "Spotify", "nickname": "Spotify Premium", "payment_amount": 11.99, "recurring_date": 12, "status": "recurring"},
        {"payee": "AT&T", "nickname": "Phone plan", "payment_amount": 85.00, "recurring_date": 20, "status": "recurring"},
    ],
}
