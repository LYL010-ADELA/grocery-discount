#!/usr/bin/env python3
"""Assemble the deployable site into _site/.

    python build_site.py            # build only
    python build_site.py --serve    # build, then serve on http://localhost:8000

The site is plain HTML/CSS/JS with no build step; this only copies `site/`
next to the scraped `data/offers.json` so the page's relative fetch resolves
both locally and on GitHub Pages.
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SITE, DATA, OUT = ROOT / "site", ROOT / "data", ROOT / "_site"


def build() -> Path:
    if not SITE.is_dir():
        sys.exit("site/ is missing")

    if OUT.exists():
        shutil.rmtree(OUT)
    shutil.copytree(SITE, OUT)

    offers = DATA / "offers.json"
    if offers.exists():
        (OUT / "data").mkdir(parents=True, exist_ok=True)
        shutil.copy2(offers, OUT / "data" / "offers.json")
        size = offers.stat().st_size // 1024
        print(f"built {OUT.name}/ with data/offers.json ({size} KB)")
    else:
        print("built _site/ WITHOUT offer data - run: python -m scrapers.run")
    return OUT


def serve(directory: Path, port: int = 8000) -> None:
    import functools
    import http.server
    import socketserver

    handler = functools.partial(http.server.SimpleHTTPRequestHandler,
                                directory=str(directory))
    with socketserver.TCPServer(("", port), handler) as httpd:
        print(f"serving {directory.name}/ at http://localhost:{port}  (ctrl-c to stop)")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nstopped")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--serve", action="store_true", help="serve after building")
    ap.add_argument("--port", type=int, default=8000)
    args = ap.parse_args()
    out = build()
    if args.serve:
        serve(out, args.port)
