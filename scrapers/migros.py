"""Migros: internal JSON API, no headless browser needed.

Endpoints were confirmed by intercepting the requests the real offers page
(migros.ch/en/offers/home) makes:

  1. GET  /authentication/public/v1/api/guest
         -> `leshopch` response header, used as a bearer-style header
  2. GET  /product-display/public/v1/promotions/instore/{new,weekend,personalized}
         -> the ids of this week's in-store promotions
  3. POST /product-display/public/v4/product-cards        (type PRODUCT)
         -> name, regular price, promotion price, badges, dates, category
  4. GET  /product-display/public/v2/promotions-details/   (type GROUP_PROMOTION)
         -> range deals ("whole X assortment"), priced via an example in the
            German discount hint

The feed mixes both types: single products and group promotions ("whole
Maybelline range, -50%"). Handling only the first kind loses most of the deals.

Note on coverage: there is a richer endpoint, /products/promotion/search, that
lists roughly four times as many promotions. Migros' robots.txt disallows
`*/promotion/`, which that path matches, so this scraper does not use it - and
does not reconstruct the same list through another door either. The instore
endpoints below are explicitly not disallowed. scripts/check_robots.py enforces
this.
"""
from __future__ import annotations

import datetime as _dt
import re
import time

import requests

from .base import Offer, USER_AGENT, clean_text, parse_percent, parse_price
from .categorize import categorize

BASE = "https://www.migros.ch"
AUTH = f"{BASE}/authentication/public/v1/api/guest"
INSTORE = BASE + "/product-display/public/v1/promotions/instore/{kind}"
CARDS = f"{BASE}/product-display/public/v4/product-cards"
DETAILS = BASE + "/product-display/public/v2/promotions-details/{ids}"

# "national" covers every cooperative. Regional codes (gmzh Zürich, gmaa Aare,
# gmvd Vaud, gmge Genève, gmos Ostschweiz, ...) return cooperative-only prices.
DEFAULT_REGION = "national"

# The three in-store feeds overlap; together they are the week's promotions.
INSTORE_KINDS = ("new", "weekend", "personalized")
CARD_BATCH = 40     # uids per product-cards call
RETAILER = "Migros"


def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update(
        {
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
            "Accept-Language": "en-US,en;q=0.9,de;q=0.8",
            "Origin": BASE,
            "Referer": f"{BASE}/en/offers/home",
        }
    )
    r = s.get(AUTH, timeout=30)
    r.raise_for_status()
    token = r.headers.get("leshopch")
    if not token:
        raise RuntimeError("Migros guest auth returned no leshopch header")
    s.headers["leshopch"] = token
    return s


def _promotion_ids(s: requests.Session, region: str) -> tuple[list[int], list[str]]:
    """Return (product uids, group-promotion ids) for the current week."""
    products: list[int] = []
    groups: list[str] = []
    seen: set[str] = set()

    for kind in INSTORE_KINDS:
        try:
            r = s.get(
                INSTORE.format(kind=kind),
                params={"region": region, "language": "en"},
                timeout=30,
            )
            r.raise_for_status()
            items = r.json().get("items") or []
        except (requests.RequestException, ValueError) as e:
            print(f"  [Migros] instore/{kind} failed: {e}")
            continue

        for it in items:
            if not isinstance(it, dict):
                continue
            raw, sort = it.get("id"), it.get("type")
            key = f"{sort}:{raw}"
            if raw is None or key in seen:
                continue
            seen.add(key)
            if sort == "GROUP_PROMOTION":
                groups.append(str(raw))
            else:
                products.append(int(raw))
        time.sleep(0.4)  # be polite

    return products, groups


# rokka serves images from named stacks; "w400" is not one of them and 404s.
IMAGE_STACK = "mo-custom/v-w-400-h-340"


def _img(card: dict) -> str:
    for key in ("images", "imageTransparent"):
        v = card.get(key)
        entry = v[0] if isinstance(v, list) and v else v
        if isinstance(entry, dict) and entry.get("url"):
            return str(entry["url"]).replace("{stack}", IMAGE_STACK)
    return ""


