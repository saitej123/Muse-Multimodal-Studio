/* Overlay loaded AFTER app.js: keeps the cron style/theme selects in sync with
 * the catalog (templates grouped by design family) and refreshes the pickers
 * once the catalog has loaded. Previews live in app.js and use the real renderer.
 */
(function () {
  const THEME_ALIASES = {
    paper: "snow", ivory: "snow", mint: "snow",
    nebula: "aurora", slate: "midnight", mono: "midnight",
  };
  const catalog = { styles: [], presets: [], themes: [] };

  function $(id) { return document.getElementById(id); }
  function esc(x) {
    return String(x == null ? "" : x)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }
  function aliasTheme(key) {
    const k = String(key || "").toLowerCase();
    return THEME_ALIASES[k] || k;
  }

  function fillCronVisualSelects(styleVal, themeVal) {
    const ss = $("rt-video-style");
    const ts = $("rt-video-theme");
    if (ss) {
      const cats = {};
      catalog.styles.forEach((s) => {
        if (!s.key || s.key === "auto") return;
        const g = s.category_label || s.category || "Other";
        (cats[g] || (cats[g] = [])).push(s);
      });
      const order = ["Whiteboard", "Notebook", "Chalkboard", "Editorial", "Magazine", "Broadcast", "Glass", "Bento", "Poster", "Pop", "Cinema", "Terminal"];
      const rank = (g) => { const i = order.indexOf(g); return i < 0 ? 99 : i; };
      const groups = Object.keys(cats).sort((a, b) => rank(a) - rank(b)).map((g) => {
        const opts = cats[g].map((s) => `<option value="${esc(s.key)}">${esc(s.label)}</option>`).join("");
        return `<optgroup label="${esc(g)}">${opts}</optgroup>`;
      }).join("");
      ss.innerHTML = `<option value="auto">Auto</option>${groups}`;
      const want = styleVal || ss.value;
      if (want && [...ss.options].some((o) => o.value === want)) ss.value = want;
    }
    if (ts) {
      ts.innerHTML = catalog.themes.map((th) =>
        `<option value="${esc(th.key)}">${esc(th.label)}</option>`
      ).join("");
      const wantT = themeVal || ts.value;
      if (wantT && [...ts.options].some((o) => o.value === wantT)) ts.value = wantT;
    }
  }

  async function refreshCatalog() {
    try {
      const data = await (await fetch("/api/video-formats")).json();
      catalog.styles = data.styles || [];
      catalog.presets = data.visual_presets || [];
      catalog.themes = data.themes || [];
    } catch (e) { /* keep last */ }
  }

  window.fillCronVisualSelects = fillCronVisualSelects;
  const origFetch = window.fetch.bind(window);
  window.fetch = function (url, opts) {
    const u = String(url || "");
    const method = (opts && opts.method) || "GET";
    if (u.includes("/api/video-formats") && method === "GET") {
      return origFetch(url, opts).then((res) => {
        res.clone().json().then((data) => {
          catalog.styles = data.styles || catalog.styles;
          catalog.presets = data.visual_presets || catalog.presets;
          catalog.themes = data.themes || catalog.themes;
          fillCronVisualSelects();
        }).catch(() => {});
        return res;
      });
    }
    if (u.includes("/api/admin/runtime-settings") && method === "PUT" && opts && opts.body) {
      try {
        const body = JSON.parse(opts.body);
        const ss = $("rt-video-style");
        const ts = $("rt-video-theme");
        if (ss) body.auto_video_style = ss.value || body.auto_video_style || "whiteboard";
        if (ts) body.auto_video_theme = ts.value || body.auto_video_theme || "snow";
        opts = Object.assign({}, opts, { body: JSON.stringify(body) });
      } catch (e) { /* keep original body */ }
    }
    return origFetch(url, opts).then((res) => {
      if (u.includes("/api/admin/runtime-settings") && method === "GET") {
        res.clone().json().then((data) => {
          fillCronVisualSelects(data.auto_video_style || "whiteboard", aliasTheme(data.auto_video_theme || "snow"));
        }).catch(() => {});
      }
      return res;
    });
  };

  refreshCatalog().then(() => {
    fillCronVisualSelects();
    if (typeof renderVisualPresets === "function") renderVisualPresets();
    if (typeof renderAdminVisualStyles === "function") renderAdminVisualStyles();
  });
})();
