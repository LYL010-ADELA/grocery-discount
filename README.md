# Swiss Grocery Deals

This week's supermarket discounts in Switzerland, collected from four retailers
and shown in one English-language page you can filter by store, category and
keyword. Built for price-sensitive students deciding where to shop.

Product names stay in German or French on purpose — that is what the shelf
label says. Categories, notes and the interface are in English.

---

## Where the data comes from

| Retailer | Method | Typical yield |
|---|---|---|
| **Migros** | Internal JSON API (`product-display`), guest token from `/authentication/public/v1/api/guest` | ~145 |
| **Denner** | `POST /nuxt-api/promotions`, the endpoint its own offers page paginates against | ~230 |
| **Lidl** | `data-grid-data` JSON embedded in the offer pages, incl. Lidl Plus app prices | ~185 |
| **Aligro** | `pagination` JSON on each `/actions/...` category page | ~2200 |

All four sources are plain HTTP and JSON. No headless browser runs in
production, so a scheduled update finishes in about a minute.

### Coop is not included

coop.ch is behind **DataDome**, a commercial anti-bot service that fingerprints
the client and answers with a CAPTCHA challenge. Every request — plain HTTP,
headless Chromium, and real Chrome — comes back `403 Forbidden`. Getting past
that would mean forging device fingerprints and wiring up a CAPTCHA solver,
which is circumventing an access control the retailer deliberately operates, so
this project does not attempt it, and Coop is left out rather than half-served.

---

## Searching across languages

Product names stay in German or French, but the search box accepts all three
languages: `bread` finds *Pain au Maïs* and *Kartoffel-Nuss-Brot*, `beer` finds
*Feldschlösschen Bier*, `egg` finds *Œuf CH*.

This runs entirely offline - no translation API, no key, no per-week cost. The
query is not translated; instead every offer is tagged at scrape time with the
words for what it is in the two languages it is *not* written in, and those go
into `offers.json` as `search_terms`. The vocabulary comes from the Open Food
Facts taxonomies (ODbL), distilled once into `data/lexicon.json`:

```bash
python scripts/build_lexicon.py     # refresh the lexicon (rarely needed)
```

`data/lexicon.json` is committed, so a normal scrape never downloads it, and
the 1 MB file is never served to the browser - only the ~18 KB of aliases it
produces. If the file is missing, scraping still works and search simply stays
single-language.

Results are ranked by how directly they matched, best first:

| | match |
|---|---|
| 5 | a word of the label — `cola` in *Coca-Cola* |
| 4 | the other language's word for it — `bread` → *Kartoffel-Nuss-Brot* |
| 3 | opens or closes a longer label word — German *Erdbeer* for `beer` |
| 2 | buried inside a label word, 5+ characters — `schoko` in *Tafelschokolade* |
| 1 | only its category or store — the rest of the aisle |

Tier 4 sits above tier 3 on purpose: a curated translation beats two languages
happening to share a few letters, which is why `beer` lists *Feldschlösschen
Bier* before *Erdbeer*-flavoured yoghurt. Nothing is filtered out, only ordered.

The lexicon is a *food* lexicon, so offers in Household, Health & Beauty, Baby,
Pet and Non-food get no aliases at all — otherwise "Canard-WC" would be filed
under duck, which is the same trap the categoriser had to learn.

---

## Running it

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

python -m scrapers.run              # collect everything -> data/offers.json
python build_site.py --serve        # build _site/ and open localhost:8000
```

Useful flags:

```bash
python -m scrapers.run --only migros denner   # refresh some retailers only
python -m scrapers.run --quick                # trim Aligro's 101-category walk
python -m scrapers.migros                     # run one scraper and print samples
```

A retailer that breaks never takes the run down: the others still publish, and
the page footer says which source went missing.

---

## Deploying to GitHub Pages

1. Push this repository to GitHub.
2. **Settings → Pages → Source: GitHub Actions**.
3. That's it. `.github/workflows/update.yml` runs daily at 05:10 UTC, commits a
   refreshed `data/offers.json`, and deploys.

Swiss promo weeks start Tuesday (Migros, Denner) and Thursday (Lidl), so
a daily run always catches the changeover. Trigger one by hand any time from the
Actions tab.

---

## Layout

```
scrapers/
  base.py         Offer model, price/note/unit normalisation
  categorize.py   German + French keywords -> 15 English categories
  lexicon.py      offline DE/FR/EN aliases for cross-language search
  migros.py  denner.py  lidl.py  aligro.py
  run.py          orchestrator -> data/offers.json
site/             index.html, style.css, app.js (no build step)
scripts/
  build_lexicon.py  rebuild data/lexicon.json from Open Food Facts
build_site.py     assembles _site/ for deployment
```

### Adding a retailer

Write `scrapers/<name>.py` exposing `scrape() -> list[Offer]`, register it in
`SOURCES` in `run.py`, and add the display name to `RETAILERS` in `base.py`.
`Offer.finalise()` derives the missing one of price / was-price / percentage,
cleans the text and translates notes, so a scraper only needs to fill in
whatever the source actually provides.

### Categories

`categorize.py` matches German and French keywords after stripping accents, so
`Gemüse` and `gemuse` both hit. German compounds collide by substring —
`Butternuss` is a squash, not butter — so brand names and known compounds are
checked in a strong-keyword tier before the general longest-match sweep. When a
product lands in the wrong place, add the word there.

---

## Known limits

- **Aligro pagination.** Each category page serves at most 48 items and paging
  is client-side, so subcategories larger than that lose the tail — roughly 75%
  of its ~2 950 promotions are captured. Aligro is also a wholesaler: pack sizes
  are catering-sized, which is why its offers carry a *Wholesale pack* note.
- **Regional prices.** Migros is fetched with `region="national"`. Cooperatives
  price differently; set `DEFAULT_REGION` in `scrapers/migros.py` to `gmzh`
  (Zürich), `gmaa` (Aare), `gmvd` (Vaud), `gmge` (Genève) or `gmos`
  (Ostschweiz) for local prices.
- **Denner next week.** The `promo_next_week` feed is queried but is usually
  empty until the weekend before.
- **Endpoints are internal.** None of these are documented public APIs. A site
  redesign will break a scraper; re-discover the endpoint by intercepting the
  page's own XHRs with Playwright (see `requirements.txt`).

Scraping runs once a day with a pause between requests. Prices may lag behind
the shelf — always check in store.
