"""Coop: manual entry.

coop.ch sits behind DataDome, a commercial anti-bot service that fingerprints
the client and serves a CAPTCHA challenge. Getting past it would mean forging
device fingerprints and wiring up a CAPTCHA solver — that is circumventing an
access control the retailer deliberately runs, so this project does not do it.

Instead Coop offers are typed into `data/coop_manual.json` from the printed
weekly flyer or the app, and merged in like any other source. Twenty minutes
a week covers the deals worth comparing.

Schema (every field optional except name and price):

  {
    "valid_from": "2026-09-16",
    "valid_to":   "2026-09-22",
    "offers": [
      {
        "name":     "Rindshackfleisch",
        "subtitle": "Schweiz, 2 x 400 g",
        "price":    12.95,
        "was_price": 19.90,
        "category": "Meat & Poultry",   // omit to auto-detect from the name
        "note":     "Supercard required"
      }
    ]
  }
"""
from __future__ import annotations

import json
from pathlib import Path

from .base import Offer, parse_price, week_end
from .categorize import CATEGORIES, categorize

RETAILER = "Coop"
DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "coop_manual.json"

TEMPLATE = {
    "_comment": "Type this week's Coop deals here; see scrapers/coop.py for the schema.",
    "valid_from": "",
    "valid_to": "",
    "offers": [],
}


def _ensure_file() -> dict:
    if not DATA_FILE.exists():
        DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
        DATA_FILE.write_text(
            json.dumps(TEMPLATE, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        print(f"  [Coop] created blank {DATA_FILE.name} - fill it in to show Coop deals")
        return TEMPLATE
    try:
        return json.loads(DATA_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"  [Coop] {DATA_FILE.name} is not valid JSON ({e}); skipping")
        return TEMPLATE


def scrape() -> list[Offer]:
    data = _ensure_file()
    default_from = str(data.get("valid_from") or "")
    default_to = str(data.get("valid_to") or "") or week_end()

    offers: list[Offer] = []
    for i, row in enumerate(data.get("offers") or []):
        if not isinstance(row, dict):
            continue
        name = str(row.get("name") or "").strip()
        if not name:
            print(f"  [Coop] entry {i + 1} has no name; skipped")
            continue

        category = str(row.get("category") or "").strip()
        if category not in CATEGORIES:
            if category:
                print(f"  [Coop] unknown category {category!r} for {name!r}; auto-detecting")
            category = categorize(name, str(row.get("subtitle") or ""))

        o = Offer(
            retailer=RETAILER,
            id=f"coop-manual-{row.get('id') or i}",
            name=name,
            subtitle=str(row.get("subtitle") or ""),
            category=category,
            price=parse_price(row.get("price")),
            was_price=parse_price(row.get("was_price")),
            discount_pct=row.get("discount_pct"),
            unit=str(row.get("unit") or ""),
            note=str(row.get("note") or ""),
            valid_from=str(row.get("valid_from") or default_from),
            valid_to=str(row.get("valid_to") or default_to),
            image=str(row.get("image") or ""),
            url=str(row.get("url") or "https://www.coop.ch/en/promotions"),
        ).finalise()
        if o.is_actionable:
            offers.append(o)
        else:
            print(f"  [Coop] {name!r} has no price or discount; skipped")

    if offers:
        print(f"  [Coop] {len(offers)} manually entered offers")
    else:
        print(f"  [Coop] no offers in {DATA_FILE.name} (blocked by DataDome, manual entry)")
    return offers


if __name__ == "__main__":
    for o in scrape():
        print(o.as_dict())
