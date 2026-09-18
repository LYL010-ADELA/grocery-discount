# Swiss Grocery Deals

This week's supermarket discounts in Switzerland, collected from five retailers
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
| **Coop** | **Manual entry** — see below | you decide |

All four automated sources are plain HTTP and JSON. No headless browser runs in
production, so a scheduled update finishes in about a minute.

### Why Coop is manual

coop.ch is behind **DataDome**, a commercial anti-bot service that fingerprints
the client and answers with a CAPTCHA challenge. Every request — plain HTTP,
headless Chromium, and real Chrome — comes back `403 Forbidden`. Getting past
that would mean forging device fingerprints and wiring up a CAPTCHA solver,
which is circumventing an access control the retailer deliberately operates, so
this project does not attempt it.

Instead, type the Coop deals worth comparing straight from the weekly flyer:

```bash
python scripts/add_coop.py          # guided prompts, guesses the category
python -m scrapers.run --only coop  # merge into the dataset
```

Twenty minutes a week covers the deals actually worth comparing. A partial run
keeps every other retailer's data intact.

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

Swiss promo weeks start Tuesday (Migros, Coop, Denner) and Thursday (Lidl), so
a daily run always catches the changeover. Trigger one by hand any time from the
Actions tab.

---

## Layout

```
scrapers/
  base.py         Offer model, price/note/unit normalisation
  categorize.py   German + French keywords -> 15 English categories
  migros.py  denner.py  lidl.py  aligro.py  coop.py
  run.py          orchestrator -> data/offers.json
site/             index.html, style.css, app.js (no build step)
scripts/
  add_coop.py     guided entry for Coop
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
