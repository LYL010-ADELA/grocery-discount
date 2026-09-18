"""Run every retailer scraper and write the dataset the website reads.

    python -m scrapers.run                 # everything
    python -m scrapers.run --only migros   # one retailer, for debugging
    python -m scrapers.run --quick         # trims Aligro's long category walk

A failing retailer never takes the run down: the site keeps the other four and
shows which source went stale.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import sys
import traceback
from pathlib import Path

from .base import Offer, RETAILERS
from .categorize import CATEGORIES

from . import aligro, coop, denner, lidl, migros

OUT = Path(__file__).resolve().parent.parent / "data" / "offers.json"

SOURCES = {
    "migros": migros.scrape,
    "coop": coop.scrape,
    "denner": denner.scrape,
    "lidl": lidl.scrape,
    "aligro": aligro.scrape,
}


def collect(only: list[str] | None, quick: bool) -> tuple[list[Offer], dict]:
    offers: list[Offer] = []
    status: dict[str, dict] = {}

    for key, fn in SOURCES.items():
        if only and key not in only:
            continue
        name = key.capitalize()
        print(f"[{name}]")
        try:
            got = fn(max_categories=12) if (key == "aligro" and quick) else fn()
            usable = [o for o in got if o.is_actionable]
            dropped = len(got) - len(usable)
            if dropped:
                print(f"  [{name}] dropped {dropped} entries with no price or discount")
            offers += usable
            status[name] = {"ok": True, "count": len(usable)}
        except Exception as e:                      # keep the other retailers
            print(f"  [{name}] FAILED: {e}", file=sys.stderr)
            traceback.print_exc(file=sys.stderr)
            status[name] = {"ok": False, "count": 0, "error": str(e)}
    return offers, status


def build_payload(offers: list[Offer], status: dict) -> dict:
    return build_payload_from_rows([o.as_dict() for o in offers], status)


def build_payload_from_rows(rows: list[dict], status: dict) -> dict:
    # Best discounts first; unknown discount sinks to the bottom.
    rows.sort(key=lambda r: (-(r.get("discount_pct") or 0), r.get("name", "")))

    per_retailer: dict[str, dict] = {}
    for r in rows:
        b = per_retailer.setdefault(r["retailer"], {"count": 0, "discounts": []})
        b["count"] += 1
        if r.get("discount_pct"):
            b["discounts"].append(r["discount_pct"])

    summary = []
    for name in RETAILERS:
        b = per_retailer.get(name)
        if not b:
            summary.append({"retailer": name, "count": 0, "avg_discount": 0, "best_discount": 0})
            continue
        d = b["discounts"]
        summary.append(
            {
                "retailer": name,
                "count": b["count"],
                "avg_discount": round(sum(d) / len(d)) if d else 0,
                "best_discount": max(d) if d else 0,
            }
        )

    used = [c for c in CATEGORIES if any(r["category"] == c for r in rows)]
    return {
        "generated_at": _dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "retailers": RETAILERS,
        "categories": used,
        "summary": summary,
        "status": status,
        "offers": rows,
    }


def _carry_over(offers: list[Offer], status: dict, only: list[str]) -> tuple[list[dict], dict]:
    """A partial run must not wipe the retailers it did not touch, so reuse
    their rows from the previous dataset."""
    rows = [o.as_dict() for o in offers]
    if not OUT.exists():
        return rows, status
    try:
        old = json.loads(OUT.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return rows, status

    fresh = {k.capitalize() for k in only}
    kept = [r for r in old.get("offers", []) if r.get("retailer") not in fresh]
    if kept:
        print(f"  kept {len(kept)} offers from retailers not in this run")
    merged_status = dict(old.get("status") or {})
    merged_status.update(status)
    return rows + kept, merged_status


def main() -> int:
    ap = argparse.ArgumentParser(description="Collect Swiss supermarket discounts")
    ap.add_argument("--only", nargs="+", choices=sorted(SOURCES), help="limit to these retailers")
    ap.add_argument("--quick", action="store_true", help="shorten the Aligro category walk")
    args = ap.parse_args()

    offers, status = collect(args.only, args.quick)
    if args.only:
        rows, status = _carry_over(offers, status, args.only)
        payload = build_payload_from_rows(rows, status)
    else:
        payload = build_payload(offers, status)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    # Compact separators: this file is fetched by phones on mobile data, and
    # indentation costs ~15% of the payload for nothing.
    OUT.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
    )

    print(f"\nwrote {OUT.relative_to(Path.cwd())}  "
          f"({len(payload['offers'])} offers, {OUT.stat().st_size // 1024} KB)")
    for row in payload["summary"]:
        print(f"  {row['retailer']:8} {row['count']:5} offers   "
              f"avg -{row['avg_discount']}%   best -{row['best_discount']}%")
    failed = [n for n, s in status.items() if not s["ok"]]
    if failed:
        print(f"\nfailed sources: {', '.join(failed)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
