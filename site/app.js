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
  const fold = (s) => (s || "").toLowerCase()
    .replace(/ä/g, "a").replace(/ö/g, "o").replace(/ü/g, "u").replace(/ß/g, "ss")
    .normalize("NFKD").replace(/[̀-ͯ]/g, "");

  const chf = (n) => (typeof n === "number" ? n.toFixed(2) : "");

  const esc = (s) => String(s ?? "").replace(/[&<>"']/g,
    (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  function haystack(o) {
    if (!o._hay) o._hay = fold(`${o.name} ${o.subtitle || ""} ${o.category} ${o.retailer}`);
    return o._hay;
  }

  const watchHits = (o) =>
    state.watch.length > 0 && state.watch.some((w) => haystack(o).includes(fold(w)));

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
    return state.offers.filter((o) => {
      if (state.retailers.size && !state.retailers.has(o.retailer)) return false;
      if (state.categories.size && !state.categories.has(o.category)) return false;
      if (state.onlyBig && (o.discount_pct || 0) < 30) return false;
      if (terms.length) {
        const h = haystack(o);
        if (!terms.every((t) => h.includes(t))) return false;
      }
      return true;
    });
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
    const rows = filtered().sort(SORTS[state.sort] || SORTS.discount);
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
        const why = r.retailer === "Coop" ? "needs manual entry" : "no data";
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

  function renderWatch() {
    $("watch-tags").innerHTML = state.watch.map((w) =>
      `<span class="tag">${esc(w)}<button type="button" data-kw="${esc(w)}"
        aria-label="Remove ${esc(w)}">×</button></span>`).join("");

    const hits = $("watch-hits");
    if (!state.watch.length) {
      hits.innerHTML = `<p class="watch-empty">Add a keyword and any matching deal
        gets highlighted and listed here.</p>`;
      return;
    }
    const matches = state.offers.filter(watchHits)
      .sort((a, b) => (b.discount_pct || 0) - (a.discount_pct || 0));
    hits.innerHTML = matches.length
      ? `<div class="grid">${matches.slice(0, 12).map(cardHTML).join("")}</div>`
      : `<p class="watch-empty">Nothing on offer for those keywords this week.</p>`;
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
