#!/usr/bin/env python3
"""Distil a trilingual grocery lexicon from the Open Food Facts taxonomies.

    python scripts/build_lexicon.py

Downloads two public taxonomy files, keeps the entries that carry an English,
German and French name, and writes `data/lexicon.json`. That file is committed,
so scraping and the website never touch the network for translation and no
API key is involved.

Source: Open Food Facts taxonomies, Open Database Licence (ODbL).
https://world.openfoodfacts.org/data
"""
from __future__ import annotations

import json
import re
import sys
import unicodedata
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scrapers.base import USER_AGENT  # noqa: E402

OUT = ROOT / "data" / "lexicon.json"
BASE = "https://static.openfoodfacts.org/data/taxonomies"
SOURCES = ("categories", "ingredients")
LANGS = ("en", "de", "fr")

# Words that match far too much to be useful as a search alias, or that name a
# property rather than a food ("bio", "colorant", "sans sucre").
STOP = {
    "aliment", "aliments", "food", "foods", "lebensmittel", "produit", "produits",
    "product", "products", "produkt", "produkte", "boisson", "boissons", "drink",
    "drinks", "getrank", "getranke", "plat", "plats", "dish", "dishes", "gericht",
    "snack", "snacks", "dessert", "desserts", "nahrungsmittel", "zutat", "zutaten",
    "ingredient", "ingredients", "bio", "organic", "naturel", "natural", "natur",
    "colorant", "colorants", "farbstoff", "farbstoffe", "arome", "aromes", "aroma",
    "additif", "additifs", "additive", "additives", "zusatzstoff", "zusatzstoffe",
    "conservateur", "preservative", "konservierungsstoff", "emulsifiant",
    "emulsifier", "emulgator", "stabilisant", "stabiliser", "stabilisator",
    "antioxydant", "antioxidant", "acidifiant", "acidity regulator", "saure",
    "extrait", "extract", "extrakt", "poudre", "powder", "pulver", "concentre",
    "concentrate", "konzentrat", "sirop", "syrup", "sirup", "frais", "fresh",
    "frisch", "surgele", "frozen", "tiefgekuhlt", "sec", "dry", "trocken",
    "entier", "whole", "ganz", "demi", "half", "halb", "petit", "small", "klein",
    "grand", "large", "gross", "mini", "maxi", "classic", "classique", "original",
    "color", "colour", "couleur", "farbe", "sucre", "sugar", "zucker", "sel",
    "salt", "salz", "eau", "water", "wasser", "huile", "oil", "ol",
}

_ADDITIVE_KEY = re.compile(r"^en:e\d{3}|additive|colou?r|flavour|aroma", re.I)


def norm(s: str) -> str:
    s = (s or "").lower()
    s = s.replace("ä", "a").replace("ö", "o").replace("ü", "u").replace("ß", "ss")
    # NFKD leaves the ligatures alone, and retailers spell them out: labels say
    # "Boeuf" and "Oeufs" where a dictionary says "bœuf" and "œufs".
    s = s.replace("œ", "oe").replace("æ", "ae")
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", s).strip()


def fetch(name: str) -> dict:
    url = f"{BASE}/{name}.json"
    print(f"  downloading {url}")
    r = requests.get(url, timeout=120, headers={"User-Agent": USER_AGENT})
    r.raise_for_status()
    return r.json()


def build() -> dict:
    concepts: dict[str, dict[str, str]] = {}
    for src in SOURCES:
        data = fetch(src)
        kept = 0
        for key, entry in data.items():
            if _ADDITIVE_KEY.search(key):
                continue
            names = entry.get("name") or {}
            if not all(isinstance(names.get(l), str) for l in LANGS):
                continue
            forms = {l: norm(names[l]) for l in LANGS}
            # Keep short words like egg / Ei / oeuf: the length rules that
            # matter are applied at match time, not here. Only drop entries
            # that are empty or absurdly long to be a search word.
            if any(not (1 < len(v) < 32) for v in forms.values()):
                continue
            if any(v in STOP for v in forms.values()):
                continue
            # A concept whose three names are identical teaches us nothing.
            if len(set(forms.values())) == 1:
                continue
            concepts[key] = forms
            kept += 1
        print(f"  {src}: kept {kept} trilingual concepts")
    return concepts


def main() -> int:
    print("building trilingual grocery lexicon")
    concepts = build()

    # Store as surface form -> the equivalents in the other two languages, which
    # is the shape the scraper actually looks things up by.
    index: dict[str, list[str]] = {}
    for forms in concepts.values():
        for lang, form in forms.items():
            others = sorted({v for l, v in forms.items() if l != lang and v != form})
            if others:
                index.setdefault(form, [])
                for o in others:
                    if o not in index[form]:
                        index[form].append(o)

    payload = {
        "source": "Open Food Facts taxonomies (ODbL)",
        "url": "https://world.openfoodfacts.org/data",
        "languages": list(LANGS),
        "concepts": len(concepts),
        "terms": index,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\nwrote {OUT.relative_to(ROOT)}: {len(index)} terms, "
          f"{OUT.stat().st_size // 1024} KB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
