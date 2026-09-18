"""Cross-language search aliases, resolved offline.

A shopper searching "bread" should find "Pain au Maïs" and "Kartoffel-Nuss-Brot"
even though neither name contains an English word. Rather than translate the
query in the browser, every offer is tagged at scrape time with the equivalents
of the food words in its name, in the two languages it is not written in.

The lexicon is `data/lexicon.json`, built once by scripts/build_lexicon.py from
the Open Food Facts taxonomies. Nothing here touches the network, and no
translation API is involved.
"""
from __future__ import annotations

import json
import re
import unicodedata
from functools import lru_cache
from pathlib import Path

LEXICON = Path(__file__).resolve().parent.parent / "data" / "lexicon.json"

# A term has to be reasonably long before matching it against a product name
# is safe, but the alias it produces can be shorter - "egg" is a word people
# search for, while a two-letter alias like "ei" would match almost anything.
MIN_MATCH = 4
MIN_ALIAS = 3
MAX_ALIASES = 6     # keep the payload small; beyond this adds noise, not recall


def _norm(s: str) -> str:
    s = (s or "").lower()
    s = s.replace("ä", "a").replace("ö", "o").replace("ü", "u").replace("ß", "ss")
    # NFKD leaves the ligatures alone, and retailers spell them out: labels say
    # "Boeuf" and "Oeufs" where a dictionary says "bœuf" and "œufs".
    s = s.replace("œ", "oe").replace("æ", "ae")
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", s).strip()


@lru_cache(maxsize=1)
def _terms() -> tuple[dict[str, list[str]], list[str]]:
    """Return the term index and its keys ordered longest-first."""
    if not LEXICON.exists():
        print(f"  [lexicon] {LEXICON.name} missing; "
              f"run scripts/build_lexicon.py for cross-language search")
        return {}, []
    try:
        data = json.loads(LEXICON.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        print(f"  [lexicon] could not read {LEXICON.name}: {e}")
        return {}, []
    index = {k: v for k, v in (data.get("terms") or {}).items() if len(k) >= MIN_MATCH}
    return index, sorted(index, key=len, reverse=True)


def _on_word_boundary(term: str, blob: str) -> bool:
    n = len(term)
    i = blob.find(term)
    while i != -1:
        before = i == 0 or not blob[i - 1].isalnum()
        after = i + n >= len(blob) or not blob[i + n].isalnum()
        if before and after:
            return True
        i = blob.find(term, i + 1)
    return False


# The lexicon is a food lexicon, so applying it to a cleaning product repeats
# the mistake the categoriser already learned: "Canard-WC" is a brand, and
# tagging it "duck" would put toilet gel in a search for poultry.
NON_FOOD_CATEGORIES = frozenset(
    {"Household", "Health & Beauty", "Baby & Kids", "Pet", "Non-food & Other"}
)


def aliases_for(*texts: str, category: str = "") -> list[str]:
    """Words in the other two languages for the food terms found in `texts`.

    Terms already present in the text are left out - they would only repeat
    what the search box can match directly.
    """
    if category in NON_FOOD_CATEGORIES:
        return []
    index, ordered = _terms()
    if not index:
        return []

    blob = _norm(" ".join(t for t in texts if t))
    if len(blob) < MIN_MATCH:
        return []

    out: list[str] = []
    for term in ordered:
        if len(out) >= MAX_ALIASES:
            break
        if not _on_word_boundary(term, blob):
            continue
        for alias in index[term]:
            if (
                len(alias) >= MIN_ALIAS
                and alias not in out
                and not _on_word_boundary(alias, blob)
            ):
                out.append(alias)
                if len(out) >= MAX_ALIASES:
                    break
    return out


def available() -> bool:
    return bool(_terms()[0])
