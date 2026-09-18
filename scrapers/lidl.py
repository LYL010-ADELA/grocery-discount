"""Lidl Switzerland: offers are server-rendered into the page.

Every product tile carries a `data-grid-data="{...}"` attribute holding
HTML-escaped JSON with title, price, deleted price, discount percentage,
image and product URL. No API call and no headless browser required.
"""
from __future__ import annotations

import datetime as _dt
import html as _html
import json
import re
import time

import requests

from .base import Offer, USER_AGENT, clean_text, parse_percent, parse_price
from .categorize import categorize

BASE = "https://www.lidl.ch"
RETAILER = "Lidl"

# The weekly leaflet is split across a few landing pages.
OFFER_PAGES = [
    ("/c/de-CH/wochenaktion/a10102783", "Weekly offer"),
    ("/c/de-CH/super-wochenende/a10102782", "Weekend offer"),
    ("/c/de-CH/lidl-plus-angebote/a10020520", "Lidl Plus (app required)"),
]

_GRID = re.compile(r'data-grid-data="([^"]+)"')


def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update(
        {
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "de-CH,de;q=0.9,en;q=0.8",
        }
    )
    return s


def _ts_to_date(ts) -> str:
    try:
        return _dt.datetime.fromtimestamp(int(ts)).date().isoformat()
    except (TypeError, ValueError):
        return ""


def _subtitle(rec: dict) -> str:
    """Lidl puts pack size / variety in a few different places."""
    for key in ("keyfacts", "description", "subtitle"):
        v = rec.get(key)
        if isinstance(v, str) and v.strip():
            return clean_text(v)
        if isinstance(v, dict):
            for sub in ("supplementalDescription", "description", "fullTitle"):
                if isinstance(v.get(sub), str) and v[sub].strip():
                    return clean_text(v[sub])
    return ""


def _to_offer(rec: dict, note: str) -> Offer | None:
    title = clean_text(rec.get("fullTitle") or rec.get("title") or "")
    pid = rec.get("productId")
    if not title or not pid:
        return None

    price_block = rec.get("price") or {}
    notes = [note] if note else []

    # Some tiles carry no shelf price because the deal is app-only; the real
    # figures then sit under `lidlPlus`.
    if parse_price(price_block.get("price")) is None:
        plus = rec.get("lidlPlus") or []
        if plus and isinstance(plus[0], dict) and plus[0].get("price"):
            price_block = plus[0]["price"]
            if "Lidl Plus app price" not in notes:
                notes.append("Lidl Plus app price")
    if not price_block:
        return None

    now = parse_price(price_block.get("price"))
    was = parse_price(price_block.get("oldPrice"))
    disc = price_block.get("discount") or {}
    if was is None:
        was = parse_price(disc.get("deletedPrice"))

    pct = disc.get("percentageDiscount")
    pct = int(pct) if isinstance(pct, (int, float)) and pct else None
    if pct is None:
        # app-only deals express the reduction as text, e.g. "-28%"
        pct = parse_percent(disc.get("discountText") or "")

    brand = rec.get("brand") or {}
    brand_name = clean_text(brand.get("name", "")) if isinstance(brand, dict) else ""
    if brand_name and not title.lower().startswith(brand_name.lower()):
        title = f"{brand_name} {title}"

    url = rec.get("canonicalUrl") or ""
    if url.startswith("/"):
        url = BASE + url

    sub = _subtitle(rec)
    return Offer(
        retailer=RETAILER,
        id=f"lidl-{pid}",
        name=title,
        subtitle=sub,
        category=categorize(title, sub),
        price=now,
        was_price=was,
        discount_pct=pct,
        note="; ".join(dict.fromkeys(notes)),
        valid_from=_ts_to_date(rec.get("storeStartDate")),
        valid_to=_ts_to_date(rec.get("storeEndDate")),
        image=rec.get("image") or "",
        url=url or BASE,
    ).finalise()


def _scrape_page(s: requests.Session, path: str, note: str) -> list[Offer]:
    try:
        r = s.get(BASE + path, timeout=40)
        r.raise_for_status()
    except requests.RequestException as e:
        print(f"  [Lidl] {path} failed: {e}")
        return []

    offers: list[Offer] = []
    for blob in _GRID.findall(r.text):
        try:
            rec = json.loads(_html.unescape(blob))
        except json.JSONDecodeError:
            continue
        if isinstance(rec, dict):
            o = _to_offer(rec, note)
            if o:
                offers.append(o)
    return offers


def scrape() -> list[Offer]:
    s = _session()
    offers: list[Offer] = []
    seen: set[str] = set()
    for path, note in OFFER_PAGES:
        page = _scrape_page(s, path, note)
        # Lidl repeats hero products across landing pages.
        fresh = [o for o in page if o.id not in seen]
        seen.update(o.id for o in fresh)
        offers += fresh
        print(f"  [Lidl] {len(fresh):3d} offers from {path}")
        time.sleep(0.5)  # be polite
    return offers


if __name__ == "__main__":
    res = scrape()
    for o in res[:8]:
        d = o.as_dict()
        print(f"{str(d.get('discount_pct','-')):>3}% {str(d.get('price','-')):>6} "
              f"(was {d.get('was_price','-')}) {d['category'][:18]:18} {d['name'][:40]}")
    print("total:", len(res))
