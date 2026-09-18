"""Denner: the JSON endpoint its own offers page paginates against.

  POST https://www.denner.ch/nuxt-api/promotions
  {"lang":"de","promoFlag":"promo_current_week","page":1,"hitsPerPage":24, ...}

Each item is an attribute bag; everything useful (name, price, reference
price, discount %, validity window, native category) lives in `attributeInfo`.
`promoFlag` also accepts `promo_next_week`, which is how we preview the deals
that start next Tuesday.
"""
from __future__ import annotations

import datetime as _dt
import time

import requests

from .base import Offer, USER_AGENT, clean_text, parse_percent, parse_price
from .categorize import categorize

BASE = "https://www.denner.ch"
API = f"{BASE}/nuxt-api/promotions"
PAGE_SIZE = 24          # the site's own page size; larger values are ignored
MAX_PAGES = 40          # safety stop
RETAILER = "Denner"


def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update(
        {
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Origin": BASE,
            "Referer": f"{BASE}/de/aktionen/aktuelle-aktionen",
        }
    )
    return s


def _attrs(item: dict) -> dict[str, str]:
    """Flatten the attributeInfo bag into {name: first value}."""
    out: dict[str, str] = {}
    for a in item.get("attributeInfo") or []:
        name = a.get("attributeName")
        vals = a.get("vals") or []
        if name and vals:
            out[name] = str(vals[0].get("value", ""))
    return out


def _ts_to_date(raw: str) -> str:
    try:
        return _dt.datetime.fromtimestamp(int(raw)).date().isoformat()
    except (TypeError, ValueError):
        return ""


def _to_offer(item: dict, upcoming: bool) -> Offer | None:
    a = _attrs(item)
    name = clean_text(a.get("name") or a.get("_tracking_item_name") or "")
    sku = a.get("articleId") or item.get("sku") or ""
    if not name or not sku:
        return None

    price = parse_price(a.get("price") or item.get("price"))
    # `standardPrice` equals `price` unless there is a real reduction; the
    # pre-discount figure is then in insteadPriceText ("statt 19.95").
    was = parse_price(a.get("insteadPriceText")) or None
    std = parse_price(a.get("standardPrice"))
    if was is None and std is not None and price is not None and std > price:
        was = std

    pct = parse_percent(a.get("discount_percent")) if a.get("has_discount") == "true" else None
    if pct is None:
        pct = parse_percent(a.get("discount_percent") or "")

    notes = []
    for key in ("discount_text", "extraDiscountBadgeLabel", "footnote"):
        v = clean_text(a.get(key) or "")
        # "SPECIAL" is Denner's generic flag and adds nothing for the reader.
        if v and v.upper() != "SPECIAL":
            notes.append(v)

    url = a.get("itemUrl") or a.get("canonical") or ""
    if url.startswith("/"):
        url = BASE + url

    native = a.get("_tracking_item_category2") or ""
    subtitle = clean_text(a.get("nameSubline") or "")

    return Offer(
        retailer=RETAILER,
        id=f"denner-{sku}" + ("-next" if upcoming else ""),
        name=name,
        subtitle=subtitle,
        category=categorize(name, subtitle, native, native=native),
        price=price,
        was_price=was,
        discount_pct=pct,
        unit=clean_text(a.get("content_size_text") or ""),
        note="; ".join(dict.fromkeys(notes)),
        valid_from=_ts_to_date(a.get("promotionFrom", "")),
        valid_to=_ts_to_date(a.get("promotionTo", "")),
        image=a.get("imageUrl") or a.get("thumbnailUrl") or "",
        url=url or f"{BASE}/de/aktionen/aktuelle-aktionen",
    ).finalise()


def _fetch_flag(s: requests.Session, flag: str) -> list[Offer]:
    upcoming = flag == "promo_next_week"
    offers: list[Offer] = []
    for page in range(1, MAX_PAGES + 1):
        body = {
            "lang": "de",
            "promoFlag": flag,
            "facetName": None,
            "facetValue": None,
            "page": page,
            "hitsPerPage": PAGE_SIZE,
            "sort": None,
            "includeHighlights": False,
        }
        try:
            r = s.post(API, json=body, timeout=40)
            r.raise_for_status()
            items = r.json().get("items") or []
        except (requests.RequestException, ValueError) as e:
            print(f"  [Denner] page {page} failed: {e}")
            break
        if not items:
            break
        for it in items:
            o = _to_offer(it, upcoming)
            if o:
                offers.append(o)
        if len(items) < PAGE_SIZE:
            break
        time.sleep(0.4)  # be polite
    return offers


def scrape(include_next_week: bool = True) -> list[Offer]:
    s = _session()
    offers = _fetch_flag(s, "promo_current_week")
    print(f"  [Denner] {len(offers)} current-week offers")
    if include_next_week:
        nxt = _fetch_flag(s, "promo_next_week")
        print(f"  [Denner] {len(nxt)} next-week offers")
        offers += nxt
    return offers


if __name__ == "__main__":
    res = scrape()
    for o in res[:8]:
        d = o.as_dict()
        print(f"{str(d.get('discount_pct','-')):>3}% {str(d.get('price','-')):>6} "
              f"(was {d.get('was_price','-')}) {d['category'][:18]:18} {d['name'][:42]}")
    print("total:", len(res))
