/* ═══════════════════════════════════════════════════════════════════
   Section23 Jobs — Obsidian UI
   ═══════════════════════════════════════════════════════════════════ */

(function () {
  "use strict";

  /* ── API ────────────────────────────────────────────────────────── */

  var API = {
    _handle: function (r) {
      if (r.status === 401) { location.href = "/login"; return Promise.resolve(null); }
      if (r.status === 403) return Promise.resolve(null);
      if (r.status === 204) return Promise.resolve(true);
      if (!r.ok) return Promise.resolve(null);
      return r.json().catch(function () { return null; });
    },
    get: function (url) { return fetch(url).then(this._handle.bind(this)); },
    post: function (url, body) {
      return fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }).then(this._handle.bind(this));
    },
    put: function (url, body) {
      return fetch(url, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }).then(this._handle.bind(this));
    },
    del: function (url) {
      return fetch(url, { method: "DELETE" }).then(function (r) {
        if (r.status === 401) { location.href = "/login"; return false; }
        if (r.status === 403) return false;
        return r.ok;
      });
    }
  };

  /* ── State ──────────────────────────────────────────────────────── */

  var families = [];
  var regions = [];
  var state = {
    familyId: "", regionId: "", radiusKm: 50,
    contractType: "", viewStatus: "", q: "",
    anchorLat: null, anchorLon: null,
    offset: 0, limit: 25
  };

  /* ── Index page ─────────────────────────────────────────────────── */

  function initIndex() {
    var pillGroup = document.getElementById("family-pills");
    var regionSel = document.getElementById("region-select");
    if (!pillGroup) return;

    Promise.all([API.get("/api/families"), API.get("/api/regions")]).then(function (res) {
      families = res[0] || [];
      regions = res[1] || [];

      buildViewToggle();

      pillGroup.innerHTML = '<button class="pill active" data-family="">Toutes</button>';
      families.forEach(function (f) {
        var b = document.createElement("button");
        b.className = "pill";
        b.dataset.family = f.id;
        b.textContent = f.display_name;
        pillGroup.appendChild(b);
      });

      pillGroup.addEventListener("click", function (e) {
        var p = e.target.closest(".pill");
        if (!p) return;
        pillGroup.querySelectorAll(".pill").forEach(function (x) { x.classList.remove("active"); });
        p.classList.add("active");
        state.familyId = p.dataset.family;
        state.offset = 0;
        loadOffers();
      });

      regionSel.innerHTML = '<option value="">Toutes les régions</option>';
      regions.forEach(function (r) {
        var o = document.createElement("option");
        o.value = r.id;
        o.textContent = r.display_name;
        regionSel.appendChild(o);
      });
      regionSel.addEventListener("change", function () {
        state.regionId = regionSel.value;
        state.offset = 0;
        if (state.regionId) { state.anchorLat = null; state.anchorLon = null; }
        loadOffers();
      });

      var contractSel = document.getElementById("contract-select");
      contractSel.addEventListener("change", function () {
        state.contractType = contractSel.value;
        state.offset = 0;
        loadOffers();
      });

      var slider = document.getElementById("radius-slider");
      var rVal = document.getElementById("radius-val");
      slider.addEventListener("input", function () {
        rVal.textContent = slider.value + " km";
        state.radiusKm = parseInt(slider.value, 10);
      });
      slider.addEventListener("change", function () { state.offset = 0; loadOffers(); });

      var searchTimer = null;
      var searchInput = document.getElementById("search-input");
      searchInput.addEventListener("input", function () {
        clearTimeout(searchTimer);
        searchTimer = setTimeout(function () {
          state.q = searchInput.value.trim();
          state.offset = 0;
          loadOffers();
        }, 350);
      });

      document.getElementById("geo-btn").addEventListener("click", requestGeo);
      document.getElementById("offer-list").addEventListener("click", handleOfferAction);

      loadOffers();
    });
  }

  function buildViewToggle() {
    var c = document.getElementById("view-toggle");
    if (!c) return;
    c.innerHTML =
      '<button class="seg-btn active" data-view="">Toutes</button>' +
      '<button class="seg-btn seg-btn--amber" data-view="saved">Sauvegard\u00e9es</button>' +
      '<button class="seg-btn" data-view="viewed">D\u00e9j\u00e0 vues</button>' +
      '<button class="seg-btn seg-btn--ghost" data-view="clear-dismissed">Restaurer masqu\u00e9es</button>';

    c.addEventListener("click", function (e) {
      var btn = e.target.closest("[data-view]");
      if (!btn) return;
      var v = btn.dataset.view;
      if (v === "clear-dismissed") {
        if (!confirm("R\u00e9afficher toutes les offres masqu\u00e9es ?")) return;
        API.del("/api/views/dismissed").then(function () { loadOffers(); });
        return;
      }
      c.querySelectorAll(".seg-btn").forEach(function (b) { b.classList.remove("active"); });
      btn.classList.add("active");
      state.viewStatus = v;
      state.offset = 0;
      loadOffers();
    });
  }

  function requestGeo() {
    if (!navigator.geolocation) return;
    var btn = document.getElementById("geo-btn");
    btn.textContent = "...";
    navigator.geolocation.getCurrentPosition(
      function (pos) {
        state.anchorLat = pos.coords.latitude;
        state.anchorLon = pos.coords.longitude;
        btn.textContent = "OK";
        btn.classList.add("geo-btn--ok");
        loadOffers();
      },
      function () {
        btn.textContent = "GPS";
        setTimeout(function () { btn.classList.remove("geo-btn--ok"); }, 1500);
      },
      { enableHighAccuracy: false, timeout: 8000 }
    );
  }

  function showSkeleton() {
    var list = document.getElementById("offer-list");
    var h = '<div class="skel-list">';
    for (var i = 0; i < 6; i++) {
      h += '<div class="skel-card"><div class="skel-line skel-line--t"></div><div class="skel-line skel-line--m"></div><div class="skel-line skel-line--b"></div></div>';
    }
    h += "</div>";
    list.innerHTML = h;
  }

  function loadOffers() {
    showSkeleton();

    var p = new URLSearchParams();
    if (state.familyId) p.set("family_id", state.familyId);
    if (state.regionId) p.set("region_id", state.regionId);
    p.set("radius_km", state.radiusKm);
    if (state.contractType) p.set("contract_type", state.contractType);
    if (state.viewStatus) p.set("view_status", state.viewStatus);
    if (state.q) p.set("q", state.q);
    if (state.anchorLat != null) p.set("anchor_lat", state.anchorLat);
    if (state.anchorLon != null) p.set("anchor_lon", state.anchorLon);
    p.set("limit", state.limit);
    p.set("offset", state.offset);
    if (state.anchorLat != null || state.regionId) p.set("sort", "distance");

    API.get("/api/offers?" + p).then(function (data) {
      if (!data) return;

      var list = document.getElementById("offer-list");
      var meta = document.getElementById("results-meta");
      meta.textContent = data.total + " offre" + (data.total !== 1 ? "s" : "");

      if (!data.items.length) {
        list.innerHTML = '<div class="no-results">Aucune offre trouv\u00e9e.</div>';
        document.getElementById("pag").innerHTML = "";
        document.getElementById("pag-info").textContent = "";
        return;
      }

      list.innerHTML = data.items.map(function (o, i) { return renderCard(o, i); }).join("");
      renderPagination(data.total, data.limit, data.offset);
    });
  }

  function handleOfferAction(e) {
    var btn = e.target.closest("[data-action]");
    if (!btn) return;
    var action = btn.dataset.action;
    var id = btn.dataset.oid;
    var card = btn.closest(".offer-card");

    if (action === "open") {
      API.put("/api/views/" + id + "/view", { status: "viewed" });
      if (card) card.classList.add("offer-card--viewed");
      return;
    }

    if (action === "save") {
      var saved = card && card.classList.contains("offer-card--saved");
      if (saved) {
        API.del("/api/views/" + id + "/view").then(function () {
          if (state.viewStatus === "saved") {
            animateOut(card);
          } else {
            card.classList.remove("offer-card--saved");
            btn.textContent = "\u2606";
            btn.title = "Sauvegarder";
          }
        });
      } else {
        API.put("/api/views/" + id + "/view", { status: "saved" }).then(function () {
          card.classList.add("offer-card--saved");
          card.classList.remove("offer-card--viewed");
          btn.textContent = "\u2605";
          btn.title = "Retirer";
        });
      }
      return;
    }

    if (action === "dismiss") {
      API.put("/api/views/" + id + "/view", { status: "dismissed" }).then(function () {
        animateOut(card);
      });
    }
  }

  function animateOut(card) {
    if (!card) return;
    card.style.transition = "opacity .15s ease, max-height .2s ease, margin .2s ease, padding .2s ease, border-width .2s ease";
    card.style.overflow = "hidden";
    card.style.maxHeight = card.offsetHeight + "px";
    requestAnimationFrame(function () {
      card.style.opacity = "0";
      card.style.maxHeight = "0";
      card.style.marginTop = "0";
      card.style.marginBottom = "0";
      card.style.paddingTop = "0";
      card.style.paddingBottom = "0";
      card.style.borderWidth = "0";
    });
    setTimeout(function () { card.remove(); }, 220);
  }

  /* ── Contract types ─────────────────────────────────────────────── */

  var CT = {
    CDI: ["CDI","cdi"], CDD: ["CDD","cdd"], SAI: ["Saisonnier","sai"],
    MIS: ["Int\u00e9rim","mis"], DIN: ["CDI Int\u00e9rimaire","din"],
    VCA: ["Vacataire","vca"], PRO: ["Alternance","pro"],
    APP: ["Apprentissage","pro"], STG: ["Stage","stg"],
    FRA: ["Franchise","other"], LIB: ["Lib\u00e9ral","other"],
    REP: ["Reprise","other"], CCE: ["Chantier","other"],
    DDI: ["Insertion","other"], CUI: ["CUI","other"], CVA: ["Volontariat","other"]
  };

  function ctBadge(code) {
    if (!code) return "";
    var c = CT[code.toUpperCase()];
    var label = c ? c[0] : code;
    var mod = c ? c[1] : "other";
    return '<span class="badge badge-ct-' + mod + '">' + esc(label) + "</span>";
  }

  /* ── Card rendering ─────────────────────────────────────────────── */

  function renderCard(o, idx) {
    var saved = o.user_status === "saved";
    var viewed = o.user_status === "viewed";
    var cls = "offer-card" + (saved ? " offer-card--saved" : viewed ? " offer-card--viewed" : "");
    var delay = Math.min(idx * 0.04, 0.4);

    var dist = o.distance_km != null ? '<span class="badge badge-distance">' + o.distance_km + ' km</span>' : "";
    var ct = ctBadge(o.contract_type);
    var src = '<span class="badge badge-source">' + esc(o.source) + "</span>";

    var starChar = saved ? "\u2605" : "\u2606";
    var starTitle = saved ? "Retirer" : "Sauvegarder";

    var meta = [];
    if (o.company) meta.push("<span>" + esc(o.company) + "</span>");
    if (o.location) meta.push("<span>" + esc(o.location) + "</span>");
    if (o.department) meta.push("<span>" + esc(o.department) + "</span>");
    meta.push("<span>" + new Date(o.created_at).toLocaleDateString("fr-FR", { day: "numeric", month: "short" }) + "</span>");

    return '<article class="' + cls + '" style="animation-delay:' + delay + 's">' +
      '<div class="offer-header">' +
        '<h3 class="offer-title"><a href="' + esc(o.url) + '" target="_blank" rel="noopener" data-action="open" data-oid="' + o.id + '">' + esc(o.title) + '</a></h3>' +
        '<div class="offer-right">' +
          '<div class="offer-badges">' + dist + ct + src + '</div>' +
          '<div class="offer-actions">' +
            '<button class="act-btn act-btn--save" data-action="save" data-oid="' + o.id + '" title="' + starTitle + '">' + starChar + '</button>' +
            '<button class="act-btn act-btn--dismiss" data-action="dismiss" data-oid="' + o.id + '" title="Masquer">&times;</button>' +
          '</div>' +
        '</div>' +
      '</div>' +
      '<div class="offer-meta">' + meta.join("") + '</div>' +
    '</article>';
  }

  /* ── Pagination ─────────────────────────────────────────────────── */

  function renderPagination(total, limit, offset) {
    var pages = Math.ceil(total / limit);
    var cur = Math.floor(offset / limit);
    var el = document.getElementById("pag");
    var info = document.getElementById("pag-info");

    if (pages <= 1) { el.innerHTML = ""; info.textContent = ""; return; }

    info.textContent = "Page " + (cur + 1) + " sur " + pages;

    var html = "";
    var max = 7;
    var start = Math.max(0, cur - 3);
    var end = Math.min(pages, start + max);
    if (end - start < max) start = Math.max(0, end - max);

    if (cur > 0) html += '<button class="pag-btn" data-pg="' + (cur - 1) + '">\u2039</button>';
    for (var i = start; i < end; i++) {
      html += '<button class="pag-btn' + (i === cur ? " active" : "") + '" data-pg="' + i + '">' + (i + 1) + '</button>';
    }
    if (cur < pages - 1) html += '<button class="pag-btn" data-pg="' + (cur + 1) + '">\u203a</button>';

    el.innerHTML = html;
    el.querySelectorAll("[data-pg]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        state.offset = parseInt(btn.dataset.pg, 10) * state.limit;
        loadOffers();
        window.scrollTo({ top: 0, behavior: "smooth" });
      });
    });
  }

  /* ── Admin page ─────────────────────────────────────────────────── */

  function initAdmin() {
    Promise.all([loadFamilies(), loadRegions(), loadUsers()]);

    document.getElementById("family-form").addEventListener("submit", function (e) {
      e.preventDefault();
      var fd = new FormData(e.target);
      API.post("/api/families", {
        slug: fd.get("slug"), display_name: fd.get("display_name"),
        description: fd.get("description") || null,
        sort_order: parseInt(fd.get("sort_order"), 10) || 0
      }).then(function () { e.target.reset(); loadFamilies(); });
    });

    document.getElementById("region-form").addEventListener("submit", function (e) {
      e.preventDefault();
      var fd = new FormData(e.target);
      var dc = null; var raw = fd.get("department_codes");
      if (raw) { try { dc = JSON.parse(raw); } catch (ex) { /* ignore */ } }
      API.post("/api/regions", {
        slug: fd.get("slug"), display_name: fd.get("display_name"),
        center_lat: parseFloat(fd.get("center_lat")),
        center_lon: parseFloat(fd.get("center_lon")),
        department_codes: dc
      }).then(function () { e.target.reset(); loadRegions(); });
    });

    document.getElementById("user-form").addEventListener("submit", function (e) {
      e.preventDefault();
      var fd = new FormData(e.target);
      API.post("/api/users", {
        username: fd.get("username"), email: fd.get("email") || null,
        password: fd.get("password"), is_admin: fd.get("is_admin") === "on"
      }).then(function (r) { if (r) { e.target.reset(); loadUsers(); } });
    });
  }

  function loadFamilies() {
    var c = document.getElementById("family-list");
    if (!c) return Promise.resolve();
    return API.get("/api/families").then(function (data) {
      families = data || [];
      c.innerHTML = families.map(renderFamilyItem).join("");
      wireFamily(c);
    });
  }

  function wireFamily(c) {
    c.querySelectorAll("[data-del-family]").forEach(function (b) {
      b.addEventListener("click", function () {
        if (!confirm("Supprimer cette famille ?")) return;
        API.del("/api/families/" + b.dataset.delFamily).then(loadFamilies);
      });
    });
    c.querySelectorAll("[data-del-kw]").forEach(function (b) {
      b.addEventListener("click", function () {
        API.del("/api/families/" + b.dataset.family + "/keywords/" + b.dataset.delKw).then(loadFamilies);
      });
    });
    c.querySelectorAll(".kw-add").forEach(function (form) {
      form.addEventListener("submit", function (e) {
        e.preventDefault();
        var inp = form.querySelector("input"); var kw = inp.value.trim();
        if (!kw) return;
        API.post("/api/families/" + form.dataset.family + "/keywords", { keyword: kw }).then(function () { inp.value = ""; loadFamilies(); });
      });
    });
    c.querySelectorAll(".family-edit-btn").forEach(function (b) {
      b.addEventListener("click", function () {
        var item = b.closest(".admin-item");
        item.querySelector(".family-name-display").style.display = "none";
        b.style.display = "none";
        item.querySelector(".family-name-edit").style.display = "flex";
        item.querySelector(".family-name-edit input").focus();
      });
    });
    c.querySelectorAll(".family-edit-cancel").forEach(function (b) {
      b.addEventListener("click", function () {
        var item = b.closest(".admin-item");
        item.querySelector(".family-name-display").style.display = "";
        item.querySelector(".family-edit-btn").style.display = "";
        item.querySelector(".family-name-edit").style.display = "none";
      });
    });
    c.querySelectorAll(".family-name-edit").forEach(function (form) {
      form.addEventListener("submit", function (e) {
        e.preventDefault();
        var item = form.closest(".admin-item");
        var fid = item.dataset.familyId;
        var name = form.querySelector("input").value.trim();
        if (!name) return;
        API.put("/api/families/" + fid, { display_name: name }).then(loadFamilies);
      });
    });
  }

  function renderFamilyItem(f) {
    var kws = f.keywords.map(function (k) {
      return '<span class="kw-tag">' + esc(k.keyword) + '<button data-del-kw="' + k.id + '" data-family="' + f.id + '">&times;</button></span>';
    }).join("");

    return '<div class="admin-item" data-family-id="' + f.id + '">' +
      '<div class="admin-item-info">' +
        '<div class="admin-item-title">' +
          '<span class="family-name-display">' + esc(f.display_name) + '</span>' +
          '<form class="family-name-edit" style="display:none">' +
            '<input class="admin-input admin-input--inline" type="text" value="' + esc(f.display_name) + '">' +
            '<button type="submit" class="btn btn-accent btn-sm">OK</button>' +
            '<button type="button" class="btn btn-sm family-edit-cancel">Annuler</button>' +
          '</form>' +
          '<button class="btn-icon family-edit-btn" title="Renommer">&#9998;</button>' +
        '</div>' +
        '<div class="admin-item-slug">' + esc(f.slug) + '</div>' +
        '<div class="kw-tags">' + kws + '</div>' +
        '<form class="kw-add" data-family="' + f.id + '">' +
          '<input type="text" placeholder="Mot-cl\u00e9\u2026">' +
          '<button type="submit" class="btn btn-sm">+</button>' +
        '</form>' +
      '</div>' +
      '<div class="admin-item-actions">' +
        '<button class="btn-ghost-red" data-del-family="' + f.id + '">Supprimer</button>' +
      '</div>' +
    '</div>';
  }

  function loadRegions() {
    var c = document.getElementById("region-list");
    if (!c) return Promise.resolve();
    return API.get("/api/regions").then(function (data) {
      regions = data || [];
      c.innerHTML = regions.map(renderRegionItem).join("");
      c.querySelectorAll("[data-del-region]").forEach(function (b) {
        b.addEventListener("click", function () {
          if (!confirm("Supprimer cette r\u00e9gion ?")) return;
          API.del("/api/regions/" + b.dataset.delRegion).then(loadRegions);
        });
      });
    });
  }

  function renderRegionItem(r) {
    var d = r.department_codes ? r.department_codes.join(", ") : "\u2014";
    return '<div class="admin-item">' +
      '<div class="admin-item-info">' +
        '<div class="admin-item-title">' + esc(r.display_name) + '</div>' +
        '<div class="admin-item-slug">' + esc(r.slug) + ' \u00b7 ' + r.center_lat.toFixed(4) + ', ' + r.center_lon.toFixed(4) + ' \u00b7 Depts: ' + esc(d) + '</div>' +
      '</div>' +
      '<div class="admin-item-actions">' +
        '<button class="btn-ghost-red" data-del-region="' + r.id + '">Supprimer</button>' +
      '</div>' +
    '</div>';
  }

  function loadUsers() {
    var c = document.getElementById("user-list");
    if (!c) return Promise.resolve();
    return API.get("/api/users").then(function (data) {
      var users = data || [];
      c.innerHTML = users.map(renderUserItem).join("");

      c.querySelectorAll("[data-del-user]").forEach(function (b) {
        b.addEventListener("click", function () {
          if (!confirm('Supprimer "' + b.dataset.username + '" ?')) return;
          API.del("/api/users/" + b.dataset.delUser).then(loadUsers);
        });
      });
      c.querySelectorAll("[data-toggle-admin]").forEach(function (b) {
        b.addEventListener("click", function () {
          var cur = b.dataset.toggleAdmin === "true";
          API.put("/api/users/" + b.dataset.userId, { is_admin: !cur }).then(loadUsers);
        });
      });
      c.querySelectorAll("[data-toggle-active]").forEach(function (b) {
        b.addEventListener("click", function () {
          var cur = b.dataset.toggleActive === "true";
          API.put("/api/users/" + b.dataset.userId, { is_active: !cur }).then(loadUsers);
        });
      });
      c.querySelectorAll("[data-reset-pwd]").forEach(function (b) {
        b.addEventListener("click", function () {
          var pwd = prompt('Nouveau mot de passe pour "' + b.dataset.username + '" :');
          if (!pwd || pwd.length < 6) { if (pwd !== null) alert("Min. 6 caract\u00e8res."); return; }
          API.put("/api/users/" + b.dataset.resetPwd, { password: pwd }).then(function () { alert("Mot de passe mis \u00e0 jour."); });
        });
      });
    });
  }

  function renderUserItem(u) {
    var ll = u.last_login_at ? new Date(u.last_login_at).toLocaleDateString("fr-FR", { day: "numeric", month: "short", year: "numeric" }) : "jamais";
    var ab = u.is_admin ? ' <span class="badge badge-admin">admin</span>' : "";
    var ib = u.is_active ? "" : ' <span class="badge badge-inactive">inactif</span>';

    return '<div class="admin-item">' +
      '<div class="admin-item-info">' +
        '<div class="admin-item-title">' + esc(u.username) + ab + ib + '</div>' +
        '<div class="admin-item-slug">' + (u.email ? esc(u.email) + " \u00b7 " : "") + "Derni\u00e8re connexion : " + ll + '</div>' +
      '</div>' +
      '<div class="admin-item-actions admin-item-actions--wrap">' +
        '<button class="btn btn-sm" data-toggle-admin="' + u.is_admin + '" data-user-id="' + u.id + '">' + (u.is_admin ? "Retirer admin" : "Passer admin") + '</button>' +
        '<button class="btn btn-sm" data-toggle-active="' + u.is_active + '" data-user-id="' + u.id + '">' + (u.is_active ? "D\u00e9sactiver" : "R\u00e9activer") + '</button>' +
        '<button class="btn btn-sm" data-reset-pwd="' + u.id + '" data-username="' + esc(u.username) + '">Reset MDP</button>' +
        '<button class="btn-ghost-red" data-del-user="' + u.id + '" data-username="' + esc(u.username) + '">Supprimer</button>' +
      '</div>' +
    '</div>';
  }

  /* ── Helpers ────────────────────────────────────────────────────── */

  function esc(s) {
    if (!s) return "";
    var d = document.createElement("div");
    d.textContent = s;
    return d.innerHTML;
  }

  /* ── Boot ───────────────────────────────────────────────────────── */

  window.Section23 = { initAdmin: initAdmin };
  document.addEventListener("DOMContentLoaded", function () {
    if (document.getElementById("offer-list")) initIndex();
  });
})();
