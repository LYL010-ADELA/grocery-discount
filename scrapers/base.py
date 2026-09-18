"""Shared data model and helpers for all retailer scrapers."""
from __future__ import annotations

import dataclasses
import datetime as _dt
import re
from html import unescape as _unescape
from dataclasses import dataclass
from typing import Optional

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
)

# Retailers we aggregate, in the order they show up in the UI.
RETAILERS = ["Migros", "Denner", "Lidl", "Aligro"]


@dataclass
class Offer:
    """One discounted product at one retailer.

    Product names stay in their original language (DE/FR) on purpose: that is
    what the shelf label says. Only `category` is normalised to English.
    """

    retailer: str
    id: str
    name: str
    category: str = "Non-food & Other"
    subtitle: str = ""          # origin / pack size, original language
    price: Optional[float] = None       # discounted price in CHF
    was_price: Optional[float] = None   # reference price in CHF
    discount_pct: Optional[int] = None
    unit: str = ""              # "per kg", "per piece", ...
    note: str = ""              # "from 2 pieces", loyalty-card conditions
    valid_from: str = ""        # ISO date
    valid_to: str = ""          # ISO date
    image: str = ""
    url: str = ""
    # Equivalents of the food words in `name`, in the two languages this offer
    # is not written in, so an English search finds a German product.
    search_terms: list = dataclasses.field(default_factory=list)

    def finalise(self) -> "Offer":
        """Fill in whatever can be derived, and tidy up text fields."""
        self.name = clean_text(self.name)
        self.subtitle = clean_text(self.subtitle)
        self.note = normalise_note(self.note)
        self.unit = normalise_unit(self.unit)

        # Derive the third value whenever we know the other two.
        if self.discount_pct is None and self.price and self.was_price:
            if self.was_price > self.price > 0:
                self.discount_pct = round((1 - self.price / self.was_price) * 100)
        if self.was_price is None and self.price and self.discount_pct:
            if 0 < self.discount_pct < 100:
                self.was_price = round(self.price / (1 - self.discount_pct / 100), 2)

        # A "discount" outside this band is almost always a parsing artefact.
        if self.discount_pct is not None and not (1 <= self.discount_pct <= 95):
            self.discount_pct = None
        return self

    @property
    def is_actionable(self) -> bool:
        """An entry with neither a price nor a discount tells a shopper
        nothing; retailers emit these as variant placeholders."""
        return self.price is not None or self.discount_pct is not None

    def as_dict(self) -> dict:
        return {k: v for k, v in dataclasses.asdict(self).items() if v not in (None, "")}


# Notes are UI metadata, not product names, so they do get translated - a
# German badge on an English page just reads as a glitch. Anything not listed
# here is passed through untouched.
_NOTE_MAP = {
    "konkurrenzvergleich": "vs. competitor price",
    "vergleich mit konkurrenz": "vs. competitor price",
    "neu": "New",
    "nouveau": "New",
    "aktion": "Promotion",
    "solange vorrat": "while stocks last",
    "solange vorrat reicht": "while stocks last",
    "jusqu'a epuisement du stock": "while stocks last",
    "ab 2 stuck": "from 2 items",
    "ab 3 stuck": "from 3 items",
    "ab 2 stück": "from 2 items",
    "ab 3 stück": "from 3 items",
    "des 2 pieces": "from 2 items",
    "duo pack": "duo pack",
    "duopack": "duo pack",
    "multipack": "multipack",
    "nur mit supercard": "Supercard required",
    "mit cumulus": "Cumulus card required",
    "special": "",
    "wochenhit": "Weekly highlight",
    "hit der woche": "Weekly highlight",
}

# A note that is only a percentage or a bare amount repeats the discount badge.
_NOISE_NOTE = re.compile(r"^\s*[-–]?\s*\d{1,3}\s*(%|\.[-–]|\.\-)?\s*$")
# Migros writes its loyalty-point multiplier as a bare "20x".
_CUMULUS = re.compile(r"^(\d{1,3})\s*[x×]$", re.I)


# Denner leaks unresolved i18n keys into its size field ("0.8 unit.g"), and
# the number in front of them does not reliably mean what it says. The pack
# size is already in the subtitle, so drop those rather than show nonsense.
_BROKEN_UNIT = re.compile(r"\bunit\.[a-z]+", re.I)


def normalise_unit(raw: str) -> str:
    u = clean_text(raw)
    if not u or _BROKEN_UNIT.search(u):
        return ""
    return re.sub(r"^env\.\s*", "approx. ", u, flags=re.I)


def normalise_note(raw: str) -> str:
    """Translate recurring retailer badges and drop ones that say nothing."""
    out = []
    for part in re.split(r"\s*;\s*", clean_text(raw)):
        if not part or _NOISE_NOTE.match(part):
            continue
        m = _CUMULUS.match(part)
        if m:
            part = f"{m.group(1)}\u00d7 Cumulus points"
        else:
            mapped = _NOTE_MAP.get(part.lower().strip(" .!"))
            part = mapped if mapped is not None else part
        if part and part not in out:
            out.append(part)
    return "; ".join(out)


def clean_text(s: str) -> str:
    if not s:
        return ""
    s = re.sub(r"<[^>]+>", " ", str(s))          # strip inline markup
    # Retailers emit the full range of named entities (&uuml;, &eacute;, ...),
    # so decode properly instead of hand-listing a few.
    s = _unescape(s).replace("\xa0", " ")
    return re.sub(r"\s+", " ", s).strip()


def parse_price(raw) -> Optional[float]:
    """Pull a CHF amount out of whatever the site gave us.

    Swiss pricing uses both '4.95' and '4,95', and sometimes a '.-' suffix.
    """
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return round(float(raw), 2)
    s = str(raw).strip().replace("CHF", "").replace("Fr.", "")
    s = s.replace("–", "-").replace("—", "-")
    s = re.sub(r"(\d)\.-", r"\1.00", s)          # "5.-" -> "5.00"
    m = re.search(r"\d+(?:[.,]\d{1,2})?", s)
    if not m:
        return None
    try:
        return round(float(m.group(0).replace(",", ".")), 2)
    except ValueError:
        return None


def parse_percent(raw) -> Optional[int]:
    if raw is None:
        return None
    m = re.search(r"(\d{1,2})\s*%", str(raw))
    return int(m.group(1)) if m else None


def today() -> str:
    return _dt.date.today().isoformat()


def week_end() -> str:
    """Swiss promo weeks run Mon-Sat; use the coming Saturday as a fallback."""
    d = _dt.date.today()
    return (d + _dt.timedelta(days=(5 - d.weekday()) % 7)).isoformat()
