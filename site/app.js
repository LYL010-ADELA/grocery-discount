/* Swiss Grocery Deals - reads data/offers.json and renders the browser. */
(() => {
  "use strict";

  const PAGE = 60;                      // cards rendered per "Show more" press
  const WATCH_KEY = "sgd.watchlist";
  const THEME_KEY = "sgd.theme";

  const CAT_ICON = {
    "Fruits & Vegetables": "🥬", "Meat & Poultry": "🥩", "Fish & Seafood": "🐟",
    "Dairy & Eggs": "🧀", "Bread & Bakery": "🥖", "Pantry & Dry Goods": "🥫",
    "Frozen": "🧊", "Snacks & Sweets": "🍫", "Beverages": "🥤", "Alcohol": "🍷",
    "Household": "🧻", "Health & Beauty": "🧴", "Baby & Kids": "🍼",
    "Pet": "🐾", "Non-food & Other": "📦",
  };

  const state = {
    offers: [], meta: null,
    retailers: new Set(), categories: new Set(),
    search: "", sort: "discount", onlyBig: false,
    shown: PAGE, watch: [],
  };

  const $ = (id) => document.getElementById(id);

  /* ---------- storage (may throw in private mode) ---------- */
  const store = {
    get(key, fallback) {
      try {
        const raw = localStorage.getItem(key);
        return raw === null ? fallback : JSON.parse(raw);
      } catch { return fallback; }
    },
    set(key, value) {
      try { localStorage.setItem(key, JSON.stringify(value)); } catch { /* ignore */ }
    },
  };

  /* ---------- helpers ---------- */
  // NFKD does not split the œ/æ ligatures, and labels spell them out:
  // a shelf says "Boeuf" where a dictionary says "bœuf".
  const fold = (s) => (s || "").toLowerCase()
    .replace(/ä/g, "a").replace(/ö/g, "o").replace(/ü/g, "u").replace(/ß/g, "ss")
    .replace(/œ/g, "oe").replace(/æ/g, "ae")
    .normalize("NFKD").replace(/[̀-ͯ]/g, "");

  const chf = (n) => (typeof n === "number" ? n.toFixed(2) : "");

  const esc = (s) => String(s ?? "").replace(/[&<>"']/g,
    (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  // The product's own label. Category and store live in a separate field so a
  // search for "bread" ranks a loaf above everything else in Bread & Bakery.
  function haystack(o) {
    if (!o._hay) o._hay = fold(`${o.name} ${o.subtitle || ""}`);
    return o._hay;
  }

  function haystackMeta(o) {
    if (!o._hayMeta) o._hayMeta = fold(`${o.category} ${o.retailer}`);
    return o._hayMeta;
  }

  // The other languages' words for what this product is, so "bread" reaches
  // "Kartoffel-Nuss-Brot" and "Pain au Maïs".
  function haystackAlias(o) {
    if (!o._hayAlias) o._hayAlias = fold((o.search_terms || []).join(" "));
    return o._hayAlias;
  }

  // A watchlist keyword should behave like a search term: label first, but
  // "salmon" must still find "Lachs".
  function watchable(o) {
    if (!o._watch) {
      const a = haystackAlias(o);
      o._watch = a ? `${haystack(o)} ${a}` : haystack(o);
    }
    return o._watch;
  }

  const watchHits = (o) =>
    state.watch.length > 0 && state.watch.some((w) => watchable(o).includes(fold(w)));

  // Below this length, a match buried inside a word is noise, not a morpheme.
  const MIN_LOOSE = 5;

  const reCache = new Map();
  function res(term) {
    let r = reCache.get(term);
    if (!r) {
      const e = term.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
      r = {
        // the term is a word of its own
        whole: new RegExp(`(?:^|[^a-z0-9])${e}(?:$|[^a-z0-9])`),
        // the term opens or closes a longer word
        edge: new RegExp(`(?:^|[^a-z0-9])${e}|${e}(?:$|[^a-z0-9])`),
      };
      reCache.set(term, r);
    }
    return r;
  }

  // Ranked by how directly the term matched, best first:
  //   5  a word of the label                  ("cola" in "Coca-Cola")
  //   4  the other language's word for it     ("bread" -> "Kartoffel-Nuss-Brot")
  //   3  opens or closes a longer label word  (German "Erdbeer" for "beer" -
  //      a coincidence across languages, so it sits below a real translation)
  //   2  buried inside a label word, and long enough to be a morpheme
  //      ("schoko" in "Tafelschokolade")
  //   1  only its category or store           (the rest of the aisle)
  //   0  no match
  function relevance(o, terms) {
    if (!terms.length) return 5;
    let best = 5;
    for (const t of terms) {
      const r = res(t);
      const label = haystack(o);
      if (r.whole.test(label)) continue;
      if (r.whole.test(haystackAlias(o))) {
        best = Math.min(best, 4);
        continue;
      }
      if (r.edge.test(label)) {
        best = Math.min(best, 3);
        continue;
      }
      if (t.length >= MIN_LOOSE && label.includes(t)) {
        best = Math.min(best, 2);
        continue;
      }
      if (r.edge.test(haystackMeta(o))) {
        best = Math.min(best, 1);
        continue;
      }
      return 0;
    }
    return best;
  }

  function validity(o) {
    if (!o.valid_to) return "";
    const end = new Date(o.valid_to + "T23:59:59");
    if (Number.isNaN(end.getTime())) return "";
    const days = Math.ceil((end - Date.now()) / 86400000);
    if (days < 0) return "expired";
    if (days === 0) return "last day";
    if (days === 1) return "1 day left";
    return `${days} days left`;
  }

  /* ---------- filtering ---------- */
  function filtered() {
    const q = fold(state.search.trim());
    const terms = q ? q.split(/\s+/) : [];
    const out = [];
    for (const o of state.offers) {
      if (state.retailers.size && !state.retailers.has(o.retailer)) continue;
      if (state.categories.size && !state.categories.has(o.category)) continue;
      if (state.onlyBig && (o.discount_pct || 0) < 30) continue;
      const score = relevance(o, terms);
      if (!score) continue;
      o._score = score;
      out.push(o);
    }
    return out;
  }

  const SORTS = {
    discount: (a, b) => (b.discount_pct || 0) - (a.discount_pct || 0),
    "price-asc": (a, b) => (a.price ?? Infinity) - (b.price ?? Infinity),
    "price-desc": (a, b) => (b.price ?? -Infinity) - (a.price ?? -Infinity),
    saving: (a, b) => ((b.was_price || 0) - (b.price || 0)) - ((a.was_price || 0) - (a.price || 0)),
    name: (a, b) => a.name.localeCompare(b.name, "de"),
  };

  /* ---------- rendering ---------- */
  function cardHTML(o) {
    const pct = o.discount_pct ? `<span class="pct">-${o.discount_pct}%</span>` : "";
    const icon = CAT_ICON[o.category] || "🛒";
    // Retailer CDNs drop images fairly often; fall back to the category glyph
    // rather than leaving an empty box.
    const img = o.image
      ? `<img src="${esc(o.image)}" alt="" loading="lazy" decoding="async"
              onerror="this.closest('.card-media').querySelector('.placeholder').hidden=false;
                       this.remove();">
         <span class="placeholder" hidden>${icon}</span>`
      : `<span class="placeholder">${icon}</span>`;
    const was = o.was_price ? `<span class="price-was">${chf(o.was_price)}</span>` : "";
    const price = o.price != null
      ? `<span class="price-now">CHF ${chf(o.price)}</span>`
      : `<span class="price-now">—</span>`;
    const unit = o.unit ? `<span class="price-unit">${esc(o.unit)}</span>` : "";
    const note = o.note ? `<span class="card-note">${esc(o.note)}</span>` : "";
    const left = validity(o);
    const name = o.url
      ? `<a href="${esc(o.url)}" target="_blank" rel="noopener noreferrer">${esc(o.name)}</a>`
      : esc(o.name);

    return `<article class="card${watchHits(o) ? " is-watched" : ""}">
      <div class="card-media">${img}${pct}<span class="store-tag">${esc(o.retailer)}</span></div>
      <div class="card-body">
        <span class="card-cat">${esc(o.category)}</span>
        <h3 class="card-name">${name}</h3>
        ${o.subtitle ? `<p class="card-sub">${esc(o.subtitle)}</p>` : ""}
        ${note}
        <div class="card-prices">${price}${was}${unit}</div>
        ${left ? `<span class="card-valid">${esc(left)}</span>` : ""}
      </div>
    </article>`;
  }

  function renderGrid() {
    const order = SORTS[state.sort] || SORTS.discount;
    // Clean matches come first; the chosen sort applies inside each group, so
    // a search never hides a result, it just ranks the obvious ones on top.
    const rows = filtered().sort((a, b) => (b._score - a._score) || order(a, b));
    const slice = rows.slice(0, state.shown);

    $("grid").innerHTML = slice.map(cardHTML).join("");
    $("empty").hidden = rows.length > 0;
    $("more").hidden = rows.length <= state.shown;
    $("result-count").textContent = rows.length
      ? `${rows.length} offer${rows.length === 1 ? "" : "s"}` +
        (rows.length > slice.length ? ` — showing ${slice.length}` : "")
      : "";
  }

  function renderSummary() {
    const box = $("summary");
    const rows = (state.meta?.summary || []).slice();
    const best = Math.max(...rows.map((r) => (r.count ? r.avg_discount : 0)), 0);

    box.innerHTML = rows.map((r) => {
      if (!r.count) {
        const why = "no data this week";
        return `<div class="store-card is-empty">
          <div class="store-name">${esc(r.retailer)}</div>
          <p class="store-stat">—</p>
          <span class="store-sub">${why}</span>
        </div>`;
      }
      const isBest = r.avg_discount === best && best > 0;
      return `<div class="store-card${isBest ? " is-best" : ""}">
        <div class="store-name">${esc(r.retailer)}
          ${isBest ? '<span class="store-badge">best avg</span>' : ""}</div>
        <p class="store-stat">-${r.avg_discount}%</p>
        <span class="store-sub">${r.count} offers · best -${r.best_discount}%</span>
      </div>`;
    }).join("");
  }

  function renderChips() {
    const counts = (key) => {
      const m = new Map();
      for (const o of state.offers) m.set(o[key], (m.get(o[key]) || 0) + 1);
      return m;
    };

    const build = (el, values, countMap, selected) => {
      el.innerHTML = values.map((v) => {
        const n = countMap.get(v) || 0;
        const on = selected.has(v);
        return `<button class="chip" type="button" role="button"
                  aria-pressed="${on}" data-value="${esc(v)}"${n ? "" : " disabled"}>
                  ${esc(v)}<span class="n">${n}</span></button>`;
      }).join("");
    };

    build($("retailer-chips"), state.meta.retailers, counts("retailer"), state.retailers);
    build($("category-chips"), state.meta.categories, counts("category"), state.categories);
  }

  const countFor = (kw) => {
    const needle = fold(kw);
    return state.offers.reduce((n, o) => n + (watchable(o).includes(needle) ? 1 : 0), 0);
  };

  function renderWatch() {
    // The per-keyword count is the point of the panel: it answers "is the
    // stuff I always buy on sale this week?" without searching one by one.
    $("watch-tags").innerHTML = state.watch.map((w) => {
      const n = countFor(w);
      return `<span class="tag${n ? "" : " is-cold"}">${esc(w)}
        <span class="tag-n">${n || "none"}</span>
        <button type="button" data-kw="${esc(w)}"
          aria-label="Stop watching ${esc(w)}">×</button></span>`;
    }).join("");

    const hits = $("watch-hits");
    if (!state.watch.length) {
      hits.innerHTML = `<p class="watch-empty">Save the things you buy every week
        — <em>Lachs</em>, <em>Kaffee</em>, <em>WC-Papier</em>. They stay saved, so each
        time you open this page you can see at a glance which of them are on offer.</p>`;
      return;
    }
    const matches = state.offers.filter(watchHits)
      .sort((a, b) => (b.discount_pct || 0) - (a.discount_pct || 0));
    hits.innerHTML = matches.length
      ? `<div class="grid">${matches.slice(0, 12).map(cardHTML).join("")}</div>` +
        (matches.length > 12
          ? `<p class="watch-empty">+ ${matches.length - 12} more, highlighted below.</p>`
          : "")
      : `<p class="watch-empty">None of your keywords are on offer this week.</p>`;
  }

  function renderAll() {
    renderSummary();
    renderChips();
    renderWatch();
    renderGrid();
  }

  /* ---------- events ---------- */
  function toggleSet(set, value) {
    set.has(value) ? set.delete(value) : set.add(value);
    state.shown = PAGE;
  }

  function wire() {
    $("search").addEventListener("input", (e) => {
      state.search = e.target.value;
      state.shown = PAGE;
      renderGrid();
    });

    $("sort").addEventListener("change", (e) => {
      state.sort = e.target.value;
      renderGrid();
    });

    $("only-big").addEventListener("change", (e) => {
      state.onlyBig = e.target.checked;
      state.shown = PAGE;
      renderGrid();
    });

    $("retailer-chips").addEventListener("click", (e) => {
      const btn = e.target.closest(".chip");
      if (!btn) return;
      toggleSet(state.retailers, btn.dataset.value);
      renderChips();
      renderGrid();
    });

    $("category-chips").addEventListener("click", (e) => {
      const btn = e.target.closest(".chip");
      if (!btn) return;
      toggleSet(state.categories, btn.dataset.value);
      renderChips();
      renderGrid();
    });

    $("more").addEventListener("click", () => {
      state.shown += PAGE;
      renderGrid();
    });

    $("reset").addEventListener("click", () => {
      state.retailers.clear();
      state.categories.clear();
      state.search = "";
      state.onlyBig = false;
      state.shown = PAGE;
      $("search").value = "";
      $("only-big").checked = false;
      renderChips();
      renderGrid();
    });

    $("watch-form").addEventListener("submit", (e) => {
      e.preventDefault();
      const input = $("watch-input");
      const kw = input.value.trim();
      if (kw && !state.watch.some((w) => fold(w) === fold(kw))) {
        state.watch.push(kw);
        store.set(WATCH_KEY, state.watch);
        renderWatch();
        renderGrid();
      }
      input.value = "";
    });

    $("watch-tags").addEventListener("click", (e) => {
      const btn = e.target.closest("button[data-kw]");
      if (!btn) return;
      state.watch = state.watch.filter((w) => w !== btn.dataset.kw);
      store.set(WATCH_KEY, state.watch);
      renderWatch();
      renderGrid();
    });

    $("theme-toggle").addEventListener("click", () => {
      const now = document.documentElement.getAttribute("data-theme");
      const prefersDark = matchMedia("(prefers-color-scheme: dark)").matches;
      const next = now ? (now === "dark" ? "light" : "dark")
                       : (prefersDark ? "light" : "dark");
      document.documentElement.setAttribute("data-theme", next);
      store.set(THEME_KEY, next);
    });
  }

  /* ---------- boot ---------- */
  function applyStoredTheme() {
    const t = store.get(THEME_KEY, null);
    if (t === "dark" || t === "light") document.documentElement.setAttribute("data-theme", t);
  }

  function renderFooter() {
    const s = state.meta?.status || {};
    const parts = Object.entries(s).map(([name, v]) =>
      v.ok ? `${name}: ${v.count}` : `${name}: unavailable`);
    $("sources").textContent = parts.length ? `Sources — ${parts.join(" · ")}` : "";
  }

  async function boot() {
    applyStoredTheme();
    state.watch = store.get(WATCH_KEY, []).filter((w) => typeof w === "string");

    try {
      const res = await fetch("data/offers.json", { cache: "no-cache" });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      state.meta = data;
      state.offers = data.offers || [];
    } catch (err) {
      $("updated").textContent = "Could not load offers";
      $("grid").innerHTML = `<p class="empty">Offer data could not be loaded
        (${esc(err.message)}). Run <code>python -m scrapers.run</code> first.</p>`;
      return;
    }

    const when = new Date(state.meta.generated_at);
    $("updated").textContent = Number.isNaN(when.getTime())
      ? "" : `Updated ${when.toLocaleDateString("en-GB", { day: "numeric", month: "short" })}, ` +
             `${when.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" })}`;

    wire();
    renderAll();
    renderFooter();
  }

  boot();
})();