def _to_offer(card: dict) -> Offer | None:
    offer = card.get("offer") or {}
    if not offer:
        return None

    uid = card.get("uid") or card.get("migrosId")
    name = clean_text(card.get("name") or card.get("title") or "")
    if not uid or not name:
        return None

    brand = clean_text(card.get("brand") or "")
    if brand and not name.lower().startswith(brand.lower()):
        name = f"{brand} {name}"

    def _val(block) -> float | None:
        if isinstance(block, dict):
            v = block.get("effectiveValue", block.get("advertisedValue"))
            if isinstance(v, (int, float)):
                return round(float(v), 2)
        return None

    was = _val(offer.get("price"))
    now = _val(offer.get("promotionPrice"))
    # Some entries only carry a single price (e.g. multibuy deals).
    if now is None and was is not None:
        now, was = was, None
    if was is not None and now is not None and was <= now:
        was = None  # not actually a reduction

    pct = None
    notes = []
    for b in offer.get("badges") or []:
        text = clean_text(b.get("description") or b.get("rawDescription") or "")
        if b.get("type") == "PERCENTAGE_PROMOTION" and pct is None:
            pct = parse_percent(text)
        elif text:
            notes.append(text)

    crumbs = [c.get("name", "") for c in card.get("breadcrumb") or [] if c.get("name")]
    native = crumbs[0] if crumbs else ""

    rng = offer.get("promotionDateRange") or {}
    desc = clean_text(card.get("description") or "")

    return Offer(
        retailer=RETAILER,
        id=f"migros-{uid}",
        name=name,
        subtitle=desc if desc.lower() != name.lower() else "",
        category=categorize(name, desc, " ".join(crumbs), native=native),
        price=now,
        was_price=was,
        discount_pct=pct,
        unit=clean_text(offer.get("quantity") or ""),
        note="; ".join(notes),
        valid_from=str(rng.get("startDate") or ""),
        valid_to=str(rng.get("endDate") or ""),
        image=_img(card),
        url=str(card.get("productUrls") or f"{BASE}/en/promotions"),
    ).finalise()


# Group promotions quote an example, e.g. "z.B. Mascara ..., 9.98 statt 19.95".
_STATT = re.compile(
    r"(\d+[.,]\d{2})\s*(?:statt|au lieu de|instead of)\s*(\d+[.,]\d{2})", re.I
)


def _group_to_offer(p: dict) -> Offer | None:
    pid = str(p.get("id") or "")
    name = clean_text(p.get("description") or "")
    if not pid or not name:
        return None

    pct, notes = None, []
    for b in p.get("badges") or []:
        text = clean_text(b.get("description") or b.get("rawDescription") or "")
        if b.get("type") == "PERCENTAGE_PROMOTION" and pct is None:
            pct = parse_percent(text)
        elif text:
            notes.append(text)

    hint_raw = p.get("discountHint") or ""
    hint = clean_text(hint_raw)
    m = _STATT.search(hint_raw)
    price = parse_price(m.group(1)) if m else None
    was = parse_price(m.group(2)) if m else None

    cats = p.get("categories") or []
    native = cats[0].get("name", "") if cats else ""
    img = p.get("image") or {}
    image = str(img.get("url", "")).replace("{stack}", IMAGE_STACK) if img.get("url") else ""

    return Offer(
        retailer=RETAILER,
        id=f"migros-grp-{pid}",
        name=name,
        subtitle=hint,
        category=categorize(name, hint, native, native=native),
        price=price,
        was_price=was,
        discount_pct=pct,
        note="; ".join(notes),
        valid_from=str(p.get("startDate") or ""),
        valid_to=str(p.get("endDate") or ""),
        image=image,
        url=f"{BASE}/en/promotions",
    ).finalise()


def _scrape_groups(s: requests.Session, ids: list[str], region: str) -> list[Offer]:
    offers: list[Offer] = []
    for i in range(0, len(ids), CARD_BATCH):
        batch = ids[i : i + CARD_BATCH]
        try:
            r = s.get(
                DETAILS.format(ids=",".join(batch)),
                params={"language": "en", "region": region},
                timeout=40,
            )
            r.raise_for_status()
            payload = r.json()
        except (requests.RequestException, ValueError) as e:
            print(f"  [Migros] promotions-details batch failed: {e}")
            continue
        for p in payload if isinstance(payload, list) else []:
            o = _group_to_offer(p)
            if o:
                offers.append(o)
        time.sleep(0.4)
    return offers


def scrape(region: str = DEFAULT_REGION) -> list[Offer]:
    s = _session()
    uids, group_ids = _promotion_ids(s, region)
    print(f"  [Migros] {len(uids)} products + {len(group_ids)} group promotions "
          f"(region={region})")

    today = _dt.date.today().isoformat() + "T00:00:00"
    offers: list[Offer] = []
    for i in range(0, len(uids), CARD_BATCH):
        batch = uids[i : i + CARD_BATCH]
        body = {
            "offerFilter": {
                "storeType": "OFFLINE",
                "region": region,
                "ongoingOfferDate": today,
            },
            "productFilter": {"uids": batch},
        }
        try:
            r = s.post(CARDS, json=body, timeout=40)
            r.raise_for_status()
            payload = r.json()
        except (requests.RequestException, ValueError) as e:
            print(f"  [Migros] product-cards batch failed: {e}")
            continue

        cards = payload if isinstance(payload, list) else list(payload.values())
        for card in cards:
            if isinstance(card, dict):
                o = _to_offer(card)
                if o:
                    offers.append(o)
        time.sleep(0.4)  # be polite

    offers += _scrape_groups(s, group_ids, region)
    print(f"  [Migros] {len(offers)} offers parsed")
    return offers


if __name__ == "__main__":
    res = scrape()
    for o in res[:6]:
        d = o.as_dict()
        print(f"{d.get('discount_pct','?'):>3}% {d['price']:>6} (was {d.get('was_price','-')}) "
              f"{d['category'][:18]:18} {d['name'][:45]}")
    print("total:", len(res))
