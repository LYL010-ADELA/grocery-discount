#!/usr/bin/env python3
"""Interactive entry for Coop deals (coop.ch blocks automated access).

    python scripts/add_coop.py

Type one deal per prompt; press Enter on an empty name to finish. Everything
is appended to data/coop_manual.json, which `python -m scrapers.run` reads.
Categories are guessed from the product name and can be overridden.
"""
from __future__ import annotations

import datetime as _dt
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scrapers.base import parse_price, week_end          # noqa: E402
from scrapers.categorize import CATEGORIES, categorize   # noqa: E402

FILE = ROOT / "data" / "coop_manual.json"


def load() -> dict:
    if FILE.exists():
        try:
            return json.loads(FILE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            print(f"{FILE.name} is not valid JSON; starting a fresh list.")
    return {"valid_from": "", "valid_to": "", "offers": []}


def ask(label: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    try:
        v = input(f"  {label}{suffix}: ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        raise SystemExit(0)
    return v or default


def main() -> int:
    data = load()
    today = _dt.date.today()
    monday = today - _dt.timedelta(days=today.weekday())

    print("Coop weekly deals - Enter an empty name to stop.\n")
    data["valid_from"] = ask("Valid from (YYYY-MM-DD)", data.get("valid_from") or monday.isoformat())
    data["valid_to"] = ask("Valid to   (YYYY-MM-DD)", data.get("valid_to") or week_end())

    if ask("Replace the existing list? (y/N)", "n").lower().startswith("y"):
        data["offers"] = []
    print(f"\n{len(data['offers'])} offer(s) already stored.\n")

    added = 0
    while True:
        print(f"--- offer {len(data['offers']) + 1} ---")
        name = ask("Product name (empty to finish)")
        if not name:
            break

        price = parse_price(ask("Price CHF"))
        if price is None:
            print("  ! a price is required; skipping this one\n")
            continue
        was = parse_price(ask("Was CHF (optional)"))

        guess = categorize(name)
        cat = ask(f"Category", guess)
        if cat not in CATEGORIES:
            print(f"  ! unknown category, using {guess}")
            cat = guess

        row = {
            "name": name,
            "price": price,
            "category": cat,
            "subtitle": ask("Size / origin (optional)"),
            "note": ask("Note, e.g. Supercard required (optional)"),
        }
        if was:
            row["was_price"] = was
        data["offers"].append({k: v for k, v in row.items() if v not in ("", None)})
        added += 1
        print()

    FILE.parent.mkdir(parents=True, exist_ok=True)
    FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"\nsaved {added} new offer(s); {len(data['offers'])} total in {FILE.name}")
    print("now run:  python -m scrapers.run --only coop && python build_site.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
