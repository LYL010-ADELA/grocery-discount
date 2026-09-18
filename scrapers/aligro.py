"""Aligro: a cash & carry wholesaler, French-first, plain server-rendered HTML.

Each `/actions/...` page carries a `pagination="{...}"` attribute holding
HTML-escaped JSON with up to 48 article records, prices included. Paging is
client-side, so instead of chasing it we walk the ~100 sub-category pages
listed on /actions, which also hands us Aligro's own category wording.

Note for shoppers: Aligro sells in catering pack sizes (2 kg bags, 6-packs).
Offers are tagged accordingly in the UI.
"""
from __future__ import annotations

import html as _html
import json
import re
import time

import requests

from .base import Offer, USER_AGENT, clean_text
from .categorize import categorize

BASE = "https://www.aligro.ch"
ACTIONS = f"{BASE}/actions"
RETAILER = "Aligro"

_PAGINATION = re.compile(r'pagination="(\{&quot;[^"]+)"')
# Aligro serves its own "image indisponible" graphic for articles without a
# photo; drop it so the site falls back to the category glyph instead.
_NO_IMAGE = re.compile(r"/build/missing-picture", re.I)
_CAT_LINK = re.compile(r'href="(/actions/(\d{4})-[a-z0-9-]+)"')
_WINDOW = re.compile(
    r'actions-start-date="([\d-]+)[^"]*"\s*\n?\s*actions-end-date="([\d-]+)'
)


def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update(
        {
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "fr-CH,fr;q=0.9,de;q=0.8,en;q=0.7",
        }
    )
    return s


def _pagination(page_html: str) -> dict:
    m = _PAGINATION.search(page_html)
    if not m:
        return {}
    try:
        return json.loads(_html.unescape(m.group(1)))
    except json.JSONDecodeError:
        return {}


def _text(item: dict, key: str) -> str:
    tr = (item.get("translations") or {}).get("fr") or {}
    return clean_text(tr.get(key) or "")


def _to_offer(item: dict, valid_from: str, valid_to: str) -> Offer | None:
    sku = item.get("sKU") or item.get("id")
    name = _text(item, "description") or _text(item, "advertisingText")
    if not sku or not name:
        return None

    p = item.get("mainArticleDetailPrice") or {}
    # TTC = incl. VAT, which is what a private shopper actually pays.
    was = p.get("unitPriceWithoutDiscountTTC") or p.get("salesPriceTTC")
    now = p.get("unitPriceTTC") or p.get("discountPriceTTC")
    was = round(float(was), 2) if isinstance(was, (int, float)) else None
    now = round(float(now), 2) if isinstance(now, (int, float)) else None
    if was is not None and now is not None and was <= now:
        was = None

    rate = p.get("discountRatePrivate")
    pct = round(float(rate) * 100) if isinstance(rate, (int, float)) and rate else None

    group = ((item.get("article") or {}).get("articleGroup") or {})
    native = clean_text(
        ((group.get("translations") or {}).get("fr") or {}).get("wording") or ""
    )

    img = ((item.get("images") or {}).get("main") or {})
    image = img.get("image/jpeg") or img.get("image/webp") or ""
    if _NO_IMAGE.search(image):
        image = ""

    qty = _text(item, "quantityLabel") or _text(item, "weightVolume")
    brand = _text(item, "brand")
    if brand and not name.lower().startswith(brand.lower()):
        name = f"{brand} {name}"

    notes = ["Wholesale pack"]
    if p.get("nextWeek"):
        notes.append("Starts next week")

    return Offer(
        retailer=RETAILER,
        id=f"aligro-{sku}",
        name=name,
        subtitle=_text(item, "advertisingText") if _text(item, "advertisingText") != name else "",
        category=categorize(name, native, native=native),
        price=now,
        was_price=was,
        discount_pct=pct,
        unit=qty,
        note="; ".join(notes),
        valid_from=valid_from,
        valid_to=valid_to,
        image=image,
        url=((item.get("href") or {}).get("self") or ACTIONS),
    ).finalise()


def scrape(max_categories: int | None = None) -> list[Offer]:
    s = _session()
    try:
        root = s.get(ACTIONS, timeout=40)
        root.raise_for_status()
    except requests.RequestException as e:
        print(f"  [Aligro] index failed: {e}")
        return []

    w = _WINDOW.search(root.text)
    valid_from, valid_to = (w.group(1), w.group(2)) if w else ("", "")

    cats = sorted({m.group(1) for m in _CAT_LINK.finditer(root.text)})
    if max_categories:
        cats = cats[:max_categories]
    print(f"  [Aligro] walking {len(cats)} sub-categories")

    offers: list[Offer] = []
    seen: set[str] = set()
    for i, path in enumerate(cats, 1):
        try:
            r = s.get(BASE + path, timeout=40)
            r.raise_for_status()
        except requests.RequestException as e:
            print(f"  [Aligro] {path} failed: {e}")
            continue
        data = _pagination(r.text)
        for item in data.get("items") or []:
            o = _to_offer(item, valid_from, valid_to)
            if o and o.id not in seen:
                seen.add(o.id)
                offers.append(o)
        if i % 25 == 0:
            print(f"  [Aligro] {i}/{len(cats)} categories, {len(offers)} offers")
        time.sleep(0.3)  # be polite

    print(f"  [Aligro] {len(offers)} offers")
    return offers


if __name__ == "__main__":
    res = scrape(max_categories=6)
    for o in res[:8]:
        d = o.as_dict()
        print(f"{str(d.get('discount_pct','-')):>3}% {str(d.get('price','-')):>6} "
              f"(was {d.get('was_price','-')}) {d['category'][:18]:18} {d['name'][:40]}")
    print("total:", len(res))
