#!/usr/bin/env python3
"""Check every endpoint the scrapers request against each site's live robots.txt.

    python scripts/check_robots.py

Exits non-zero if any request path is disallowed, so CI fails rather than
quietly scraping somewhere a retailer asked crawlers not to go.

Python's built-in urllib.robotparser mishandles leading-wildcard rules - it
reported Migros' `Disallow: */promotion/` as allowing
`/products/promotion/search` - so this uses protego, which implements Google's
specification.
"""
from __future__ import annotations

import sys
from pathlib import Path
from urllib.parse import urlparse

import requests
from protego import Protego

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scrapers.base import USER_AGENT  # noqa: E402

# Every path the scrapers actually request, with a representative id where the
# real URL carries one. Keep this in step with the scrapers.
ENDPOINTS: dict[str, list[str]] = {
    "https://www.migros.ch": [
        "/authentication/public/v1/api/guest",
        "/product-display/public/v1/promotions/instore/new",
        "/product-display/public/v1/promotions/instore/weekend",
        "/product-display/public/v1/promotions/instore/personalized",
        "/product-display/public/v4/product-cards",
        "/product-display/public/v2/promotions-details/2499568",
    ],
    "https://www.denner.ch": [
        "/nuxt-api/promotions",
    ],
    "https://www.lidl.ch": [
        "/c/de-CH/wochenaktion/a10102783",
        "/c/de-CH/super-wochenende/a10102782",
        "/c/de-CH/lidl-plus-angebote/a10020520",
    ],
    "https://www.aligro.ch": [
        "/actions",
        "/actions/1011-legumes",
    ],
}


def main() -> int:
    failures: list[str] = []
    for base, paths in ENDPOINTS.items():
        host = urlparse(base).netloc
        try:
            r = requests.get(
                f"{base}/robots.txt", timeout=30, headers={"User-Agent": USER_AGENT}
            )
            r.raise_for_status()
        except requests.RequestException as e:
            print(f"{host}: could not read robots.txt ({e})")
            failures.append(f"{host}: robots.txt unreachable")
            continue

        rules = Protego.parse(r.text)
        print(f"{host}")
        for path in paths:
            url = base + path
            allowed = rules.can_fetch(url, "*")
            print(f"   {'ok ' if allowed else 'BLOCKED'} {path}")
            if not allowed:
                failures.append(f"{host}{path}")
        delay = rules.crawl_delay("*")
        if delay:
            print(f"   (crawl-delay requested: {delay}s)")
        print()

    if failures:
        print("DISALLOWED by robots.txt:")
        for f in failures:
            print(f"   {f}")
        print("\nRemove the endpoint or find one the site permits.")
        return 1

    print("every endpoint is permitted by robots.txt")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
